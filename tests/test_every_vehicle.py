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
    assert a.value["counterexamples"] == [{"class": "motorbike", "condition": None}]
    assert "B.4" in articles(a)


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


def counter(a):
    return {c["class"]: c["condition"] for c in a.value["counterexamples"]}


def test_members_on_both_sides_are_counterexamples(engine):
    # P.107a bans coaches with more than 29 seats
    sc = scene(sign("s1", "P.107a", value=29))
    may = permitted(engine, sc, "enter")
    assert may.verdict == Verdict.no                    # coaches over 29 seats may not
    assert counter(may) == {"coach": "seats > 29"} and "B.7a" in articles(may)
    banned = engine.answer(sc, Forbidden(action="enter", vehicle=EVERY))
    assert banned.verdict == Verdict.no                 # most vehicles may enter


def test_forbidden_for_every_vehicle_with_a_weight_limit(engine):
    # P.115 bans every vehicle over 10 t gross: "every vehicle is banned" is false
    # (lighter vehicles may enter), and so is "every vehicle may enter".
    sc = scene(sign("s1", "P.115", value=10))
    banned = engine.answer(sc, Forbidden(action="enter", vehicle=EVERY))
    assert banned.verdict == Verdict.no
    assert counter(banned) == {"vehicle": "gross_t < 10"}
    may = permitted(engine, sc, "enter")
    assert may.verdict == Verdict.no and counter(may) == {"vehicle": "gross_t > 10"}


def test_weight_and_outright_counterexamples(engine):
    a = permitted(engine, scene(sign("s1", "P.106b", value=2.5)), "enter")
    assert a.verdict == Verdict.no
    assert counter(a) == {"truck": "load_t > 2.5", "special_machine": None}


def test_unknown_only_for_unknowns_in_the_scene(engine):
    # the coach answer also depends on the time, which the question does not give
    sc = scene(sign("s1", "P.107a", value=29, plates=[times(("06:00", "09:00"))]))
    assert permitted(engine, sc, "enter").verdict == Verdict.unknown
    assert permitted(engine, sc, "enter", when=at(7)).verdict == Verdict.no
    assert permitted(engine, sc, "enter", when=at(12)).verdict == Verdict.yes
    # an unreadable sign is unknown in the scene too
    assert permitted(engine, scene(sign("s1", "UNKNOWN")), "enter").verdict == Verdict.unknown


def test_stated_attributes_are_not_varied(engine):
    sc = scene(sign("s1", "P.107a", value=29))
    assert permitted(engine, sc, "enter", vehicle=V("every_vehicle", seats=16)).verdict == Verdict.yes


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
