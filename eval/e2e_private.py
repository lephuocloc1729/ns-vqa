"""The private-test benchmark runs (docs/plans/phase-5.md, item 1). Aggregate only.

This is the only code that names the private question file. It is the scoring code:
the private answers are read here, in memory, graded and summed, and never printed
or written (CLAUDE.md, "Dataset rules").

- **Run once, with the frozen phase-4 system exactly as is** (P11). It refuses to start
  unless:
  - `--confirm-frozen` is given;
  - the git working tree is clean;
  - the live configuration and prompt ids equal `eval/frozen_phase45.json` (from B5 on; it was `frozen_phase4.json`), with the
    perception model the record names (`eval/freeze.py`);
  - it has never run: no sentinel `eval/private_ran.json` (committed after the run)
    and no private aggregate file in the runs folder;
  - every question's image file resolves (counts only), and the file has 146 questions
    on 104 images;
  - git ignores the replay folder.
  The sentinel is written before the first call, so a run that stops part way also
  counts as the one run.
- **Three runs in all (owner, 2026-11-21)**, for the mean and spread: perception, parsing and the
  writer are Claude calls whose output varies from run to run. Run 1 is the run above
  (`eval/private_ran.json`, unchanged). `--run 2` and `--run 3` each have their own sentinel
  (`eval/private_ran_2.json`, `eval/private_ran_3.json`), run id, replay folder, fresh scene cache and
  aggregate file, with the same frozen phase52 record and every guard above. A run refuses unless every
  earlier run has finished on the same freeze record, its own sentinel does not exist, and every private
  aggregate file present belongs to an earlier run. Nothing is tuned between runs, and all three are
  reported, never the best one.
- **Fresh perception** into a new, empty scene cache under the replay folder.
- **Answer fallback off** (owner, 2026-11-20, `docs/plans/rag-fallback.md`): non-decided questions get
  the engine's template answer; the RAG fallback is merged in afterwards (`eval/e2e_private_rag.py`).
- **Replay records (P4)**, local and gitignored under `cache/private_run/<run_id>/`,
  deleted at the end of phase 5: the scene cache (`scenes/`) and `records.jsonl`, one
  line per question with model outputs and the pipeline's trace only (`RECORD_FIELDS`:
  no gold answer, no grade). Only replay code reads them, and it writes aggregates only.
- **The owner's grading sheet** (`owner_grading.csv` in the same gitignored folder; owner, 2026-11-20, P6):
  one row per question with the question, gold answer, the system's answer and the judge's grade, for
  the owner's hand grading only. The assistant never reads it; nothing from it is printed.
- **No per-question line is printed.** Each grade is kept in memory only long enough
  to sum it; the report (no question or image ids) is the only file in the runs folder.
- **The by-feature breakdown** uses `FEATURES`, keyword rules over the question text
  for the DESIGN section 8 categories. The question text is reduced to feature names
  in memory and dropped.

- **Rules-only figures (phase 4.6 step 2):** `rules_only` in the report gives decided coverage,
  accuracy on decided and overall with non-decided counted wrong (95% CIs), by question type,
  and on all, non-duplicate and duplicate images (duplicate: also in train or public).
- **The estimate** uses counts only (146 questions, 104 images, 76 Natural QA, from DESIGN.md)
  and phase-4.5 measured stage rates calibrated to the final validation; it does not read the
  private file.

    .venv/bin/python eval/e2e_private.py estimate
    .venv/bin/python eval/e2e_private.py run --confirm-frozen --max-spend 3            # run 1 (done)
    .venv/bin/python eval/e2e_private.py run --run 2 --confirm-frozen --max-spend 2.25
    .venv/bin/python eval/e2e_private.py run --run 3 --confirm-frozen --max-spend 2.25
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import hashlib
import json
import re
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_eval as ee  # noqa: E402
from eval import freeze  # noqa: E402
from eval import parser_eval as pev  # noqa: E402
from eval.report import duplicated_images, wilson_ci  # noqa: E402

SPLIT = "private"                          # duplicates: also in train or public (eval/report.py)
PRIVATE_DIR = pev.DATASET / "private_test data (post submission)"
PRIVATE_QA = PRIVATE_DIR / "vlsp_2025_private_test.json"
PRIVATE_IMAGES = PRIVATE_DIR / "private_test_images"
EXPECTED = {"questions": 146, "images": 104}
# The question-type split, from DESIGN.md's data table (70 Yes/No, 76 Natural QA), so the
# estimate needs no read of the private file.
EXPECTED_TYPES = {"Yes/No": 70, "Natural QA": 76}
DECIDED = ("yes", "no", "value")
OUT = ROOT / "eval" / "runs" / "e2e"
SENTINEL = ROOT / "eval" / "private_ran.json"
# Owner, 2026-11-21: the private test runs 3 times on the frozen phase52 setup, for the mean and
# spread. Run 1 is SENTINEL; runs 2 and 3 are the only further runs allowed.
EXTRA_RUNS = (2, 3)
REPLAY = ROOT / "cache" / "private_run"
CATALOGS = (ROOT / "kb" / "sign_catalog.yaml", ROOT / "kb" / "sign_catalog_meaning.yaml")

# The owner's grading sheet (owner, 2026-11-20; phase-5 P6): one row per question, written during the
# run into the gitignored replay folder, for the owner's hand grading only. The assistant never reads it
# and nothing from it is printed. It holds the question, the gold answer, the system's answer and the
# judge's grade, so it is kept apart from records.jsonl, which stays free of gold and grades.
OWNER_SHEET = "owner_grading.csv"
OWNER_SHEET_FIELDS = ("id", "question_type", "question", "gold_answer", "system", "system_answer",
                      "answered_by", "trigger", "auto_correct", "auto_strict", "judge_label", "judge_reason",
                      "human_score", "human_note")


def owner_sheet_row(q: dict, system: str, text: str, answered_by: str | None, trigger: str | None,
                    g: dict) -> dict:
    return {"id": q["id"], "question_type": q["question_type"], "question": q["question"],
            "gold_answer": q["answer"], "system": system, "system_answer": text, "answered_by": answered_by,
            "trigger": trigger, "auto_correct": g.get("correct"), "auto_strict": g.get("strict"),
            "judge_label": g.get("judge_label"), "judge_reason": g.get("judge_reason"),
            "human_score": "", "human_note": ""}


def open_owner_sheet(path: Path):
    """utf-8-sig so a spreadsheet opens the Vietnamese text correctly."""
    f = open(path, "w", encoding="utf-8-sig", newline="")
    w = csv.DictWriter(f, fieldnames=OWNER_SHEET_FIELDS)
    w.writeheader()
    return f, w


# Fields of a question kept from the file. The answer is read for grading only.
QUESTION_FIELDS = ("id", "question", "image_id", "question_type", "answer")
# One replay record (P4): model outputs and the pipeline's trace. Never the gold answer,
# the question text or a grade.
RECORD_FIELDS = ("id", "image_id", "question_type", "text", "verdict", "answered_by", "trigger",
                 "fallback_status", "writer_status", "engine_verdict", "parse_status",
                 "cost_usd", "seconds", "trace")
# Fields of a per-question record that the aggregate needs, in memory only. Nothing
# that identifies a question is kept, except the image id until the duplicate split
# is computed.
_KEEP = ("image_id", "question_type", "correct", "strict", "trigger", "writer_status", "verdict",
         "engine_verdict", "fallback_status", "judge_label", "cost_usd", "judge_cost_usd", "seconds",
         "answered_by", "features", "decided")

# ---------------------------------------------------------------- question features
# Keyword rules for the DESIGN section 8 categories ("What the private test asks").
# The rules behind that table were not kept, so these are new; they overlap, as the
# table's do. Matched on the lowercased question text.
FEATURES: dict[str, re.Pattern] = {k: re.compile(v) for k, v in {
    "claim": r"đúng hay sai|đúng không|phải không|đúng hay không|có đúng|đúng\s*\?|sai\s*\?",
    "vehicle_class": (r"xe máy|mô tô|xe gắn máy|ô tô|xe con|xe tải|xe khách|xe buýt|xe bus|xe đạp|"
                      r"xe ba bánh|xe lam|xích lô|thô sơ|máy kéo|xe cứu thương|xe cứu hỏa|xe ưu tiên|"
                      r"container|rơ moóc|sơ mi|xe kéo|xe chở|các loại xe|phương tiện|xe cơ giới|"
                      r"xe điện|người đi bộ"),
    "turn_stop_park_overtake": r"\brẽ\b|quay đầu|quẹo|\bdừng\b|\bđỗ\b|\bvượt\b",
    "speed": r"tốc độ|km/h|km/giờ",
    "lanes": r"\blàn\b",
    "time": (r"\d{1,2}\s*(?:h|giờ)\b|\d{1,2}:\d{2}|khung giờ|thời gian|thời điểm|\blúc\b|buổi|"
             r"\bsáng\b|\btrưa\b|\bchiều\b|\btối\b(?! đa| thiểu)|\bđêm\b|\bngày\b|"
             r"thứ (?:hai|ba|tư|năm|sáu|bảy)|chủ nhật"),
    "meaning": (r"biển (?:báo )?(?:gì|nào)|ý nghĩa|là biển|biển (?:báo )?này là|loại biển|"
                r"tên (?:của )?biển|mã biển|nhóm biển|mã gì|thuộc nhóm|có nghĩa|nghĩa là|"
                r"(?:báo hiệu|chỉ dẫn|báo trước|cho biết) (?:điều|những thông tin|thông tin) gì"),
    "weight_or_seats": r"tấn|\bkg\b|trọng tải|tải trọng|khối lượng|chỗ ngồi|\d+\s*chỗ",
    "violation": r"vi phạm|phạm luật|sai luật|trái luật",
}.items()}


def features(question: str) -> list[str]:
    q = question.lower()
    return [k for k, rx in FEATURES.items() if rx.search(q)]


# ---------------------------------------------------------------- the private questions

def load_questions(path: Path | None = None, *, with_answers: bool = True) -> list[dict]:
    """The private questions. `with_answers=False` drops the answer as the file is read
    (the estimate and the preflight need ids, types and images only)."""
    rows = json.loads(Path(path or PRIVATE_QA).read_text(encoding="utf-8"))
    keep = QUESTION_FIELDS if with_answers else tuple(f for f in QUESTION_FIELDS if f != "answer")
    out = []
    for n, q in enumerate(rows):
        if missing := [f for f in keep if f not in q]:
            raise SystemExit(f"private question row {n}: missing fields {missing}")
        out.append({k: q[k] for k in keep})
    return out


def image_file(image_id: str, folder: Path | None = None) -> Path:
    folder = folder or PRIVATE_IMAGES
    hits = sorted(Path(folder).glob(f"{glob.escape(image_id)}.*"))
    if not hits:
        raise FileNotFoundError(f"no image file for a private question in {folder}")   # no id printed
    return hits[0]


def preflight(qs: list[dict], image_path: Callable[[str], Path], *, expected: dict | None = EXPECTED) -> dict:
    """Counts and image files, before the sentinel (the first holdout start stopped on an
    image resolver). Reports counts only."""
    images = {q["image_id"] for q in qs}
    if expected is not None and (len(qs), len(images)) != (expected["questions"], expected["images"]):
        raise SystemExit(f"expected {expected['questions']} questions on {expected['images']} images, "
                         f"found {len(qs)} on {len(images)}")
    missing = 0
    for i in images:
        try:
            image_path(i)
        except FileNotFoundError:
            missing += 1
    if missing:
        raise SystemExit(f"{missing} of {len(images)} private images have no file")
    return {"questions": len(qs), "images": len(images),
            "question_types": dict(Counter(q["question_type"] for q in qs))}


# ---------------------------------------------------------------- the report

def catalog_review(paths=CATALOGS) -> dict[str, Any]:
    """Who checked the catalog rows (CLAUDE.md: only `human` counts as checked). The
    catalog is not reviewed before the private run (owner, 2026-11-16): it is frozen."""
    import yaml

    out = {}
    for p in paths:
        rows = yaml.safe_load(Path(p).read_text(encoding="utf-8"))["signs"]
        out[Path(p).name] = {
            "rows": len(rows),
            "reviewed_by": dict(Counter(str(r.get("reviewed_by") or "none") for r in rows)),
            "visual_reviewed_by": dict(Counter(str(r.get("visual_reviewed_by") or "none") for r in rows)),
        }
    out["note"] = "the catalog is mostly assistant-reviewed: only reviewed_by human counts as checked"
    return out


def _group(rs: list[dict]) -> dict[str, Any]:
    graded = [r for r in rs if r.get("correct") is not None]
    return {"n": len(rs), "score": ee._mean([r["correct"] for r in graded]),
            "strict": ee._mean([r["strict"] for r in graded]),
            "yes_no_n": sum(r["question_type"] == "Yes/No" for r in rs),
            "rule_coverage": sum(r.get("trigger") is None for r in rs) / len(rs) if rs else None}


def by_feature(records: list[dict]) -> dict[str, Any]:
    out = {k: _group([r for r in records if k in r["features"]]) for k in FEATURES}
    out["no_feature"] = _group([r for r in records if not r["features"]])
    return out


def by_trigger(records: list[dict]) -> dict[str, Any]:
    keys = sorted({r.get("trigger") or "rules" for r in records})
    return {k: _group([r for r in records if (r.get("trigger") or "rules") == k]) for k in keys}


def _rules_figs(rs: list[dict]) -> dict[str, Any]:
    """Rules-only figures (phase 4.5 requirement): a question is decided when the rules answer
    yes, no or a value; every other question counts as wrong."""
    n = len(rs)
    dec = [r for r in rs if r.get("decided")]
    graded = [r for r in dec if r.get("correct") is not None]
    right = sum(r["correct"] for r in graded)
    return {"questions": n, "decided": len(dec),
            "decided_coverage": len(dec) / n if n else None,
            "decided_coverage_ci95": list(wilson_ci(len(dec), n)) if n else None,
            "accuracy_on_decided": right / len(graded) if graded else None,
            "accuracy_on_decided_ci95": list(wilson_ci(right, len(graded))) if graded else None,
            "accuracy_on_decided_strict": (sum(r["strict"] for r in graded) / len(graded)) if graded else None,
            "overall_non_decided_wrong": right / n if n else None,
            "overall_non_decided_wrong_ci95": list(wilson_ci(right, n)) if n else None}


def rules_only(records: list[dict], duplicates: dict | None = None) -> dict[str, Any]:
    """The rules-only report, as `eval/e2e_validation.py`'s `aggregate`, plus the duplicate split
    (private: an image also in train or public, eval/report.py) with 95% CIs on non-duplicates."""
    dup = duplicated_images(SPLIT, duplicates)
    nd = [r for r in records if r["image_id"] not in dup]
    out = {**_rules_figs(records),
           "not_decided_by_cause": dict(Counter(r.get("trigger") or "decided_but_not_yes_no_value"
                                                for r in records if not r.get("decided"))),
           "by_question_type": {t: _rules_figs([r for r in records if r["question_type"] == t])
                                for t in sorted({r["question_type"] for r in records})},
           "by_images": {"split": SPLIT, "against": ["public", "train"], "all_images": _rules_figs(records),
                         "non_duplicate_images": _rules_figs(nd),
                         "duplicate_images": _rules_figs([r for r in records if r["image_id"] in dup])}}
    return out


def aggregate(records: list[dict], duplicates: dict | None = None) -> dict[str, Any]:
    rep = ee.summarize(records, split=SPLIT)
    fb = [r for r in records if r.get("trigger") is not None and r.get("correct") is not None]
    rep.update(fallback_score=ee._mean([r["correct"] for r in fb]), fallback_n=len(fb),
               by_trigger=by_trigger(records), by_feature=by_feature(records),
               rules_only=rules_only(records, duplicates))
    return rep


# ---------------------------------------------------------------- guards

def git_ignores(path: Path) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=ROOT, capture_output=True)
    return r.returncode == 0


# Phase 4.7 (owner, 2026-11-18): the private runner requires frozen_phase47.json; an older record
# (phase 4.5, phase 4.6) is refused even when it matches its own profile.
# Phase 4.8 (owner, 2026-11-18): the private test runs with frozen_phase48.json only; phase 4.7 and older
# records are refused by their profile.
# Phase 4.9 (owner, 2026-11-18): v17 replaces v16; older profiles remain refused.
# Phase 5.1 (owner, 2026-11-20): phase51 (phase50 with parser v18 and the 65bbfbb fixes) replaces phase49;
# phase49 and phase50 are refused by their profile.
# Phase 5.2 (owner, 2026-11-20): phase52 (phase51 with the lane_reserved_is fixes of 8b45e0b) replaces
# phase51, which is refused by its profile.
PRIVATE_PROFILES = ("phase52",)
# docs/plans/rag-fallback.md (owner, 2026-11-20): no Sonnet answer fallback in the private run; the RAG
# fallback is merged in from its saved answers (eval/e2e_private_rag.py).
ANSWER_FALLBACK = False


def frozen_perception_model(frozen: Path = freeze.FROZEN_PHASE52) -> str:
    return freeze.load(frozen)["pipeline_config"]["perception_model"]


def sentinel_for(run: int, base: Path = SENTINEL) -> Path:
    """Run 1's sentinel is `base` (eval/private_ran.json); run N's is private_ran_N.json beside it."""
    return Path(base) if run == 1 else Path(base).with_name(f"{Path(base).stem}_{run}{Path(base).suffix}")


def check_run_number(run: int) -> None:
    if run != 1 and run not in EXTRA_RUNS:
        raise SystemExit(f"--run must be one of {list(EXTRA_RUNS)} (run 1 is done); got {run}")


def _earlier_runs(run: int, base: Path, frozen: Path) -> set[str]:
    """Every earlier run must have finished on the same freeze record. Returns their report names."""
    sha = hashlib.sha256(Path(frozen).read_bytes()).hexdigest()
    reports = set()
    for k in range(1, run):
        p = sentinel_for(k, base)
        if not p.exists():
            raise SystemExit(f"run {k} has not run ({p.name} is missing): run {run} comes after it")
        mark = json.loads(p.read_text(encoding="utf-8"))
        if mark.get("status") != "finished":
            raise SystemExit(f"run {k} has not finished ({p.name} is {mark.get('status')!r}): "
                             f"run {run} comes after it")
        if mark.get("frozen_record_sha256") != sha:
            raise SystemExit(f"run {k} used another freeze record ({p.name}): every run uses the same one")
        if mark.get("report"):
            reports.add(mark["report"])
    return reports


def guards(*, run: int = 1, out_dir: Path = OUT, sentinel: Path = SENTINEL, frozen: Path = freeze.FROZEN_PHASE52,
           replay_root: Path = REPLAY, git=freeze.git_state, ignored=git_ignores) -> dict:
    """Refuses (SystemExit) unless the tree is clean, the configuration is the frozen
    one, this run has never run (and every earlier one has finished) and git ignores the
    replay folder. `sentinel` is run 1's; run N's is `sentinel_for(N, sentinel)`."""
    check_run_number(run)
    g = git()
    if not g["clean"]:
        raise SystemExit("the git working tree is not clean: commit or remove these first:\n  "
                         + "\n  ".join(g["dirty"]))
    if (prof := freeze.profile_of(freeze.load(frozen))) not in PRIVATE_PROFILES:
        raise SystemExit(f"the private test runs with the phase-5.2 freeze only; {Path(frozen).name} is {prof}")
    if d := freeze.check(frozen, frozen_perception_model(frozen)):
        raise SystemExit("the live configuration differs from the freeze record:\n  " + "\n  ".join(d))
    if run == 1:
        if Path(sentinel).exists():
            raise SystemExit(f"the private test has already run ({Path(sentinel).name}); "
                             f"the further runs are --run {' and --run '.join(map(str, EXTRA_RUNS))}")
        if Path(out_dir).exists() and any(Path(out_dir).glob("private_aggregate_*.json")):
            raise SystemExit(f"a private aggregate file already exists in {out_dir}; it runs once")
    else:
        mine = sentinel_for(run, sentinel)
        if mine.exists():
            raise SystemExit(f"private run {run} has already run ({mine.name}); each run runs once")
        allowed = _earlier_runs(run, Path(sentinel), Path(frozen))
        present = {p.name for p in Path(out_dir).glob("private_aggregate_*.json")} if Path(out_dir).exists() else set()
        if extra := sorted(present - allowed):
            raise SystemExit(f"a private aggregate file already exists in {out_dir} that no earlier run "
                             f"wrote ({', '.join(extra)}); run {run} runs once")
    if not ignored(Path(replay_root) / "probe"):
        raise SystemExit(f"git does not ignore {replay_root}: the replay records must stay local")
    return g


# ---------------------------------------------------------------- the run

def run_private(max_spend: float, *, run: int = 1, confirm_frozen: bool = False, sdk=None, questions: list[dict] | None = None,
                out_dir: Path = OUT, image_path=None, sentinel: Path = SENTINEL, frozen: Path = freeze.FROZEN_PHASE52,
                replay_root: Path = REPLAY, git=freeze.git_state, ignored=git_ignores,
                expected: dict | None = EXPECTED) -> Path:
    if not confirm_frozen:
        raise SystemExit("the private test runs with the frozen system: pass --confirm-frozen")
    check_run_number(run)
    g = guards(run=run, out_dir=out_dir, sentinel=sentinel, frozen=frozen, replay_root=replay_root, git=git, ignored=ignored)
    perception_model = frozen_perception_model(frozen)
    profile = freeze.profile_of(freeze.load(frozen))
    config = freeze.live(perception_model, profile)
    image_path = image_path or image_file
    qs = questions if questions is not None else load_questions()
    counts = preflight(qs, image_path, expected=expected)
    run_id = uuid.uuid4().hex[:12]
    replay = Path(replay_root) / run_id
    if replay.exists():
        raise SystemExit(f"the replay folder {replay} already exists")
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    sentinel = sentinel_for(run, sentinel)
    what = ("the one private-test benchmark run (phase 5, item 1); its existence blocks a second run" if run == 1
            else f"private-test benchmark run {run} of 3 (owner, 2026-11-21: mean and spread); "
                 f"its existence blocks a second run {run}")
    mark = {"what": what, "run": run, "run_id": run_id, "started": started, "git_commit": g["commit"], "status": "started",
            "frozen_record_sha256": hashlib.sha256(Path(frozen).read_bytes()).hexdigest(),
            "replay_dir": f"{Path(replay_root).name}/{run_id}"}
    Path(sentinel).write_text(json.dumps(mark, indent=2) + "\n", encoding="utf-8")
    from eval.judge import Judge
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.pipeline import Pipeline

    (replay / "scenes").mkdir(parents=True)
    guard = SpendGuard(max_spend)
    records: list[dict] = []
    # the record's profile (phase 4.5 from B5 on). Answer fallback off (owner, 2026-11-20,
    # docs/plans/rag-fallback.md F4): the run gives the rules-only figures, and the RAG's saved
    # answers are merged in afterwards by eval/e2e_private_rag.py.
    pipe = Pipeline(freeze.pipeline_config(profile, perception_model, cache_dir=replay / "scenes", cache_only=False,
                                           answer_fallback=ANSWER_FALLBACK), sdk=sdk, guard=guard)
    judge = Judge(llm=LLMClient(model="claude-opus-5-5", guard=guard, sdk=sdk))
    sheet_f, sheet = open_owner_sheet(replay / OWNER_SHEET)
    with sheet_f, open(replay / "records.jsonl", "w", encoding="utf-8") as f:
        for n, q in enumerate(qs, 1):
            a = pipe.answer(image_path(q["image_id"]), q["question"])
            t = a.trace
            rec = {"id": q["id"], "image_id": q["image_id"], "question_type": q["question_type"],
                   "text": a.text, "verdict": a.verdict, "answered_by": a.answered_by,
                   "trigger": t["fallback"]["trigger"], "fallback_status": t["fallback"].get("status"),
                   "writer_status": (t.get("writer") or {}).get("status"),
                   "engine_verdict": (t.get("engine") or {}).get("verdict"),
                   "parse_status": (t.get("parser") or {}).get("status"),
                   "cost_usd": a.cost_usd, "seconds": a.seconds, "trace": t}
            f.write(json.dumps({k: rec[k] for k in RECORD_FIELDS}, ensure_ascii=False, default=str) + "\n")
            f.flush()
            rec["features"] = features(q["question"])
            rec["decided"] = rec["trigger"] is None and rec["engine_verdict"] in DECIDED
            grade = ee.grade(q, a.text, judge)
            rec.update(grade)
            sheet.writerow(owner_sheet_row(q, "v1_rules_only", a.text, rec["answered_by"], rec["trigger"], grade))
            sheet_f.flush()
            records.append({k: rec.get(k) for k in _KEEP})
            del a, t, rec
            print(f"[{n}/{len(qs)}]  spent ${guard.spent:.4f}")        # a counter only
    report = {"what": "private test, aggregate only (phase 5, item 1)", "run": run, "run_id": run_id,
              "perception_model": perception_model, "answer_fallback": ANSWER_FALLBACK, **counts, "started": started,
              "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "git_commit": g["commit"], "frozen_config": config,
              "prompt_ids": {k: v["id"] for k, v in config["prompts"].items()},
              "catalog_review": catalog_review(), "feature_rules": {k: v.pattern for k, v in FEATURES.items()},
              "spent_usd": round(guard.spent, 4), **aggregate(records)}
    records.clear()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"private_aggregate_{run_id}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    mark.update(status="finished", finished=report["finished"], report=out.name, spent_usd=report["spent_usd"])
    Path(sentinel).write_text(json.dumps(mark, indent=2) + "\n", encoding="utf-8")
    print(f"aggregate report -> {out}")
    return out


# ---------------------------------------------------------------- estimate (no call)

# Phase 4.5 measured rates (phase 4.6, step 2; docs/plans/phase-4.6.md). Per stage:
# - perception v5 + scene fallback + guide call, per image: the candidate dev run (7caed6170de6);
# - parser v9, per question: the v9 gate run and the v9 dev re-parse (51 calls);
# - writer per decided answer and judge per judged Natural QA answer: the candidate dev run;
# - the fallback answer per non-decided question: the phase-4 rate (ee.COST), the last measured.
# CALIBRATION scales the sum to the final validation's measured total ($0.8329 on 110 questions,
# 54 images, 52 decided, 31 decided Natural QA, fallback off; $0.0076 per question): the stage
# rates give $0.727 there, so x1.146.
RATES = {"perception_per_image": 0.0021, "parser_per_question": 0.00396, "writer_per_decided": 0.00025,
         "judge_per_answer": 0.00533, "fallback_per_question": ee.COST["fallback"]}
CALIBRATION = 1.146
DECIDED_SHARE = 0.473          # final validation (7a3dbec997f7); dev after phase 4.6 step 1: 0.805
# Phase 4.7 (owner, 2026-11-18): the frozen phase-4.7 system. Measured: parser v14 per question, writer
# per decided answer and judge per judged answer on the judged dev run dev_phase47_d6790322b0dc (87
# questions, 73 decided: $0.4001, $0.0189, $0.4054); perception v5 + scene fallback + guide call per
# image on the candidate dev run 7caed6170de6 (60 images, $0.00193; kept at $0.0021); the fallback answer
# at the phase-4 rate. Decided share: the judged phase-4.7 candidate on dev, 73 / 87.
RATES_47 = {"perception_per_image": 0.0021, "parser_per_question": 0.0046, "writer_per_decided": 0.00026,
            "judge_per_answer": 0.00555, "fallback_per_question": ee.COST["fallback"]}
DECIDED_SHARE_47 = 0.839
# Phase 4.8 (owner, 2026-11-18): the frozen phase-4.8 system. Perception, writer and judge as RATES_47
# (perception unchanged); parser v16 per question from its gate run ($0.2216 / 47). Decided shares:
# dev 74 / 87 (dev_reparse_v16_248e38bd215e) and dev2 79 / 100 (dev2_reparse_v16_c95f3934da5c, biased).
RATES_48 = {**RATES_47, "parser_per_question": 0.0047}
DECIDED_SHARE_48 = 0.851
DECIDED_SHARE_48_DEV2 = 0.79


def estimate(qs: list[dict] | None = None, decided_share: float = DECIDED_SHARE_48,
             rates: dict[str, float] | None = None) -> dict[str, Any]:
    """Counts only. With no questions given it uses EXPECTED and EXPECTED_TYPES (DESIGN.md), so
    the private file is not read. Two figures: with the fallback off (rules only) and with it on
    (the private run's default: every non-decided question gets a fallback answer, and every
    Natural QA answer is judged)."""
    if qs is not None:
        n, images = len(qs), len({q["image_id"] for q in qs})
        nqa = sum(q["question_type"] != "Yes/No" for q in qs)
    else:
        n, images, nqa = EXPECTED["questions"], EXPECTED["images"], EXPECTED_TYPES["Natural QA"]
    r = rates or RATES_48
    off = {"perception, per image": images * r["perception_per_image"],
           "parser, per question": n * r["parser_per_question"],
           "writer, decided share": n * decided_share * r["writer_per_decided"],
           "judge, decided Natural QA": nqa * decided_share * r["judge_per_answer"]}
    on_extra = {"fallback answer, non-decided share": n * (1 - decided_share) * r["fallback_per_question"],
                "judge, non-decided Natural QA": nqa * (1 - decided_share) * r["judge_per_answer"]}
    t_off = sum(off.values()) * CALIBRATION
    t_on = (sum(off.values()) + sum(on_extra.values())) * CALIBRATION
    return {"questions": n, "images": images, "natural_qa": nqa, "decided_share_assumed": decided_share,
            "rates_usd": r, "calibration": CALIBRATION,
            "lines_usd": {k: round(v, 3) for k, v in {**off, **on_extra}.items()},
            "total_usd": round(t_on, 2), "total_fallback_off_usd": round(t_off, 2),
            "range_usd": [round(0.8 * t_on, 2), round(1.3 * t_on, 2)],
            "range_fallback_off_usd": [round(0.8 * t_off, 2), round(1.3 * t_off, 2)],
            "minutes": round(n * 17.4 / 60)}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estimate")
    r = sub.add_parser("run")
    r.add_argument("--confirm-frozen", action="store_true")
    r.add_argument("--max-spend", type=float, required=True)
    r.add_argument("--run", type=int, default=1, help="2 or 3 (owner, 2026-11-21); run 1 is done")
    a = ap.parse_args()
    if a.cmd == "estimate":
        print(json.dumps({"phase48_at_dev_decided_share": estimate(),
                          "phase48_at_dev2_decided_share": estimate(decided_share=DECIDED_SHARE_48_DEV2),
                          "phase48_at_validation_decided_share": estimate(decided_share=DECIDED_SHARE)},
                         indent=2, ensure_ascii=False))
    else:
        run_private(a.max_spend, run=a.run, confirm_frozen=a.confirm_frozen)


if __name__ == "__main__":
    main()
