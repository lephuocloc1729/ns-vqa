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


def test_rejudge_reads_a_dev2_run_with_its_profile(tmp_path, monkeypatch):
    """Phase 4.8: a dev2 run's header names profile phase47; rejudge builds that profile's pipeline
    and loads dev2's questions (here passed in), and a changed answer is listed."""
    from eval import freeze
    seen = {}
    real = freeze.pipeline_config

    def spy(profile, pm=None, **kw):
        seen["profile"] = profile
        return real(profile, pm, **kw)
    monkeypatch.setattr(freeze, "pipeline_config", spy)
    scene = {"scene_id": "s", "signs": [{"id": "s1", "code": "P.106b", "value": 2.5}]}
    ban = {"intent": "forbidden", "action": "enter", "vehicle": {"class": "truck", "load_t": 5}}
    old = [_row("q1", ban, scene, False)]
    _write(tmp_path / "dev2.jsonl", {"run_id": "d2", "kind": "dev2", "profile": "phase47"}, old)
    qs = [{"id": "q1", "question": "?", "answer": "Có"}]
    rep = ed.rejudge(tmp_path / "dev2.jsonl", [tmp_path / "dev2.jsonl"], 0.0, dry_run=True, git=CLEAN, questions=qs)
    assert seen["profile"] == "phase47" and rep["judge_ids"] == ["q1"]


def test_reparse_reads_a_dev2_run_with_its_profile(tmp_path):
    """Phase 4.8: a re-parse of a dev2 run uses the run's profile, the given parser version, and writes
    a dev2_reparse file; an unchanged parse keeps its row."""
    from tests.test_e2e_eval import RoutedSDK
    scene = {"scene_id": "s", "signs": [{"id": "s1", "code": "P.104", "shape": "circle", "border": "red",
                                         "background": "white"}]}
    prog = {"intent": "forbidden", "action": "enter", "vehicle": {"class": "motorbike"}}
    from vqa.reasoning.engine import Engine
    from vqa.schemas import QueryProgram, SceneGraph
    a = Engine(reading_policy="higher_confidence").answer(SceneGraph.model_validate(scene),
                                                          QueryProgram.model_validate({"program": prog}))
    row = {**_row("q1", prog, scene, True, a.verdict.value, a.value), "question_type": "Yes/No"}
    row["trace"]["parser"]["status"] = "ok"
    src = tmp_path / "dev2.jsonl"
    _write(src, {"run_id": "d2", "kind": "dev2_rejudge", "profile": "phase47"}, [row])
    sdk = RoutedSDK(parser=[{"program": {"intent": "forbidden", "action": "enter",
                                         "vehicle": {"vehicle_class": "motorbike"}}}])
    qs = [{"id": "q1", "question": "Xe máy có bị cấm đi vào không?", "answer": "Có", "question_type": "Yes/No"}]
    out = ed.reparse(src, "v16", 0.5, select="all", sdk=sdk, out_dir=tmp_path, git=CLEAN, questions=qs,
                     reading_policy="higher_confidence")
    head, rows = ed.ee.load(out)
    assert out.name.startswith("dev2_reparse_v16_") and head["kind"] == "dev2_reparse"
    assert head["parser_version"] == "v16" and sdk.created == ["parser"] and rows[0]["changed"] is False


def test_rejudge_records_current_switches_instead_of_inheriting_source(tmp_path):
    from tests.test_e2e_eval import RoutedSDK
    from vqa.reasoning.engine import switches_from_kb
    src = tmp_path / "source.jsonl"
    _write(src, {"run_id": "old", "kind": "dev", "switches_48": {"stated_exceptions": True}}, [])
    report = ed.rejudge(src, [src], 0, sdk=RoutedSDK(), out_dir=tmp_path,
                        git=CLEAN, questions=[])
    head, rows = ed.ee.load(report["file"])
    assert head["switches_48"] == switches_from_kb()
    assert rows == []
