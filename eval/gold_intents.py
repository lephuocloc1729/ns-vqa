"""Gold intents: draft query programs with Claude Opus 5.5 (Batch API), review them
by hand, import the reviewed set.

Scope: every public_dev question and a seeded sample of 150 train questions
(few-shot examples excluded). No public_holdout or private questions: those are
scored end to end only.

    .venv/bin/python eval/gold_intents.py select              # write questions.jsonl
    .venv/bin/python eval/gold_intents.py estimate            # cost estimate, no spend
    .venv/bin/python eval/gold_intents.py submit --max-spend N  # send the batch
    .venv/bin/python eval/gold_intents.py collect             # write drafts.jsonl + review.csv
    .venv/bin/python eval/gold_intents.py import              # review.csv -> gold_intents_v1.jsonl

questions.jsonl, drafts.jsonl, review.csv and batch.json hold dataset question
text and stay local (gitignored); gold_intents_v1.jsonl keeps ids and programs.

Review CSV columns: id, split, question, draft_status, draft_program, verdict,
corrected_program, also_accept, notes. verdict: ok (take the draft) | fix (take
corrected_program) | out_of_scope | skip; empty = not reviewed yet.
corrected_program and also_accept hold wire JSON in the compact form used in
prompts/parser/v1/fewshot.jsonl (also_accept: a JSON list of such objects).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vqa.llm.pricing import cost_usd, worst_case_usd  # noqa: E402
from vqa.llm.spend import SpendGuard, log_call  # noqa: E402
from vqa.parsing import validator  # noqa: E402
from vqa.parsing.prompt import examples, system_prompt  # noqa: E402
from vqa.parsing.wire import WParse, compact, json_schema, to_query  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATASET = Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural")) / "dataset"
OUT = ROOT / "data" / "annotations" / "gold_intents_v1"
MODEL = "claude-opus-5-5"
EFFORT = "medium"
MAX_TOKENS = 4000
TRAIN_SAMPLE = 150
SEED = 20261115
PROMPT_VERSION = "v1"
CONTEXT_YEAR = 2025  # questions in this dataset come from 2025; used for missing years


def user_text(q: str) -> str:
    return f"Question: {q.strip()}"


# --------------------------------------------------------------------------- select

def select() -> list[dict]:
    split = json.loads((ROOT / "data" / "splits" / "public_split.json").read_text())
    dev_ids = set(split["public_dev"]["questions"])
    public = json.loads((DATASET / "public_test data" / "vlsp_2025_public_test.json")
                        .read_text(encoding="utf-8"))
    train = json.loads((DATASET / "train data" / "vlsp_2025_train.json").read_text(encoding="utf-8"))
    shots = {ex["id"] for ex in examples(PROMPT_VERSION)}
    rows = [{"id": q["id"], "split": "public_dev", "question": q["question"]}
            for q in public if q["id"] in dev_ids]
    pool = sorted((t for t in train if t["id"] not in shots and t["id"] != "train_284"),
                  key=lambda t: int(t["id"].split("_")[1]))
    sample = random.Random(SEED).sample(pool, TRAIN_SAMPLE)
    rows += [{"id": t["id"], "split": "train", "question": t["question"]}
             for t in sorted(sample, key=lambda t: int(t["id"].split("_")[1]))]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "questions.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{len(rows)} questions ({len(dev_ids)} public_dev, {TRAIN_SAMPLE} train) "
          f"-> {(OUT / 'questions.jsonl').relative_to(ROOT)}")
    return rows


def load_questions() -> list[dict]:
    return [json.loads(l) for l in (OUT / "questions.jsonl").read_text(encoding="utf-8").splitlines()]


# --------------------------------------------------------------------------- estimate

def rough_tokens(text: str) -> int:
    """Rough token count without the API: ~3.5 UTF-8 bytes per token (Vietnamese
    diacritics make bytes, not characters, the better proxy). +-30%."""
    return int(len(text.encode("utf-8")) / 3.5) + 1


def expected_output_tokens() -> int:
    """Average full wire answer (all fields, as the model must write it) plus an
    allowance for adaptive thinking at medium effort."""
    sizes = []
    for ex in examples(PROMPT_VERSION):
        full = WParse.model_validate(ex["output"]).model_dump()
        sizes.append(rough_tokens(json.dumps(full, ensure_ascii=False)))
    return int(sum(sizes) / len(sizes)) + 800


def estimate(sdk=None) -> dict:
    rows = load_questions()
    system = system_prompt(PROMPT_VERSION)
    sys_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    if sdk is not None:
        counts = [sdk.messages.count_tokens(
            model=MODEL, system=sys_blocks, messages=[{"role": "user", "content": user_text(r["question"])}],
            output_config={"format": {"type": "json_schema", "schema": json_schema()},
                           "effort": EFFORT}).input_tokens for r in rows]
        method = "exact (messages.count_tokens)"
    else:
        base = rough_tokens(system) + rough_tokens(json.dumps(json_schema()))
        counts = [base + rough_tokens(user_text(r["question"])) for r in rows]
        method = "rough (no API key: ~3.5 bytes per token, +-30%)"
    n, prompt = len(rows), sum(counts)
    sys_tokens = min(counts) - 20
    out = expected_output_tokens() * n
    no_cache = cost_usd(MODEL, input_tokens=prompt, output_tokens=out, batch=True)
    # batch caching is best-effort: one write, then reads for the shared system prompt
    cached = cost_usd(MODEL, cache_write_tokens=sys_tokens, cache_read_tokens=sys_tokens * (n - 1),
                      input_tokens=prompt - sys_tokens * n, output_tokens=out, batch=True)
    worst = sum(worst_case_usd(MODEL, c, MAX_TOKENS, batch=True) for c in counts)
    est = {"method": method, "requests": n, "prompt_tokens_total": prompt,
           "prompt_tokens_per_request": round(prompt / n), "expected_output_tokens_total": out,
           "expected_usd_no_cache_hits": round(no_cache, 2),
           "expected_usd_all_cache_hits": round(cached, 2),
           "worst_case_usd": round(worst, 2), "model": MODEL, "effort": EFFORT,
           "max_tokens": MAX_TOKENS}
    return est


# --------------------------------------------------------------------------- submit / collect

def submit(max_spend: float) -> str:
    import anthropic

    sdk = anthropic.Anthropic()
    est = estimate(sdk)
    print(json.dumps(est, indent=2))
    guard = SpendGuard(max_spend)
    guard.check(est["worst_case_usd"], "gold-intent batch")
    system = system_prompt(PROMPT_VERSION)
    sys_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    schema = json_schema()
    reqs = [{"custom_id": r["id"], "params": {
        "model": MODEL, "max_tokens": MAX_TOKENS, "system": sys_blocks,
        "messages": [{"role": "user", "content": user_text(r["question"])}],
        "output_config": {"format": {"type": "json_schema", "schema": schema}, "effort": EFFORT}}}
        for r in load_questions()]
    batch = sdk.messages.batches.create(requests=reqs)
    (OUT / "batch.json").write_text(json.dumps({"batch_id": batch.id, "estimate": est,
                                                "submitted": time.time()}, indent=2))
    print(f"submitted batch {batch.id} ({len(reqs)} requests)")
    return batch.id


def collect(wait: bool = False) -> None:
    import anthropic

    sdk = anthropic.Anthropic()
    batch_id = json.loads((OUT / "batch.json").read_text())["batch_id"]
    while True:
        b = sdk.messages.batches.retrieve(batch_id)
        if b.processing_status == "ended" or not wait:
            break
        time.sleep(60)
    if b.processing_status != "ended":
        print(f"batch {batch_id} is {b.processing_status}; run collect again later")
        return
    from vqa.reasoning.engine import Engine
    engine = Engine()
    qs = {r["id"]: r for r in load_questions()}
    drafts, total = {}, 0.0
    for res in sdk.messages.batches.results(batch_id):
        rid = res.custom_id
        rec = {**qs[rid], "draft_status": res.result.type, "draft": None, "errors": []}
        if res.result.type == "succeeded":
            msg = res.result.message
            u = msg.usage
            usage = {"input_tokens": u.input_tokens or 0, "output_tokens": u.output_tokens or 0,
                     "cache_read_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
                     "cache_write_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0}
            cost = cost_usd(MODEL, batch=True, **usage)
            total += cost
            log_call({"run_id": batch_id, "purpose": "gold-intent draft", "model": MODEL,
                      "batch": True, "custom_id": rid, "stop_reason": msg.stop_reason,
                      **usage, "cost_usd": round(cost, 6)})
            text = next((x.text for x in msg.content if x.type == "text"), "")
            if msg.stop_reason == "refusal":
                rec["draft_status"] = "refused"
            else:
                try:
                    w = WParse.model_validate(json.loads(text))
                    rec["draft"] = compact(w)
                    rec["errors"] = validator.check(to_query(w, CONTEXT_YEAR), engine)
                    rec["draft_status"] = "invalid" if rec["errors"] else (
                        "out_of_scope" if w.out_of_scope else "ok")
                except Exception as e:  # noqa: BLE001 - recorded for the reviewer
                    rec["draft_status"], rec["errors"] = "invalid", [str(e)]
        drafts[rid] = rec
    order = [r["id"] for r in load_questions()]
    with open(OUT / "drafts.jsonl", "w", encoding="utf-8") as f:
        for rid in order:
            f.write(json.dumps(drafts.get(rid, {**qs[rid], "draft_status": "missing"}),
                               ensure_ascii=False) + "\n")
    with open(OUT / "review.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "split", "question", "draft_status", "draft_program", "verdict",
                    "corrected_program", "also_accept", "notes"])
        for rid in order:
            d = drafts.get(rid, {})
            w.writerow([rid, qs[rid]["split"], qs[rid]["question"], d.get("draft_status", "missing"),
                        json.dumps(d.get("draft"), ensure_ascii=False) if d.get("draft") else "",
                        "", "", "", "; ".join(d.get("errors", []))])
    print(f"collected {len(drafts)} drafts, cost ${total:.2f} -> {OUT}")


# --------------------------------------------------------------------------- import

def import_review(path: Path | None = None) -> list[dict]:
    from vqa.reasoning.engine import Engine
    engine = Engine()
    path = path or OUT / "review.csv"
    gold, problems = [], []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            verdict = (row.get("verdict") or "").strip().lower()
            if verdict in ("", "skip"):
                continue
            if verdict == "out_of_scope":
                program = {"out_of_scope": True, "out_of_scope_reason": row.get("notes") or "reviewer"}
            elif verdict == "ok":
                program = json.loads(row["draft_program"])
            elif verdict == "fix":
                program = json.loads(row["corrected_program"])
            else:
                problems.append(f"{row['id']}: unknown verdict {verdict!r}")
                continue
            also = json.loads(row["also_accept"]) if (row.get("also_accept") or "").strip() else []
            for prog in [program, *also]:
                errs = validator.check(to_query(WParse.model_validate(prog), CONTEXT_YEAR), engine)
                if errs:
                    problems.append(f"{row['id']}: {errs}")
            # ids and programs only: question text stays in the dataset (CLAUDE.md)
            gold.append({"id": row["id"], "split": row["split"],
                         "program": program, "also_accept": also, "verdict": verdict})
    if problems:
        raise SystemExit("review has problems:\n" + "\n".join(problems))
    out = OUT / "gold_intents_v1.jsonl"
    out.write_text("".join(json.dumps(g, ensure_ascii=False) + "\n" for g in gold), encoding="utf-8")
    print(f"{len(gold)} reviewed programs -> {out}")
    return gold


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select")
    sub.add_parser("estimate")
    s = sub.add_parser("submit")
    s.add_argument("--max-spend", type=float, required=True)
    c = sub.add_parser("collect")
    c.add_argument("--wait", action="store_true")
    i = sub.add_parser("import")
    i.add_argument("--csv", type=Path)
    a = ap.parse_args()
    if a.cmd == "select":
        select()
    elif a.cmd == "estimate":
        sdk = None
        if os.environ.get("ANTHROPIC_API_KEY"):
            import anthropic
            sdk = anthropic.Anthropic()
        print(json.dumps(estimate(sdk), indent=2))
    elif a.cmd == "submit":
        submit(a.max_spend)
    elif a.cmd == "collect":
        collect(a.wait)
    elif a.cmd == "import":
        import_review(a.csv)


if __name__ == "__main__":
    main()
