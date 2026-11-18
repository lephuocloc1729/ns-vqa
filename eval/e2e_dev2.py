"""The phase-4.8 dev2 runs (owner, 2026-11-18).

dev2 (`data/splits/train_dev2.json`, built by `eval/make_dev2_split.py`) is 100 train
working-set questions, readable question by question. **It is biased** (its images are shared
with public and private, and train is the rules' source): it is used to find and fix coverage
gaps, never to report scores. The guardrail for a fix stays the original dev set.

A dev2 run is the frozen phase-4.7 system (`eval/frozen_phase47.json`, profile `phase47`: scene
v5 with the guide call, parser v14, writer v3, reading policy A, signals off) with the answer
fallback **off**, judged like a dev run (`eval/e2e_dev.run_dev`): Yes/No by the yes/no mapping,
Natural QA by the Opus judge, on decided answers only. Per-question records go to the gitignored
`eval/runs/e2e/dev2_<label>_<run_id>.jsonl`, the scene cache beside it
(`dev2_cache_<run_id>/`), so later replays and rejudges need no perception call.

Guards: dev2 shares no question or image with dev or validation; the record is profile
`phase47` and the live configuration matches it (engine-code hash included); the git tree is
clean.

    .venv/bin/python eval/e2e_dev2.py estimate
    .venv/bin/python eval/e2e_dev2.py run --label baseline --max-spend <cap>
    .venv/bin/python eval/e2e_dev2.py summary eval/runs/e2e/dev2_baseline_<run_id>.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_dev as ed  # noqa: E402
from eval import e2e_validation as ev  # noqa: E402
from eval import freeze  # noqa: E402
from eval.make_dev2_split import OUT as DEV2_OUT  # noqa: E402
from eval.make_validation_split import DEV_OUT, OUT as VALIDATION  # noqa: E402

PROFILE = "phase47"
FROZEN = freeze.FROZEN_PHASE47
# Phase 4.8 step 4: a candidate run is the phase-4.7 profile with these fields changed (the KB switches
# in kb/switches_48.yaml apply as committed). The engine has changed since the phase-4.7 record, so a
# candidate run checks the phase-4 record's frozen prompt files instead (as e2e_dev.py --candidate does).
PHASE47_FIELDS = {"scene_version": "v5", "parser_version": "v14", "guide_reading": True,
                  "reading_policy": "higher_confidence"}
# Decided shares for the estimate: the judged phase-4.7 dev run (73 of 87), and every question.
DECIDED_SHARES = {"dev_phase47": 0.839, "all_decided": 1.0}


def _ids(path: Path) -> tuple[set[str], set[str]]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return set(d["questions"]), set(d["images"])


def check_disjoint(dev2_file: Path = DEV2_OUT, dev_file: Path = DEV_OUT, validation_file: Path = VALIDATION) -> None:
    """dev2 shares no question id and no image id with dev or validation (ids only)."""
    q2, i2 = _ids(dev2_file)
    for name, f in (("dev", dev_file), ("validation", validation_file)):
        q, i = _ids(f)
        if q2 & q or i2 & i:
            raise SystemExit(f"the dev2 set overlaps the {name} set")


def load_questions(dev2_file: Path = DEV2_OUT, qa_file: Path | None = None, *, with_answers: bool = True,
                   dev_file: Path = DEV_OUT, validation_file: Path = VALIDATION) -> list[dict]:
    """dev2's questions; the overlap check runs first, so no validation text is ever loaded."""
    check_disjoint(dev2_file, dev_file, validation_file)
    return ev.load_questions(dev2_file, qa_file, with_answers=with_answers)


def candidate(scene_version: str | None = None, parser_version: str | None = None) -> dict:
    out = dict(PHASE47_FIELDS)
    if scene_version:
        out["scene_version"] = scene_version
    if parser_version:
        out["parser_version"] = parser_version
    return out


