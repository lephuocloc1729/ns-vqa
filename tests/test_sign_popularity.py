"""eval/sign_popularity.py: code extraction and the train-only rule (owner, 2026-11-17). No API call."""

from __future__ import annotations

import json

import eval.sign_popularity as sp


def test_codes_are_read_from_text():
    assert sp.text_codes("Biển P.127 và P. 124a, IE.452, W.207c; không phải P.12") == {"P.127", "P.124a", "IE.452", "W.207c"}


def test_the_count_leaves_out_the_validation_questions():
    val = set(json.loads(sp.VALIDATION.read_text(encoding="utf-8"))["questions"])
    out = sp.count(top=5)
    assert out["train_questions_counted"] == 530 - len(val)
    assert len(out["top"]) == 5 and all(x["questions_touched"] > 0 for x in out["top"])
