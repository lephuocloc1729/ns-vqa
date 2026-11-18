"""Parser v12 new-types test (owner, 2026-11-17). Separate from the no-regression gate.

The gold is data/annotations/gold_v12_new/gold_v12_new.yaml: train working-set rows by id (their text
is read from the dataset at run time) and assistant-written rows with their own text. Each question is
parsed once with parser v12; a parse is right when its normalized program equals the expected one
(eval.parser_eval.canonical). Reported per group (train, owner-written, AI-drafted owner-reviewed,
assistant-written) and type; the rule is fixed: >= 80% where a type has >= 5 train or >= 3 owner-written
questions. Only train and owner-written rows decide which types stay on; the other two are smoke tests.

    .venv/bin/python eval/parser_newtypes.py estimate
    .venv/bin/python eval/parser_newtypes.py run --max-spend 0.60          # paid: the owner runs it
    .venv/bin/python eval/parser_newtypes.py run --sources train owner_written --max-spend <estimate's cap>
    .venv/bin/python eval/parser_newtypes.py score logs/parser_eval/newtypes_v12_*.jsonl

Parser v13 (owner, 2026-11-18): `--version v13`, and the group owner2 (the "owner2 |" lines of
owner_questions.txt at d427da1, the new types 4-11). owner2 decides a new type at >= 80% where it has
>= 3 questions; the rest are reported.

    .venv/bin/python eval/parser_newtypes.py estimate --version v13 --sources train owner_written owner2
    .venv/bin/python eval/parser_newtypes.py run --version v13 --sources train owner_written owner2 --max-spend <cap>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
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
# parser v13: measured on the v12 run of 2026-11-18 (first call $0.0578, then $0.00419 each), times
# v13's prompt growth over v12 (48,590 / 44,907 characters)
V13_FIRST_CALL_USD, V13_PER_CALL_USD, V13_GROWTH = 0.0578, 0.00419, 1.082


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
    """Question text per row: assistant- and owner-written rows carry it; train rows are read by id."""
    bad_q, bad_i = refused_ids()
    out = {r["id"]: r["question"] for r in rows if r["source"] != "train"}
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


def estimate(rows: list[dict], version: str = VERSION) -> dict:
    n = len(rows)
    exp = (FIRST_CALL_USD + PER_CALL_USD * (n - 1)) * PROMPT_GROWTH
    if version in ("v13", "v14"):                 # v14 = v13 plus one spec line
        exp = (V13_FIRST_CALL_USD + V13_PER_CALL_USD * (n - 1)) * V13_GROWTH
    top = exp * 1.3
    # the spend guard keeps one call's worst case (about $0.09) free, so the cap sits that far above
    cap = round(-(-(top + 0.09) // 0.05) * 0.05, 2)
    return {"questions": n, "by_source": dict(Counter(r["source"] for r in rows)), "expected_usd": round(exp, 4),
            "range_usd": [round(exp * 0.85, 4), round(top, 4)], "cap_usd": cap}


def select(rows: list[dict], sources: list[str] | None) -> list[dict]:
    return [r for r in rows if not sources or r["source"] in sources]


def run(max_spend: float, sdk=None, engine=None, out_dir: Path = OUT_DIR, gold: Path = GOLD,
        train: Path = TRAIN, sources: list[str] | None = None, version: str = VERSION) -> Path:
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard, SpendLimitExceeded
    from vqa.parsing.claude_parser import ClaudeParser
    rows = select(load(gold), sources)
    qs = questions(rows, train)
    if sdk is None:
        import anthropic
        sdk = anthropic.Anthropic()
    if engine is None:
        from vqa.reasoning.engine import Engine
        engine = Engine()
    llm = LLMClient(model=MODEL, guard=SpendGuard(max_spend), sdk=sdk)
    parser = ClaudeParser(llm=llm, effort=EFFORT, prompt_version=version, context_year=CONTEXT_YEAR,
                          engine=engine, max_tokens=MAX_TOKENS)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"newtypes_{version}_{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
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
                                "errors": p.errors, "cost_usd": round(p.cost_usd, 6), "prompt_version": version},
                               ensure_ascii=False) + "\n")
            print(f"[{n}/{len(rows)}] {r['id']}: {p.status}  spent ${llm.guard.spent:.4f}")
    print(f"predictions -> {path}  (spent ${llm.guard.spent:.4f})")
    return path


def _subgroup(r: dict) -> str:
    p = (r["program"].get("program") or {})
    if r["intent"] != "rule_permitted":
        return r["intent"]
    if p.get("at_signal") or (p.get("claim") or {}).get("at_signal"):
        return "rule_permitted/lights"
    if p.get("maneuver") or (p.get("claim") or {}).get("maneuver"):
        return "rule_permitted/markings"
    return "rule_permitted/places"


# Per group (owner, 2026-11-17): the minimum questions per type for the 80% rule, and whether the
# group decides which types stay on (assistant-written rows are a smoke test only).
GROUPS = {"train": (5, True), "owner_written": (3, True), "ai_drafted_owner_reviewed": (3, False),
          "assistant_written": (5, False),
          "owner2": (3, True)}          # parser v13 (owner, 2026-11-18): the new types 4-11


def _rate_rule(c: int, n: int, min_n: int) -> str:
    if n < min_n:
        return f"fewer than {min_n} questions: reported only"
    return "pass" if c / n >= PASS_RATE else "below 80%"


def score(preds: list[dict], rows: list[dict]) -> dict:
    """Per group and type: exact programs (any `also_accept` program counts). `gap` rows (the DSL
    can't express the question; expected out of scope) are reported apart, not in the type rates."""
    from vqa.schemas import QueryProgram
    by_id = {p["id"]: p for p in preds}
    cells: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    sub: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    gaps, misses = [], []
    for r in rows:
        wants = [canonical(gold_query(r["program"]))] + [canonical(gold_query(a)) for a in r.get("also_accept", [])]
        p = by_id.get(r["id"])
        got = canonical(QueryProgram.model_validate(p["query"])) if p and p.get("query") else None
        ok = got in wants
        if r.get("gap"):
            gaps.append({"id": r["id"], "intent": r["intent"], "parsed_out_of_scope": ok})
            continue
        for d, k in ((cells, r["intent"]), (sub, _subgroup(r))):
            d[(r["source"], k)][0] += ok
            d[(r["source"], k)][1] += 1
        if not ok:
            misses.append({"id": r["id"], "source": r["source"], "intent": r["intent"],
                           "status": p and p.get("status")})
    groups: dict[str, dict] = {}
    for (src, k), (c, n) in sorted(cells.items()):
        min_n = GROUPS[src][0]
        groups.setdefault(src, {})[k] = {"correct": c, "n": n, "rate": round(c / n, 3), "rule": _rate_rule(c, n, min_n)}
    types = sorted({k for _, k in cells})
    decision = {}
    for k in types:
        rules = [groups.get(src, {}).get(k, {}).get("rule") for src, (_, decides) in GROUPS.items() if decides]
        rules = [x for x in rules if x]
        if any(x == "below 80%" for x in rules):
            decision[k] = "below 80% in a deciding group: listed; its rules stay on only with the owner's yes"
        elif any(x == "pass" for x in rules):
            decision[k] = "stays on"
        else:
            decision[k] = "not decided: too few train / owner-written questions"
    return {"groups": groups, "subgroups": {f"{s}:{k}": f"{c}/{n}" for (s, k), (c, n) in sorted(sub.items())},
            "decision": decision, "weaker_intents": [k for k, v in decision.items() if v.startswith("below")],
            "gaps": gaps, "missing_predictions": sorted({r["id"] for r in rows} - by_id.keys()), "misses": misses}


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    e = sp.add_parser("estimate")
    e.add_argument("--sources", nargs="*", choices=list(GROUPS))
    e.add_argument("--version", default=VERSION, choices=["v12", "v13", "v14"])
    r = sp.add_parser("run")
    r.add_argument("--version", default=VERSION, choices=["v12", "v13", "v14"])
    r.add_argument("--max-spend", type=float, required=True)
    r.add_argument("--sources", nargs="*", choices=list(GROUPS),
                   help="only these groups (default: all); train owner_written = the deciding groups")
    s = sp.add_parser("score")
    s.add_argument("predictions", type=Path)
    a = ap.parse_args()
    rows = load()
    if a.cmd == "estimate":
        print(json.dumps(estimate(select(rows, a.sources), a.version), indent=2))
    elif a.cmd == "run":
        est = estimate(select(rows, a.sources), a.version)
        if est["expected_usd"] > a.max_spend:
            raise SystemExit(f"expected ${est['expected_usd']} exceeds --max-spend ${a.max_spend}; nothing sent")
        run(a.max_spend, sources=a.sources, version=a.version)
    else:
        preds = [json.loads(x) for x in a.predictions.read_text(encoding="utf-8").splitlines() if x.strip()]
        print(json.dumps(score(preds, rows), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
