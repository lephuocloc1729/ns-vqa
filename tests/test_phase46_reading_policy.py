"""Phase 4.6 step 1 (owner, 2026-11-17, D1 = policy A): when alternative sign readings disagree,
answer with each sign's highest-confidence reading (a tie keeps the first reading). Hand-made
scenes modelled on train questions; no API call."""

from __future__ import annotations

import pytest

from vqa.reasoning.engine import Engine
from vqa.reasoning.facts import top_reading
from vqa.schemas import AltReading, BanTimes, Meaning, Position, SceneGraph, Selector, Sign, SpeedOk, Verdict

from conftest import V


@pytest.fixture(scope="module")
def frozen():
    return Engine()


@pytest.fixture(scope="module")
def policy_a():
    return Engine(reading_policy="higher_confidence")


def S(sid, code, conf, alts, rank=1, value=None, background="white"):
    return Sign(id=sid, code=code, value=value, confidence=conf, shape="circle", border="red",
                background=background, position=Position(rank_top_down=rank, side="right"),
                alternatives=[AltReading(code=c, confidence=k, value=v) for c, k, v in alts])


def ONLY(aspect):
    return Meaning(sign=Selector(only=True), aspect=aspect)


def test_unknown_policy_is_refused():
    with pytest.raises(ValueError):
        Engine(reading_policy="vote")


def test_medium_reading_beats_a_low_alternative(frozen, policy_a):
    """Modelled on "Biển trong ảnh cấm xe đi những hướng nào?": a U-turn disc read P.124a at
    medium, P.124c at low."""
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.124a", "medium", [("P.124c", "low", None)])])
    assert frozen.answer(sc, ONLY("conduct")).verdict is Verdict.uncertain
    a = policy_a.answer(sc, ONLY("conduct"))
    assert a.verdict is Verdict.value
    assert [o["code"] for o in a.value["conduct"]] == ["P.124a"]
    assert a.uncertain_signs == ["s1"] and "reading_choice" in a.basis
    assert "s1 P.124a" in a.note and "P.124c (low)" in a.note


def test_a_higher_confidence_alternative_wins():
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.124a", "low", [("P.124c", "medium", None)])])
    top, chosen, others = top_reading(sc)
    assert chosen == {"s1": "P.124c"} and top.sign("s1").code == "P.124c"
    assert top.sign("s1").alternatives == [] and others == {"s1": [("P.124a", "low")]}
    assert sc.sign("s1").code == "P.124a"                     # the input scene is not changed


def test_a_low_tie_keeps_the_first_reading(policy_a):
    """Modelled on "Biển trong ảnh cấm đỗ xe vào những ngày nào?" over P.131c / P.131b, both low."""
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.131c", "low", [("P.131b", "low", None)], background="blue")])
    a = policy_a.answer(sc, BanTimes(vehicle=V("motor_vehicle"), action="park", sign=Selector(only=True)))
    assert a.verdict is Verdict.value
    assert [b["days"] for b in a.value["bans"]] == ["even"]


def test_the_chosen_value_is_used(policy_a):
    """A speed disc read 50 (medium) or 60 (low): 55 km/h breaks the higher-confidence reading."""
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.127", "medium", [("P.127", "low", 60)], value=50)])
    a = policy_a.answer(sc, SpeedOk(vehicle=V("passenger_car"), speed_kmh=55))
    assert a.verdict is Verdict.no and "reading_choice" in a.basis


def test_agreeing_readings_are_unchanged(frozen, policy_a):
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.127", "low", [("P.127", "low", 60)], value=50)])
    q = SpeedOk(vehicle=V("passenger_car"), speed_kmh=70)
    a, b = frozen.answer(sc, q), policy_a.answer(sc, q)
    assert a.verdict is b.verdict is Verdict.no and b.basis == a.basis and b.note == a.note


def test_high_confidence_signs_are_not_touched():
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.102", "high", [("R.302a", "medium", None)])])
    top, chosen, _ = top_reading(sc)
    assert chosen == {} and top.sign("s1").code == "P.102"


def test_pipeline_switch_defaults_to_the_frozen_behaviour():
    from vqa.pipeline import PipelineConfig
    assert PipelineConfig().reading_policy == "all"
