"""The one private-test benchmark run (docs/plans/phase-5.md, item 1). Aggregate only.

This is the only code that names the private question file. It is the scoring code:
the private answers are read here, in memory, graded and summed, and never printed
or written (CLAUDE.md, "Dataset rules").

- **Run once, with the frozen phase-4 system exactly as is** (P11). It refuses to start
  unless:
  - `--confirm-frozen` is given;
  - the git working tree is clean;
  - the live configuration and prompt ids equal `eval/frozen_phase4.json`, with the
    perception model the record names (`eval/freeze.py`);
  - it has never run: no sentinel `eval/private_ran.json` (committed after the run)
    and no private aggregate file in the runs folder;
  - every question's image file resolves (counts only), and the file has 146 questions
    on 104 images;
  - git ignores the replay folder.
  The sentinel is written before the first call, so a run that stops part way also
  counts as the one run.
- **Fresh perception** into a new, empty scene cache under the replay folder.
- **Replay records (P4)**, local and gitignored under `cache/private_run/<run_id>/`,
  deleted at the end of phase 5: the scene cache (`scenes/`) and `records.jsonl`, one
  line per question with model outputs and the pipeline's trace only (`RECORD_FIELDS`:
  no gold answer, no grade). Only replay code reads them, and it writes aggregates only.
- **No per-question line is printed.** Each grade is kept in memory only long enough
  to sum it; the report (no question or image ids) is the only file in the runs folder.
- **The by-feature breakdown** uses `FEATURES`, keyword rules over the question text
  for the DESIGN section 8 categories. The question text is reduced to feature names
  in memory and dropped.

    .venv/bin/python eval/e2e_private.py estimate
    .venv/bin/python eval/e2e_private.py run --confirm-frozen --max-spend 3
"""

from __future__ import annotations

import argparse
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

SPLIT = "private"                          # duplicates: also in train or public (eval/report.py)
PRIVATE_DIR = pev.DATASET / "private_test data (post submission)"
PRIVATE_QA = PRIVATE_DIR / "vlsp_2025_private_test.json"
PRIVATE_IMAGES = PRIVATE_DIR / "private_test_images"
EXPECTED = {"questions": 146, "images": 104}
OUT = ROOT / "eval" / "runs" / "e2e"
SENTINEL = ROOT / "eval" / "private_ran.json"
REPLAY = ROOT / "cache" / "private_run"
CATALOGS = (ROOT / "kb" / "sign_catalog.yaml", ROOT / "kb" / "sign_catalog_meaning.yaml")

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
         "answered_by", "features")

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


def aggregate(records: list[dict]) -> dict[str, Any]:
    rep = ee.summarize(records, split=SPLIT)
    fb = [r for r in records if r.get("trigger") is not None and r.get("correct") is not None]
    rep.update(fallback_score=ee._mean([r["correct"] for r in fb]), fallback_n=len(fb),
               by_trigger=by_trigger(records), by_feature=by_feature(records))
    return rep


# ---------------------------------------------------------------- guards

def git_ignores(path: Path) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=ROOT, capture_output=True)
    return r.returncode == 0


def frozen_perception_model(frozen: Path = freeze.FROZEN) -> str:
    return freeze.load(frozen)["pipeline_config"]["perception_model"]


def guards(*, out_dir: Path = OUT, sentinel: Path = SENTINEL, frozen: Path = freeze.FROZEN,
           replay_root: Path = REPLAY, git=freeze.git_state, ignored=git_ignores) -> dict:
    """Refuses (SystemExit) unless the tree is clean, the configuration is the frozen
    one, the private test has never run and git ignores the replay folder."""
    g = git()
    if not g["clean"]:
        raise SystemExit("the git working tree is not clean: commit or remove these first:\n  "
                         + "\n  ".join(g["dirty"]))
    if d := freeze.check(frozen, frozen_perception_model(frozen)):
        raise SystemExit("the live configuration differs from the freeze record:\n  " + "\n  ".join(d))
    if Path(sentinel).exists():
        raise SystemExit(f"the private test has already run ({Path(sentinel).name}); it runs once")
    if Path(out_dir).exists() and any(Path(out_dir).glob("private_aggregate_*.json")):
        raise SystemExit(f"a private aggregate file already exists in {out_dir}; it runs once")
    if not ignored(Path(replay_root) / "probe"):
        raise SystemExit(f"git does not ignore {replay_root}: the replay records must stay local")
    return g


