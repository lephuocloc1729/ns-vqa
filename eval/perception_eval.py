"""Perception eval (docs/plans/phase-3.md, item 5): estimate, run, score.

    .venv/bin/python eval/perception_eval.py estimate --set T --model claude-haiku-5-5 [--runs 1] [--version v2]
    .venv/bin/python eval/perception_eval.py run --set T --model claude-haiku-5-5 --max-spend 0.5 [--version v2]
    .venv/bin/python eval/perception_eval.py score eval/runs/perception/<run>.jsonl [...]
    .venv/bin/python eval/perception_eval.py rescore --reverify <run>.jsonl [...]   # no API call

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

# perception_gate_v1 (1c6dc57) matched on rank before side. The owner changed it to
# side before rank on 2026-11-15, after the first set-T run and before any public_dev
# result: perception_gate_v2. Everything else is unchanged.
GATE = {
    "name": "perception_gate_v2",
    "fixed": "2026-11-15, before any public_dev result (v1: before any perception result)",
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
    "matching": "one-to-one; same catalog row or same visual category; then side, rank, order",
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


def rule_bearing(code: str | None, catalog) -> bool:
    """A sign the rule engine acts on: a catalog row with an effect, not meaning-only,
    not effect_unmodelled, not an auxiliary plate (reported metric only, not gated)."""
    r = row_of(code, catalog)
    if r is None:
        return False
    s = catalog.get(r)
    e = s.effect
    has = any([e.prohibits, e.max_speed, e.min_speed, e.lane_board, e.lane_reserved,
               e.only_directions, e.ends])
    return has and not s.meaning_only and not s.effect_unmodelled and s.category != "auxiliary"


def score_image(gold: list[dict], pred: list[dict], catalog=None) -> dict[str, int]:
    """Counts for one image (gold signs and predicted signs as dicts)."""
    catalog = catalog or load_catalog()
    pairs = match([_view(g) for g in gold], [_view(p) for p in pred], catalog)
    by_gold = dict(pairs)
    matched_pred = {j: i for i, j in pairs}
    c = {"gold": 0, "found": 0, "tp": 0, "tp_strict": 0, "pred": 0,
         "local_notice": 0, "local_notice_found": 0, "readable_false": 0,
         "value_pairs": 0, "value_ok": 0, "look_pairs": 0, "shape_ok": 0, "border_ok": 0, "background_ok": 0,
         "gold_rule": 0, "tp_rule": 0, "pred_rule": 0}
    for i, g in enumerate(gold):
        ex = excluded(g)
        if ex:
            c[ex] += 1
            if ex == "local_notice" and i in by_gold:
                c["local_notice_found"] += 1
            continue
        c["gold"] += 1
        g_rule = rule_bearing(g["code"], catalog)
        c["gold_rule"] += g_rule
        if i not in by_gold:
            continue
        c["found"] += 1
        p = pred[by_gold[i]]
        rg, rp = row_of(g["code"], catalog), row_of(p.get("code"), catalog)
        if rp is not None and rg == rp:
            c["tp"] += 1
            c["tp_rule"] += g_rule
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
        c["pred_rule"] += rule_bearing(pred[j].get("code"), catalog)
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


def code_f1_rule(units):
    s = _sum(units)
    if not s.get("gold_rule"):
        return None
    p = s["tp_rule"] / s["pred_rule"] if s["pred_rule"] else 0.0
    r = s["tp_rule"] / s["gold_rule"]
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
        # reported, not gated: code F1 on the signs the rule engine acts on
        out["sign_code_f1_rule_bearing"] = code_f1_rule(units)
        out["rule_bearing_gold_signs"] = s["gold_rule"]
        out["readable_false_gold"] = s["readable_false"]
    if with_ci and units:
        ci = GATE["ci"]
        out["sign_recall_ci95"] = bootstrap_ci(units, recall, ci["resamples"], ci["seed"], ci["level"])
        out["sign_code_f1_ci95"] = bootstrap_ci(units, code_f1, ci["resamples"], ci["seed"], ci["level"])
    return out


# ---------------------------------------------------------------- estimate


def estimate(set_name: str, model: str, runs: int = 1, sdk=None, version: str = "v1",
             output_tokens: int | None = None, rerun_share: float | None = None) -> dict[str, Any]:
    """Cost of `runs` runs on a set, with no API call (token counting only with an
    SDK client, which is free but is an API call)."""
    from PIL import Image

    images = set_images(set_name)
    system = scene_prompt.system_prompt(version)
    sys_tokens = int(len(system.encode("utf-8")) / BYTES_PER_TOKEN) + 1
    pict_tokens = 0                      # reference figures: part of the cached prefix
    for b in scene_prompt.pictogram_blocks(version):
        if b["type"] == "text":
            pict_tokens += int(len(b["text"].encode("utf-8")) / BYTES_PER_TOKEN) + 1
        else:
            import base64 as _b64
            import io as _io
            with Image.open(_io.BytesIO(_b64.b64decode(b["source"]["data"]))) as im:
                pict_tokens += int(im.size[0] * im.size[1] / 750) + 1
    sys_tokens += pict_tokens
    counts = []
    for image_id, split in images:
        path = gs.image_path(image_id, split)
        with Image.open(path) as im:
            w, h = im.size
        nw, nh = native_size(w, h)
        counts.append(sys_tokens + int(nw * nh / 750) + 1 + 20)
    max_tokens = scene_prompt.config(version)["max_tokens"]
    effort = scene_prompt.effort_for(model, version)
    o = output_tokens or EXPECTED_OUTPUT_TOKENS

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
        "prompt_id": scene_prompt.prompt_id(version), "max_tokens": max_tokens,
        "method": f"rough (system prompt bytes / {BYTES_PER_TOKEN}; images w x h / 750 at native size; "
                  f"{o} output tokens per image" + (", measured" if output_tokens else "") + ")",
        "system_tokens": sys_tokens, "pictogram_tokens": pict_tokens,
        "mean_prompt_tokens": round(sum(counts) / len(counts)),
        "per_run_usd_no_reruns": round(one, 4),
        "per_run_usd_all_rerun": round(one + rerun_one, 4),
        "per_run_usd_double_output_all_rerun": round(run_cost(2 * o) * 2, 4),
        "total_usd_range": [round(one * runs, 4), round((one + rerun_one) * runs, 4)],
        **({"rerun_share": rerun_share,
            "calibrated_usd": round((one + rerun_share * rerun_one) * runs, 4)} if rerun_share is not None else {}),
        "worst_case_per_call_usd": round(worst_call, 4),
        "worst_case_total_usd": round(worst_call * len(images) * 2 * runs, 4),
    }


# ---------------------------------------------------------------- run


def run(set_name: str, model: str, max_spend: float, sdk=None, out_dir: Path = RUNS,
        version: str = "v1") -> Path:
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
    out = out_dir / f"{set_name}_{model}_{version}_{run_id}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": run_id, "set": set_name, "model": model,
                            "prompt_id": scene_prompt.prompt_id(version), "gate": GATE["name"],
                            "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}) + "\n")
        for n, (image_id, split) in enumerate(images, 1):
            res = perceive(gs.image_path(image_id, split), model=model, version=version, client=client,
                           use_cache=False)
            f.write(json.dumps({"image_id": image_id, "ok": res.ok, "error": res.error,
                                "retried": res.retried, "cost_usd": res.cost_usd,
                                "reran": any(r["pass"] == "rerun" for r in res.replies),
                                "issues": res.issues, "raw_codes": res.raw_codes,
                                "scene": res.scene.model_dump(mode="json", by_alias=True) if res.scene else None,
                                # phase 4, P1: the raw pass-1 / re-run replies (model outputs
                                # only), so `warm` can rebuild this run's cache records
                                "effort": res.effort, "replies": res.replies},
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


def run_units(path: Path, gold: dict | None = None, catalog=None) -> tuple[dict, list[dict], dict[str, dict]]:
    """(head, rows, per-image counts in file order) for one run file."""
    head, rows = load_run(path)
    gold = gold if gold is not None else gold_rows()
    catalog = catalog or load_catalog()
    units = {}
    for r in rows:
        pred = (r["scene"] or {}).get("signs", [])
        units[r["image_id"]] = score_image(gold[r["image_id"]]["signs"], pred, catalog)
    return head, rows, units


def score_run(path: Path, scored: tuple | None = None) -> dict[str, Any]:
    head, rows, units = scored if scored is not None else run_units(path)
    ids = list(units)
    nd = non_duplicate(head["set"], ids)
    return {"run_id": head["run_id"], "set": head["set"], "model": head["model"],
            "prompt_id": head["prompt_id"],
            "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
            "errors": sum(not r["ok"] for r in rows), "reran": sum(r.get("reran", False) for r in rows),
            "all_images": metrics([units[i] for i in ids], with_ci=True),
            "non_duplicate_images": metrics([units[i] for i in ids if i in nd], with_ci=True)}


def pooled_units(per_run: list[dict[str, dict]], ids: list[str]) -> list[dict[str, int]]:
    """One unit per image with its counts summed over the runs, so a bootstrap resample
    keeps an image's runs together (the CI of a mean of runs)."""
    return [_sum([run[i] for run in per_run]) for i in ids]


