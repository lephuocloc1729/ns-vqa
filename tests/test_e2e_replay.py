"""Tuning (owner, 2026-11-16): the replay tool reuses a stored H run's scenes and parsed
programs and runs the rest with the current code. Fake SDK and hand-made images; no
API call and no dataset file."""

from __future__ import annotations

import json

import pytest

import eval.e2e_eval as ee
import eval.e2e_replay as er
import eval.perception_eval as pe
from tests.test_e2e_eval import QS, RoutedSDK, _perception_run, fake_set  # noqa: F401

OOS = {"program": None, "out_of_scope": True, "out_of_scope_reason": "guide sign"}
WRITER_YES = {"verdict": "yes", "answer": "Có. Biển P.104 (Cấm xe máy).", "cited_signs": ["s1"],
              "cited_rules": ["r_prohibition"]}


def _stored(fake_set):
    fb = _perception_run(fake_set)
    sdk = RoutedSDK(parser=[{"program": {"intent": "forbidden", "action": "enter",
                                         "vehicle": {"vehicle_class": "motorbike"}}}, OOS],
                    writer=[WRITER_YES], fallback=[{"verdict": "value", "answer": "Cấm xe máy."}],
                    judge=[{"label": "correct", "reason": "same meaning"}])
    run = ee.run_pipeline(fb, "H1", 1.0, sdk=sdk, warm_dir=fake_set / "warm", out_dir=fake_set / "e2e",
                          questions=QS)
    return fb, run


def test_replay_reuses_parses_fallback_and_grades_and_reruns_the_writer(fake_set):
    fb, run = _stored(fake_set)
    sdk = RoutedSDK(writer=[WRITER_YES])
    out = er.replay(run, fb, "T1-H1", 0.5, sdk=sdk, warm_dir=fake_set / "warm", out_dir=fake_set / "e2e",
                    questions=QS)
    assert sdk.created == ["writer"]                       # no parser, perception, fallback or judge call
    head, rows = ee.load(out)
    sh, srows = ee.load(run)
    assert head["kind"] == "replay" and head["replay_of"] == sh["run_id"] and head["scene_changes"] == []
    assert head["writer"].startswith("answer/v3@")
    assert [r["text"] for r in rows] == [r["text"] for r in srows]
    assert [r["correct"] for r in rows] == [r["correct"] for r in srows] and all(r["judge_reused"] for r in rows)
    assert (rows[1]["answered_by"], rows[1]["fallback_reused"]) == ("fallback", True)
    assert rows[0]["trace"]["parser"]["attempts"] == 0 and rows[0]["trace"]["writer"]["raw"]


def test_a_changed_answer_is_judged_again(fake_set):
    fb, run = _stored(fake_set)
    other = dict(WRITER_YES, answer="Có. Biển P.104 (Cấm xe máy) cấm xe máy.")
    sdk = RoutedSDK(writer=[other])
    out = er.replay(run, fb, "T1-H1", 0.5, sdk=sdk, warm_dir=fake_set / "warm", out_dir=fake_set / "e2e",
                    questions=QS)
    _, rows = ee.load(out)
    assert rows[0]["text"] == other["answer"] and rows[0]["judge_reused"] is False and rows[0]["correct"] == 1.0
    assert "judge" not in sdk.created                      # Yes/No: graded without the judge


def test_a_changed_fallback_prompt_calls_the_fallback(fake_set, monkeypatch):
    fb, run = _stored(fake_set)
    lines = run.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[2])
    rec["trace"]["fallback"]["prompt_id"] = "answer_fallback/v0@000000000000"
    lines[2] = json.dumps(rec, ensure_ascii=False)
    run.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sdk = RoutedSDK(writer=[WRITER_YES], fallback=[{"verdict": "value", "answer": "Cấm xe máy."}])
    out = er.replay(run, fb, "T2-H1", 0.5, sdk=sdk, warm_dir=fake_set / "warm", out_dir=fake_set / "e2e",
                    questions=QS)
    _, rows = ee.load(out)
    assert "fallback" in sdk.created and rows[1]["fallback_reused"] is False


def test_replay_refuses_the_wrong_perception_file(fake_set):
    fb, run = _stored(fake_set)
    other = _perception_run(fake_set)
    with pytest.raises(SystemExit, match="used scenes"):
        er.replay(run, other, "T1-H1", 0.5, sdk=RoutedSDK(), warm_dir=fake_set / "warm",
                  out_dir=fake_set / "e2e", questions=QS)


def test_changed_scenes_need_the_flag_and_are_listed(fake_set, monkeypatch):
    fb, run = _stored(fake_set)
    real = pe.warm_run

    def changed(path, cache_dir=None):
        rep = real(path, cache_dir)
        return {**rep, "ok": False, "mismatches": ["public_test_1_1"]}

    monkeypatch.setattr(pe, "warm_run", changed)
    with pytest.raises(SystemExit, match="allow-scene-changes"):
        er.replay(run, fb, "T4-H1", 0.5, sdk=RoutedSDK(), warm_dir=fake_set / "warm", out_dir=fake_set / "e2e",
                  questions=QS)
    out = er.replay(run, fb, "T4-H1", 0.5, sdk=RoutedSDK(writer=[WRITER_YES]), warm_dir=fake_set / "warm",
                    out_dir=fake_set / "e2e", questions=QS, allow_scene_changes=True)
    assert ee.load(out)[0]["scene_changes"] == ["public_test_1_1"]


def test_estimate_counts_writer_path_answers_and_the_fallback_only_when_changed(fake_set):
    _, run = _stored(fake_set)
    e = er.estimate([run])
    assert e["calls"] == {"writer": 1, "fallback": 0, "judge (Natural QA)": 0}
    e = er.estimate([run], fallback_changed=True)
    assert e["calls"] == {"writer": 1, "fallback": 1, "judge (Natural QA)": 1}