def run(label: str, max_spend: float, *, dev2_file: Path = DEV2_OUT, dev_file: Path = DEV_OUT,
        validation_file: Path = VALIDATION, frozen: Path | None = None, questions: list[dict] | None = None,
        cand: dict | None = None, **kw: Any) -> Path:
    check_disjoint(dev2_file, dev_file, validation_file)
    qs = questions if questions is not None else load_questions(dev2_file, dev_file=dev_file,
                                                                validation_file=validation_file)
    split = json.loads(Path(dev2_file).read_text(encoding="utf-8"))
    extra = {"biased": True, "biased_note": split.get("biased_note"), "split_file": Path(dev2_file).name,
             "split_sha256": hashlib.sha256(Path(dev2_file).read_bytes()).hexdigest()}
    if cand is not None:
        from vqa.reasoning.engine import switches_from_kb
        extra["switches_48"] = switches_from_kb()
        return ed.run_dev(label, max_spend, questions=qs, frozen=frozen or freeze.FROZEN, dev_file=dev2_file,
                          validation_file=validation_file, candidate=cand, prefix="dev2", head_extra=extra, **kw)
    return ed.run_dev(label, max_spend, questions=qs, frozen=frozen or FROZEN, dev_file=dev2_file,
                      validation_file=validation_file, profile=PROFILE, prefix="dev2", head_extra=extra, **kw)


def summary(path: Path) -> dict[str, Any]:
    s = ed.summary(path)
    _, rows = ed.ee.load(path)
    by_type = {}
    for t in sorted({r["question_type"] for r in rows}):
        rs = [r for r in rows if r["question_type"] == t]
        dec = [r for r in rs if r["decided"] and r["correct"] is not None]
        by_type[t] = {"questions": len(rs), "decided": sum(r["decided"] for r in rs),
                      "accuracy_on_decided": sum(r["correct"] for r in dec) / len(dec) if dec else None,
                      "overall_non_decided_wrong": sum(r["correct"] for r in dec) / len(rs) if rs else None}
    s["by_type"] = by_type
    s["biased"] = True
    s["not_decided_by_parse_status"] = dict(Counter(r.get("parse_status") for r in rows if not r["decided"]))
    return s


def estimate(dev2_file: Path = DEV2_OUT) -> dict[str, Any]:
    """Counts only (no question text): the private runner's measured phase-4.7 rates and
    calibration, with the fallback off, at two decided shares; the cap is the top of the range at
    every question decided, rounded up to 5 cents."""
    from eval import e2e_private as ep
    qs = load_questions(dev2_file, with_answers=False)
    out = {}
    for name, share in DECIDED_SHARES.items():
        e = ep.estimate(qs, decided_share=share)
        out[name] = {"decided_share": share, "total_usd": e["total_fallback_off_usd"],
                     "range_usd": e["range_fallback_off_usd"],
                     "lines_usd": {k: v for k, v in e["lines_usd"].items() if "fallback" not in k
                                   and "non-decided" not in k}}
    top = out["all_decided"]["range_usd"][1]
    return {"questions": len(qs), "images": len({q["image_id"] for q in qs}),
            "question_types": dict(Counter(q["question_type"] for q in qs)),
            "rates_usd": ep.RATES_47, "calibration": ep.CALIBRATION, "estimates": out,
            "suggested_max_spend": math.ceil(top * 20) / 20,
            "note": "fallback off; Yes/No is graded by the yes/no mapping (no judge call); writer and judge "
                    "run on decided answers only; a fresh scene cache, so every image is perceived"}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estimate")
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--max-spend", type=float, required=True)
    r.add_argument("--scene-version", help="phase 4.8 candidate: scene prompt version (default v5)")
    r.add_argument("--parser-version", help="phase 4.8 candidate: parser prompt version (default v14)")
    s = sub.add_parser("summary")
    s.add_argument("file", type=Path)
    a = ap.parse_args()
    if a.cmd == "estimate":
        print(json.dumps(estimate(), indent=2, ensure_ascii=False))
    elif a.cmd == "summary":
        print(json.dumps(summary(a.file), indent=2, ensure_ascii=False))
    else:
        cand = candidate(a.scene_version, a.parser_version) if (a.scene_version or a.parser_version) else None
        run(a.label, a.max_spend, cand=cand)


if __name__ == "__main__":
    main()
