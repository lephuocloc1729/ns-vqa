"""Gold intents: draft query programs with Claude Opus 5.5 (Batch API), review them
by hand, import the reviewed set.

Scope: every public_dev question plus a small train sample (default 40), drawn
evenly across rough question categories (one question per image where possible,
few-shot examples and train_284 excluded) so a few questions cover many forms.
No public_holdout or private questions: those are scored end to end only.

    .venv/bin/python eval/gold_intents.py select [--train N]  # write questions.jsonl
    .venv/bin/python eval/gold_intents.py estimate            # cost estimate, no spend
    .venv/bin/python eval/gold_intents.py run --max-spend N     # sequential, cached (recommended)
    .venv/bin/python eval/gold_intents.py submit --max-spend N  # or: send a batch (half price,
    .venv/bin/python eval/gold_intents.py collect             #   caching best effort), then collect
    .venv/bin/python eval/gold_intents.py import              # review.csv -> gold_intents_v1.jsonl

questions.jsonl, drafts.jsonl, review.csv, run_progress.jsonl and batch.json hold dataset question
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
import re
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
# exact count (2026-11-15) was 36,817 prompt tokens per request against a rough 17,210:
# Vietnamese text and the JSON schema take far more tokens than bytes / 3.5 suggests
ROUGH_PROMPT_CALIBRATION = 2.14
MIN_CACHE_SHARE = 0.9   # sequential run: share of the prompt that must come from the cache
SEED = 20261115
TRAIN_SAMPLE = 40
PROMPT_VERSION = "v2"
CONTEXT_YEAR = 2025  # questions in this dataset come from 2025; used for missing years


# Rough categories for spreading the train sample; first match wins. Used only to
# choose which train questions to draft, never at inference.
TRAIN_CATEGORIES = [
    ("violation", r"vi phạm"), ("counting", r"bao nhiêu (biển|cái)|mấy biển"),
    ("lane", r"làn"), ("speed", r"km/h|tốc độ"), ("size_weight", r"tấn|trọng|chiều cao|chiều rộng|khối lượng"),
    ("time", r"\d+[:h]\d*|giờ|ngày|thứ"), ("stop_park", r"đỗ|dừng"),
    ("direction", r"hướng|đi đâu|điểm đến|muốn đi"), ("required", r"bắt buộc|phải đi|phải rẽ"),
    ("identity", r"(là|phải là) biển|biển gì|loại biển|thuộc nhóm"),
    ("meaning", r"ý nghĩa|báo hiệu|cảnh báo|nghĩa là|chỉ dẫn"),
    ("which_vehicles", r"(loại )?xe nào|phương tiện nào|ai được"),
    ("banned_what", r"cấm (hành vi|những|điều) gì|không được làm gì|lệnh cấm"),
    ("warning", r"báo trước|phía trước có|chú ý"), ("choice", r" hay |trong số|trong các"),
    ("action", r"được (rẽ|quay|vượt|đi|chạy)|có cấm"),
]


def category(question: str) -> str:
    q = question.lower()
    return next((name for name, pat in TRAIN_CATEGORIES if re.search(pat, q)), "other")


def spread_sample(pool: list[dict], n: int, seed: int = SEED) -> list[dict]:
    """n questions taken round-robin over categories (each shuffled with the seed),
    preferring images not yet used, so a small sample covers many question forms."""
    rng = random.Random(seed)
    groups: dict[str, list[dict]] = {}
    for t in pool:
        groups.setdefault(category(t["question"]), []).append(t)
    for g in groups.values():
        rng.shuffle(g)
    picked, images = [], set()
    while len(picked) < n and any(groups.values()):
        for name in sorted(groups):
            g = groups[name]
            if not g or len(picked) >= n:
                continue
            i = next((k for k, t in enumerate(g) if t["image_id"] not in images), 0)
            t = g.pop(i)
            picked.append(t)
            images.add(t["image_id"])
    return picked


def user_text(q: str) -> str:
    return f"Question: {q.strip()}"


# --------------------------------------------------------------------------- select

def select(train_sample: int = TRAIN_SAMPLE) -> list[dict]:
    split = json.loads((ROOT / "data" / "splits" / "public_split.json").read_text())
    dev_ids = set(split["public_dev"]["questions"])
    public = json.loads((DATASET / "public_test data" / "vlsp_2025_public_test.json")
                        .read_text(encoding="utf-8"))
    train = json.loads((DATASET / "train data" / "vlsp_2025_train.json").read_text(encoding="utf-8"))
    shots = {ex["id"] for ex in examples(PROMPT_VERSION)}
    # a public_dev few-shot is in the prompt and out of the gate score: nothing to draft
    rows = [{"id": q["id"], "split": "public_dev", "question": q["question"]}
            for q in public if q["id"] in dev_ids and q["id"] not in shots]
    pool = sorted((t for t in train if t["id"] not in shots and t["id"] != "train_284"),
                  key=lambda t: int(t["id"].split("_")[1]))
    sample = spread_sample(pool, train_sample)
    rows += [{"id": t["id"], "split": "train", "question": t["question"]}
             for t in sorted(sample, key=lambda t: int(t["id"].split("_")[1]))]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "questions.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{len(rows)} questions ({len(rows) - len(sample)} public_dev, {len(sample)} train) "
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
        counts = [int((base + rough_tokens(user_text(r["question"]))) * ROUGH_PROMPT_CALIBRATION)
                  for r in rows]
        method = f"rough (no API key: bytes / 3.5 x {ROUGH_PROMPT_CALIBRATION}, +-30%)"
    n, prompt = len(rows), sum(counts)
    sys_tokens = min(counts) - 20
    out = expected_output_tokens() * n
    no_cache = cost_usd(MODEL, input_tokens=prompt, output_tokens=out, batch=True)
    # batch caching is best-effort: one write, then reads for the shared system prompt
    cached = cost_usd(MODEL, cache_write_tokens=sys_tokens, cache_read_tokens=sys_tokens * (n - 1),
                      input_tokens=prompt - sys_tokens * n, output_tokens=out, batch=True)
    # sequential run: full price, one cache write, every later call reads the shared prompt
    sequential = cost_usd(MODEL, cache_write_tokens=sys_tokens, cache_read_tokens=sys_tokens * (n - 1),
                          input_tokens=prompt - sys_tokens * n, output_tokens=out)
    worst = sum(worst_case_usd(MODEL, c, MAX_TOKENS, batch=True) for c in counts)
    est = {"method": method, "requests": n, "prompt_tokens_total": prompt,
           "prompt_tokens_per_request": round(prompt / n), "expected_output_tokens_total": out,
           "expected_usd_no_cache_hits": round(no_cache, 2),
           "expected_usd_all_cache_hits": round(cached, 2),
           "worst_case_usd": round(worst, 2),
           "sequential_expected_usd": round(sequential, 2),
           "sequential_expected_usd_double_output": round(
               sequential + cost_usd(MODEL, output_tokens=out), 2), "model": MODEL, "effort": EFFORT,
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


def reviewed_rows(path: Path) -> int:
    """Rows of an existing review CSV that already carry a verdict."""
    if not path.exists():
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for row in csv.DictReader(f) if (row.get("verdict") or "").strip())


def parse_draft(rec: dict, text: str, engine) -> dict:
    """Fill a draft record from the model's JSON text: draft program, validator
    errors, and draft_status (ok | out_of_scope | invalid)."""
    try:
        w = WParse.model_validate(json.loads(text))
        rec["draft"] = compact(w)
        rec["errors"] = validator.check(to_query(w, CONTEXT_YEAR), engine)
        rec["draft_status"] = "invalid" if rec["errors"] else (
            "out_of_scope" if w.out_of_scope else "ok")
    except Exception as e:  # noqa: BLE001 - recorded for the reviewer
        rec["draft_status"], rec["errors"] = "invalid", [str(e)]
    return rec


def write_outputs(drafts: dict[str, dict]) -> None:
    """drafts.jsonl and review.csv in question order; questions without a draft
    are marked missing."""
    qs = {r["id"]: r for r in load_questions()}
    order = list(qs)
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


def refuse_if_reviewed() -> None:
    if n := reviewed_rows(OUT / "review.csv"):
        raise SystemExit(f"review.csv already has {n} reviewed rows; move it aside before "
                         "writing new drafts")


def collect(wait: bool = False) -> None:
    import anthropic

    refuse_if_reviewed()
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
                parse_draft(rec, text, engine)
        drafts[rid] = rec
    write_outputs(drafts)
    print(f"collected {len(drafts)} drafts, cost ${total:.2f} -> {OUT}")


# --------------------------------------------------------------------------- run (sequential)

class CacheMiss(SystemExit):
    pass


def run(max_spend: float, sdk=None, engine=None, check_at: int = 2,
        min_cache_share: float = MIN_CACHE_SHARE) -> dict:
    """Draft the questions one call at a time (full price, but the shared prompt is
    written to the cache once and read back by every later call).

    - The spend guard checks each call's worst case before it is sent.
    - After the `check_at`-th call of this invocation, at least `min_cache_share` of
      the prompt must have come from the cache; otherwise the run stops (CacheMiss),
      since every later call would pay full price for the prompt.
    - Progress is appended to run_progress.jsonl, so an interrupted run resumes
      where it stopped. drafts.jsonl and review.csv are rewritten after every call.
    """
    from vqa.llm.client import LLMClient, LLMError, LLMRefusal, LLMTruncated

    refuse_if_reviewed()
    if engine is None:
        from vqa.reasoning.engine import Engine
        engine = Engine()
    client = LLMClient(model=MODEL, guard=SpendGuard(max_spend), sdk=sdk)
    progress = OUT / "run_progress.jsonl"
    drafts = {}
    if progress.exists():
        for line in progress.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                drafts[rec["id"]] = rec
    system, schema = system_prompt(PROMPT_VERSION), json_schema()
    todo = [q for q in load_questions() if q["id"] not in drafts]
    print(f"{len(drafts)} already drafted, {len(todo)} to go (limit ${max_spend:.2f})")
    for n, q in enumerate(todo, 1):
        rec = {**q, "draft": None, "errors": []}
        try:
            res = client.structured(system=system, user=user_text(q["question"]), schema=schema,
                                    max_tokens=MAX_TOKENS, effort=EFFORT,
                                    purpose="gold-intent draft (sequential)")
            parse_draft(rec, res.raw_text, engine)
        except LLMRefusal:
            rec["draft_status"] = "refused"
        except LLMTruncated as e:
            rec["draft_status"], rec["errors"] = "invalid", [str(e)]
        except LLMError as e:
            rec["draft_status"], rec["errors"] = "invalid", [str(e)]
        rec["usage"] = client.last_usage
        drafts[q["id"]] = rec
        with open(progress, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        write_outputs(drafts)
        u = client.last_usage or {}
        print(f"[{n}/{len(todo)}] {q['id']}: {rec['draft_status']}  "
              f"spent ${client.guard.spent:.2f}")
        if n == check_at:
            prompt = u.get("input_tokens", 0) + u.get("cache_read_tokens", 0) + u.get("cache_write_tokens", 0)
            share = u.get("cache_read_tokens", 0) / prompt if prompt else 0.0
            if share < min_cache_share:
                raise CacheMiss(
                    f"call {n} read only {share:.0%} of its {prompt} prompt tokens from the cache "
                    f"(need {min_cache_share:.0%}); stopped after ${client.guard.spent:.2f}. "
                    "Progress is saved; consider the batch path instead.")
            print(f"cache check passed: {share:.0%} of the prompt read from the cache")
    print(f"done: {len(drafts)} drafts, this run spent ${client.guard.spent:.2f} -> {OUT}")
    return drafts


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
    sel = sub.add_parser("select")
    sel.add_argument("--train", type=int, default=TRAIN_SAMPLE,
                     help=f"train questions to draft, spread over categories (default {TRAIN_SAMPLE})")
    sub.add_parser("estimate")
    s = sub.add_parser("submit")
    s.add_argument("--max-spend", type=float, required=True)
    r = sub.add_parser("run")
    r.add_argument("--max-spend", type=float, required=True)
    c = sub.add_parser("collect")
    c.add_argument("--wait", action="store_true")
    i = sub.add_parser("import")
    i.add_argument("--csv", type=Path)
    a = ap.parse_args()
    if a.cmd == "select":
        select(a.train)
    elif a.cmd == "estimate":
        sdk = None
        if os.environ.get("ANTHROPIC_API_KEY"):
            import anthropic
            sdk = anthropic.Anthropic()
        print(json.dumps(estimate(sdk), indent=2))
    elif a.cmd == "submit":
        submit(a.max_spend)
    elif a.cmd == "run":
        run(a.max_spend)
    elif a.cmd == "collect":
        collect(a.wait)
    elif a.cmd == "import":
        import_review(a.csv)


if __name__ == "__main__":
    main()
