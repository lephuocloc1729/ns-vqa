"""The phase-4.5 validation runs (docs/plans/phase-4.5.md, sections 4-5): aggregate only.

Two runs on the validation set (`data/splits/train_validation.json`, untouched train
questions), each once:
- `baseline`: today's frozen phase-4 system (`eval/frozen_phase4.json`), before any fix (Q4);
- `final`: the phase-4.5 freeze (`eval/frozen_phase45.json`), after the fixes.

Rules-only: the pipeline runs with the answer fallback **off**. A question is decided
when the rules answer yes, no or a value; every other question counts as wrong and is
not judged. Decided Yes/No answers are graded from the answer text (the dataset's
mapping), decided Natural QA answers by the same judge (`judge/v1`, Opus 5.5).

Guards, as the holdout's: `--confirm-frozen`; a clean git tree; the live configuration
equal to the given freeze record (with its perception model); the run has never run (a
committed sentinel `eval/validation_ran_<label>.json`, and no aggregate file for the
label); the split file's sha256 recorded; every image resolves (counts only) before the
sentinel is written. Fresh perception into a temporary cache, deleted afterwards.

No per-question line is printed or written. The report holds the three figures with
Wilson 95% CIs, counts by cause (fallback trigger), by question type, cost and time,
and the targets and floors fixed in the plan (section 4) with whether each is met.

    .venv/bin/python eval/e2e_validation.py estimate
    .venv/bin/python eval/e2e_validation.py run --label baseline --confirm-frozen --max-spend 2
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import tempfile
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_eval as ee  # noqa: E402
from eval import freeze  # noqa: E402
from eval import gold_signs as gs  # noqa: E402
from eval.make_validation_split import OUT as SPLIT_FILE  # noqa: E402
from eval.report import wilson_ci  # noqa: E402

OUT = ROOT / "eval" / "runs" / "e2e"
LABELS = {"baseline": ROOT / "eval" / "frozen_phase4.json", "final": ROOT / "eval" / "frozen_phase45.json"}
DECIDED = ("yes", "no", "value")
# docs/plans/phase-4.5.md, section 4 (owner, 2026-11-16): fixed, they don't move after any result.
TARGETS = {"decided_coverage": {"target": 0.80, "floor": 0.70},
           "accuracy_on_decided": {"target": 0.88, "floor": 0.85},
           "overall_non_decided_wrong": {"target": 0.70, "floor": 0.60}}
_KEEP = ("question_type", "decided", "correct", "strict", "trigger", "cost_usd", "judge_cost_usd", "seconds")


def sentinel(label: str) -> Path:
    return ROOT / "eval" / f"validation_ran_{label}.json"


def load_questions(split_file: Path = SPLIT_FILE, qa_file: Path | None = None, *, with_answers: bool = True) -> list[dict]:
    ids = set(json.loads(Path(split_file).read_text(encoding="utf-8"))["questions"])
    keep = ("id", "question", "image_id", "question_type") + (("answer",) if with_answers else ())
    rows = json.loads(Path(qa_file or gs.TRAIN_QA).read_text(encoding="utf-8"))
    out = [{k: q[k] for k in keep} for q in rows if q["id"] in ids]
    if len(out) != len(ids):
        raise SystemExit(f"{len(ids) - len(out)} validation question ids are not in the train file")
    return out


def image_file(image_id: str) -> Path:
    return gs.image_path(image_id, "train")


def aggregate(records: list[dict]) -> dict[str, Any]:
    n = len(records)
    dec = [r for r in records if r["decided"]]
    graded = [r for r in dec if r["correct"] is not None]
    right = sum(r["correct"] for r in graded)
    right_strict = sum(r["strict"] for r in graded)
    by_type = {}
    for t in sorted({r["question_type"] for r in records}):
        rs = [r for r in records if r["question_type"] == t]
        ds = [r for r in rs if r["decided"] and r["correct"] is not None]
        by_type[t] = {"questions": len(rs), "decided": len(ds),
                      "coverage": len(ds) / len(rs) if rs else None,
                      "accuracy_on_decided": sum(r["correct"] for r in ds) / len(ds) if ds else None,
                      "overall_non_decided_wrong": sum(r["correct"] for r in ds) / len(rs) if rs else None}
    figs = {"questions": n, "decided": len(dec),
            "decided_coverage": len(dec) / n if n else None,
            "decided_coverage_ci95": list(wilson_ci(len(dec), n)) if n else None,
            "accuracy_on_decided": right / len(graded) if graded else None,
            "accuracy_on_decided_ci95": list(wilson_ci(right, len(graded))) if graded else None,
            "accuracy_on_decided_strict": right_strict / len(graded) if graded else None,
            "overall_non_decided_wrong": right / n if n else None,
            "overall_non_decided_wrong_ci95": list(wilson_ci(right, n)) if n else None,
            "not_decided_by_cause": dict(Counter(r["trigger"] or "decided_but_not_yes_no_value"
                                                 for r in records if not r["decided"])),
            "judge_labels": dict(Counter(r.get("judge_label") for r in dec if r["question_type"] != "Yes/No")),
            "by_question_type": by_type,
            "duplicates": "none: the pool excludes images duplicated with public, private or excluded train images",
            "cost_per_question_usd": sum((r.get("cost_usd") or 0) + (r.get("judge_cost_usd") or 0) for r in records) / n
            if n else None,
            "seconds_per_question": sum(r.get("seconds") or 0 for r in records) / n if n else None}
    figs["targets"] = {k: {**v, "measured": figs[k],
                           "target_met": figs[k] is not None and figs[k] >= v["target"],
                           "floor_met": figs[k] is not None and figs[k] >= v["floor"]} for k, v in TARGETS.items()}
    return figs


def guards(label: str, *, frozen: Path, out_dir: Path = OUT, sentinel_path: Path | None = None,
           git=freeze.git_state) -> dict:
    if label not in LABELS:
        raise SystemExit(f"--label must be one of {sorted(LABELS)}")
    g = git()
    if not g["clean"]:
        raise SystemExit("the git working tree is not clean: commit or remove these first:\n  " + "\n  ".join(g["dirty"]))
    pm = freeze.load(frozen)["pipeline_config"]["perception_model"]
    if d := freeze.check(frozen, pm):
        raise SystemExit("the live configuration differs from the freeze record:\n  " + "\n  ".join(d))
    s = sentinel_path or sentinel(label)
    if s.exists():
        raise SystemExit(f"the {label} validation run has already run ({s.name}); it runs once")
    if Path(out_dir).exists() and any(Path(out_dir).glob(f"validation_aggregate_{label}_*.json")):
        raise SystemExit(f"a {label} validation aggregate file already exists in {out_dir}; it runs once")
    return {**g, "perception_model": pm}


def run_validation(label: str, max_spend: float, *, confirm_frozen: bool = False, sdk=None,
                   questions: list[dict] | None = None, out_dir: Path = OUT, image_path=None,
                   frozen: Path | None = None, sentinel_path: Path | None = None, split_file: Path = SPLIT_FILE,
                   git=freeze.git_state) -> Path:
    if not confirm_frozen:
        raise SystemExit("a validation run runs once, with a frozen system: pass --confirm-frozen")
    frozen = frozen or LABELS.get(label)
    if frozen is None:
        raise SystemExit(f"--label must be one of {sorted(LABELS)}")
    g = guards(label, frozen=frozen, out_dir=out_dir, sentinel_path=sentinel_path, git=git)
    image_path = image_path or image_file
    qs = questions if questions is not None else load_questions(split_file)
    missing = 0
    for i in {q["image_id"] for q in qs}:
        try:
            if not Path(image_path(i)).exists():
                missing += 1
        except (FileNotFoundError, KeyError):
            missing += 1
    if missing:
        raise SystemExit(f"{missing} validation images have no file")
    config = freeze.live(g["perception_model"])
    run_id = uuid.uuid4().hex[:12]
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    s = sentinel_path or sentinel(label)
    mark = {"what": f"the one {label} validation run (phase 4.5); its existence blocks a second run",
            "run_id": run_id, "started": started, "git_commit": g["commit"], "status": "started",
            "frozen_record": Path(frozen).name,
            "frozen_record_sha256": hashlib.sha256(Path(frozen).read_bytes()).hexdigest(),
            "split_sha256": hashlib.sha256(Path(split_file).read_bytes()).hexdigest()}
    s.write_text(json.dumps(mark, indent=2) + "\n", encoding="utf-8")
    from eval.judge import Judge
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.pipeline import Pipeline, PipelineConfig

    guard = SpendGuard(max_spend)
    records: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="vqa_validation_cache_") as tmp:
        pipe = Pipeline(PipelineConfig(perception_model=g["perception_model"], cache_dir=Path(tmp),
                                       cache_only=False, answer_fallback=False), sdk=sdk, guard=guard)
        judge = Judge(llm=LLMClient(model="claude-opus-5-5", guard=guard, sdk=sdk))
        for n, q in enumerate(qs, 1):
            a = pipe.answer(image_path(q["image_id"]), q["question"])
            t = a.trace
            engine_verdict = (t.get("engine") or {}).get("verdict")
            decided = t["fallback"]["trigger"] is None and engine_verdict in DECIDED
            rec = {"question_type": q["question_type"], "decided": decided, "trigger": t["fallback"]["trigger"],
                   "cost_usd": a.cost_usd, "seconds": a.seconds, "correct": None, "strict": None}
            if decided:
                rec.update(ee.grade(q, a.text, judge))
            records.append({k: rec.get(k) for k in _KEEP + ("judge_label",)})
            del a, t, rec
            print(f"[{n}/{len(qs)}]  spent ${guard.spent:.4f}")          # a counter only
    report = {"what": f"phase-4.5 validation, {label}, aggregate only, fallback off", "run_id": run_id,
              "label": label, "started": started,
              "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "git_commit": g["commit"], "frozen_record": Path(frozen).name, "frozen_config": config,
              "prompt_ids": {k: v["id"] for k, v in config["prompts"].items()},
              "split_sha256": mark["split_sha256"], "spent_usd": round(guard.spent, 4), **aggregate(records)}
    records.clear()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"validation_aggregate_{label}_{run_id}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    mark.update(status="finished", finished=report["finished"], report=out.name, spent_usd=report["spent_usd"])
    s.write_text(json.dumps(mark, indent=2) + "\n", encoding="utf-8")
    print(f"aggregate report -> {out}")
    return out


# ---------------------------------------------------------------- estimate (no call)

# public_holdout, measured: decided coverage 51% (phase 4, step 6).
DECIDED_SHARE = 0.51


def estimate(split_file: Path = SPLIT_FILE) -> dict[str, Any]:
    qs = load_questions(split_file, with_answers=False)
    n, images = len(qs), len({q["image_id"] for q in qs})
    nqa = sum(q["question_type"] != "Yes/No" for q in qs)
    c = ee.COST
    parser = ee._measured_parser_cost() or c["parser"]
    lines = {"perception, Haiku + re-run + scene fallback, per image": images * c["perception_haiku_fb"],
             "parser, Sonnet, per question (measured mean)": n * parser,
             "answer writer, Haiku, decided share": n * DECIDED_SHARE * c["writer"],
             "judge, Opus, decided Natural QA": nqa * DECIDED_SHARE * c["judge"],
             "answer fallback": 0.0}
    total = sum(lines.values())
    return {"questions": n, "images": images, "natural_qa": nqa, "decided_share_assumed": DECIDED_SHARE,
            "lines_usd": {k: round(v, 3) for k, v in lines.items()}, "total_usd": round(total, 2),
            "if_every_question_is_decided_usd": round(total + n * (1 - DECIDED_SHARE) * c["writer"]
                                                      + nqa * (1 - DECIDED_SHARE) * c["judge"], 2),
            "range_usd_pm50": [round(0.5 * total, 2), round(1.5 * total, 2)],
            "minutes_approx": round(n * 30 / 60)}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estimate")
    r = sub.add_parser("run")
    r.add_argument("--label", required=True, choices=sorted(LABELS))
    r.add_argument("--confirm-frozen", action="store_true")
    r.add_argument("--max-spend", type=float, required=True)
    a = ap.parse_args()
    if a.cmd == "estimate":
        print(json.dumps(estimate(), indent=2))
    else:
        run_validation(a.label, a.max_spend, confirm_frozen=a.confirm_frozen)


if __name__ == "__main__":
    main()
