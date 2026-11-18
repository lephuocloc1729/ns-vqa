"""Phase 4.7 (owner, 2026-11-18): `e2e_dev.py rejudge`: programs from one dev run on stored scenes of
another; an identical engine answer keeps its row, a changed decided one is listed for writer + judge.
Hand-made run files; dry run only, no API call."""

from __future__ import annotations

import json

from eval import e2e_dev as ed

CLEAN = lambda: {"clean": True, "commit": "x", "dirty": []}  # noqa: E731


def _write(path, head, rows):
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in [head, *rows]) + "\n", encoding="utf-8")


def _row(qid, program, scene, decided, verdict=None, value=None):
    return {"id": qid, "image_id": "i", "question_type": "Natural QA", "decided": decided, "correct": 1.0 if decided else None,
            "scene": scene, "engine_answer": {"verdict": verdict, "value": value} if verdict else None,
            "trace": {"parser": {"status": "ok", "program": {"program": program}}}}


def test_rejudge_keeps_identical_answers_and_lists_changed_ones(tmp_path):
    scene = {"scene_id": "s", "signs": [{"id": "s1", "code": "P.106b", "value": 2.5}]}
    ban = {"intent": "forbidden", "action": "enter", "vehicle": {"class": "truck", "load_t": 5}}
    ok = {"intent": "forbidden", "action": "enter", "vehicle": {"class": "truck", "load_t": 1}}
    from vqa.reasoning.engine import Engine
    from vqa.schemas import QueryProgram, SceneGraph
    a = Engine(reading_policy="higher_confidence").answer(SceneGraph.model_validate(scene),
                                                          QueryProgram.model_validate({"program": ban}))
    old = [_row("q1", ban, scene, True, a.verdict.value, a.value), _row("q2", ban, scene, True, a.verdict.value, a.value)]
    new = [_row("q1", ban, None, True), _row("q2", ok, None, True)]
    _write(tmp_path / "old.jsonl", {"run_id": "old", "candidate": {}}, old)
    _write(tmp_path / "new.jsonl", {"run_id": "new"}, new)
    qs = [{"id": "q1", "question": "?", "answer": "Có"}, {"id": "q2", "question": "?", "answer": "Có"}]
    rep = ed.rejudge(tmp_path / "new.jsonl", [tmp_path / "old.jsonl"], 0.0, dry_run=True, git=CLEAN, questions=qs)
    assert rep["judge_ids"] == ["q2"] and rep["changed_undecided"] == []
    assert rep["estimate_usd"] == round(ed.REJUDGE_WRITER_USD + ed.REJUDGE_JUDGE_USD, 4)
