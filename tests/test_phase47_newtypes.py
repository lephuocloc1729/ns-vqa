"""Phase 4.7: the parser v12 new-types test (eval/parser_newtypes.py, gold_v12_new.yaml). No API call."""

from __future__ import annotations

import json
from collections import Counter

import pytest

from eval import parser_newtypes as pn
from eval.parser_eval import gold_query
from vqa.parsing import validator
from vqa.parsing.prompt import examples
from vqa.reasoning.engine import Engine

NEW_INTENTS = {"count", "count_is", "applies_to", "sign_applies", "rule_permitted", "duties", "signal_meaning",
               "marking_meaning", "marking_is"}


def test_every_new_intent_has_at_least_five_questions():
    n = Counter(r["intent"] for r in pn.load())
    assert set(n) == NEW_INTENTS and min(n.values()) >= 5
    sub = Counter(pn._subgroup(r) for r in pn.load() if r["intent"] == "rule_permitted")
    assert all(v >= 5 for v in sub.values()), sub


def test_programs_are_valid_and_match_their_intent():
    engine = Engine()
    for r in pn.load():
        q = gold_query(r["program"])
        assert validator.check(q, engine) == [], r["id"]
        assert q.program.intent == r["intent"], r["id"]


def test_train_rows_keep_ids_only_and_are_outside_dev_validation_and_fewshots():
    bad_q, _ = pn.refused_ids()
    shots = {e["id"] for e in examples("v12")}
    for r in pn.load():
        if r["source"] == "train":
            assert "question" not in r and r["id"] not in bad_q and r["id"] not in shots, r["id"]
        else:
            assert r["source"] == "assistant_written" and r["id"].startswith("syn_") and r["question"]
    if pn.TRAIN.exists():
        assert len(pn.questions(pn.load())) == len(pn.load())     # refuses dev / validation images too


def test_a_dev_question_is_refused(tmp_path):
    bad_q, _ = pn.refused_ids()
    qid = sorted(bad_q)[0]
    rows = [{"id": qid, "source": "train", "intent": "count", "program": {"program": {"intent": "count"}}}]
    train = tmp_path / "train.json"
    train.write_text(json.dumps([{"id": qid, "image_id": "x", "question": "q"}]), encoding="utf-8")
    with pytest.raises(SystemExit, match="refused"):
        pn.questions(rows, train)


def test_score_applies_the_fixed_rule():
    rows = pn.load()
    right = [{"id": r["id"], "status": "ok", "query": gold_query(r["program"]).model_dump(mode="json")} for r in rows]
    s = pn.score(right, rows)
    assert all(v["rule"] == "pass" for v in s["intents"].values()) and not s["weaker_intents"]
    wrong_duties = [p if not p["id"] in {r["id"] for r in rows if r["intent"] == "duties"}
                    else {**p, "query": None, "status": "parse_failed"} for p in right]
    s = pn.score(wrong_duties, rows)
    assert s["weaker_intents"] == ["duties"] and s["intents"]["duties"]["rate"] == 0.0


def test_estimate_fits_the_cap():
    e = pn.estimate(pn.load())
    assert e["range_usd"][1] < e["cap_usd"] == 0.40
