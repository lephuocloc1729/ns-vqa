"""Phase 4.5 scope round (owner, 2026-11-17): the dev set and the per-question dev runs
(eval/e2e_dev.py). The split tests read ids only; the run test uses a fake SDK and
hand-made images; no API call."""

from __future__ import annotations

import json

import pytest

import eval.e2e_dev as ed
import eval.make_validation_split as mvs
from eval import coverage_analysis as ca
from tests.test_e2e_eval import CLEAN, QS, SCENE_REPLY, _e2e_sdk, fake_set  # noqa: F401

DEV = json.loads(mvs.DEV_OUT.read_text(encoding="utf-8"))
VAL = json.loads(mvs.OUT.read_text(encoding="utf-8"))


def test_the_dev_set_does_not_overlap_the_validation_set():
    assert not set(DEV["questions"]) & set(VAL["questions"])
    assert not set(DEV["images"]) & set(VAL["images"])
    ed.check_disjoint()


def test_dev_plus_validation_is_the_pool():
    images, questions, _ = ca.pool()
    assert set(DEV["images"]) | set(VAL["images"]) == set(images)
    assert set(DEV["questions"]) | set(VAL["questions"]) == {q["id"] for q in questions}
    assert mvs.build_dev() == DEV and DEV["counts"] == {"images": 60, "questions": 87,
                                                         "question_types": {"Natural QA": 87}}


def test_an_overlap_is_refused(tmp_path):
    p = tmp_path / "dev.json"
    p.write_text(json.dumps({"questions": VAL["questions"][:1], "images": []}), encoding="utf-8")
    with pytest.raises(SystemExit, match="overlaps"):
        ed.check_disjoint(p)


def test_a_dev_run_keeps_per_question_records_with_the_fallback_off(fake_set):
    sdk = _e2e_sdk()
    sdk.replies["perception"] = [SCENE_REPLY, SCENE_REPLY]
    out = ed.run_dev("t", 1.0, sdk=sdk, questions=QS, out_dir=fake_set / "dev",
                     image_path=lambda i: fake_set / f"{i}.jpg", git=CLEAN)
    head, rows = ed.ee.load(out)
    assert head["answer_fallback"] is False and head["kind"] == "dev"
    assert [r["id"] for r in rows] == ["q1", "q2"] and all(r["decided"] for r in rows)
    assert rows[0]["scene"]["signs"][0]["code"] == "P.104" and rows[0]["trace"]["parser"]["program"]
    assert rows[0]["correct"] == 1.0 and "fallback" not in sdk.created
    assert (fake_set / "dev" / head["cache_dir"]).is_dir()
    s = ed.summary(out)
    assert s["decided"] == 2 and s["coverage"] == 1.0


def test_a_dirty_tree_is_refused(fake_set):
    dirty = lambda: {"commit": "c", "clean": False, "dirty": [" M x"]}  # noqa: E731
    with pytest.raises(SystemExit, match="not clean"):
        ed.run_dev("t", 1.0, sdk=_e2e_sdk(), questions=QS, out_dir=fake_set / "dev", git=dirty)
