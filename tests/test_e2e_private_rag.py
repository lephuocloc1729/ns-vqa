"""docs/plans/rag-fallback.md F4.3–F4.4 (owner, 2026-11-20; live V2 answers 2026-11-21): the
triggered-ids export and the RAG merge on the private test (eval/e2e_private_rag.py). Hand-made
records, RAG answers and questions; fake judge; no API call and no dataset file."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import eval.e2e_private_rag as er
from tests.test_e2e_eval import RoutedSDK

QS = [{"id": "p1", "image_id": "i1", "question_type": "Yes/No", "question": "Xe máy có bị cấm không?",
       "answer": "Có secret-gold-1"},
      {"id": "p2", "image_id": "i2", "question_type": "Yes/No", "question": "Ô tô được rẽ trái không?",
       "answer": "Không secret-gold-2"},
      {"id": "p3", "image_id": "i3", "question_type": "Natural QA", "question": "Biển này là gì?",
       "answer": "Cấm xe máy secret-gold-3"}]
# p1 decided by the rules (right); p2 and p3 triggered, answered by the RAG (p2 right, p3 judged)
RECORDS = [{"id": "p1", "image_id": "i1", "question_type": "Yes/No", "text": "Có, xe máy bị cấm.",
            "trigger": None, "answered_by": "rules"},
           {"id": "p2", "image_id": "i2", "question_type": "Yes/No", "text": "Chưa xác định.",
            "trigger": "unknown", "answered_by": "not_decided"},
           {"id": "p3", "image_id": "i3", "question_type": "Natural QA", "text": "Chưa xác định.",
            "trigger": "out_of_scope", "answered_by": "not_decided"}]
RAG = [{"id": "p1", "status": "COMPLETED", "answer": "Không."},       # the RAG alone is wrong on p1
       {"id": "p2", "status": "COMPLETED", "answer": "Không, ô tô không được rẽ trái."},
       {"id": "p3", "status": "COMPLETED", "answer": "Biển cấm xe máy."}]
# the live run on the triggered p2 and p3: p2 equals the saved answer, p3 differs (and is judged)
LIVE = [{"id": "p2", "status": "COMPLETED", "answer": "Không, ô tô không được rẽ trái.",
         "caption_status": "COMPLETED", "caption_seconds": 3.0, "embed_seconds": 0.1, "answer_seconds": 8.0},
        {"id": "p3", "status": "COMPLETED", "answer": "Đây là biển cấm mô tô.",
         "caption_status": "INCOMPLETE", "caption_seconds": 5.0, "embed_seconds": 0.1, "answer_seconds": 10.0}]


@pytest.fixture
def setup(tmp_path):
    run = tmp_path / "private_run" / "run1"
    run.mkdir(parents=True)
    (run / "records.jsonl").write_text("\n".join(json.dumps({**r, "trace": {}}, ensure_ascii=False)
                                                 for r in RECORDS), encoding="utf-8")
    preds = tmp_path / "rag" / "predictions.jsonl"
    preds.parent.mkdir()
    preds.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in RAG), encoding="utf-8")
    (preds.parent / "run_config.json").write_text(json.dumps({"fewshot_k": 5, "answer_model": "qwen3.5-9b-gguf",
                                                               "secret": "x"}), encoding="utf-8")
    live = tmp_path / "live" / "rag_live.jsonl"
    live.parent.mkdir()
    live.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in LIVE), encoding="utf-8")
    (live.parent / "rag_live_meta.json").write_text(json.dumps({"retrieval_seconds_per_question": 0.9,
                                                                "run_config_sha256": "abc",
                                                                "config": {"fewshot_k": 5}}), encoding="utf-8")
    priv = tmp_path / "private_ran.json"
    priv.write_text(json.dumps({"run_id": "run1", "status": "finished", "git_commit": "c0ffee"}), encoding="utf-8")
    return tmp_path, preds, priv


def _run(setup, **kw):
    tmp, preds, priv = setup
    sdk = kw.pop("sdk", None) or RoutedSDK(default={"judge": {"label": "correct", "reason": "same meaning"}})
    args = dict(confirm=True, rag_predictions=preds, rag_live=tmp / "live" / "rag_live.jsonl", questions=QS, sdk=sdk, out_dir=tmp / "agg",
                sentinel=tmp / "private_rag_ran.json", private_sentinel=priv, replay_root=tmp / "private_run",
                ignored=lambda p: True)
    args.update(kw)
    return er.run_merge(1.0, **args), sdk


def test_it_refuses_without_confirm(setup):
    with pytest.raises(SystemExit, match="--confirm"):
        _run(setup, confirm=False)


def test_it_refuses_before_the_private_run_finishes(setup):
    tmp, _, priv = setup
    priv.write_text(json.dumps({"run_id": "run1", "status": "started"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="not finished"):
        _run(setup)
    assert not (tmp / "private_rag_ran.json").exists()


def test_it_refuses_records_of_another_run(setup, tmp_path):
    other = tmp_path / "private_run" / "run2"
    other.mkdir()
    (other / "records.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="not the finished private run"):
        _run(setup, records=other / "records.jsonl")


def test_it_refuses_inputs_that_cover_different_questions(setup):
    tmp, preds, _ = setup
    preds.write_text("\n".join(json.dumps(r) for r in RAG[:2]), encoding="utf-8")
    with pytest.raises(SystemExit, match="different questions"):
        _run(setup)
    assert not (tmp / "private_rag_ran.json").exists()


def test_an_incomplete_rag_prediction_is_refused(setup):
    _, preds, _ = setup
    preds.write_text("\n".join(json.dumps({**r, "status": "FAILED"} if r["id"] == "p2" else r) for r in RAG),
                     encoding="utf-8")
    with pytest.raises(SystemExit, match="1 RAG predictions did not complete"):
        _run(setup)


def test_v2_takes_the_rules_where_decided_and_the_live_rag_where_triggered(setup):
    out, sdk = _run(setup)
    rep = json.loads(out.read_text())
    v2, b2 = rep["v2_rules_plus_rag_fallback"], rep["b2_rag_alone"]
    assert v2["rules_answered"] == 1 and v2["rag_answered"] == 2
    assert v2["overall"] == 1.0                           # p1 by the rules, p2 and p3 by the live RAG: all right
    assert b2["overall"] == pytest.approx(2 / 3)          # the RAG alone (saved answers) misses p1
    assert set(v2["rag_part_by_trigger"]) == {"unknown", "out_of_scope"}
    assert sdk.created == ["judge", "judge"]              # p3's saved answer (B2) and its live answer (V2)
    assert rep["rag_predictions"]["config"] == {"fewshot_k": 5, "answer_model": "qwen3.5-9b-gguf"}


def test_the_report_has_the_determinism_check_and_the_live_seconds(setup):
    out, _ = _run(setup)
    lv = json.loads(out.read_text())["rag_live"]
    assert lv["answers"] == 2 and lv["identical_to_saved"] == 1 and lv["incomplete_captions"] == 1
    assert lv["seconds"]["total"]["mean"] == pytest.approx((3 + 0.1 + 8 + 0.9 + 5 + 0.1 + 10 + 0.9) / 2, abs=0.01)
    assert lv["seconds"]["retrieval"]["mean"] == 0.9
    assert lv["live_runs"] == [{"run_config_sha256": "abc", "config": {"fewshot_k": 5}}]


def test_v2_grades_the_live_answer_not_the_saved_one(setup):
    sdk = RoutedSDK(judge=[{"label": "correct", "reason": "saved"}, {"label": "wrong", "reason": "live"}])
    out, _ = _run(setup, sdk=sdk)
    rep = json.loads(out.read_text())
    assert rep["b2_rag_alone"]["natural_qa_score"] == 1.0
    assert rep["v2_rules_plus_rag_fallback"]["natural_qa_score"] == 0.0


def test_live_answers_must_cover_every_triggered_question(setup):
    tmp, _, _ = setup
    (tmp / "live" / "rag_live.jsonl").write_text(json.dumps(LIVE[0]), encoding="utf-8")
    with pytest.raises(SystemExit, match="miss 1 of the 2 triggered questions"):
        _run(setup)
    assert not (tmp / "private_rag_ran.json").exists()


def test_a_live_file_may_hold_more_questions_than_the_triggered_ones(setup):
    tmp, _, _ = setup
    extra = {"id": "p1", "status": "FAILED", "answer": ""}          # not triggered: neither used nor checked
    (tmp / "live" / "rag_live.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                                           for r in [*LIVE, extra]), encoding="utf-8")
    rep = json.loads(_run(setup)[0].read_text())
    assert rep["rag_live"]["answers"] == 2 and rep["v2_rules_plus_rag_fallback"]["rag_answered"] == 2


def test_two_live_files_are_read_together(setup):
    tmp, _, _ = setup
    (tmp / "live" / "rag_live.jsonl").write_text(json.dumps(LIVE[0], ensure_ascii=False), encoding="utf-8")
    rest = tmp / "live_rest" / "rag_live.jsonl"
    rest.parent.mkdir()
    rest.write_text(json.dumps(LIVE[1], ensure_ascii=False), encoding="utf-8")
    rep = json.loads(_run(setup, rag_live=[tmp / "live" / "rag_live.jsonl", rest])[0].read_text())
    assert rep["rag_live"]["answers"] == 2 and len(rep["rag_live"]["files_sha256"]) == 2


def test_a_question_in_two_live_files_is_refused(setup):
    tmp, _, _ = setup
    dup = tmp / "live_dup" / "rag_live.jsonl"
    dup.parent.mkdir()
    dup.write_text(json.dumps(LIVE[0], ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SystemExit, match="more than one live RAG file"):
        _run(setup, rag_live=[tmp / "live" / "rag_live.jsonl", dup])


def test_run_2_uses_its_own_sentinels_and_records(setup):
    tmp, _, priv = setup
    run2 = tmp / "private_run" / "run2"
    run2.mkdir()
    (run2 / "records.jsonl").write_text((tmp / "private_run" / "run1" / "records.jsonl").read_text(encoding="utf-8"),
                                        encoding="utf-8")
    with pytest.raises(SystemExit, match="has not run yet"):
        _run(setup, run=2)                                   # no private_ran_2.json yet
    (tmp / "private_ran_2.json").write_text(json.dumps({"run_id": "run2", "status": "finished"}), encoding="utf-8")
    out, _ = _run(setup, run=2)
    assert json.loads(out.read_text())["run"] == 2 and out.name == "private_rag_aggregate_run2.json"
    assert json.loads((tmp / "private_rag_ran_2.json").read_text())["private_run_id"] == "run2"
    assert not (tmp / "private_rag_ran.json").exists()      # run 1's merge is still open
    with pytest.raises(SystemExit, match="must be one of"):
        _run(setup, run=4)


def test_the_ids_export_takes_a_run(setup):
    tmp, _, priv = setup
    (tmp / "private_run" / "run2").mkdir()
    (tmp / "private_run" / "run2" / "records.jsonl").write_text(json.dumps({**RECORDS[0], "trace": {}}),
                                                                encoding="utf-8")
    (tmp / "private_ran_2.json").write_text(json.dumps({"run_id": "run2", "status": "finished"}), encoding="utf-8")
    out = er.write_ids(run=2, private_sentinel=priv, replay_root=tmp / "private_run", ignored=lambda p: True)
    assert out.parent.name == "run2" and json.loads(out.read_text()) == []


def test_an_incomplete_live_answer_is_refused(setup):
    tmp, _, _ = setup
    (tmp / "live" / "rag_live.jsonl").write_text("\n".join(json.dumps({**r, "status": "SKIPPED_OOM"})
                                                           if r["id"] == "p3" else json.dumps(r) for r in LIVE),
                                                 encoding="utf-8")
    with pytest.raises(SystemExit, match="1 live RAG answers did not complete"):
        _run(setup)


def test_the_ids_export_writes_the_triggered_ids_only(setup):
    tmp, _, priv = setup
    out = er.write_ids(private_sentinel=priv, replay_root=tmp / "private_run", ignored=lambda p: True)
    assert out == tmp / "private_run" / "run1" / er.TRIGGERED_IDS
    assert json.loads(out.read_text()) == ["p2", "p3"]
    with pytest.raises(SystemExit, match="does not ignore"):
        er.write_ids(private_sentinel=priv, replay_root=tmp / "private_run", ignored=lambda p: False)


def test_it_runs_once_and_its_report_holds_no_ids_or_gold(setup):
    tmp, _, _ = setup
    out, _ = _run(setup)
    text = out.read_text()
    for q in QS:
        assert q["id"] not in text and q["image_id"] not in text and "secret-gold" not in text
    mark = json.loads((tmp / "private_rag_ran.json").read_text())
    assert mark["status"] == "finished" and mark["private_run_id"] == "run1"
    with pytest.raises(SystemExit, match="already run"):
        _run(setup)


def test_it_reads_the_finished_runs_records_by_default(setup):
    out, _ = _run(setup, records=None)
    assert json.loads(out.read_text())["private_run_id"] == "run1"


def test_the_merge_prints_only_counters():
    src = (Path(er.__file__)).read_text(encoding="utf-8")
    prints = [ast.unparse(n) for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "print"]
    assert prints and all("spent" in p or "aggregate report" in p or "triggered ids" in p for p in prints), prints


def test_the_owner_sheet_has_v2_and_b2_rows_in_the_replay_folder(setup):
    import csv
    tmp, _, _ = setup
    _run(setup)
    rows = list(csv.DictReader(open(tmp / "private_run" / "run1" / er.OWNER_SHEET, encoding="utf-8-sig")))
    assert len(rows) == 6 and {r["system"] for r in rows} == {"v2_rules_plus_rag", "b2_rag_alone"}
    v2 = {r["id"]: r for r in rows if r["system"] == "v2_rules_plus_rag"}
    assert v2["p1"]["answered_by"] == "rules" and v2["p2"]["answered_by"] == "rag_live"
    assert v2["p3"]["system_answer"] == LIVE[1]["answer"]
    assert v2["p3"]["judge_label"] == "correct" and rows[0]["human_score"] == ""
    assert not list((tmp / "agg").glob("*.csv"))                      # the runs folder gets the aggregate only


def test_a_replay_folder_git_does_not_ignore_is_refused(setup):
    tmp, _, _ = setup
    with pytest.raises(SystemExit, match="does not ignore"):
        _run(setup, ignored=lambda p: False)
    assert not (tmp / "private_rag_ran.json").exists()


def test_rag_alone_is_scored_on_the_same_questions_as_each_part_of_v2(setup):
    rep = json.loads(_run(setup)[0].read_text())
    sq = rep["same_questions"]
    rd = sq["rules_decided"]                                  # p1: the rules are right, the RAG alone wrong
    assert rd["v2_rules"]["n"] == 1 and rd["v2_rules"]["overall"] == 1.0 and rd["rag_alone"]["overall"] == 0.0
    assert rd["paired"] == {"n": 1, "both_right": 0, "only_v2_right": 1, "only_rag_alone_right": 0,
                            "both_wrong": 0, "mcnemar_exact_p": 1.0}
    tr = sq["triggered"]                                      # p2 and p3: live and saved both right
    assert tr["v2_live_rag"]["n"] == 2 and tr["paired"]["both_right"] == 2
    assert sq["all"]["paired"]["n"] == 3 and sq["all"]["paired"]["only_v2_right"] == 1


def test_the_exact_mcnemar_p_value():
    assert er._mcnemar_p(0, 0) is None
    assert er._mcnemar_p(5, 5) == 1.0
    assert er._mcnemar_p(10, 0) == pytest.approx(2 / 2 ** 10)
    assert er._mcnemar_p(8, 2) == pytest.approx(2 * (1 + 10 + 45) / 1024)


# ---------------------------------------------------------------- reproduction runs (owner, 2026-11-25)

@pytest.fixture
def repro(setup):
    """A finished reproduction run's replay folder, beside the benchmark's records."""
    tmp, preds, priv = setup
    rid = "repro-abc123"
    folder = tmp / "private_run" / rid
    folder.mkdir(parents=True)
    (folder / "records.jsonl").write_text((tmp / "private_run" / "run1" / "records.jsonl").read_text(encoding="utf-8"),
                                          encoding="utf-8")
    (folder / "reproduce.json").write_text(json.dumps({"run_id": rid, "status": "finished", "run": "reproduce",
                                                       "git_commit": "c0ffee"}), encoding="utf-8")
    return tmp, preds, priv, rid


def test_a_reproduction_merge_uses_its_own_markers_and_folder(repro):
    tmp, preds, priv, rid = repro
    priv_before = priv.read_text()
    out, _ = _run(repro[:3], reproduce=rid, out_dir=tmp / "repro_agg")
    rep = json.loads(out.read_text())
    assert out.name == f"private_rag_reproduce_{rid}.json" and rep["run"] == "reproduce"
    assert rep["private_run_id"] == rid and rep["v2_rules_plus_rag_fallback"]["n"] == 3
    me = json.loads((tmp / "private_run" / rid / er.REPRO_RAG_MARK).read_text())
    assert me["status"] == "finished" and me["report"] == out.name
    assert not (tmp / "private_rag_ran.json").exists() and priv.read_text() == priv_before
    assert (tmp / "private_run" / rid / er.OWNER_SHEET).exists()


def test_a_reproduction_merge_runs_once_per_reproduction_run(repro):
    tmp, *_, rid = repro
    _run(repro[:3], reproduce=rid, out_dir=tmp / "repro_agg")
    with pytest.raises(SystemExit, match="already run"):
        _run(repro[:3], reproduce=rid, out_dir=tmp / "repro_agg")


def test_a_reproduction_merge_needs_a_finished_reproduction_run(repro):
    tmp, *_, rid = repro
    (tmp / "private_run" / rid / "reproduce.json").write_text(json.dumps({"run_id": rid, "status": "started"}))
    with pytest.raises(SystemExit, match="not finished"):
        _run(repro[:3], reproduce=rid)


@pytest.mark.parametrize("bad", ["run1", "../run1", "repro-x/../../run1"])
def test_a_reproduction_merge_takes_only_a_reproduction_id(repro, bad):
    with pytest.raises(SystemExit, match="reproduction run id"):
        _run(repro[:3], reproduce=bad)


def test_the_ids_of_a_reproduction_run(repro):
    tmp, *_, rid = repro
    out = er.write_ids(reproduce=rid, replay_root=tmp / "private_run", ignored=lambda p: True)
    assert out == tmp / "private_run" / rid / er.TRIGGERED_IDS
    assert json.loads(out.read_text()) == ["p2", "p3"]