# ---------------------------------------------------------------- the run

def run_private(max_spend: float, *, confirm_frozen: bool = False, sdk=None, questions: list[dict] | None = None,
                out_dir: Path = OUT, image_path=None, sentinel: Path = SENTINEL, frozen: Path = freeze.FROZEN,
                replay_root: Path = REPLAY, git=freeze.git_state, ignored=git_ignores,
                expected: dict | None = EXPECTED) -> Path:
    if not confirm_frozen:
        raise SystemExit("the private test runs once, with the frozen system: pass --confirm-frozen")
    g = guards(out_dir=out_dir, sentinel=sentinel, frozen=frozen, replay_root=replay_root, git=git, ignored=ignored)
    perception_model = frozen_perception_model(frozen)
    config = freeze.live(perception_model)
    image_path = image_path or image_file
    qs = questions if questions is not None else load_questions()
    counts = preflight(qs, image_path, expected=expected)
    run_id = uuid.uuid4().hex[:12]
    replay = Path(replay_root) / run_id
    if replay.exists():
        raise SystemExit(f"the replay folder {replay} already exists")
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    mark = {"what": "the one private-test benchmark run (phase 5, item 1); its existence blocks a second run",
            "run_id": run_id, "started": started, "git_commit": g["commit"], "status": "started",
            "frozen_record_sha256": hashlib.sha256(Path(frozen).read_bytes()).hexdigest(),
            "replay_dir": f"{Path(replay_root).name}/{run_id}"}
    Path(sentinel).write_text(json.dumps(mark, indent=2) + "\n", encoding="utf-8")
    from eval.judge import Judge
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.pipeline import Pipeline, PipelineConfig

    (replay / "scenes").mkdir(parents=True)
    guard = SpendGuard(max_spend)
    records: list[dict] = []
    pipe = Pipeline(PipelineConfig(perception_model=perception_model, cache_dir=replay / "scenes", cache_only=False),
                    sdk=sdk, guard=guard)
    judge = Judge(llm=LLMClient(model="claude-opus-5-5", guard=guard, sdk=sdk))
    with open(replay / "records.jsonl", "w", encoding="utf-8") as f:
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
            rec.update(ee.grade(q, a.text, judge))
            records.append({k: rec.get(k) for k in _KEEP})
            del a, t, rec
            print(f"[{n}/{len(qs)}]  spent ${guard.spent:.4f}")        # a counter only
    report = {"what": "private test, aggregate only (phase 5, item 1)", "run_id": run_id,
              "perception_model": perception_model, **counts, "started": started,
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

# public_holdout, measured (docs/status.md, phase 4 step 6): fallback rate and cost per question.
HOLDOUT = {"fallback_rate": 0.49, "usd_per_question": 0.0127, "seconds_per_question": 39.7}


def estimate(qs: list[dict] | None = None) -> dict[str, Any]:
    qs = qs if qs is not None else load_questions(with_answers=False)
    n, images = len(qs), len({q["image_id"] for q in qs})
    nqa = sum(q["question_type"] != "Yes/No" for q in qs)
    c, fr = ee.COST, HOLDOUT["fallback_rate"]
    lines = {"perception, Haiku + re-run + scene fallback, per image": images * c["perception_haiku_fb"],
             "parser, Sonnet, per question": n * c["parser"],
             "answer writer, Haiku, rules share": n * (1 - fr) * c["writer"],
             "answer fallback, Sonnet, fallback share": n * fr * c["fallback"],
             "judge, Opus, Natural QA": nqa * c["judge"]}
    total = sum(lines.values())
    return {"questions": n, "images": images, "natural_qa": nqa,
            "lines_usd": {k: round(v, 3) for k, v in lines.items()}, "total_usd": round(total, 2),
            "holdout_rate_usd": round(n * HOLDOUT["usd_per_question"], 2),
            "range_usd_pm50": [round(0.5 * total, 2), round(1.5 * total, 2)],
            "minutes": round(n * HOLDOUT["seconds_per_question"] / 60)}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estimate")
    r = sub.add_parser("run")
    r.add_argument("--confirm-frozen", action="store_true")
    r.add_argument("--max-spend", type=float, required=True)
    a = ap.parse_args()
    if a.cmd == "estimate":
        print(json.dumps(estimate(), indent=2, ensure_ascii=False))
    else:
        run_private(a.max_spend, confirm_frozen=a.confirm_frozen)


if __name__ == "__main__":
    main()
