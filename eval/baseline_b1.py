"""Baseline B1, "Claude alone" (docs/plans/phase-5.md, item 2; P2, P5). Eval only.

The photo and the question go to one model (Haiku, Sonnet or Opus 5.5) with one plain
prompt (`eval/prompts/baseline/<version>/`): no rules, no scene graph, no law_db. The
requests go through the Message Batches API at half price. Natural QA answers are graded
by the same Opus judge as the system (`eval/judge.py`), Yes/No answers by their first word.

**public_dev (fixing the prompt), readable per question:**

    .venv/bin/python eval/baseline_b1.py estimate --split dev --model sonnet
    .venv/bin/python eval/baseline_b1.py submit --split dev --model sonnet --max-spend X
    .venv/bin/python eval/baseline_b1.py collect eval/runs/e2e/b1_dev_<model>_<run_id>.state.json --max-spend Y

  `collect` writes `b1_dev_<model>_<run_id>.jsonl` (header, then one graded line per
  question) next to the state file, in the gitignored runs folder.

**Pinning:** once the prompt is fixed on public_dev, `pin --version vN` writes the
committed, write-once `eval/baseline_pinned.json` (the prompt id). The private run refuses
any other prompt.

**private, once per model, aggregate only:**

    .venv/bin/python eval/baseline_b1.py estimate --split private --model sonnet
    .venv/bin/python eval/baseline_b1.py submit --split private --model sonnet --max-spend X --confirm-pinned
    .venv/bin/python eval/baseline_b1.py collect-private --model sonnet --max-spend Y

- `submit` refuses unless the git tree is clean, the prompt is the pinned one, this
  model's sentinel `eval/baseline_ran_b1_<model>.json` doesn't exist, there is no
  aggregate for this model, git ignores the answers folder, and the counts and image
  files check out. The sentinel is written before the batch is created, so a start that
  stops part way counts as the one run. Requests carry index ids (`q0001`, ...), never a
  question id; the sentinel keeps only a hash of the question order.
- `collect-private` reads the private answers in memory through `eval/e2e_private.py`
  (the scoring code), grades, sums, and writes one aggregate file with no question,
  image or answer id. Nothing per question is printed.
- The model's answers are kept for the owner's human scoring (P6) under
  `cache/private_run/b1_<model>_<run_id>/answers.jsonl` (gitignored, model outputs only:
  no gold answer, no grade; deleted at the end of phase 5, as the P4 replay records).

`estimate` uses counts only (rough tokens, no API call); for private it uses
`e2e_private.EXPECTED` and does not read the private file.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import sys
import time
import uuid
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_eval as ee  # noqa: E402
from eval import e2e_private as ep  # noqa: E402
from eval import freeze  # noqa: E402
from eval import judge as jd  # noqa: E402
from eval.report import score_report  # noqa: E402
from vqa.llm.pricing import cost_usd, worst_case_usd  # noqa: E402
from vqa.llm.spend import SpendGuard, log_call  # noqa: E402

PROMPTS = ROOT / "eval" / "prompts" / "baseline"
DEFAULT_VERSION = "v1"
MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
OUT = ROOT / "eval" / "runs" / "e2e"
PINNED = ROOT / "eval" / "baseline_pinned.json"
ANSWERS = ROOT / "cache" / "private_run"
PURPOSE = "baseline b1"

# estimate only
IMAGE_TOKENS_MAX = 1534          # 1.15 MP / 750: prepare() never sends more
EXPECTED_OUTPUT_TOKENS = 700     # short answer + adaptive thinking at medium (rough)
QUESTION_TOKENS = 80
JUDGE_PER_ANSWER = ep.RATES_48["judge_per_answer"]
ANSWER_FIELDS = ("custom_id", "id", "text", "status")   # model outputs only (P6 scoring sheet)


# ---------------------------------------------------------------- prompt

@lru_cache(maxsize=4)
def config(version: str = DEFAULT_VERSION) -> dict[str, Any]:
    return yaml.safe_load((PROMPTS / version / "config.yaml").read_text(encoding="utf-8"))


def system_prompt(version: str = DEFAULT_VERSION) -> str:
    return (PROMPTS / version / "spec.md").read_text(encoding="utf-8").strip()


def prompt_hash(version: str = DEFAULT_VERSION) -> str:
    text = system_prompt(version) + "\n--config--\n" + (PROMPTS / version / "config.yaml").read_text("utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_id(version: str = DEFAULT_VERSION) -> str:
    return f"baseline/{version}@{prompt_hash(version)[:12]}"


def model_id(name: str) -> str:
    if name not in MODELS:
        raise SystemExit(f"model must be one of {', '.join(MODELS)}")
    return MODELS[name]


def custom_id(n: int) -> str:
    return f"q{n:04d}"


def user_content(image_bytes: bytes, question: str) -> list[dict[str, Any]]:
    from vqa.perception.image import prepare

    return [prepare(image_bytes).content_block(), {"type": "text", "text": f"Câu hỏi: {question.strip()}"}]


def request(n: int, question: str, image_bytes: bytes, model: str, version: str = DEFAULT_VERSION) -> dict:
    cfg = config(version)
    return {"custom_id": custom_id(n), "params": {
        "model": model, "max_tokens": int(cfg["max_tokens"]), "system": system_prompt(version),
        "messages": [{"role": "user", "content": user_content(image_bytes, question)}],
        "output_config": {"effort": cfg["effort"]}}}


def ids_hash(qs: list[dict]) -> str:
    return hashlib.sha256("\n".join(q["id"] for q in qs).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- estimate (no call)

def rough_tokens(text: str) -> int:
    return int(len(text.encode("utf-8")) / 3.5) + 1


def estimate(model: str, n: int, nqa: int, version: str = DEFAULT_VERSION) -> dict[str, Any]:
    cfg = config(version)
    prompt = rough_tokens(system_prompt(version)) + QUESTION_TOKENS + IMAGE_TOKENS_MAX
    expected = n * cost_usd(model, input_tokens=prompt, output_tokens=EXPECTED_OUTPUT_TOKENS, batch=True)
    worst = batch_worst_case(model, n, version)
    judge = nqa * JUDGE_PER_ANSWER
    return {"model": model, "prompt_id": prompt_id(version), "requests": n, "natural_qa": nqa,
            "prompt_tokens_per_request": prompt, "expected_output_tokens_per_request": EXPECTED_OUTPUT_TOKENS,
            "batch_expected_usd": round(expected, 3), "batch_range_usd": [round(0.6 * expected, 3),
                                                                          round(1.6 * expected, 3)],
            "batch_worst_case_usd": round(worst, 2),
            "min_max_spend_usd": math.ceil(worst * 10) / 10,
            "judge_expected_usd": round(judge, 3),
            "total_expected_usd": round(expected + judge, 2),
            "note": "rough: image tokens at the 1.15 MP cap, output a guess; submit checks "
                    "batch_worst_case_usd against --max-spend, so pass at least min_max_spend_usd"}


# ---------------------------------------------------------------- the batch

def batch_worst_case(model: str, n: int, version: str = DEFAULT_VERSION) -> float:
    """Every request at max_tokens, with the rough prompt count padded by 30%. The
    estimate and the submit's spend check both use this, so they agree."""
    cfg = config(version)
    prompt = rough_tokens(system_prompt(version)) + QUESTION_TOKENS + IMAGE_TOKENS_MAX
    return n * worst_case_usd(model, int(prompt * 1.3), int(cfg["max_tokens"]), batch=True)


