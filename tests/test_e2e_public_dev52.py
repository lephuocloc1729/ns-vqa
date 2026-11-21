"""phase52 on public_dev for the Chapter 4 error analysis (eval/e2e_public_dev52.py, owner,
2026-11-21): guards, per-question records, and the merge with the RAG's saved public answers.
Fake SDK, hand-made images and questions; no API call and no dataset file."""

from __future__ import annotations

import json

import pytest

import eval.e2e_public_dev52 as pd
import eval.freeze as fz
from tests.test_e2e_eval import CLEAN, QS, SCENE_REPLY, RoutedSDK, _e2e_sdk, fake_set  # noqa: F401


def _run(fake_set, **kw):
    sdk = kw.pop("sdk", None) or _e2e_sdk()
    sdk.replies["perception"] = [SCENE_REPLY, SCENE_REPLY]
    args = dict(confirm_frozen=True, sdk=sdk, questions=QS, image_path=lambda i: fake_set / f"{i}.jpg",
                out_root=fake_set / "runs", frozen=fz.FROZEN_PHASE52, git=CLEAN, ignored=lambda p: True)
    args.update(kw)
    return pd.run(1.0, **args), sdk


def test_it_refuses_without_the_freeze_flag(fake_set):
    with pytest.raises(SystemExit, match="--confirm-frozen"):
        _run(fake_set, confirm_frozen=False)


def test_a_dirty_tree_is_refused(fake_set):
    dirty = lambda: {"clean": False, "dirty": ["x.py"], "commit": "c"}
    with pytest.raises(SystemExit, match="not clean"):
        _run(fake_set, git=dirty)
    assert not (fake_set / "runs").exists()


def test_a_folder_git_does_not_ignore_is_refused(fake_set):
    with pytest.raises(SystemExit, match="does not ignore"):
        _run(fake_set, ignored=lambda p: False)


def test_it_writes_records_and_an_aggregate_with_fresh_perception(fake_set):
    out, sdk = _run(fake_set)
    folder = out.parent
    recs = [json.loads(x) for x in (folder / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in recs] == [q["id"] for q in QS]
    assert all("correct" in r and "trace" in r and r["gold_answer"] for r in recs)   # public_dev: readable
    rep = json.loads(out.read_text())
    assert rep["questions"] == len(QS) and rep["answer_fallback"] is False
    assert "by_images" not in rep and "by_images" not in rep["rules_only"]
    assert "perception" in sdk.created and (folder / "scenes").is_dir()


def _preds(tmp_path, rows):
    p = tmp_path / "rag" / "predictions.jsonl"
    p.parent.mkdir(exist_ok=True)
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return p


def test_the_merge_reuses_the_rules_grades_and_reads_public_dev_ids_only(fake_set, tmp_path):
    out, _ = _run(fake_set)
    run_id = out.parent.name
    folder = out.parent
    recs = [json.loads(x) for x in (folder / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    # make one question a triggered one so the RAG answers it in V2
    recs[0]["trigger"] = "out_of_scope"
    (folder / "records.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    rows = [{"id": q["id"], "status": "COMPLETED", "answer": q["answer"]} for q in QS]
    rows.append({"id": "public_holdout_secret", "status": "FAILED", "answer": ""})      # skipped, not an error
    sdk = RoutedSDK(default={"judge": {"label": "correct", "reason": "same"}})
    m = pd.merge(1.0, run_id=run_id, rag_predictions=_preds(tmp_path, rows), sdk=sdk, out_root=fake_set / "runs",
                 questions=QS)
    rep = json.loads(m.read_text())
    assert rep["v2_rules_plus_rag_fallback"]["rag_answered"] == 1
    assert rep["v2_rules_plus_rag_fallback"]["rules_answered"] == len(QS) - 1
    assert "same_questions" in rep and rep["b2_rag_alone"]["n"] == len(QS)
    assert "public_holdout_secret" not in m.read_text()
    mr = [json.loads(x) for x in (folder / "merge_records.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["v2_source"] for r in mr} == {"rules", "rag"} and len(mr) == len(QS)


def test_the_merge_refuses_missing_public_dev_predictions(fake_set, tmp_path):
    out, _ = _run(fake_set)
    rows = [{"id": QS[0]["id"], "status": "COMPLETED", "answer": "x"}]
    with pytest.raises(SystemExit, match="miss"):
        pd.merge(1.0, run_id=out.parent.name, rag_predictions=_preds(tmp_path, rows), out_root=fake_set / "runs",
                 questions=QS)
