"""eval/coverage_analysis.py helpers: the decided figures, the source of an alternative
reading, and the id patterns behind the validation pool. No API call."""

from __future__ import annotations

import eval.coverage_analysis as ca


def test_decided_summary_counts_non_decided_as_wrong():
    rows = [{"image_id": "a", "decided": True, "correct": 1.0},
            {"image_id": "b", "decided": True, "correct": 0.5},
            {"image_id": "c", "decided": False, "correct": 1.0},       # a right fallback answer: not counted
            {"image_id": "d", "decided": False, "correct": None}]
    s = ca.decided_summary(rows, "train")
    assert s["questions"] == 4 and s["decided"] == 2 and s["coverage"] == 0.5
    assert s["accuracy_on_decided"] == 0.75 and s["overall_non_decided_wrong"] == 1.5 / 4


def test_alt_source_reads_the_issue_log():
    crop = ["s2 P.131a: crop read P.130; replaces P.131a"]
    assert ca.alt_source("P.130", "P.131a", crop).startswith("crop")
    assert ca.alt_source("P.130", "P.131a", ["s2 P.130: the re-run read P.131a; kept as an alternative"]) == "re-run"
    assert ca.alt_source("P.130", "P.131a", []) == "pass 1's own alt"


def test_id_patterns_tell_images_from_questions():
    t = "train_12_3 and train_45, not train_7_8x; train_9."
    assert set(ca._IMG.findall(t)) == {"train_12_3", "train_7_8"}
    assert set(ca._QID.findall(t)) == {"train_45", "train_9"}