MEAN_KEYS = ("sign_recall", "sign_code_f1", "sign_code_f1_strict", "sign_code_f1_rule_bearing",
             "value_accuracy")


def summarise(per_run: list[dict[str, dict]], ids: list[str]) -> dict[str, Any]:
    """Mean of the runs' metrics on `ids`, their range, and pooled bootstrap CIs."""
    mets = [metrics([r[i] for i in ids], with_ci=False) for r in per_run]
    out: dict[str, Any] = {"runs": len(per_run), "images": len(ids),
                           "gold_signs": mets[0]["gold_signs"] if mets else 0}
    for k in MEAN_KEYS:
        vals = [m[k] for m in mets if m.get(k) is not None]
        out[f"mean_{k}"] = statistics.mean(vals) if vals else None
        if k in ("sign_recall", "sign_code_f1"):
            out[f"range_{k}"] = [min(vals), max(vals)] if vals else None
    out["mean_predicted"] = statistics.mean(m["predicted"] for m in mets) if mets else None
    ci = GATE["ci"]
    pooled = pooled_units(per_run, ids)
    out["sign_recall_ci95"] = bootstrap_ci(pooled, recall, ci["resamples"], ci["seed"], ci["level"])
    out["sign_code_f1_ci95"] = bootstrap_ci(pooled, code_f1, ci["resamples"], ci["seed"], ci["level"])
    return out


