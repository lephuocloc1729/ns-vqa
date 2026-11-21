"""The combined phase52 public report (eval/public52_report.py, owner, 2026-11-21): public_dev and
public_holdout runs and merges joined into one report. Fake SDK, hand-made questions; no API call."""

from __future__ import annotations

import json

import pytest

import eval.e2e_public_dev52 as pd
import eval.public52_report as pr
from tests.test_e2e_eval import QS, RoutedSDK, fake_set  # noqa: F401
from tests.test_e2e_public_dev52 import _preds, _run


def _half(fake_set, tmp_path, split):
    out, _ = _run(fake_set, split=split, out_root=fake_set / split)
    folder = out.parent
    recs = [json.loads(x) for x in (folder / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    recs[0]["trigger"] = "unknown"                    # one question goes to the RAG in V2
    (folder / "records.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    rows = [{"id": q["id"], "status": "COMPLETED", "answer": q["answer"]} for q in QS]
    pd.merge(1.0, run_id=folder.name, split=split, rag_predictions=_preds(tmp_path / split, rows),
             sdk=RoutedSDK(default={"judge": {"label": "correct", "reason": "same"}}), out_root=fake_set / split,
             questions=QS)
    return folder


def test_the_report_joins_both_halves(fake_set, tmp_path):
    dev, hold = _half(fake_set, tmp_path, "public_dev"), _half(fake_set, tmp_path, "public_holdout")
    out = pr.build(dev, hold, tmp_path / "report.json")
    rep = json.loads(out.read_text())
    assert rep["public_test"]["questions"] == 2 * len(QS)
    assert rep["public_dev"]["questions"] == rep["public_holdout"]["questions"] == len(QS)
    v2 = rep["public_test"]["v2_rules_plus_rag_fallback"]
    assert v2["rag_answered"] == 2 and v2["rules_answered"] == 2 * len(QS) - 2
    assert "by_images" not in rep["public_test"]["v1_rules_only"]
    assert set(rep["runs"]) == {"public_dev", "public_holdout"}
    text = pr.table(rep)
    assert "V2 rules + RAG fallback" in text and text.count("\n") == 9


def test_a_half_without_its_merge_is_refused(fake_set, tmp_path):
    out, _ = _run(fake_set, split="public_dev", out_root=fake_set / "d")
    with pytest.raises(SystemExit, match="no merge records"):
        pr.half(out.parent)


def test_the_halves_must_come_in_order(fake_set, tmp_path):
    dev, hold = _half(fake_set, tmp_path, "public_dev"), _half(fake_set, tmp_path, "public_holdout")
    with pytest.raises(SystemExit, match="expected a public_dev run"):
        pr.build(hold, dev, tmp_path / "r.json")