def worst_case(model: str, reqs: list[dict], version: str = DEFAULT_VERSION) -> float:
    return batch_worst_case(model, len(reqs), version)


def build_requests(qs: list[dict], image_path: Callable[[str], Path], model: str,
                   version: str = DEFAULT_VERSION) -> list[dict]:
    return [request(n, q["question"], Path(image_path(q["image_id"])).read_bytes(), model, version)
            for n, q in enumerate(qs, 1)]


def create_batch(sdk, reqs: list[dict]) -> str:
    return sdk.messages.batches.create(requests=reqs).id


def batch_status(sdk, batch_id: str, wait: bool = False) -> str:
    while True:
        status = sdk.messages.batches.retrieve(batch_id).processing_status
        if status == "ended" or not wait:
            return status
        time.sleep(60)


def read_results(sdk, batch_id: str, model: str, run_id: str) -> tuple[dict[str, dict], float]:
    """{custom_id: {"text", "status"}} and the batch's cost. Every result is logged
    (no question id: custom ids only stay in memory)."""
    out, total = {}, 0.0
    for res in sdk.messages.batches.results(batch_id):
        kind = res.result.type
        if kind != "succeeded":
            out[res.custom_id] = {"text": "", "status": kind}
            continue
        msg = res.result.message
        u = msg.usage
        usage = {"input_tokens": u.input_tokens or 0, "output_tokens": u.output_tokens or 0,
                 "cache_read_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
                 "cache_write_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0}
        cost = cost_usd(model, batch=True, **usage)
        total += cost
        status = {"refusal": "refusal", "max_tokens": "max_tokens"}.get(msg.stop_reason, "ok")
        text = "\n".join(b.text for b in msg.content if b.type == "text").strip() if status == "ok" else ""
        log_call({"run_id": run_id, "purpose": PURPOSE, "model": model, "batch": True, "status": status,
                  "stop_reason": msg.stop_reason, **usage, "cost_usd": round(cost, 6)})
        out[res.custom_id] = {"text": text, "status": status}
    return out, total


def make_judge(guard: SpendGuard, sdk=None):
    from vqa.llm.client import LLMClient

    return jd.Judge(llm=LLMClient(model=jd.config()["model"], guard=guard, sdk=sdk))


def grade_all(qs: list[dict], answers: dict[str, dict], judge) -> list[dict]:
    """One graded record per question, in question order. A missing or failed answer
    is graded on an empty text (wrong)."""
    out = []
    for n, q in enumerate(qs, 1):
        a = answers.get(custom_id(n), {"text": "", "status": "missing"})
        rec = {"id": q["id"], "image_id": q["image_id"], "question_type": q["question_type"],
               "text": a["text"], "status": a["status"]}
        if q["question_type"] != "Yes/No" and not a["text"].strip():
            rec.update(correct=0.0, strict=0.0, judge_label="wrong", judge_cost_usd=0.0)
        else:
            rec.update(ee.grade(q, a["text"], judge))
        out.append(rec)
    return out


def aggregate(records: list[dict], split: str, duplicates: dict | None = None) -> dict[str, Any]:
    graded = [r for r in records if r.get("correct") is not None]
    yn = [r for r in graded if r["question_type"] == "Yes/No"]
    nq = [r for r in graded if r["question_type"] != "Yes/No"]

    def group(rs: list[dict]) -> dict[str, Any]:
        return {"n": len(rs), "score": ee._mean([r["correct"] for r in rs]),
                "strict": ee._mean([r["strict"] for r in rs])}

    feats = {k: group([r for r in graded if k in r.get("features", ())]) for k in ep.FEATURES}
    feats["no_feature"] = group([r for r in graded if not r.get("features")])
    return {"questions": len(records), "overall": ee._mean([r["correct"] for r in graded]),
            "overall_strict": ee._mean([r["strict"] for r in graded]),
            "yes_no_accuracy": ee._mean([r["correct"] for r in yn]), "yes_no_n": len(yn),
            "yes_no_unmapped": sum(r.get("yes_no_pred") is None for r in yn),
            "natural_qa_score": ee._mean([r["correct"] for r in nq]),
            "natural_qa_strict": ee._mean([r["strict"] for r in nq]), "natural_qa_n": len(nq),
            "judge_labels": dict(Counter(r.get("judge_label") for r in nq)),
            "answer_status": dict(Counter(r["status"] for r in records)),
            "by_images": score_report([{"image_id": r["image_id"], "correct": r["correct"]} for r in graded],
                                      split, duplicates),
            "by_feature": feats,
            "judge_usd": round(sum(r.get("judge_cost_usd") or 0.0 for r in records), 4)}


# ---------------------------------------------------------------- public_dev

def submit_dev(model_name: str, max_spend: float, *, sdk=None, questions: list[dict] | None = None,
               image_path=None, out_dir: Path = OUT, version: str = DEFAULT_VERSION) -> Path:
    model = model_id(model_name)
    qs = questions if questions is not None else ee.load_dev()
    from eval import gold_signs as gs
    image_path = image_path or (lambda i: gs.image_path(i, "public_dev"))
    reqs = build_requests(qs, image_path, model, version)
    SpendGuard(max_spend).check(worst_case(model, reqs, version), "baseline B1 batch (public_dev)")
    if sdk is None:
        import anthropic
        sdk = anthropic.Anthropic()
    run_id = uuid.uuid4().hex[:12]
    batch_id = create_batch(sdk, reqs)
    out_dir.mkdir(parents=True, exist_ok=True)
    state = out_dir / f"b1_dev_{model_name}_{run_id}.state.json"
    state.write_text(json.dumps({"split": "public_dev", "run_id": run_id, "batch_id": batch_id, "model": model,
                                 "model_name": model_name, "prompt_id": prompt_id(version), "version": version,
                                 "questions": [q["id"] for q in qs],
                                 "submitted": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
                                indent=2) + "\n", encoding="utf-8")
    print(f"submitted batch {batch_id} ({len(reqs)} requests) -> {state}")
    return state


def collect_dev(state_file: Path, max_spend: float, *, sdk=None, questions: list[dict] | None = None,
                wait: bool = False) -> Path | None:
    st = json.loads(Path(state_file).read_text(encoding="utf-8"))
    if sdk is None:
        import anthropic
        sdk = anthropic.Anthropic()
    if (status := batch_status(sdk, st["batch_id"], wait)) != "ended":
        print(f"batch {st['batch_id']} is {status}; run collect again later")
        return None
    by_id = {q["id"]: q for q in (questions if questions is not None else ee.load_dev())}
    qs = [by_id[i] for i in st["questions"]]
    answers, batch_cost = read_results(sdk, st["batch_id"], st["model"], st["run_id"])
    guard = SpendGuard(max_spend)
    records = grade_all(qs, answers, make_judge(guard, sdk))
    for r, q in zip(records, qs):
        r["features"] = ep.features(q["question"])
    rep = aggregate(records, "public")
    head = {"kind": "header", "what": "baseline B1 on public_dev", **{k: st[k] for k in
            ("run_id", "batch_id", "model", "prompt_id", "version")},
            "batch_usd": round(batch_cost, 4), "summary": rep}
    out = Path(state_file).with_name(Path(state_file).name.replace(".state.json", ".jsonl"))
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(head, ensure_ascii=False) + "\n")
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({k: rep[k] for k in ("questions", "overall", "overall_strict", "yes_no_accuracy",
                                          "natural_qa_score", "answer_status", "judge_labels")}, indent=2))
    print(f"batch ${batch_cost:.4f}, judge ${guard.spent:.4f} -> {out}")
    return out


