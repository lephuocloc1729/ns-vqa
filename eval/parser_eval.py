"""Parser evaluation against the reviewed gold intents (phase 2, plan item 5).

    .venv/bin/python eval/parser_eval.py run --model claude-haiku-5-5 --effort low --max-spend 0.5
    .venv/bin/python eval/parser_eval.py score logs/parser_eval/<predictions>.jsonl [more ...]

`run` parses the gate questions (below) with the Claude parser and writes one
prediction record per question to logs/parser_eval/ (gitignored): id, split,
image_id, status, query (QueryProgram, or out_of_scope), errors, raw replies,
token usage, cost, attempts, model, effort, prompt version. No question text is
written. Before the first call it prints the estimate and stops if the spend
guard's worst case (every question retried, nothing cached) exceeds --max-spend.

`score` compares predictions with the gold and prints, per split: program exact
match, slot F1, out-of-scope precision/recall and cost; every accuracy is given
on all images and on non-duplicate images (eval/report.py), and the gate result.
Given several prediction files it adds an effort-comparison table.

Gate (fixed on 2026-11-15, before any Haiku result):
- Gate set: the public_dev rows of data/annotations/gold_intents_v1/gold_intents_v1.jsonl,
  excluding the public_dev few-shot ids of the prompt (public_natural_0026, 0097,
  0082 in v4) and rows the owner skipped (skipped rows are not in the gold file).
- Out-of-scope gold rows count. A prediction matches one only if it is out_of_scope.
- A parse failure after the retry (status invalid or error), or a missing
  prediction, counts as wrong.
- Program accuracy = exact matches / gate rows. The gate passes if the point
  estimate is >= 90%. It is reported with a 95% Wilson CI.

Normalization before comparing (both gold and prediction, per the plan):
- both become QueryPrograms with the parser's defaults filled (context year 2025,
  the year the dataset's questions come from; vehicle motor_vehicle);
- Forbidden is compiled to Verify(Permitted, expect=False) (vqa.parsing.dsl), also
  inside all_of / any_of;
- Verify(claim, expect=True) is the bare claim;
- choice labels are ignored;
- defaults_applied, missing_slots and out_of_scope_reason are not compared.
A prediction is correct if it equals the gold program or any also_accept program.

Slot F1: each program is flattened to (path, value) leaves of its normalized form
(choice labels dropped, list positions kept); per question the best gold
alternative is used; counts are summed over the gate rows whose gold has a
program (an out-of-scope or failed prediction contributes no slots).

Data access: only public_dev questions are read. The public test file is loaded
and immediately filtered to public_dev ids; a gold id outside public_dev stops the
run. public_holdout and private questions are never used.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.report import format_report, score_report, wilson_ci  # noqa: E402
from vqa.llm.pricing import cost_usd, worst_case_usd  # noqa: E402
from vqa.parsing.dsl import normalize  # noqa: E402
from vqa.parsing.prompt import examples, system_prompt  # noqa: E402
from vqa.parsing.wire import WParse, to_query  # noqa: E402
from vqa.schemas import AllOf, AnyOf, Choose, QueryProgram, Verify  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATASET = Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural")) / "dataset"
PUBLIC_FILE = DATASET / "public_test data" / "vlsp_2025_public_test.json"
SPLIT_FILE = ROOT / "data" / "splits" / "public_split.json"
GOLD_FILE = ROOT / "data" / "annotations" / "gold_intents_v1" / "gold_intents_v1.jsonl"
OUT_DIR = ROOT / "logs" / "parser_eval"

PROMPT_VERSION = "v4"
CONTEXT_YEAR = 2025          # as in gold drafting: the dataset's questions are from 2025
MAX_TOKENS = 4096
GATE = 0.90
EXPECTED_OUTPUT_TOKENS = 400  # per call, for the printed estimate only (answer + thinking)
RETRY_SHARE = 0.10            # share of questions expected to need the retry, estimate only


# --------------------------------------------------------------------------- data

def load_gold(path: Path | None = None) -> list[dict]:
    path = path or GOLD_FILE
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fewshot_ids(version: str = PROMPT_VERSION) -> set[str]:
    return {ex["id"] for ex in examples(version)}


def gate_rows(gold: list[dict], version: str = PROMPT_VERSION) -> list[dict]:
    """Gate set: public_dev gold rows that are not few-shots of the prompt."""
    shots = fewshot_ids(version)
    return [g for g in gold if g["split"] == "public_dev" and g["id"] not in shots]


def public_dev_ids(split_file: Path | None = None) -> set[str]:
    split = json.loads((split_file or SPLIT_FILE).read_text())
    return set(split["public_dev"]["questions"])


def load_dev_questions(ids: set[str], public_file: Path | None = None,
                       split_file: Path | None = None) -> dict[str, dict]:
    """{id: {"question", "image_id"}} for public_dev ids only. Raises if an id is
    not in public_dev, so a holdout or private id can never be parsed or scored."""
    dev = public_dev_ids(split_file)
    outside = sorted(set(ids) - dev)
    if outside:
        raise SystemExit(f"not public_dev questions, refusing to read them: {outside[:5]}")
    rows = json.loads((public_file or PUBLIC_FILE).read_text(encoding="utf-8"))
    return {q["id"]: {"question": q["question"], "image_id": q["image_id"]}
            for q in rows if q["id"] in ids}


# --------------------------------------------------------------------------- normalize

def gold_query(program: dict) -> QueryProgram:
    return to_query(WParse.model_validate(program), CONTEXT_YEAR)


def _canon(p: Any) -> dict:
    """A program as a plain JSON dict after the plan's normalization. Built as dicts
    because a compiled Forbidden (a Verify) is not a valid all_of member type."""
    p = normalize(p)
    if isinstance(p, (AllOf, AnyOf)):
        return {**p.model_dump(mode="json", exclude={"claims"}),
                "claims": [_canon(c) for c in p.claims]}
    if isinstance(p, Verify):
        claim = _canon(p.claim)
        return claim if p.expect else {**p.model_dump(mode="json", exclude={"claim"}), "claim": claim}
    if isinstance(p, Choose):
        return {**p.model_dump(mode="json", exclude={"options"}),
                "options": [{"claim": _canon(o.claim), "expect": o.expect} for o in p.options]}
    return p.model_dump(mode="json")


def canonical(q: QueryProgram) -> dict:
    """The comparable form of a program: {"out_of_scope": True} or the normalized
    program as JSON."""
    if q.out_of_scope:
        return {"out_of_scope": True}
    return {"program": _canon(q.program)}


def _leaves(node: Any, path: str = "") -> set[tuple[str, str]]:
    if isinstance(node, dict):
        out: set[tuple[str, str]] = set()
        for k, v in node.items():
            if k == "label":
                continue
            out |= _leaves(v, f"{path}.{k}" if path else k)
        return out
    if isinstance(node, list):
        out = set()
        for i, v in enumerate(node):
            out |= _leaves(v, f"{path}[{i}]")
        return out
    if node is None:
        return set()
    return {(path, json.dumps(node))}


def slots(c: dict) -> set[tuple[str, str]]:
    return set() if "program" not in c else _leaves(c["program"])


# --------------------------------------------------------------------------- score

def score_one(gold: dict, pred: dict | None) -> dict:
    alts = [canonical(gold_query(gold["program"]))] + \
           [canonical(gold_query(a)) for a in gold.get("also_accept", [])]
    gold_oos = "out_of_scope" in alts[0]
    if pred is None or pred.get("status") not in ("ok", "out_of_scope"):
        got = None
    else:
        got = canonical(QueryProgram.model_validate(pred["query"]))
    correct = got is not None and got in alts
    pred_oos = got is not None and "out_of_scope" in got
    tp = fp = fn = 0
    if not gold_oos:
        g_slots = [slots(a) for a in alts if "program" in a]
        p_slots = slots(got) if got else set()
        best = max(g_slots, key=lambda g: (2 * len(g & p_slots)) / (len(g) + len(p_slots) or 1))
        tp, fp, fn = len(best & p_slots), len(p_slots - best), len(best - p_slots)
    return {"id": gold["id"], "split": gold["split"], "correct": correct, "gold_oos": gold_oos,
            "pred_oos": pred_oos, "failed": got is None, "tp": tp, "fp": fp, "fn": fn}


def _ratio(a: float, b: float) -> float | None:
    return a / b if b else None


def score_predictions(preds: list[dict], gold: list[dict], image_of: dict[str, str],
                      duplicates: dict | None = None, version: str | None = None) -> dict:
    """Scores for one prediction file. Splits: the gate set (public_dev) and any
    other split present in both gold and predictions."""
    version = version or (preds[0].get("prompt_version") if preds else PROMPT_VERSION)
    by_id = {p["id"]: p for p in preds}
    shots = fewshot_ids(version)
    out: dict[str, Any] = {"model": preds[0].get("model") if preds else None,
                           "effort": preds[0].get("effort") if preds else None,
                           "prompt_version": version, "splits": {}}
    for split in sorted({g["split"] for g in gold}):
        rows = [g for g in gold if g["split"] == split and g["id"] not in shots]
        if split != "public_dev":
            rows = [g for g in rows if g["id"] in by_id]   # only splits that were run
        if not rows:
            continue
        res = [score_one(g, by_id.get(g["id"])) for g in rows]
        n, correct = len(res), sum(r["correct"] for r in res)
        tp, fp, fn = (sum(r[k] for r in res) for k in ("tp", "fp", "fn"))
        oos_tp = sum(r["gold_oos"] and r["pred_oos"] for r in res)
        cost = sum(by_id[g["id"]].get("cost_usd", 0.0) for g in rows if g["id"] in by_id)
        s: dict[str, Any] = {
            "n": n, "correct": correct, "accuracy": correct / n,
            "ci95": list(wilson_ci(correct, n)),
            "failed": sum(r["failed"] for r in res),
            "slot_f1": _ratio(2 * tp, 2 * tp + fp + fn),
            "oos_precision": _ratio(oos_tp, sum(r["pred_oos"] for r in res)),
            "oos_recall": _ratio(oos_tp, sum(r["gold_oos"] for r in res)),
            "cost_usd": cost, "wrong": [r["id"] for r in res if not r["correct"]],
        }
        if split == "public_dev":
            s["gate"] = {"threshold": GATE, "passed": s["accuracy"] >= GATE}
            s["report"] = score_report(
                [{"question_id": r["id"], "image_id": image_of[r["id"]], "correct": r["correct"]}
                 for r in res], split="public", duplicates=duplicates)
        out["splits"][split] = s
    return out


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def format_scores(sc: dict) -> str:
    lines = [f"model {sc['model']}  effort {sc['effort']}  prompt {sc['prompt_version']}"]
    for split, s in sc["splits"].items():
        lo, hi = s["ci95"]
        lines.append(f"[{split}] program accuracy {_pct(s['accuracy'])} ({s['correct']}/{s['n']}), "
                     f"95% CI {_pct(lo)}-{_pct(hi)}; failed parses {s['failed']}")
        lines.append(f"  slot F1 {_pct(s['slot_f1'])}; out-of-scope precision {_pct(s['oos_precision'])}, "
                     f"recall {_pct(s['oos_recall'])}; cost ${s['cost_usd']:.4f}")
        if "gate" in s:
            verdict = "PASS" if s["gate"]["passed"] else "FAIL"
            lines.append(f"  gate (>= {_pct(GATE)} on the point estimate): {verdict}")
            lines.append("  " + format_report(s["report"]).replace("\n", "\n  "))
        if s["wrong"]:
            lines.append(f"  wrong: {', '.join(s['wrong'])}")
    return "\n".join(lines)


def comparison_table(scores: list[dict]) -> str:
    head = "| model | effort | n | accuracy | 95% CI | slot F1 | OOS P | OOS R | cost | per question |"
    rows = [head, "|" + "---|" * 10]
    for sc in scores:
        s = sc["splits"].get("public_dev")
        if not s:
            continue
        lo, hi = s["ci95"]
        rows.append(f"| {sc['model']} | {sc['effort']} | {s['n']} | {_pct(s['accuracy'])} | "
                    f"{_pct(lo)}-{_pct(hi)} | {_pct(s['slot_f1'])} | {_pct(s['oos_precision'])} | "
                    f"{_pct(s['oos_recall'])} | ${s['cost_usd']:.4f} | ${s['cost_usd'] / s['n']:.5f} |")
    return "\n".join(rows)


def load_predictions(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score_files(paths: list[Path], gold_path: Path | None = None) -> str:
    gold = load_gold(gold_path)
    image_of = {k: v["image_id"]
                for k, v in load_dev_questions({g["id"] for g in gate_rows(gold)}).items()}
    scores = [score_predictions(load_predictions(p), gold, image_of) for p in paths]
    text = "\n\n".join(format_scores(s) for s in scores)
    if len(scores) > 1:
        text += "\n\n" + comparison_table(scores)
    return text


# --------------------------------------------------------------------------- run

def estimate(model: str, prompt_tokens: list[int], max_tokens: int = MAX_TOKENS) -> dict:
    """Expected cost (one cache write, then cache reads; some retries) and the
    worst case the run is checked against (every question twice, nothing cached,
    full max_tokens out)."""
    n = len(prompt_tokens)
    shared = min(prompt_tokens) - 20 if prompt_tokens else 0
    calls = n * (1 + RETRY_SHARE)
    expected = 0.0
    if n:
        expected = cost_usd(model, cache_write_tokens=shared, input_tokens=20,
                            output_tokens=EXPECTED_OUTPUT_TOKENS)
        expected += (calls - 1) * cost_usd(model, cache_read_tokens=shared, input_tokens=20,
                                           output_tokens=EXPECTED_OUTPUT_TOKENS)
    worst = 2 * sum(worst_case_usd(model, t, max_tokens) for t in prompt_tokens)
    return {"questions": n, "prompt_tokens_per_request": round(sum(prompt_tokens) / n) if n else 0,
            "expected_usd": round(expected, 4), "worst_case_usd": round(worst, 4)}


def run(model: str, effort: str | None, max_spend: float, sdk=None, engine=None,
        gold_path: Path | None = None, public_file: Path | None = None,
        split_file: Path | None = None, out_dir: Path | None = None) -> Path:
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.parsing.claude_parser import ClaudeParser

    if sdk is None:
        import anthropic
        sdk = anthropic.Anthropic()
    rows = gate_rows(load_gold(gold_path))
    qs = load_dev_questions({g["id"] for g in rows}, public_file, split_file)
    system = system_prompt(PROMPT_VERSION)
    sys_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    kw = {"output_config": {"effort": effort}} if effort else {}
    counts = [sdk.messages.count_tokens(model=model, system=sys_blocks,
                                        messages=[{"role": "user", "content": f"Question: {qs[g['id']]['question'].strip()}"}],
                                        **kw).input_tokens for g in rows]
    est = estimate(model, counts)
    print(json.dumps({"model": model, "effort": effort, "prompt_version": PROMPT_VERSION,
                      "max_spend_usd": max_spend, **est}, indent=2))
    if est["worst_case_usd"] > max_spend:
        raise SystemExit(f"worst case ${est['worst_case_usd']:.4f} exceeds --max-spend "
                         f"${max_spend:.2f}; nothing was sent")
    if engine is None:
        from vqa.reasoning.engine import Engine
        engine = Engine()
    llm = LLMClient(model=model, guard=SpendGuard(max_spend), sdk=sdk)
    parser = ClaudeParser(llm=llm, effort=effort, prompt_version=PROMPT_VERSION,
                          context_year=CONTEXT_YEAR, engine=engine, max_tokens=MAX_TOKENS)
    out_dir = out_dir or OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"pred_{model}_{effort or 'default'}_{PROMPT_VERSION}_{stamp}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for n, g in enumerate(rows, 1):
            r = parser.parse(qs[g["id"]]["question"])
            rec = {"id": g["id"], "split": g["split"], "image_id": qs[g["id"]]["image_id"],
                   "status": r.status, "query": r.query.model_dump(mode="json") if r.query else None,
                   "errors": r.errors, "raw": r.raw, "usage": r.usage, "attempts": r.attempts,
                   "cost_usd": round(r.cost_usd, 6), "model": model, "effort": effort,
                   "prompt_version": PROMPT_VERSION, "run_id": llm.run_id}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{n}/{len(rows)}] {g['id']}: {r.status}  spent ${llm.guard.spent:.4f}")
    print(f"predictions -> {path}  (spent ${llm.guard.spent:.4f})")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--model", default="claude-haiku-5-5")
    r.add_argument("--effort", choices=["low", "medium"], required=True)
    r.add_argument("--max-spend", type=float, required=True)
    s = sub.add_parser("score")
    s.add_argument("predictions", nargs="+", type=Path)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.model, a.effort, a.max_spend)
    else:
        print(score_files(a.predictions))


if __name__ == "__main__":
    main()
