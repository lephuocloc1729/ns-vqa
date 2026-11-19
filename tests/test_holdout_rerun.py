"""The paired re-run check on public_holdout (docs/plans/rerun-removal.md, R2): guards, the paired
figures, the decision rule, and a fake run that shares pass 1 and the program between the arms and
writes aggregates only."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from eval import e2e_eval as ee
from eval import e2e_holdout_rerun as hr
from vqa.schemas import Answer, SceneGraph, Verdict

CLEAN = lambda: {"commit": "c0ffee", "clean": True, "dirty": []}  # noqa: E731


def test_it_needs_confirm(tmp_path):
    with pytest.raises(SystemExit, match="--confirm"):
        hr.run(0.1, out_dir=tmp_path, sentinel=tmp_path / "s.json", git=CLEAN)


def test_it_refuses_a_dirty_tree_a_sentinel_and_an_earlier_report(tmp_path):
    with pytest.raises(SystemExit, match="not clean"):
        hr.guards(out_dir=tmp_path, sentinel=tmp_path / "s.json",
                  git=lambda: {"commit": "x", "clean": False, "dirty": [" M a.py"]})
    (tmp_path / "s.json").write_text("{}")
    with pytest.raises(SystemExit, match="runs once"):
        hr.guards(out_dir=tmp_path, sentinel=tmp_path / "s.json", git=CLEAN)
    (tmp_path / "s.json").unlink()
    (tmp_path / "holdout_rerun_aggregate_abc.json").write_text("{}")
    with pytest.raises(SystemExit, match="runs once"):
        hr.guards(out_dir=tmp_path, sentinel=tmp_path / "s.json", git=CLEAN)


def test_only_the_engine_code_hash_may_differ_from_phase49(tmp_path, monkeypatch):
    monkeypatch.setattr(hr.freeze, "check", lambda *a, **k: ["engine_code.sha256: record 'a', live 'b'"])
    assert hr.guards(out_dir=tmp_path, sentinel=tmp_path / "s.json", git=CLEAN)["commit"] == "c0ffee"
    monkeypatch.setattr(hr.freeze, "check", lambda *a, **k: ["pipeline_config.parser_version: record 'v17', live 'v18'"])
    with pytest.raises(SystemExit, match="differs"):
        hr.guards(out_dir=tmp_path, sentinel=tmp_path / "s.json", git=CLEAN)


def test_the_live_configuration_matches_phase49_apart_from_the_code_hash():
    rec = hr.freeze.load(hr.FROZEN)
    diffs = hr.freeze.check(hr.FROZEN, rec["pipeline_config"]["perception_model"])
    assert [d for d in diffs if not d.startswith("engine_code")] == []


def _row(a_dec, a_ok, b_dec, b_ok, changed=True):
    return {"changed": changed, "A": {"decided": a_dec, "correct": a_ok}, "B": {"decided": b_dec, "correct": b_ok}}


def test_paired_figures_and_the_decision_rule():
    rows = [_row(True, 1.0, True, 1.0, False), _row(True, 1.0, False, None), _row(True, 0.0, True, 1.0),
            _row(False, None, True, 0.5)]
    p = hr.paired(rows)
    assert (p["answers_changed"], p["decided_A"], p["decided_B"]) == (3, 3, 3)
    assert (p["correct_A"], p["correct_B"], p["net_correct_B_minus_A"]) == (2.0, 2.5, 0.5)
    assert (p["fully_right_only_A"], p["fully_right_only_B"]) == (1, 1) and p["mcnemar_exact_p"] == 1.0
    assert hr.decision(p)["adopt_no_rerun"] is True
    assert hr.decision({**p, "net_correct_B_minus_A": -1.5})["adopt_no_rerun"] is False
    assert hr.decision({**p, "decided_B": 1})["adopt_no_rerun"] is False
    assert hr.decision({**p, "net_correct_B_minus_A": -1.0, "decided_B": 2})["adopt_no_rerun"] is True
    assert hr.mcnemar_exact(0, 0) is None and hr.mcnemar_exact(0, 6) == pytest.approx(2 / 64)


# ---------------------------------------------------------------- a fake run

QS = [{"id": "q1", "image_id": "img_a", "question_type": "Yes/No", "question": "Q one?", "answer": "Đúng"},
      {"id": "q2", "image_id": "img_a", "question_type": "Natural QA", "question": "Q two?", "answer": "gold two"},
      {"id": "q3", "image_id": "img_b", "question_type": "Natural QA", "question": "Q three?", "answer": "gold three"}]


class FakeClient:
    def __init__(self):
        self.purposes = []

    def json_reply(self, **kw):
        self.purposes.append(kw["purpose"])
        return SimpleNamespace(cost_usd=0.001)


class FakePipe:
    made: list = []

    def __init__(self, cfg, sdk=None, guard=None):
        self.config, self._perception_client = cfg, FakeClient()
        self.parses, self.writes = [], []
        self.parser = SimpleNamespace(parse=self._parse)
        self.writer = SimpleNamespace(write=self._write)
        self.engine = SimpleNamespace(answer=self._engine)
        FakePipe.made.append(self)

    def _perceive(self, img, *, rerun=None):
        self._perception_client.json_reply(purpose="scene")
        if rerun:
            self._perception_client.json_reply(purpose="scene rerun")
        return SimpleNamespace(ok=True, scene=SceneGraph(scene_id=f"{img.stem}-{'A' if rerun else 'B'}")), {}

    def _parse(self, question):
        self.parses.append(question)
        return SimpleNamespace(status="ok", query=question)

    def _engine(self, scene, question):
        # q3 on img_b: arm B is not decided (the re-run mattered there)
        if question == "Q three?" and scene.scene_id.endswith("-B"):
            return Answer(verdict=Verdict.unknown)
        return Answer(verdict=Verdict.yes)

    def _write(self, question, answer, scene):
        self.writes.append((question, scene.scene_id))
        return SimpleNamespace(text="Đúng" if question == "Q one?" else "ans")


def test_a_fake_run_shares_pass1_and_the_program_and_writes_aggregates_only(tmp_path, monkeypatch, capsys):
    FakePipe.made.clear()
    monkeypatch.setattr("vqa.pipeline.Pipeline", FakePipe)
    monkeypatch.setattr(ee, "grade", lambda q, text, judge: {"correct": 1.0, "strict": 1.0})
    monkeypatch.setattr(hr.freeze, "check", lambda *a, **k: [])
    images = {i: tmp_path / f"{i}.jpg" for i in ("img_a", "img_b")}
    out = hr.run(1.0, confirm=True, sdk=object(), questions=QS, out_dir=tmp_path / "runs",
                 image_path=images.__getitem__, sentinel=tmp_path / "s.json", git=CLEAN)
    pipe = FakePipe.made[0]
    assert pipe.config.answer_fallback is False and pipe.config.scene_rerun is True
    assert pipe.parses == ["Q one?", "Q two?", "Q three?"]               # one parse per question
    assert pipe._perception_client.client.purposes.count("scene rerun") == 2      # arm A only, per image
    # same decided answer: written once; q3 decided in A only: written for A only
    assert pipe.writes == [("Q one?", "img_a-A"), ("Q two?", "img_a-A"), ("Q three?", "img_b-A")]
    rep = json.loads(out.read_text())
    assert rep["paired"]["decided_A"] == 3 and rep["paired"]["decided_B"] == 2
    assert rep["paired"]["answers_changed"] == 1 and rep["paired"]["net_correct_B_minus_A"] == -1.0
    assert rep["decision_R3"]["adopt_no_rerun"] is True
    assert rep["rerun_calls"]["calls"] == 2
    text = out.read_text() + capsys.readouterr().out
    for secret in ("q1", "q2", "q3", "img_a", "img_b", "Q one", "gold two", "Q three"):
        assert secret not in text
    mark = json.loads((tmp_path / "s.json").read_text())
    assert mark["status"] == "finished" and mark["report"] == out.name
    with pytest.raises(SystemExit, match="runs once"):
        hr.run(1.0, confirm=True, sdk=object(), questions=QS, out_dir=tmp_path / "runs",
               image_path=images.__getitem__, sentinel=tmp_path / "s.json", git=CLEAN)


def test_the_estimate_counts_only():
    e = hr.estimate(QS)
    assert (e["questions"], e["images"], e["natural_qa"]) == (3, 2, 2) and e["total_usd"] > 0