# ---------------------------------------------------------------- pin

def pin(version: str, *, pinned: Path = PINNED, git=freeze.git_state) -> Path:
    if Path(pinned).exists():
        raise SystemExit(f"{Path(pinned).name} exists: the baseline prompt is pinned once")
    rec = {"what": "baseline B1 prompt, fixed on public_dev before any private result (phase 5, item 2)",
           "version": version, "prompt_id": prompt_id(version), "prompt_sha256": prompt_hash(version),
           "git_commit": git()["commit"], "pinned": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    Path(pinned).write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    print(f"pinned {rec['prompt_id']} -> {pinned}")
    return Path(pinned)


# ---------------------------------------------------------------- private, once per model

def sentinel_path(model_name: str, root: Path = ROOT / "eval") -> Path:
    return Path(root) / f"baseline_ran_b1_{model_name}.json"


def private_guards(model_name: str, *, sentinel: Path, out_dir: Path, pinned: Path, answers_root: Path,
                   git=freeze.git_state, ignored=ep.git_ignores) -> tuple[dict, dict]:
    g = git()
    if not g["clean"]:
        raise SystemExit("the git working tree is not clean: commit or remove these first:\n  "
                         + "\n  ".join(g["dirty"]))
    if not Path(pinned).exists():
        raise SystemExit("no pinned baseline prompt: fix it on public_dev, then run `pin`")
    pin_rec = json.loads(Path(pinned).read_text(encoding="utf-8"))
    if prompt_id(pin_rec["version"]) != pin_rec["prompt_id"]:
        raise SystemExit(f"the baseline prompt {pin_rec['version']} changed since it was pinned")
    if Path(sentinel).exists():
        raise SystemExit(f"baseline B1 ({model_name}) has already run on private ({Path(sentinel).name}); "
                         "it runs once")
    if Path(out_dir).exists() and any(Path(out_dir).glob(f"b1_private_aggregate_{model_name}_*.json")):
        raise SystemExit(f"a B1 ({model_name}) private aggregate already exists in {out_dir}; it runs once")
    if not ignored(Path(answers_root) / "probe"):
        raise SystemExit(f"git does not ignore {answers_root}: the private answers must stay local")
    return g, pin_rec


def submit_private(model_name: str, max_spend: float, *, confirm_pinned: bool = False, sdk=None,
                   questions: list[dict] | None = None, image_path=None, sentinel: Path | None = None,
                   out_dir: Path = OUT, pinned: Path = PINNED, answers_root: Path = ANSWERS,
                   git=freeze.git_state, ignored=ep.git_ignores, expected: dict | None = ep.EXPECTED) -> Path:
    if not confirm_pinned:
        raise SystemExit("baseline B1 runs once on private, with the pinned prompt: pass --confirm-pinned")
    model = model_id(model_name)
    sentinel = Path(sentinel or sentinel_path(model_name))
    g, pin_rec = private_guards(model_name, sentinel=sentinel, out_dir=out_dir, pinned=pinned,
                                answers_root=answers_root, git=git, ignored=ignored)
    image_path = image_path or ep.image_file
    qs = questions if questions is not None else ep.load_questions(with_answers=False)
    counts = ep.preflight(qs, image_path, expected=expected)
    version = pin_rec["version"]
    reqs = build_requests(qs, image_path, model, version)
    worst = worst_case(model, reqs, version)
    SpendGuard(max_spend).check(worst, f"baseline B1 batch (private, {model_name})")
    if sdk is None:
        import anthropic
        sdk = anthropic.Anthropic()
    run_id = uuid.uuid4().hex[:12]
    mark = {"what": f"baseline B1 ({model_name}) on private, once (phase 5, item 2); its existence blocks a "
                    "second run", "run_id": run_id, "model": model, "prompt_id": pin_rec["prompt_id"],
            "version": version, "git_commit": g["commit"], "questions_order_sha256": ids_hash(qs), **counts,
            "max_spend_usd": max_spend, "batch_worst_case_usd": round(worst, 2), "status": "started",
            "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    sentinel.write_text(json.dumps(mark, indent=2) + "\n", encoding="utf-8")
    mark.update(batch_id=create_batch(sdk, reqs), status="submitted")
    sentinel.write_text(json.dumps(mark, indent=2) + "\n", encoding="utf-8")
    print(f"submitted batch {mark['batch_id']} ({len(reqs)} requests); sentinel {sentinel.name}")
    return sentinel


def collect_private(model_name: str, max_spend: float, *, sdk=None, questions: list[dict] | None = None,
                    sentinel: Path | None = None, out_dir: Path = OUT, answers_root: Path = ANSWERS,
                    wait: bool = False, duplicates: dict | None = None) -> Path | None:
    sentinel = Path(sentinel or sentinel_path(model_name))
    if not sentinel.exists():
        raise SystemExit(f"no {sentinel.name}: submit the private batch first")
    mark = json.loads(sentinel.read_text(encoding="utf-8"))
    if mark.get("status") != "submitted":
        raise SystemExit(f"{sentinel.name} is {mark.get('status')}, not submitted")
    if sdk is None:
        import anthropic
        sdk = anthropic.Anthropic()
    if (status := batch_status(sdk, mark["batch_id"], wait)) != "ended":
        print(f"batch {mark['batch_id']} is {status}; run collect-private again later")
        return None
    qs = questions if questions is not None else ep.load_questions()
    if ids_hash(qs) != mark["questions_order_sha256"]:
        raise SystemExit("the private questions are not in the order the batch was built from")
    answers, batch_cost = read_results(sdk, mark["batch_id"], mark["model"], mark["run_id"])
    keep = Path(answers_root) / f"b1_{model_name}_{mark['run_id']}"
    keep.mkdir(parents=True, exist_ok=True)
    with open(keep / "answers.jsonl", "w", encoding="utf-8") as f:
        for n, q in enumerate(qs, 1):
            a = answers.get(custom_id(n), {"text": "", "status": "missing"})
            row = {"custom_id": custom_id(n), "id": q["id"], "text": a["text"], "status": a["status"]}
            f.write(json.dumps({k: row[k] for k in ANSWER_FIELDS}, ensure_ascii=False) + "\n")
    guard = SpendGuard(max_spend)
    records = grade_all(qs, answers, make_judge(guard, sdk))
    for r, q in zip(records, qs):
        r["features"] = ep.features(q["question"])
    keep_fields = ("image_id", "question_type", "correct", "strict", "judge_label", "judge_cost_usd",
                   "status", "yes_no_pred", "features")
    records = [{k: r.get(k) for k in keep_fields} for r in records]
    del answers, qs
    report = {"what": f"baseline B1 ({model_name}) on private, aggregate only (phase 5, item 2)",
              **{k: mark[k] for k in ("run_id", "model", "prompt_id", "version", "git_commit", "questions",
                                      "images", "question_types", "started")},
              "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "batch_usd": round(batch_cost, 4), "judge_model": jd.config()["model"],
              "judge_prompt_id": jd.prompt_id(), **aggregate(records, ep.SPLIT, duplicates)}
    report["spent_usd"] = round(batch_cost + guard.spent, 4)
    records.clear()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"b1_private_aggregate_{model_name}_{mark['run_id']}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    mark.update(status="finished", finished=report["finished"], report=out.name, spent_usd=report["spent_usd"])
    sentinel.write_text(json.dumps(mark, indent=2) + "\n", encoding="utf-8")
    print(f"aggregate report -> {out}")
    return out


# ---------------------------------------------------------------- cli

def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estimate")
    e.add_argument("--split", choices=["dev", "private"], required=True)
    e.add_argument("--model", choices=sorted(MODELS), default="sonnet")
    e.add_argument("--version", default=DEFAULT_VERSION)
    s = sub.add_parser("submit")
    s.add_argument("--split", choices=["dev", "private"], required=True)
    s.add_argument("--model", choices=sorted(MODELS), default="sonnet")
    s.add_argument("--version", default=DEFAULT_VERSION, help="public_dev only; private uses the pinned one")
    s.add_argument("--max-spend", type=float, required=True)
    s.add_argument("--confirm-pinned", action="store_true")
    c = sub.add_parser("collect")
    c.add_argument("state", type=Path)
    c.add_argument("--max-spend", type=float, required=True, help="the judge's cap")
    c.add_argument("--wait", action="store_true")
    cp = sub.add_parser("collect-private")
    cp.add_argument("--model", choices=sorted(MODELS), default="sonnet")
    cp.add_argument("--max-spend", type=float, required=True, help="the judge's cap")
    cp.add_argument("--wait", action="store_true")
    p = sub.add_parser("pin")
    p.add_argument("--version", required=True)
    a = ap.parse_args()
    if a.cmd == "estimate":
        if a.split == "dev":
            qs = ee.load_dev()
            n, nqa = len(qs), sum(q["question_type"] != "Yes/No" for q in qs)
        else:
            n, nqa = ep.EXPECTED["questions"], ep.EXPECTED_TYPES["Natural QA"]
        print(json.dumps(estimate(model_id(a.model), n, nqa, a.version), indent=2))
    elif a.cmd == "submit" and a.split == "dev":
        submit_dev(a.model, a.max_spend, version=a.version)
    elif a.cmd == "submit":
        submit_private(a.model, a.max_spend, confirm_pinned=a.confirm_pinned)
    elif a.cmd == "collect":
        collect_dev(a.state, a.max_spend, wait=a.wait)
    elif a.cmd == "collect-private":
        collect_private(a.model, a.max_spend, wait=a.wait)
    else:
        pin(a.version)


if __name__ == "__main__":
    main()
