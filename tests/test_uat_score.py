"""eval/uat/score_sus.py: SUS, CSAT and task-success scoring for the UAT."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from eval.uat.score_sus import (
    format_report, mean_ci, read_observations, read_responses, summarize, sus_grade, sus_score, wilson,
)

UAT = Path(__file__).resolve().parents[1] / "eval" / "uat"

BEST = [5, 1] * 5
WORST = [1, 5] * 5


def test_sus_score_bounds_and_midpoint():
    assert sus_score(BEST) == 100.0
    assert sus_score(WORST) == 0.0
    assert sus_score([3] * 10) == 50.0
    # a typical sheet: (4-1)+(5-2)+(4-1)+(5-1)+(4-1)+(5-2)+(5-1)+(5-2)+(4-1)+(5-2) = 32 -> 80
    assert sus_score([4, 2, 4, 1, 4, 2, 5, 2, 4, 2]) == 80.0


@pytest.mark.parametrize("bad", [[3] * 9, [3] * 9 + [6], [0] + [3] * 9])
def test_sus_score_rejects_bad_sheets(bad):
    with pytest.raises(ValueError):
        sus_score(bad)


def test_sus_grade_curve():
    assert sus_grade(100) == "A+"
    assert sus_grade(84.1) == "A+"
    assert sus_grade(80.8) == "A"
    assert sus_grade(68.0) == "C"
    assert sus_grade(51.6) == "F"


def test_mean_ci_uses_t():
    m, lo, hi = mean_ci([60.0, 70.0, 80.0])
    assert m == 70.0
    assert hi - m == pytest.approx(4.303 * 10 / math.sqrt(3), rel=1e-3)
    assert m - lo == pytest.approx(hi - m)


def test_wilson():
    lo, hi = wilson(10, 10)
    assert hi == 1.0 and 0.69 < lo < 0.73
    lo, hi = wilson(0, 0)
    assert math.isnan(lo)


def _write_form(path: Path, rows: list[list]) -> None:
    # Google Forms export: a timestamp first, titles starting with the code; columns in any order
    header = ["Dấu thời gian", "[CSAT] Mức độ hài lòng chung", "[ID] Mã người tham gia"]
    header += [f"[SUS{i}] câu {i}" for i in range(1, 11)] + ["[T1] Nhiệm vụ 1 dễ hay khó", "Góp ý"]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        for pid, csat, sus, t1 in rows:
            w.writerow(["2026-11-26 10:00", csat, pid, *sus, t1, "ok"])


def test_read_and_summarize(tmp_path):
    form = tmp_path / "responses.csv"
    _write_form(form, [
        ("p01", "5 - Rất hài lòng", BEST, 5),
        ("P02", "4", [3] * 10, 4),
        ("P03", "2", WORST, ""),
        ("P04", "", [3] * 9 + [""], 3),     # incomplete SUS: not scored
    ])
    rs = read_responses(form)
    assert [r["id"] for r in rs] == ["P01", "P02", "P03", "P04"]
    assert rs[0]["csat"] == 5 and rs[3]["sus"] is None

    s = summarize(rs)
    assert s["responses"] == 4 and s["sus_n"] == 3
    assert s["sus"]["mean"] == 50.0
    assert s["csat"]["n"] == 3 and s["csat"]["share_4_5"] == pytest.approx(2 / 3)
    assert s["task_ease"]["T1"]["n"] == 3
    assert "## SUS" in format_report(s)


def test_missing_sus_column_is_an_error(tmp_path):
    form = tmp_path / "bad.csv"
    form.write_text("[ID] x,[SUS1] a\nP01,3\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        read_responses(form)


def test_observations_and_issue_tags(tmp_path):
    obs = tmp_path / "obs.csv"
    obs.write_text(
        "participant,task,outcome,time_s,issues,notes\n"
        "P01,T1,success,40,slow,\n"
        "P01,T2,fail,,slow;evidence_hard_to_find,\n"
        "P02,T1,partial,90,,\n"
        "P02,T2,success,30,SLOW,\n",
        encoding="utf-8")
    os_ = read_observations(obs)
    s = summarize([], os_)
    t = s["task_success"]
    assert (t["attempts"], t["success"], t["partial"], t["participants"]) == (4, 2, 1, 2)
    assert t["rate_with_partial_half"] == pytest.approx(2.5 / 4)
    assert s["tasks"]["T1"]["median_time_s"] == 65.0
    assert s["tasks"]["T2"]["median_time_s"] == 30.0     # the failed attempt's time is left out
    # each participant counts a tag once, case-insensitively
    assert dict(s["issues"]) == {"slow": 2, "evidence_hard_to_find": 1}
    assert "| T1 |" in format_report(s)


def test_bad_outcome_is_an_error(tmp_path):
    obs = tmp_path / "obs.csv"
    obs.write_text("participant,task,outcome,time_s,issues,notes\nP01,T1,done,,,\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        read_observations(obs)


def test_shipped_template_parses():
    s = summarize([], read_observations(UAT / "observation_log_template.csv"))
    assert s["task_success"]["attempts"] == 5


def test_form_questions_carry_every_code():
    text = (UAT / "form_questions.md").read_text(encoding="utf-8")
    for code in ["ID", "GROUP", "CSAT", *[f"SUS{i}" for i in range(1, 11)],
                 *[f"T{i}" for i in range(1, 6)], *[f"OK{i}" for i in range(1, 6)]]:
        assert f"[{code}]" in text, code


def test_self_reported_tasks_and_groups(tmp_path):
    form = tmp_path / "responses.csv"
    header = ["[ID] Mã", "[GROUP] Nhóm", *[f"[SUS{i}] câu" for i in range(1, 11)], "[CSAT] x",
              "[OK1] Nhiệm vụ 1: hoàn thành?", "[OK2] Nhiệm vụ 2: hoàn thành?"]
    rows = [["P01", "Người lái xe", *BEST, "5", "Có", "Một phần"],
            ["P02", "Sinh viên", *[3] * 10, "4", "Không", "Có"],
            ["P03", "Người lái xe", *WORST, "2", "Có", ""]]
    with form.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    rs = read_responses(form)
    assert rs[0]["done"] == {"T1": "success", "T2": "partial"}
    assert rs[2]["done"] == {"T1": "success"}
    s = summarize(rs)
    assert s["task_source"] == "self-reported"
    t = s["task_success"]
    assert (t["attempts"], t["success"], t["partial"]) == (5, 3, 1)
    assert s["sus_by_group"]["Người lái xe"] == {"n": 2, "mean": 50.0}
    assert s["sus_by_group"]["Sinh viên"]["mean"] == 50.0
    rep = format_report(s)
    assert "self-reported on the form" in rep and "| Sinh viên | 1 |" in rep


def test_log_wins_over_self_report(tmp_path):
    obs = tmp_path / "obs.csv"
    obs.write_text("participant,task,outcome,time_s,issues,notes\nP01,T1,fail,,,\n", encoding="utf-8")
    resp = [{"id": "P01", "group": None, "sus": None, "csat": None, "ease": {}, "done": {"T1": "success"}}]
    s = summarize(resp, read_observations(obs))
    assert s["task_source"] == "observed" and s["task_success"]["success"] == 0
