"""Perception eval (docs/plans/phase-3.md, item 5): estimate, run, score.

    .venv/bin/python eval/perception_eval.py estimate --set T --model claude-haiku-5-5 [--runs 1] [--count]
    .venv/bin/python eval/perception_eval.py run --set T --model claude-haiku-5-5 --max-spend 0.5
    .venv/bin/python eval/perception_eval.py score eval/runs/perception/<run>.jsonl [...]

Sets: T (36 train images, for prompt tuning, scored as often as needed) and
public_dev (the gate set). A public_dev run is a recorded checkpoint (plan item 5)
and says so. public_holdout and private are never run here.

The gate rules are the GATE constant below, fixed before any result and pinned by
tests/test_perception_eval.py. Changing them needs the owner's decision and a new
version name.

Runs call the scene with use_cache=False, so repeated runs are independent calls.
Each run writes one JSON line per image (image id, scene, issues, cost) to
eval/runs/perception/ (gitignored).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval import gold_signs as gs  # noqa: E402
from eval.report import bootstrap_ci, duplicated_images  # noqa: E402
from vqa.kb import load_catalog  # noqa: E402
from vqa.llm.pricing import cost_usd, worst_case_usd  # noqa: E402
from vqa.perception import prompt as scene_prompt  # noqa: E402
from vqa.perception.image import native_size  # noqa: E402
from vqa.perception.matching import match, row_of  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "eval" / "runs" / "perception"

# ---------------------------------------------------------------- the gate (plan D7)

GATE = {
    "name": "perception_gate_v1",
    "fixed": "2026-11-15, before any perception result",
    "gate_set": "public_dev",
    "excluded_images": [],              # images used in the scene prompt (none from public_dev)
    "sign_recall_min": 0.90,
    "sign_code_f1_min": 0.85,
    "runs": 3,
    "aggregate": "mean",                # the gate is decided on the mean of the runs
    "pass_rule": "both point estimates (mean of runs) reach their minimum on all gate images",
    "excluded_gold": ["readable_false", "local_notice"],   # out of recall and precision
    "code_level": "catalog_row",        # variant must also match when both name one
    "unknown_prediction": "counts as found for recall, never a code true positive",
    "matching": "one-to-one; same catalog row or same visual category; then rank, side, order",
    "ci": {"method": "bootstrap", "unit": "image", "resamples": 10_000, "seed": 20261115, "level": 0.95},
    "reported_on": ["all_images", "non_duplicate_images"],
}

EXPECTED_OUTPUT_TOKENS = 1300   # Haiku 5.5 pre-fill drafts averaged 1,307 output tokens
BYTES_PER_TOKEN = gs.BYTES_PER_TOKEN

# ---------------------------------------------------------------- sets and gold


def gold_rows() -> dict[str, dict]:
    return {g["image_id"]: g for g in (json.loads(line) for line in
                                       gs.GOLD.read_text(encoding="utf-8").splitlines() if line.strip())}


def set_images(name: str) -> list[tuple[str, str]]:
    """(image_id, split) for set T or public_dev."""
    if name == "T":
        return [(i, "train") for i in gs.set_t_images()]
    if name == "public_dev":
        return [(i, "public_dev") for i in sorted(gs.dev_images()) if i not in GATE["excluded_images"]]
    raise SystemExit("--set must be T or public_dev")


def non_duplicate(name: str, image_ids: list[str]) -> set[str]:
    if name == "public_dev":
        dup = duplicated_images("public")                     # duplicates of train
    else:
        dup = duplicated_images("train", against={"public", "private"})
    return {i for i in image_ids if i not in dup}


# ---------------------------------------------------------------- scoring one image


def _view(s: dict) -> dict:
    pos = s.get("position") or {}
    return {"code": s.get("code"), "shape": s.get("shape"), "border": s.get("border"),
            "background": s.get("background"), "rank": pos.get("rank_top_down"), "side": pos.get("side")}


def excluded(g: dict) -> str | None:
    if "local_notice" in g:
        return "local_notice"
    if g.get("readable") is False:
        return "readable_false"
    return None


def same_variant(a: str, b: str) -> bool:
    """Strict check: equal codes, or one side names only the family row."""
    return a == b or "(" in a or "(" in b


def score_image(gold: list[dict], pred: list[dict], catalog=None) -> dict[str, int]:
    """Counts for one image (gold signs and predicted signs as dicts)."""
    catalog = catalog or load_catalog()
    pairs = match([_view(g) for g in gold], [_view(p) for p in pred], catalog)
    by_gold = dict(pairs)
    matched_pred = {j: i for i, j in pairs}
    c = {"gold": 0, "found": 0, "tp": 0, "tp_strict": 0, "pred": 0,
         "local_notice": 0, "local_notice_found": 0, "readable_false": 0,
         "value_pairs": 0, "value_ok": 0, "look_pairs": 0, "shape_ok": 0, "border_ok": 0, "background_ok": 0}
    for i, g in enumerate(gold):
        ex = excluded(g)
        if ex:
            c[ex] += 1
            if ex == "local_notice" and i in by_gold:
                c["local_notice_found"] += 1
            continue
        c["gold"] += 1
        if i not in by_gold:
            continue
        c["found"] += 1
        p = pred[by_gold[i]]
        rg, rp = row_of(g["code"], catalog), row_of(p.get("code"), catalog)
        if rp is not None and rg == rp:
            c["tp"] += 1
            c["tp_strict"] += same_variant(g["code"], p["code"])
            if g.get("value") is not None:
                c["value_pairs"] += 1
                c["value_ok"] += p.get("value") == g["value"]
        c["look_pairs"] += 1
        for k in ("shape", "border", "background"):
            c[f"{k}_ok"] += p.get(k) == g.get(k)
    for j in range(len(pred)):
        if j in matched_pred and excluded(gold[matched_pred[j]]):
            continue                                   # neither a true nor a false positive
        c["pred"] += 1
    return c


def _sum(units: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for u in units:
        for k, v in u.items():
            out[k] = out.get(k, 0) + v
    return out


def recall(units):
    s = _sum(units)
    return s["found"] / s["gold"] if s.get("gold") else None


def code_f1(units, strict: bool = False):
    s = _sum(units)
    tp = s["tp_strict" if strict else "tp"]
    if not s.get("gold"):
        return None
    p = tp / s["pred"] if s["pred"] else 0.0
    r = tp / s["gold"]
    return 2 * p * r / (p + r) if p + r else 0.0


def metrics(units: list[dict], with_ci: bool) -> dict[str, Any]:
    s = _sum(units) if units else {}
    out: dict[str, Any] = {"images": len(units), "gold_signs": s.get("gold", 0), "predicted": s.get("pred", 0),
                           "sign_recall": recall(units) if units else None,
                           "sign_code_f1": code_f1(units) if units else None,
                           "sign_code_f1_strict": code_f1(units, strict=True) if units else None}
    if units:
        out["value_accuracy"] = s["value_ok"] / s["value_pairs"] if s["value_pairs"] else None
        for k in ("shape", "border", "background"):
            out[f"{k}_accuracy"] = s[f"{k}_ok"] / s["look_pairs"] if s["look_pairs"] else None
        out["local_notice"] = {"gold": s["local_notice"], "found": s["local_notice_found"]}
        out["readable_false_gold"] = s["readable_false"]
    if with_ci and units:
        ci = GATE["ci"]
        out["sign_recall_ci95"] = bootstrap_ci(units, recall, ci["resamples"], ci["seed"], ci["level"])
        out["sign_code_f1_ci95"] = bootstrap_ci(units, code_f1, ci["resamples"], ci["seed"], ci["level"])
    return out


# ---------------------------------------------------------------- estimate


def estimate(set_name: str, model: str, runs: int = 1, sdk=None) -> dict[str, Any]:
    """Cost of `runs` runs on a set, with no API call (token counting only with an
    SDK client, which is free but is an API call)."""
    from PIL import Image

    images = set_images(set_name)
    system = scene_prompt.system_prompt()
    sys_tokens = int(len(system.encode("utf-8")) / BYTES_PER_TOKEN) + 1
    counts = []
    for image_id, split in images:
        path = gs.image_path(image_id, split)
        with Image.open(path) as im:
            w, h = im.size
        nw, nh = native_size(w, h)
        counts.append(sys_tokens + int(nw * nh / 750) + 1 + 20)
    max_tokens = scene_prompt.config()["max_tokens"]
    effort = scene_prompt.effort_for(model)
    o = EXPECTED_OUTPUT_TOKENS

    def run_cost(out_tokens: int) -> float:
        total = 0.0
        for k, c in enumerate(counts):
            cached = {"cache_write_tokens": sys_tokens} if k == 0 else {"cache_read_tokens": sys_tokens}
            total += cost_usd(model, input_tokens=c - sys_tokens, output_tokens=out_tokens, **cached)
        return total

    one = run_cost(o)
    rerun_one = run_cost(o) - cost_usd(model, cache_write_tokens=sys_tokens) + cost_usd(model, cache_read_tokens=sys_tokens)
    worst_call = max(worst_case_usd(model, c, max_tokens) for c in counts)
    return {
        "set": set_name, "images": len(images), "runs": runs, "model": model, "effort": effort,
        "prompt_id": scene_prompt.prompt_id(), "max_tokens": max_tokens,
        "method": f"rough (system prompt bytes / {BYTES_PER_TOKEN}; images w x h / 750 at native size; "
                  f"{o} output tokens per image)",
        "system_tokens": sys_tokens, "mean_prompt_tokens": round(sum(counts) / len(counts)),
        "per_run_usd_no_reruns": round(one, 4),
        "per_run_usd_all_rerun": round(one + rerun_one, 4),
        "per_run_usd_double_output_all_rerun": round(run_cost(2 * o) * 2, 4),
        "total_usd_range": [round(one * runs, 4), round((one + rerun_one) * runs, 4)],
        "worst_case_per_call_usd": round(worst_call, 4),
        "worst_case_total_usd": round(worst_call * len(images) * 2 * runs, 4),
    }


# ---------------------------------------------------------------- run


def run(set_name: str, model: str, max_spend: float, sdk=None, out_dir: Path = RUNS) -> Path:
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.perception.scene import perceive

    if set_name == "public_dev":
        print("WARNING: a public_dev run is a recorded checkpoint (plan item 5). Record it in "
              "docs/status.md; prompt changes come from set T, not from these errors.")
    images = set_images(set_name)
    run_id = uuid.uuid4().hex[:12]
    client = LLMClient(model=model, guard=SpendGuard(max_spend), sdk=sdk, run_id=run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{set_name}_{model}_{run_id}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": run_id, "set": set_name, "model": model,
                            "prompt_id": scene_prompt.prompt_id(), "gate": GATE["name"],
                            "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}) + "\n")
        for n, (image_id, split) in enumerate(images, 1):
            res = perceive(gs.image_path(image_id, split), model=model, client=client, use_cache=False)
            f.write(json.dumps({"image_id": image_id, "ok": res.ok, "error": res.error,
                                "retried": res.retried, "cost_usd": res.cost_usd,
                                "reran": any(r["pass"] == "rerun" for r in res.replies),
                                "issues": res.issues, "raw_codes": res.raw_codes,
                                "scene": res.scene.model_dump(mode="json", by_alias=True) if res.scene else None},
                               ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{n}/{len(images)}] {image_id}: {'ok' if res.ok else res.error}  "
                  f"spent ${client.guard.spent:.4f}")
    print(f"run {run_id} -> {out}  (spent ${client.guard.spent:.4f})")
    return out


# ---------------------------------------------------------------- score


def load_run(path: Path) -> tuple[dict, list[dict]]:
    lines = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    return lines[0], lines[1:]


def score_run(path: Path) -> dict[str, Any]:
    head, rows = load_run(path)
    gold = gold_rows()
    catalog = load_catalog()
    units = {}
    for r in rows:
        pred = (r["scene"] or {}).get("signs", [])
        units[r["image_id"]] = score_image(gold[r["image_id"]]["signs"], pred, catalog)
    ids = list(units)
    nd = non_duplicate(head["set"], ids)
    return {"run_id": head["run_id"], "set": head["set"], "model": head["model"],
            "prompt_id": head["prompt_id"],
            "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
            "errors": sum(not r["ok"] for r in rows), "reran": sum(r.get("reran", False) for r in rows),
            "all_images": metrics([units[i] for i in ids], with_ci=True),
            "non_duplicate_images": metrics([units[i] for i in ids if i in nd], with_ci=True)}


def score(paths: list[Path]) -> dict[str, Any]:
    reps, seen = [], set()
    for p in paths:
        rep = score_run(p)
        if rep["run_id"] in seen:            # the same run given twice counts once
            continue
        seen.add(rep["run_id"])
        reps.append(rep)
    out: dict[str, Any] = {"runs": reps}
    if reps and all(r["set"] == "public_dev" for r in reps):
        rec = statistics.mean(r["all_images"]["sign_recall"] for r in reps)
        f1 = statistics.mean(r["all_images"]["sign_code_f1"] for r in reps)
        enough = len(reps) >= GATE["runs"]
        out["gate"] = {"name": GATE["name"], "runs": len(reps), "mean_sign_recall": rec,
                       "mean_sign_code_f1": f1,
                       "verdict": ("PASS" if rec >= GATE["sign_recall_min"] and f1 >= GATE["sign_code_f1_min"]
                                   else "FAIL") if enough else f"not decided: {len(reps)} of {GATE['runs']} runs"}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estimate")
    e.add_argument("--set", choices=["T", "public_dev"], required=True)
    e.add_argument("--model", default="claude-haiku-5-5")
    e.add_argument("--runs", type=int, default=1)
    r = sub.add_parser("run")
    r.add_argument("--set", choices=["T", "public_dev"], required=True)
    r.add_argument("--model", default="claude-haiku-5-5")
    r.add_argument("--max-spend", type=float, required=True)
    s = sub.add_parser("score")
    s.add_argument("files", nargs="+", type=Path)
    a = ap.parse_args()
    if a.cmd == "estimate":
        print(json.dumps(estimate(a.set, a.model, a.runs), indent=2))
    elif a.cmd == "run":
        run(a.set, a.model, a.max_spend)
    else:
        print(json.dumps(score(a.files), indent=2, default=str))


if __name__ == "__main__":
    main()
