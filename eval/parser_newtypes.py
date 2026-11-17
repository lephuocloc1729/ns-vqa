"""Parser v12 new-types test (owner, 2026-11-17). Separate from the no-regression gate.

The gold is data/annotations/gold_v12_new/gold_v12_new.yaml: train working-set rows by id (their text
is read from the dataset at run time) and assistant-written rows with their own text. Each question is
parsed once with parser v12; a parse is right when its normalized program equals the expected one
(eval.parser_eval.canonical). Per intent; the pass rule is fixed: >= 80% where an intent has >= 5
questions; weaker intents are listed for the owner.

    .venv/bin/python eval/parser_newtypes.py estimate
    .venv/bin/python eval/parser_newtypes.py run --max-spend 0.40          # paid: the owner runs it
    .venv/bin/python eval/parser_newtypes.py score logs/parser_eval/newtypes_v12_*.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from eval.parser_eval import CONTEXT_YEAR, MAX_TOKENS, OUT_DIR, canonical, gold_query  # noqa: E402

GOLD = ROOT / "data" / "annotations" / "gold_v12_new" / "gold_v12_new.yaml"
TRAIN = ROOT / "VLSP2025-MLQA-Natural" / "dataset" / "train data" / "vlsp_2025_train.json"
SPLITS = ROOT / "data" / "splits"
VERSION = "v12"
MODEL, EFFORT = "claude-sonnet-5-5", "medium"
PASS_RATE, PASS_MIN_N = 0.80, 5
# measured v11 rates (gate run 2026-11-17): the first call writes the prompt cache, then each call
# reads it; v12's prompt is about 10% longer
FIRST_CALL_USD, PER_CALL_USD, PROMPT_GROWTH = 0.052, 0.0029, 1.10


def load(path: Path = GOLD) -> list[dict]:
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))["rows"]
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate ids"
    return rows


def refused_ids() -> tuple[set[str], set[str]]:
    """Dev and validation questions and images (ids only), and the v12 few-shots."""
    dev = json.loads((SPLITS / "train_dev.json").read_text())
    val = json.loads((SPLITS / "train_validation.json").read_text())
    return set(dev["questions"]) | set(val["questions"]), set(dev["images"]) | set(val["images"])


def questions(rows: list[dict], train: Path = TRAIN) -> dict[str, str]:
    """Question text per row: assistant-written rows carry it; train rows are read by id."""
    bad_q, bad_i = refused_ids()
    out = {r["id"]: r["question"] for r in rows if r["source"] == "assistant_written"}
    need = {r["id"] for r in rows if r["source"] == "train"}
    if need:
        for t in json.loads(train.read_text(encoding="utf-8")):
            if t["id"] in need:
                if t["id"] in bad_q or t["image_id"] in bad_i:
                    raise SystemExit(f"{t['id']} is a dev or validation question or image; refused")
                out[t["id"]] = t["question"]
    missing = need - out.keys()
    if missing:
        raise SystemExit(f"train rows not found: {sorted(missing)}")
    return out


def estimate(rows: list[dict]) -> dict:
    n = len(rows)
    exp = (FIRST_CALL_USD + PER_CALL_USD * (n - 1)) * PROMPT_GROWTH
    return {"questions": n, "expected_usd": round(exp, 4), "range_usd": [round(exp * 0.85, 4), round(exp * 1.3, 4)],
            "cap_usd": 0.40, "note": "the spend guard keeps one call's worst case free, so the cap sits above the range"}


def run(max_spend: float, sdk=None, engine=None, out_dir: Path = OUT_DIR, gold: Path = GOLD,
        train: Path = TRAIN) -> Path:
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard, SpendLimitExceeded
    from vqa.parsing.claude_parser import ClaudeParser
    rows = load(gold)
    qs = questions(rows, train)
    if sdk is None:
        import anthropic
        sdk = anthropic.Anthropic()
    if engine is None:
        from vqa.reasoning.engine import Engine
        engine = Engine()
    llm = LLMClient(model=MODEL, guard=SpendGuard(max_spend), sdk=sdk)
    parser = ClaudeParser(llm=llm, effort=EFFORT, prompt_version=VERSION, context_year=CONTEXT_YEAR,
                          engine=engine, max_tokens=MAX_TOKENS)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"newtypes_{VERSION}_{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for n, r in enumerate(rows, 1):
            try:
                p = parser.parse(qs[r["id"]])
            except SpendLimitExceeded as e:
                partial = path.with_suffix(".partial.jsonl")
                f.close()
                path.rename(partial)
                print(f"stopped by the spend guard after {n - 1} of {len(rows)} ({e}); partial -> {partial}")
                return partial
            f.write(json.dumps({"id": r["id"], "status": p.status,
                                "query": p.query.model_dump(mode="json") if p.query else None,
                                "errors": p.errors, "cost_usd": round(p.cost_usd, 6), "prompt_version": VERSION},
                               ensure_ascii=False) + "\n")
            print(f"[{n}/{len(rows)}] {r['id']}: {p.status}  spent ${llm.guard.spent:.4f}")
    print(f"predictions -> {path}  (spent ${llm.guard.spent:.4f})")
    return path


def _subgroup(r: dict) -> str:
    p = r["program"]["program"]
    if r["intent"] != "rule_permitted":
        return r["intent"]
    if p.get("at_signal"):
        return "rule_permitted/lights"
    if p.get("maneuver"):
        return "rule_permitted/markings"
    return "rule_permitted/places"


def score(preds: list[dict], rows: list[dict]) -> dict:
    from vqa.schemas import QueryProgram
    by_id = {p["id"]: p for p in preds}
    per: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    sub: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    src: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    misses = []
    for r in rows:
        want = canonical(gold_query(r["program"]))
        p = by_id.get(r["id"])
        got = canonical(QueryProgram.model_validate(p["query"])) if p and p.get("query") else None
        ok = got == want
        for d, k in ((per, r["intent"]), (sub, _subgroup(r)), (src, r["source"])):
            d[k][0] += ok
            d[k][1] += 1
        if not ok:
            misses.append({"id": r["id"], "intent": r["intent"], "status": p and p.get("status")})
    intents = {}
    for k, (c, n) in sorted(per.items()):
        rate = c / n
        intents[k] = {"correct": c, "n": n, "rate": round(rate, 3),
                      "rule": ("pass" if rate >= PASS_RATE else "below 80%: listed for the owner")
                      if n >= PASS_MIN_N else "fewer than 5 questions: reported only"}
    return {"intents": intents,
            "subgroups": {k: f"{c}/{n}" for k, (c, n) in sorted(sub.items())},
            "by_source": {k: f"{c}/{n}" for k, (c, n) in sorted(src.items())},
            "weaker_intents": [k for k, v in intents.items() if v["rule"].startswith("below")],
            "missing_predictions": sorted({r["id"] for r in rows} - by_id.keys()),
            "misses": misses}


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("estimate")
    r = sp.add_parser("run")
    r.add_argument("--max-spend", type=float, required=True)
    s = sp.add_parser("score")
    s.add_argument("predictions", type=Path)
    a = ap.parse_args()
    rows = load()
    if a.cmd == "estimate":
        print(json.dumps(estimate(rows), indent=2))
    elif a.cmd == "run":
        est = estimate(rows)
        if est["expected_usd"] > a.max_spend:
            raise SystemExit(f"expected ${est['expected_usd']} exceeds --max-spend ${a.max_spend}; nothing sent")
        run(a.max_spend)
    else:
        preds = [json.loads(x) for x in a.predictions.read_text(encoding="utf-8").splitlines() if x.strip()]
        print(json.dumps(score(preds, rows), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
