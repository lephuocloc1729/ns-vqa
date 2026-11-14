"""The meta-interpreter's proof trees, and sign identity questions."""

import janus_swi as janus

from vqa.reasoning import explain
from vqa.schemas import Meaning, Permitted, Selector, Verdict

from conftest import V, scene, sign, times


def test_proof_tree_shape(engine):
    sc = scene(sign("s1", "P.104", plates=[times(("06:00", "09:00"))]))
    a = engine.answer(sc, Permitted(action="enter", vehicle=V("motorbike"),
                                    when={"time": "07:00"}))
    [reason] = a.reasons
    root = reason.proof
    assert root.type == "rule" and root.goal.startswith("forbids(enter,")
    nodes = list(explain.walk(root))
    # the catalog fact is cited with the sign's own article
    facts = [n for n in nodes if n.type == "fact" and n.goal.startswith("prohibits(p104")]
    assert facts and facts[0].source.article_id == "B.4"
    assert set(explain.rules_fired(root)) >= {"r_prohibition", "r_time_plate"}
    # negation-as-failure steps are kept (no vehicle plate, no end-of-restriction sign)
    assert any(n.type == "naf" for n in nodes)
    assert "cite r_time_plate" in explain.render(root)


def test_permitted_answer_has_a_clearing_proof(engine):
    a = engine.answer(scene(sign("s1", "P.104")),
                      Permitted(action="enter", vehicle=V("passenger_car")))
    assert a.verdict == Verdict.yes
    [r] = a.reasons
    assert (r.sign_id, r.truth, r.detail) == ("s1", "false", "vehicle_not_covered")
    assert r.proof.goal.startswith("clears(enter,")
    assert {"22", "B.4"} <= {c.article_id for c in a.citations}


def test_meta_interpreter_directly(engine):
    r = janus.query_once("prove(subclass_of(taxi, car), _P), proof_dicts(_P, D)")
    assert r["truth"]
    [root] = r["D"]
    assert root["goal"] == "subclass_of(taxi,car)"
    assert [c["goal"] for c in root["children"]][0] == "is_a(taxi,passenger_car)"


def test_meaning_of_only_sign(engine):
    sc = scene(sign("s1", "P.124c"))
    a = engine.answer(sc, Meaning(sign=Selector(only=True)))
    assert a.verdict == Verdict.value
    assert a.value[0]["name_vi"] == "Cấm rẽ trái và quay đầu xe"
    assert [c.article_id for c in a.citations] == ["B.24"]


def test_meaning_by_appearance(engine):
    # "biển viền đỏ, nền trắng ở trên cùng"
    sc = scene(sign("s1", "P.127", value=60, border="red", background="white",
                    position={"rank_top_down": 1}),
               sign("s2", "R.306", value=40, background="blue", position={"rank_top_down": 2}),
               sign("s3", "P.124a", border="red", background="white",
                    position={"rank_top_down": 3}))
    a = engine.answer(sc, Meaning(sign=Selector(border="red", background="white", position="top")))
    assert [v["code"] for v in a.value] == ["P.127"]


def test_unknown_sign_code_stays_unknown(engine):
    sc = scene(sign("s1", "UNKNOWN"))
    assert engine.answer(sc, Meaning(sign=Selector(only=True))).verdict == Verdict.unknown