def configuration(head: dict) -> tuple[str, str, str, bool]:
    """What makes runs comparable: set, model, prompt version, and whether the
    two-pass fallback ran (a run header without a `fallback` field predates it: off)."""
    return (head["set"], head["model"], head["prompt_id"], bool(head.get("fallback")))


def _describe(cfg: tuple) -> str:
    set_name, model, prompt_id, fb = cfg
    return f"set {set_name}, model {model}, prompt {prompt_id}, fallback {'on' if fb else 'off'}"


def summaries(groups: dict[tuple, list[tuple[dict, dict]]], gold: dict) -> list[dict[str, Any]]:
    """Per configuration (set, model, prompt, fallback): the mean of its runs on all and
    non-duplicate images, and the split by the model that drafted each image's gold (D2)."""
    out = []
    for (set_name, model, prompt_id, fallback), runs in groups.items():
        per_run = [u for _, u in runs]
        ids = list(per_run[0])                     # the first run's file order
        if any(set(u) != set(ids) for u in per_run):
            raise SystemExit(f"runs of {model} cover different images; cannot pool them")
        nd = non_duplicate(set_name, ids)
        by: dict[str, list[str]] = {}
        for i in ids:
            by.setdefault(str(gold[i].get("draft_model")), []).append(i)
        drafters = {}
        for dm, sel in sorted(by.items()):
            s = summarise(per_run, sel)
            s["non_duplicate_images"] = sum(i in nd for i in sel)
            drafters[dm] = s
        out.append({"set": set_name, "model": model, "prompt_id": prompt_id, "fallback": fallback,
                    "run_ids": [h["run_id"] for h, _ in runs],
                    "cost_usd": round(sum(h["cost_usd"] for h, _ in runs), 4),
                    "all_images": summarise(per_run, ids),
                    "non_duplicate_images": summarise(per_run, [i for i in ids if i in nd]),
                    "by_draft_model": drafters})
    return out


def score(paths: list[Path]) -> dict[str, Any]:
    reps, seen = [], set()
    gold, catalog = gold_rows(), load_catalog()
    groups: dict[tuple, list[tuple[dict, dict]]] = {}
    for p in paths:
        head, rows, units = run_units(p, gold, catalog)
        if head["run_id"] in seen:           # the same run given twice counts once
            continue
        seen.add(head["run_id"])
        if head["set"] == "public_dev" and (head.get("use_cache") or (head.get("fallback") or {}).get("use_cache")):
            raise SystemExit(f"{Path(p).name}: a public_dev run made with use_cache can't be scored; "
                             "gate runs must be independent calls")
        rep = score_run(p, (head, rows, units))
        reps.append(rep)
        groups.setdefault(configuration(head), []).append(
            ({"run_id": head["run_id"], "cost_usd": rep["cost_usd"]}, units))
    out: dict[str, Any] = {"runs": reps}
    # reported, not gated: the mean of each configuration's runs with pooled CIs, and the drafter split
    out["summaries"] = summaries(groups, gold)
    if any(r["set"] == "public_dev" for r in reps):
        if len(groups) > 1:            # the gate is a mean over runs of one configuration
            raise SystemExit("the gate needs runs of one configuration; these files mix "
                             f"{len(groups)}: " + " | ".join(_describe(c) for c in groups)
                             + ". Score each configuration separately.")
        rec = statistics.mean(r["all_images"]["sign_recall"] for r in reps)
        f1 = statistics.mean(r["all_images"]["sign_code_f1"] for r in reps)
        enough = len(reps) >= GATE["runs"]
        out["gate"] = {"name": GATE["name"], "runs": len(reps), "mean_sign_recall": rec,
                       "mean_sign_code_f1": f1,
                       "verdict": ("PASS" if rec >= GATE["sign_recall_min"] and f1 >= GATE["sign_code_f1_min"]
                                   else "FAIL") if enough else f"not decided: {len(reps)} of {GATE['runs']} runs"}
    return out


# ---------------------------------------------------------------- rescore --reverify


class _NoCalls:
    """Stands in for LLMClient during a re-verify: any call is refused, so nothing is
    sent. perceive() treats the refusal of a re-run as "the first reading stands"."""

    def __init__(self, model: str):
        self.model, self.last_usage = model, None

    def json_reply(self, **kw):
        from vqa.llm.client import LLMRefusal
        raise LLMRefusal("re-verify makes no API calls")


def reverify_run(path: Path) -> Path:
    """Rebuild a run's scenes from the cached raw replies with the current wire,
    verification and re-run pairing (no API call), into <run>.reverified.jsonl."""
    from vqa.perception.scene import perceive

    head, rows = load_run(path)
    version = head["prompt_id"].split("/", 1)[1].split("@", 1)[0]
    if scene_prompt.prompt_id(version) != head["prompt_id"]:
        raise SystemExit(f"{path.name}: prompt {head['prompt_id']} is not the current "
                         f"{scene_prompt.prompt_id(version)}; its cache can't be replayed")
    split_of = dict(set_images(head["set"]))
    out = Path(path).with_suffix(".reverified.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps({**head, "reverified_from": Path(path).name,
                            "reverified": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}) + "\n")
        for r in rows:
            res = perceive(gs.image_path(r["image_id"], split_of[r["image_id"]]), model=head["model"],
                           version=version, client=_NoCalls(head["model"]), use_cache=True)
            if not res.cache_hit:
                raise SystemExit(f"{r['image_id']}: no cached reply for this run; can't re-verify")
            f.write(json.dumps({"image_id": r["image_id"], "ok": res.ok, "error": res.error,
                                "retried": res.retried, "cost_usd": r["cost_usd"],
                                "reran": any(x["pass"] == "rerun" for x in res.replies),
                                "issues": res.issues, "raw_codes": res.raw_codes,
                                "scene": res.scene.model_dump(mode="json", by_alias=True) if res.scene else None},
                               ensure_ascii=False) + "\n")
    return out


