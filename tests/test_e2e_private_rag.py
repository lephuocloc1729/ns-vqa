"""docs/plans/rag-fallback.md F4.3 (owner, 2026-11-20): the RAG merge on the private test
(eval/e2e_private_rag.py). Hand-made records, RAG answers and questions; fake judge; no API
call and no dataset file."""

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
    priv = tmp_path / "private_ran.json"
    priv.write_text(json.dumps({"run_id": "run1", "status": "finished", "git_commit": "c0ffee"}), encoding="utf-8")
    return tmp_path, preds, priv


def _run(setup, **kw):
    tmp, preds, priv = setup
    sdk = kw.pop("sdk", None) or RoutedSDK(judge=[{"label": "correct", "reason": "same meaning"}])
    args = dict(confirm=True, rag_predictions=preds, questions=QS, sdk=sdk, out_dir=tmp / "agg",
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


def test_v2_takes_the_rules_where_decided_and_the_rag_where_triggered(setup):
    out, sdk = _run(setup)
    rep = json.loads(out.read_text())
    v2, b2 = rep["v2_rules_plus_rag_fallback"], rep["b2_rag_alone"]
    assert v2["rules_answered"] == 1 and v2["rag_answered"] == 2
    assert v2["overall"] == 1.0                           # p1 by the rules, p2 and p3 by the RAG: all right
    assert b2["overall"] == pytest.approx(2 / 3)          # the RAG alone misses p1
    assert set(v2["rag_part_by_trigger"]) == {"unknown", "out_of_scope"}
    assert sdk.created == ["judge"]                       # one Natural QA answer, graded once for both
    assert rep["rag_predictions"]["config"] == {"fewshot_k": 5, "answer_model": "qwen3.5-9b-gguf"}


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
    assert prints and all("spent" in p or "aggregate report" in p for p in prints), prints


def test_the_owner_sheet_has_v2_and_b2_rows_in_the_replay_folder(setup):
    import csv
    tmp, _, _ = setup
    _run(setup)
    rows = list(csv.DictReader(open(tmp / "private_run" / "run1" / er.OWNER_SHEET, encoding="utf-8-sig")))
    assert len(rows) == 6 and {r["system"] for r in rows} == {"v2_rules_plus_rag", "b2_rag_alone"}
    v2 = {r["id"]: r for r in rows if r["system"] == "v2_rules_plus_rag"}
    assert v2["p1"]["answered_by"] == "rules" and v2["p2"]["answered_by"] == "rag"
    assert v2["p3"]["judge_label"] == "correct" and rows[0]["human_score"] == ""
    assert not list((tmp / "agg").glob("*.csv"))                      # the runs folder gets the aggregate only


def test_a_replay_folder_git_does_not_ignore_is_refused(setup):
    tmp, _, _ = setup
    with pytest.raises(SystemExit, match="does not ignore"):
        _run(setup, ignored=lambda p: False)
    assert not (tmp / "private_rag_ran.json").exists()
