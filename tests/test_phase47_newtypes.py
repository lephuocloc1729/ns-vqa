"""Phase 4.7: the parser v12 new-types test (eval/parser_newtypes.py, gold_v12_new.yaml): three groups
(train, owner-written, assistant-written); only train and owner-written decide. No API call."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from eval import parser_newtypes as pn
from eval.parser_eval import gold_query
from vqa.parsing import validator
from vqa.parsing.prompt import examples
from vqa.reasoning.engine import Engine

NEW_INTENTS = {"count", "count_is", "applies_to", "sign_applies", "rule_permitted", "duties", "signal_meaning",
               "marking_meaning", "marking_is"}
OWNER_FILE = Path(pn.GOLD).parent / "owner_questions.txt"


def rows(src=None):
    return [r for r in pn.load() if src is None or r["source"] == src]


def test_groups_and_sizes():
    n = Counter(r["source"] for r in rows())
    assert n == {"train": 6, "assistant_written": 50, "owner_written": 50}
    smoke = Counter(r["intent"] for r in rows() if r["source"] != "owner_written")
    assert set(smoke) == NEW_INTENTS and min(smoke.values()) >= 5
    own = Counter(r["intent"] for r in rows("owner_written") if not r.get("gap"))
    assert set(own) == NEW_INTENTS
    # 3 of the 5 owner duties questions are DSL gaps, so only duties has fewer than 3
    assert {k for k, v in own.items() if v < 3} == {"duties"}


def test_programs_are_valid():
    engine = Engine()
    for r in rows():
        for prog in [r["program"]] + r.get("also_accept", []):
            q = gold_query(prog)
            assert validator.check(q, engine) == [], r["id"]
        if r["source"] == "assistant_written":
            assert gold_query(r["program"]).program.intent == r["intent"], r["id"]
        if r.get("gap"):
            assert gold_query(r["program"]).out_of_scope, r["id"]


def test_owner_questions_are_verbatim_and_complete():
    lines = OWNER_FILE.read_text(encoding="utf-8").splitlines()
    own = rows("owner_written")
    for r in own:
        t, q = [x.strip() for x in lines[r["line"] - 1].split("|", 1)]
        assert (t, q) == (r["intent"], r["question"]), r["id"]
    listed = [l for l in lines if l.strip() and not l.lstrip().startswith("#")]
    assert len(listed) == len(own)


def test_train_rows_keep_ids_only_and_are_outside_dev_validation_and_fewshots():
    bad_q, _ = pn.refused_ids()
    shots = {e["id"] for e in examples("v12")}
    for r in rows("train"):
        assert "question" not in r and r["id"] not in bad_q and r["id"] not in shots, r["id"]
    if pn.TRAIN.exists():
        assert len(pn.questions(rows())) == len(rows())


def test_a_dev_question_is_refused(tmp_path):
    bad_q, _ = pn.refused_ids()
    qid = sorted(bad_q)[0]
    bad = [{"id": qid, "source": "train", "intent": "count", "program": {"program": {"intent": "count"}}}]
    train = tmp_path / "train.json"
    train.write_text(json.dumps([{"id": qid, "image_id": "x", "question": "q"}]), encoding="utf-8")
    with pytest.raises(SystemExit, match="refused"):
        pn.questions(bad, train)


def _right(rs):
    return [{"id": r["id"], "status": "ok", "query": gold_query(r["program"]).model_dump(mode="json")} for r in rs]


def test_all_right_keeps_every_type_on_and_gaps_apart():
    s = pn.score(_right(rows()), rows())
    assert set(s["groups"]) == {"train", "owner_written", "assistant_written"}
    assert s["decision"]["duties"].startswith("not decided") and not s["weaker_intents"]
    assert all(v == "stays on" for k, v in s["decision"].items() if k != "duties")
    assert len(s["gaps"]) == sum(1 for r in rows() if r.get("gap")) and all(g["parsed_out_of_scope"] for g in s["gaps"])


def test_also_accept_counts_as_right():
    r = next(x for x in rows("owner_written") if x.get("also_accept"))
    alt = {"id": r["id"], "status": "ok", "query": gold_query(r["also_accept"][0]).model_dump(mode="json")}
    s = pn.score([alt], [r])
    assert not s["misses"]


def test_only_deciding_groups_turn_a_type_off():
    """Assistant-written signal_meaning all wrong: still on. Owner-written signal_meaning all wrong: listed."""
    rs = rows()
    def wrong(src):
        return [p if not any(x["id"] == p["id"] and x["source"] == src and x["intent"] == "signal_meaning" for x in rs)
                else {**p, "query": None, "status": "parse_failed"} for p in _right(rs)]
    assert pn.score(wrong("assistant_written"), rs)["decision"]["signal_meaning"] == "stays on"
    assert pn.score(wrong("owner_written"), rs)["weaker_intents"] == ["signal_meaning"]


def test_estimates_and_caps():
    all_ = pn.estimate(rows())
    deciding = pn.estimate(pn.select(rows(), ["train", "owner_written"]))
    assert all_["questions"] == 106 and deciding["questions"] == 56
    for e in (all_, deciding):
        assert e["range_usd"][1] + 0.09 <= e["cap_usd"]