# ---------------------------------------------------------------- the two-pass fallback (plan item 7)

LOG = ROOT / "logs" / "api_calls.jsonl"
CROP_OUTPUT_TOKENS = {"claude-haiku-5-5": 400, "claude-sonnet-5-5": 150, "claude-opus-5-5": 150}
CROP_INPUT_TOKENS = 250            # crop image (about 384 x 400 px) plus the instruction


def _version_of(prompt_id: str) -> str:
    return prompt_id.split("/", 1)[1].split("@", 1)[0]


def fallback_run(path: Path, max_spend: float, policy: str | None = None, sdk=None, out_dir: Path = RUNS,
                 replay: Path | None = None, tiles: bool = True, crops: bool = True,
                 use_cache: bool = False) -> Path:
    """Apply the fallback to a pass-1 run file. Pass-1 scenes come from the file, so only
    tile and crop calls are made; with `replay` (an earlier fallback run of the same
    pass-1 run) its stored replies are used and no call is made (another policy).
    `use_cache` reads tile and crop replies from the scene cache (only usable replies are
    cached), so a re-run pays only for regions with no usable reply; off by default, so
    repeated runs are independent calls."""
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.perception.cache import SceneCache
    from vqa.perception.fallback import FallbackConfig, run_fallback
    from vqa.perception.image import prepare
    from vqa.schemas import SceneGraph

    from vqa.perception.fallback import CHOSEN_POLICY

    head, rows = load_run(path)
    if head.get("fallback"):
        raise SystemExit(f"{Path(path).name} already has the fallback; give its pass-1 run")
    policy = policy or CHOSEN_POLICY               # the rule frozen for checkpoint 2
    cfg = FallbackConfig(policy=policy, tiles=tiles, crops=crops)
    stored: dict[str, dict] = {}
    if replay is not None:
        rhead, rrows = load_run(replay)
        fb = rhead.get("fallback") or {}
        if fb.get("pass1_run") != head["run_id"]:
            raise SystemExit(f"{Path(replay).name} is not a fallback run of {head['run_id']}")
        want = cfg.describe()
        if (fb.get("tile"), fb.get("crop")) != (want["tile"], want["crop"]):
            raise SystemExit(f"{Path(replay).name} used prompts {fb.get('tile')}, {fb.get('crop')}; "
                             f"the current ones are {want['tile']}, {want['crop']}")
        stored = {r["image_id"]: {(x["kind"], tuple(x["box"])): x["raw_text"]
                                  for x in r.get("fallback_replies", []) if not x.get("failed")}
                  for r in rrows}
    if head["set"] == "public_dev":
        print("WARNING: a public_dev fallback run is a recorded checkpoint (plan item 5). Record it in "
              "docs/status.md; trigger and policy choices come from set T, not from these errors.")
    run_id = uuid.uuid4().hex[:12]
    client = None if replay is not None else LLMClient(model=head["model"], guard=SpendGuard(max_spend),
                                                       sdk=sdk, run_id=run_id)
    split_of = dict(set_images(head["set"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{head['set']}_{head['model']}_{_version_of(head['prompt_id'])}+fb_{run_id}.jsonl"
    total = 0.0
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps({**head, "run_id": run_id,
                            "fallback": {**cfg.describe(), "pass1_run": head["run_id"],
                                         "replayed_from": Path(replay).name if replay else None,
                                         "use_cache": use_cache},
                            "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}) + "\n")
        for n, r in enumerate(rows, 1):
            row = {**r, "pass1_cost_usd": r["cost_usd"], "fallback_cost_usd": 0.0, "fallback_replies": []}
            if r["scene"] is not None:
                data = gs.image_path(r["image_id"], split_of[r["image_id"]]).read_bytes()
                img = prepare(data)
                look = stored.get(r["image_id"], {})
                fb = run_fallback(SceneGraph.model_validate(r["scene"]), data, img, model=head["model"],
                                  client=client, cfg=cfg, cache=SceneCache(), use_cache=use_cache,
                                  replay=(lambda kind, box, look=look: look.get((kind, tuple(box))))
                                  if replay is not None else None)
                replies = fb.replies if replay is None else \
                    [{"kind": k, "box": list(b), "raw_text": t} for (k, b), t in look.items()]
                row.update(scene=fb.scene.model_dump(mode="json", by_alias=True),
                           issues=r["issues"] + fb.issues, fallback_cost_usd=fb.cost_usd,
                           cost_usd=r["cost_usd"] + fb.cost_usd, fallback_replies=replies,
                           fallback_stats={"tiled": fb.tiled, "tiles_added": fb.tiles_added,
                                           "crops": fb.crops, "codes_changed": fb.codes_changed})
                total += fb.cost_usd
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            st = row.get("fallback_stats") or {}
            print(f"[{n}/{len(rows)}] {r['image_id']}: tiled {st.get('tiled', False)}, "
                  f"added {st.get('tiles_added', 0)}, crops {st.get('crops', 0)}, "
                  f"changed {st.get('codes_changed', 0)}  spent ${total:.4f}")
    print(f"fallback run {run_id} (policy {policy}) -> {out}  (spent ${total:.4f})")
    return out


def _mean_call(model: str, run_id: str | None) -> dict[str, float] | None:
    """Mean tokens of a run's scene calls, from the usage log (no call)."""
    if run_id is None or not LOG.exists():
        return None
    calls = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    calls = [c for c in calls if c.get("run_id") == run_id and c.get("purpose") == "scene"
             and c.get("status") == "ok"]
    if not calls:
        return None
    m = lambda k: statistics.mean(c.get(k) or 0 for c in calls)  # noqa: E731
    return {"input_tokens": m("input_tokens"), "output_tokens": m("output_tokens"),
            "cache_read_tokens": m("cache_read_tokens") + m("cache_write_tokens")}


def fallback_calibration(files: list[Path]) -> dict[str, float]:
    """Per-call costs measured on earlier fallback runs (their usage-log lines): tile and
    crop calls, their retries, and the share of first attempts that needed a retry. The
    share comes only from runs made without the cache (a cache re-run calls only the
    regions that failed before, so it would overstate it)."""
    if not LOG.exists():
        raise SystemExit("no usage log to calibrate from")
    calls = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    heads = [load_run(f)[0] for f in files]
    ids = {h["run_id"] for h in heads}
    fresh = {h["run_id"] for h in heads if not (h.get("fallback") or {}).get("use_cache")}
    mine = [c for c in calls if c.get("run_id") in ids]
    out: dict[str, float] = {}
    for kind in ("tile", "crop"):
        first = [c for c in mine if c["purpose"] == f"scene {kind}"]
        retry = [c for c in mine if c["purpose"] == f"scene {kind} retry"]
        share_base = [c for c in first if c["run_id"] in fresh] or first
        if not first:
            raise SystemExit(f"no logged {kind} calls in {sorted(ids)}")
        # first attempts priced on fresh runs too: a cache re-run's are all known failures
        out[f"{kind}_usd"] = statistics.mean(c["cost_usd"] for c in share_base)
        out[f"{kind}_retry_usd"] = statistics.mean(c["cost_usd"] for c in retry) if retry else out[f"{kind}_usd"]
        out[f"{kind}_retry_share"] = (sum(c["status"] == "bad_json" for c in share_base) / len(share_base)
                                      if share_base else 0.0)
    return out


def fallback_estimate(path: Path, runs: int = 1, calibrate: list[Path] | None = None) -> dict[str, Any]:
    """What the fallback would call on a pass-1 run, and its cost (no call). Tile calls are
    priced as the run's own mean scene call (usage log); crop calls as the same cached
    prompt, CROP_INPUT_TOKENS in and CROP_OUTPUT_TOKENS out. Crops of signs the tiles
    would add are not known in advance: the range adds one crop per tile call."""
    from vqa.perception.fallback import TILE_GRID, needs_crop, needs_tiles
    from vqa.schemas import SceneGraph

    head, rows = load_run(path)
    model = head["model"]
    scenes = [SceneGraph.model_validate(r["scene"]) for r in rows if r["scene"] is not None]
    tiled = sum(needs_tiles(s) for s in scenes)
    tile_calls = tiled * TILE_GRID * TILE_GRID
    crop_calls = sum(needs_crop(x) and x.position.box is not None for s in scenes for x in s.signs)
    m = _mean_call(model, head["run_id"])
    if m is None:
        raise SystemExit(f"no logged scene calls for run {head['run_id']}; can't price the estimate")
    # a tile is enlarged to about MAX_PIXELS: its image tokens replace the photo's
    from PIL import Image
    from vqa.perception.image import MAX_PIXELS
    split_of = dict(set_images(head["set"]))
    photo = statistics.mean(gs.image_tokens(*Image.open(gs.image_path(r["image_id"], split_of[r["image_id"]])).size)
                            for r in rows)
    tile_in = m["input_tokens"] - photo + MAX_PIXELS / 750
    tile_usd = cost_usd(model, input_tokens=round(tile_in), output_tokens=round(m["output_tokens"]),
                        cache_read_tokens=round(m["cache_read_tokens"]))
    crop_usd = cost_usd(model, input_tokens=CROP_INPUT_TOKENS, output_tokens=CROP_OUTPUT_TOKENS[model],
                        cache_read_tokens=round(m["cache_read_tokens"]))
    # the tile and crop prompts are new prefixes: each is written to the cache once per run
    write_usd = 2 * cost_usd(model, cache_write_tokens=round(m["cache_read_tokens"]))
    cal = None
    if calibrate:
        # measured per-call costs and retry shares; the range runs from the listed crops to
        # one more crop per tile call; `if_every_call_retries` is the worst case apart
        cal = fallback_calibration(calibrate)
        t = cal["tile_usd"] + cal["tile_retry_share"] * cal["tile_retry_usd"]
        c = cal["crop_usd"] + cal["crop_retry_share"] * cal["crop_retry_usd"]
        mid = tile_calls * t + crop_calls * c
        hi = tile_calls * t + (crop_calls + tile_calls) * c
        every = (tile_calls * (cal["tile_usd"] + cal["tile_retry_usd"])
                 + (crop_calls + tile_calls) * (cal["crop_usd"] + cal["crop_retry_usd"]))
    else:
        mid = tile_calls * tile_usd + crop_calls * crop_usd + write_usd
        hi = tile_calls * tile_usd + (crop_calls + tile_calls) * crop_usd + write_usd
    return {"run": head["run_id"], "set": head["set"], "model": model, "images": len(rows),
            "images_tiled": tiled, "tile_calls": tile_calls, "crop_calls": crop_calls,
            "crop_calls_max": crop_calls + tile_calls,
            "photo_image_tokens": round(photo), "tile_input_tokens": round(tile_in),
            "usd_per_tile_call": round(tile_usd, 5), "usd_per_crop_call": round(crop_usd, 5),
            "calibration": {k: round(v, 5) for k, v in cal.items()} if cal else None,
            "usd_per_run_if_every_call_retries": round(every, 4) if cal else None,
            "usd_per_run": [round(mid, 4), round(hi, 4)], "runs": runs,
            "usd_total": [round(mid * runs, 4), round(hi * runs, 4)],
            "worst_case_per_call_usd": round(worst_case_usd(model, round(m["cache_read_tokens"]) + 1500, 8000), 4)}


# ---------------------------------------------------------------- compare a pass-1 run with its fallback runs


def gold_status(gold: list[dict], pred: list[dict], catalog=None) -> list[str | None]:
    """Per gold sign, with the gate's matching: "tp" (matched, right row), "wrong" (matched,
    other row or UNKNOWN), "miss" (unmatched), or None for excluded gold signs."""
    catalog = catalog or load_catalog()
    by_gold = dict(match([_view(g) for g in gold], [_view(p) for p in pred], catalog))
    out: list[str | None] = []
    for i, g in enumerate(gold):
        if excluded(g):
            out.append(None)
        elif i not in by_gold:
            out.append("miss")
        else:
            rp = row_of(pred[by_gold[i]].get("code"), catalog)
            out.append("tp" if rp is not None and rp == row_of(g["code"], catalog) else "wrong")
    return out


def compare(pass1: Path, fallbacks: list[Path]) -> dict[str, Any]:
    """Pass 1 against each fallback run of it (reported, not gated): the scores, the
    fallback's trigger counts, and gold signs fixed and broken relative to pass 1."""
    gold, catalog = gold_rows(), load_catalog()
    h1, rows1 = load_run(pass1)
    base = score_run(pass1)
    st1 = {r["image_id"]: gold_status(gold[r["image_id"]]["signs"], (r["scene"] or {}).get("signs", []), catalog)
           for r in rows1}
    keys = ("sign_recall", "sign_code_f1", "sign_code_f1_strict", "sign_code_f1_rule_bearing")
    pick = lambda rep: {k: rep["all_images"][k] for k in keys} | \
        {f"non_duplicate_{k}": rep["non_duplicate_images"][k] for k in keys[:2]} | \
        {"predicted": rep["all_images"]["predicted"]}  # noqa: E731
    out = {"pass1": {"run_id": h1["run_id"], "model": h1["model"], **pick(base)}, "fallback": []}
    for f in fallbacks:
        h, rows = load_run(f)
        if (h.get("fallback") or {}).get("pass1_run") != h1["run_id"]:
            raise SystemExit(f"{Path(f).name} is not a fallback run of {h1['run_id']}")
        rep = score_run(f)
        c = {"fixed_by_tiles": 0, "fixed_by_crops": 0, "broken": 0}
        for r in rows:
            st = gold_status(gold[r["image_id"]]["signs"], (r["scene"] or {}).get("signs", []), catalog)
            for a, b in zip(st1[r["image_id"]], st):
                if a is None:
                    continue
                if a != "tp" and b == "tp":
                    c["fixed_by_tiles" if a == "miss" else "fixed_by_crops"] += 1
                elif a == "tp" and b != "tp":
                    c["broken"] += 1
        stats = [r.get("fallback_stats") or {} for r in rows]
        crops = sum(x.get("crops", 0) for x in stats)
        changed = sum(x.get("codes_changed", 0) for x in stats)
        failed = sum(("call failed" in i or "no reply to replay" in i) and i.startswith("crop")
                     for r in rows for i in r["issues"])
        out["fallback"].append({
            "run_id": h["run_id"], "policy": h["fallback"]["policy"],
            "replayed_from": h["fallback"].get("replayed_from"), **pick(rep),
            "images_tiled": sum(bool(x.get("tiled")) for x in stats),
            "tiles_added": sum(x.get("tiles_added", 0) for x in stats),
            "crops": crops, "crops_without_a_reply": failed, "codes_changed": changed,
            "share_of_crops_changing_a_code": changed / crops if crops else None,
            **c, "fallback_cost_usd": round(sum(r.get("fallback_cost_usd", 0.0) for r in rows), 4)})
    return out


# ---------------------------------------------------------------- warming the scene cache (phase 4, P1)
#
# A run file keeps its raw replies: the pass-1 / re-run replies (`replies`, from the
# run command since phase 4) and the tile / crop replies (`fallback_replies`). `warm`
# writes them back as scene-cache records in a dedicated directory, which it empties
# first, so the cache holds one run's model outputs and nothing else. It then rebuilds
# every scene from that cache with no API call and checks it equals the run file's.

WARM_DIR = ROOT / "cache" / "warm"
WARM_MARKER = "WARMED_RUN.json"


def _sha256_file(path: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _scene_json(scene) -> Any:
    return scene.model_dump(mode="json", by_alias=True) if scene is not None else None


def backfill_raw(path: Path, cache_dir: Path | None = None, log: Path | None = None) -> Path:
    """For a fallback run made before phase 4 (no `replies` in its rows): copy each
    image's pass-1 / re-run replies from the scene cache into <run>.withraw.jsonl. Only
    if every cached reply's request id belongs to the run's pass-1 run in the usage log,
    so another run's replies can never be copied in. No API call."""
    from vqa.perception.cache import SceneCache

    head, rows = load_run(path)
    p1 = (head.get("fallback") or {}).get("pass1_run")
    if not p1:
        raise SystemExit(f"{Path(path).name}: not a fallback run (no pass1_run)")
    if any("replies" in r for r in rows):
        raise SystemExit(f"{Path(path).name} already keeps its raw replies")
    log = Path(log) if log else LOG
    ids = {c.get("request_id") for c in (json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()
                                         if l.strip()) if c.get("run_id") == p1}
    ids.discard(None)
    version = _version_of(head["prompt_id"])
    if scene_prompt.prompt_id(version) != head["prompt_id"]:
        raise SystemExit(f"{Path(path).name}: prompt {head['prompt_id']} is not the current one")
    effort = scene_prompt.effort_for(head["model"], version)
    cache = SceneCache(cache_dir)
    split_of = dict(set_images(head["set"]))
    out_rows, bad = [], []
    for r in rows:
        sha = _sha256_file(gs.image_path(r["image_id"], split_of[r["image_id"]]))
        rec = cache.get(sha, head["model"], effort, head["prompt_id"])
        replies = rec.replies if rec else []
        rids = [x.get("request_id") for x in replies if x.get("request_id")]
        if r["scene"] is not None and (not rids or any(x not in ids for x in rids)):
            bad.append(r["image_id"])
        elif r["scene"] is not None and any(x["pass"] == "rerun" for x in replies) != bool(r.get("reran")):
            bad.append(r["image_id"])
        out_rows.append({**r, "effort": effort, "replies": replies})
    if bad:
        raise SystemExit(f"the scene cache does not hold pass-1 run {p1}'s replies for: {', '.join(bad)}")
    out = Path(path).with_name(Path(path).name.replace(".jsonl", ".withraw.jsonl"))
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps({**head, "raw_backfilled": {"from": "scene cache", "pass1_run": p1,
                                                       "checked": "request ids against the usage log"}},
                           ensure_ascii=False) + "\n")
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out


def _clear_cache_dir(d: Path) -> None:
    from vqa.perception.cache import CACHE_DIR
    if d.resolve() == CACHE_DIR.resolve():
        raise SystemExit("warm never writes into the main scene cache; give a dedicated directory")
    if d.exists():
        for f in d.glob("*/*.json"):
            f.unlink()
        (d / WARM_MARKER).unlink(missing_ok=True)


def warm_run(path: Path, cache_dir: Path | None = None) -> dict[str, Any]:
    """Rebuild one run's scene-cache records from its run file in `cache_dir` (emptied
    first), then rebuild every scene from that cache with no call and compare."""
    from vqa.perception.cache import CacheRecord, RegionRecord, SceneCache
    from vqa.perception.fallback import FallbackConfig
    from vqa.perception.scene import perceive

    head, rows = load_run(path)
    d = Path(cache_dir) if cache_dir else WARM_DIR
    version = _version_of(head["prompt_id"])
    if scene_prompt.prompt_id(version) != head["prompt_id"]:
        raise SystemExit(f"{Path(path).name}: prompt {head['prompt_id']} is not the current one")
    missing = [r["image_id"] for r in rows if r["scene"] is not None and not r.get("replies")]
    if missing:
        raise SystemExit(f"{Path(path).name} keeps no raw pass-1 replies for {len(missing)} images "
                         "(run `backfill-raw`, or use a run made since phase 4)")
    fb = head.get("fallback")
    cfg = None
    if fb:
        cfg = FallbackConfig(policy=fb["policy"])
        want = cfg.describe()
        if (fb.get("tile"), fb.get("crop")) != (want["tile"], want["crop"]):
            raise SystemExit(f"{Path(path).name}: fallback prompts {fb.get('tile')}, {fb.get('crop')} "
                             f"are not the current {want['tile']}, {want['crop']}")
    _clear_cache_dir(d)
    cache = SceneCache(d)
    effort = scene_prompt.effort_for(head["model"], version)
    split_of = dict(set_images(head["set"]))
    records = 0
    for r in rows:
        img = gs.image_path(r["image_id"], split_of[r["image_id"]])
        sha = _sha256_file(img)
        if r.get("replies"):
            cache.put(CacheRecord(sha, head["model"], r.get("effort", effort), head["prompt_id"],
                                  replies=r["replies"]))
            records += 1
        for x in r.get("fallback_replies", []):
            if x.get("failed"):
                continue
            v = _version_of(x["prompt_id"])
            if scene_prompt.prompt_id(v) != x["prompt_id"]:
                raise SystemExit(f"{r['image_id']}: region prompt {x['prompt_id']} is not the current one")
            kind = x["kind"]
            cache.put_region(RegionRecord(sha, head["model"], scene_prompt.effort_for(head["model"], v),
                                          x["prompt_id"], tuple(x["box"]), replies=[{
                "pass": kind if x.get("attempt", 1) == 1 else f"{kind} retry",
                "raw_text": x["raw_text"], "stop_reason": "end_turn", "usage": x.get("usage") or {},
                "cost_usd": x.get("cost_usd", 0.0), "request_id": x.get("request_id")}]))
            records += 1
    mismatches = []
    for r in rows:
        img = gs.image_path(r["image_id"], split_of[r["image_id"]])
        res = perceive(img, model=head["model"], version=version, client=_NoCalls(head["model"]),
                       cache=cache, use_cache=True, fallback=cfg)
        if _scene_json(res.scene) != r["scene"]:
            mismatches.append(r["image_id"])
    report = {"run_id": head["run_id"], "run_file": Path(path).name, "cache_dir": str(d),
              "images": len(rows), "records": records, "mismatches": mismatches, "ok": not mismatches}
    (d / WARM_MARKER).write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estimate")
    e.add_argument("--set", choices=["T", "public_dev"], required=True)
    e.add_argument("--model", default="claude-haiku-5-5")
    e.add_argument("--runs", type=int, default=1)
    e.add_argument("--version", default="v1", help="scene prompt version (prompts/scene/<version>)")
    e.add_argument("--output-tokens", type=int, help="calibrate: mean output tokens per call, as measured")
    e.add_argument("--rerun-share", type=float, help="calibrate: share of images re-run, as measured")
    r = sub.add_parser("run")
    r.add_argument("--set", choices=["T", "public_dev"], required=True)
    r.add_argument("--model", default="claude-haiku-5-5")
    r.add_argument("--max-spend", type=float, required=True)
    r.add_argument("--version", default="v1", help="scene prompt version (prompts/scene/<version>)")
    s = sub.add_parser("score")
    s.add_argument("files", nargs="+", type=Path)
    rs = sub.add_parser("rescore", help="score runs again; --reverify rebuilds scenes from the cache first")
    rs.add_argument("files", nargs="+", type=Path)
    rs.add_argument("--reverify", action="store_true")
    fb = sub.add_parser("fallback", help="apply the two-pass fallback (plan item 7) to a pass-1 run")
    fb.add_argument("file", type=Path)
    fb.add_argument("--max-spend", type=float)
    fb.add_argument("--policy", choices=["rules", "crop_always", "crop_high", "never"],
                    help="combining rule; default: the frozen CHOSEN_POLICY")
    fb.add_argument("--replay", type=Path, help="an earlier fallback run of the same pass-1 run: no calls")
    fb.add_argument("--use-cache", action="store_true",
                    help="read usable tile and crop replies from the scene cache: pay only for the rest")
    cp = sub.add_parser("compare", help="a pass-1 run against its fallback runs (reported, not gated)")
    cp.add_argument("pass1", type=Path)
    cp.add_argument("fallbacks", nargs="+", type=Path)
    fe = sub.add_parser("fallback-estimate", help="what the fallback would cost on a pass-1 run (no call)")
    fe.add_argument("file", type=Path)
    fe.add_argument("--runs", type=int, default=1)
    fe.add_argument("--calibrate", type=Path, nargs="+",
                    help="fallback runs whose logged calls set the per-call costs and retry shares")
    bf = sub.add_parser("backfill-raw", help="copy a pre-phase-4 run's pass-1 replies from the scene cache "
                                             "into <run>.withraw.jsonl (checked against the usage log; no call)")
    bf.add_argument("file", type=Path)
    wm = sub.add_parser("warm", help="rebuild one run's scene-cache records in a dedicated directory "
                                     "(emptied first) and check the rebuilt scenes (no call)")
    wm.add_argument("file", type=Path)
    wm.add_argument("--cache-dir", type=Path, default=None, help=f"default {WARM_DIR}")
    a = ap.parse_args()
    if a.cmd == "backfill-raw":
        print(backfill_raw(a.file))
        return
    if a.cmd == "warm":
        rep = warm_run(a.file, a.cache_dir)
        print(json.dumps(rep, indent=2))
        if not rep["ok"]:
            raise SystemExit(1)
        return
    if a.cmd == "fallback":
        if a.replay is None and a.max_spend is None:
            raise SystemExit("--max-spend is required unless --replay is given")
        fallback_run(a.file, a.max_spend or 0.0, policy=a.policy, replay=a.replay, use_cache=a.use_cache)
        return
    if a.cmd == "compare":
        print(json.dumps(compare(a.pass1, a.fallbacks), indent=2))
        return
    if a.cmd == "fallback-estimate":
        print(json.dumps(fallback_estimate(a.file, a.runs, a.calibrate), indent=2))
        return
    if a.cmd == "estimate":
        print(json.dumps(estimate(a.set, a.model, a.runs, version=a.version,
                                  output_tokens=a.output_tokens, rerun_share=a.rerun_share), indent=2))
    elif a.cmd == "run":
        run(a.set, a.model, a.max_spend, version=a.version)
    elif a.cmd == "rescore":
        files = [reverify_run(f) for f in a.files] if a.reverify else a.files
        print(json.dumps(score(files), indent=2, default=str))
    else:
        print(json.dumps(score(a.files), indent=2, default=str))


if __name__ == "__main__":
    main()
