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


def _resp(pid, sus, csat, done, device=None, photo=None):
    return {"id": pid, "group": None, "device": device, "photo": photo, "sus": sus, "csat": csat,
            "ease": {}, "done": done}


def test_targets_pass_and_fail():
    ok = {f"T{i}": "success" for i in range(1, 6)}
    rs = [_resp("P01", BEST, 5, ok, "Máy tính"), _resp("P02", [4, 2] * 5, 4, ok, "Điện thoại"),
          _resp("P03", [4, 2] * 5, 3, {**ok, "T4": "fail"}, "Điện thoại", "Ảnh người điều phối gửi")]
    s = summarize(rs)
    t = {x["key"]: x for x in s["targets"]}
    assert t["sus_mean"]["value"] == pytest.approx(250 / 3) and t["sus_mean"]["pass"]
    assert t["task_success"]["value"] == pytest.approx(14 / 15) and t["task_success"]["pass"]
    assert t["csat_4_5"]["value"] == pytest.approx(2 / 3) and t["csat_4_5"]["pass"] is False
    assert t["every_task"]["value"] == pytest.approx(2 / 3) and t["every_task"]["pass"]
    assert s["sus_by_device"]["Điện thoại"]["n"] == 2
    assert s["task_success_by_device"]["Máy tính"] == {"attempts": 5, "rate": 1.0}
    assert s["free_question_photo"] == {"Ảnh người điều phối gửi": 1}
    rep = format_report(s)
    assert "| CSAT 4–5 ≥ 70% of testers | 67% | ❌ fail |" in rep
    assert "(lowest: T4)" in rep and "| Điện thoại | 2 |" in rep


def test_targets_without_data():
    s = summarize([_resp("P01", None, None, {})])
    assert all(t["value"] is None and t["pass"] is None for t in s["targets"])
    assert "no data" in format_report(s)


def test_untouched_log_rows_are_skipped(tmp_path):
    obs = tmp_path / "obs.csv"
    obs.write_text("participant,task,outcome,time_s,issues,notes\n"
                   "P01,T1,success,70,,\nP01,T2,,,,\nP02,T1,,,,\n", encoding="utf-8")
    os_ = read_observations(obs)
    assert [(o["participant"], o["task"]) for o in os_] == [("P01", "T1")]


def test_log_row_with_notes_but_no_outcome_is_an_error(tmp_path):
    obs = tmp_path / "obs.csv"
    obs.write_text("participant,task,outcome,time_s,issues,notes\nP01,T2,,90,slow,\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no outcome"):
        read_observations(obs)


# Found with a dummy Google Forms export and a dummy Sheets log (2026-11-25), before real responses.

def _form_rows(path: Path, rows: list[list]) -> None:
    header = ["Dấu thời gian", "[ID] Mã", "[GROUP] Nhóm", "[DEVICE] Thiết bị",
              *[f"[SUS{i}] câu" for i in range(1, 11)], "[CSAT] x"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def test_typed_ids_are_normalised_and_join_the_log(tmp_path):
    form = tmp_path / "responses.csv"
    _form_rows(form, [["t", "p7", "Sinh viên", "Điện thoại", *BEST, "5"],
                      ["t", "P 08", "Sinh viên", "Máy tính", *BEST, "5"],
                      ["t", " P09 ", "Sinh viên", "Máy tính", *BEST, "5"]])
    assert [r["id"] for r in read_responses(form)] == ["P07", "P08", "P09"]
    obs = tmp_path / "obs.csv"
    obs.write_text("participant,task,outcome,time_s,issues,notes\r\n"
                   "P07,T1,success,40,,\r\nP08,T1,fail,,,\r\nP09,T1,success,1:30,,\r\n", encoding="utf-8")
    os_ = read_observations(obs)
    assert os_[2]["time_s"] == 90
    s = summarize(read_responses(form), os_)
    assert s["task_success_by_device"] == {"Máy tính": {"attempts": 2, "rate": 0.5},
                                           "Điện thoại": {"attempts": 1, "rate": 1.0}}
    assert s["unmatched"] == {"log_only": [], "form_only": []}


def test_duplicate_submission_keeps_the_last(tmp_path, capsys):
    form = tmp_path / "responses.csv"
    _form_rows(form, [["t1", "P05", "Sinh viên", "", *WORST, "1"],
                      ["t2", "P06", "Sinh viên", "", *BEST, "5"],
                      ["t3", "p05", "Sinh viên", "", *BEST, "4"]])
    rs = read_responses(form)
    assert [r["id"] for r in rs] == ["P06", "P05"] and rs[1]["csat"] == 4
    s = summarize(rs)
    assert s["responses"] == 2 and s["duplicates_dropped"] == 1 and s["sus"]["mean"] == 100.0
    assert "1 earlier duplicate(s) dropped" in format_report(s)
    assert "P05" in capsys.readouterr().err


def test_other_group_text_is_folded_into_khac(tmp_path):
    form = tmp_path / "responses.csv"
    _form_rows(form, [["t", "P01", "shipper", "", *BEST, "5"],
                      ["t", "P02", "Người am hiểu luật giao thông (giảng viên, cán bộ…)", "", *BEST, "5"]])
    s = summarize(read_responses(form))
    assert set(s["sus_by_group"]) == {"Khác", "Người am hiểu luật giao thông"}
    assert "shipper" not in format_report(s)


def test_comma_tags_split_and_unknown_tags_warn(tmp_path, capsys):
    obs = tmp_path / "obs.csv"
    obs.write_text("participant,task,outcome,time_s,issues,notes\n"
                   "P01,T1,success,40,\"evidence_hard_to_find, waiting_too_long\",\n"
                   "P01,T2,success,40,boxes_hard_to_fnd,\n", encoding="utf-8")
    os_ = read_observations(obs)
    assert os_[0]["issues"] == ["evidence_hard_to_find", "waiting_too_long"]
    assert "boxes_hard_to_fnd" in capsys.readouterr().err


@pytest.mark.parametrize("body, match", [
    ("P01,T1,success,40,,\nP01,T1,fail,,,\n", "more than one row"),
    ("P01,T6,success,40,,\n", "task must be"),
    ("P01,T1,success,45s,,\n", "time_s"),
])
def test_log_mistakes_are_errors(tmp_path, body, match):
    obs = tmp_path / "obs.csv"
    obs.write_text("participant,task,outcome,time_s,issues,notes\n" + body, encoding="utf-8")
    with pytest.raises(SystemExit, match=match):
        read_observations(obs)


def test_log_and_form_mismatch_is_reported(tmp_path):
    obs = tmp_path / "obs.csv"
    obs.write_text("participant,task,outcome,time_s,issues,notes\nP01,T1,success,40,,\n", encoding="utf-8")
    s = summarize([_resp("P02", BEST, 5, {})], read_observations(obs))
    assert s["unmatched"] == {"log_only": ["P01"], "form_only": ["P02"]}
    assert "Not matched between the log and the form: 1 only in the log, 1 only on the form" in format_report(s)
