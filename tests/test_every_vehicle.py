"""every_vehicle: claims about "các loại xe" / "mọi phương tiện" hold only if they hold
for every vehicle class. `vehicle` keeps meaning "a vehicle of unknown kind"."""

import datetime as dt

import pytest

from vqa.reasoning.engine import EngineError
from vqa.schemas import (
    AllOf, ChoiceOption, Choose, Forbidden, LanesFor, Permitted, Verdict, Verify, When,
)

from conftest import V, articles, scene, sign, times

EVERY = V("every_vehicle")


def at(h):
    return When(time=dt.time(h))


def permitted(engine, sc, action, vehicle=EVERY, **kw):
    return engine.answer(sc, Permitted(action=action, vehicle=vehicle, **kw))


def test_every_vehicle_may_stop_and_park(engine):
    # "Các loại xe được dừng và đỗ vào lúc 12 giờ trưa đúng hay sai?" -> Đúng
    sc = scene(sign("s1", "P.130", plates=[times(("06:00", "09:00"), ("16:00", "19:00"))]))
    claim = lambda h: AllOf(claims=[Permitted(action="stop", vehicle=EVERY, when=at(h)),
                                    Permitted(action="park", vehicle=EVERY, when=at(h))])
    a = engine.answer(sc, Verify(claim=claim(12)))
    assert a.verdict == Verdict.yes and {"22", "B.30", "F.10"} <= articles(a)
    b = engine.answer(sc, Verify(claim=claim(7)))
    assert b.verdict == Verdict.no


def test_counterexamples_reported_at_the_broadest_level(engine):
    a = permitted(engine, scene(sign("s1", "P.104")), "enter")
    assert a.verdict == Verdict.no
    assert a.value["counterexamples"] == ["motorbike"] and "B.4" in articles(a)


def test_forbidden_for_every_vehicle_is_not_negated_permitted(engine):
    # P.101 bans every vehicle; P.104 bans only motorbikes
    assert engine.answer(scene(sign("s1", "P.101")),
                         Forbidden(action="enter", vehicle=EVERY)).verdict == Verdict.yes
    assert engine.answer(scene(sign("s1", "P.104")),
                         Forbidden(action="enter", vehicle=EVERY)).verdict == Verdict.no
    # pedestrians are not vehicles: P.112 does not ban every vehicle
    assert engine.answer(scene(sign("s1", "P.112")),
                         Forbidden(action="enter", vehicle=EVERY)).verdict == Verdict.no


def test_unknown_and_no_signs(engine):
    sc = scene(sign("s1", "P.104", plates=[times(("06:00", "09:00"))]))
    assert permitted(engine, sc, "enter").verdict == Verdict.unknown       # time not given
    assert permitted(engine, sc, "enter", when=at(12)).verdict == Verdict.yes
    assert permitted(engine, scene(), "enter").verdict == Verdict.yes


def test_vehicle_still_means_unknown_kind(engine):
    sc = scene(sign("s1", "P.104"))
    assert permitted(engine, sc, "enter", vehicle=V("vehicle")).verdict == Verdict.unknown
    assert permitted(engine, sc, "enter").verdict == Verdict.no


def test_attribute_dependent_classes_count_as_unknown(engine):
    # P.106b also bans tractors and special machines outright -> a clear counterexample
    a = permitted(engine, scene(sign("s1", "P.106b", value=2.5)), "enter")
    assert a.verdict == Verdict.no and a.value["counterexamples"] == ["special_machine"]
    # P.107a only bans coaches above a seat count: depends on the coach -> unknown
    b = permitted(engine, scene(sign("s1", "P.107a", value=29)), "enter")
    assert b.verdict == Verdict.unknown and b.value["unknown"] == ["coach"]


def test_every_vehicle_inside_choose_and_with_forbidden(engine):
    sc = scene(sign("s1", "P.104", plates=[times(("06:00", "09:00"))]))
    a = engine.answer(sc, Choose(options=[
        ChoiceOption(label="mọi xe bị cấm lúc 7h",
                     claim=Forbidden(action="enter", vehicle=EVERY, when=at(7))),
        ChoiceOption(label="mọi xe được đi lúc 12h",
                     claim=Permitted(action="enter", vehicle=EVERY, when=at(12)))]))
    assert a.value["holding"] == ["mọi xe được đi lúc 12h"]


def test_every_vehicle_only_in_claims(engine):
    with pytest.raises(EngineError):
        engine.answer(scene(sign("s1", "P.104")), LanesFor(vehicle=EVERY))
