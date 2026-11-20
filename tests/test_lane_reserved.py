"""Parser v18 (owner, 2026-11-20): `lane_reserved_is`, "Làn X được dành riêng cho xe Y, đúng hay
sai?". Lane X is open to Y and closed to every other kind of vehicle. Hand-made scenes modelled
on train questions about lane boards (R.415a, D.16) and reserved lanes (R.412, D.14); no API call."""

from __future__ import annotations

import pytest

from tests.test_phase48c import BOARD, S, V, scene
from vqa.parsing.wire import from_wire, to_query
from vqa.reasoning.engine import Engine
from vqa.reasoning.facts import scene_facts
from vqa.schemas import LaneReservedIs, Verdict

BLUE = dict(shape="rectangle", border="none", background="blue")


@pytest.fixture(scope="module")
def engine():
    return Engine(reading_policy="higher_confidence")


def ask(engine, sc, lane, cls):
    return engine.answer(sc, LaneReservedIs(lane=lane, vehicle=V(cls)))


def articles(a):
    return {c.article_id for c in a.citations}


# ---------------------------------------------------------------- lane boards (R.415a, D.16)

def test_a_lane_only_cars_may_use_is_reserved_for_cars(engine):
    a = ask(engine, scene(BOARD), 1, "car")
    assert a.verdict is Verdict.yes and a.value["open_to_others"] == []
    assert "D.16" in articles(a)


def test_a_narrower_class_than_the_named_one_is_not_reserved(engine):
    """"dành riêng cho xe ô tô con" on a lane for all cars: lorries and buses may use it too, so no
    (the owner's decision in tests/test_fixes50.py for R.412f)."""
    a = ask(engine, scene(BOARD), 1, "passenger_car")
    assert a.verdict is Verdict.no and "truck" in a.value["open_to_others"]


def test_a_lane_shared_with_another_named_class_is_not_reserved(engine):
    """Lane 3 is for motorbikes and three-wheelers: not reserved for motorbikes."""
    a = ask(engine, scene(BOARD), 3, "motorbike")
    assert a.verdict is Verdict.no and a.value["open_to_others"] == ["motor_tricycle"]


def test_a_vehicle_closed_out_of_the_lane_gives_no(engine):
    a = ask(engine, scene(BOARD), 1, "motorbike")
    assert a.verdict is Verdict.no and "D.16" in articles(a)


def test_lanes_count_from_the_right_with_the_lane_count(engine):
    a = ask(engine, scene(BOARD), -1, "motorbike")
    assert a.value["lane"] == 4 and a.verdict is Verdict.no


def test_a_class_above_the_named_one_is_unknown(engine):
    """"xe cơ giới" on a car lane: some motor vehicles may use it, others not."""
    assert ask(engine, scene(BOARD), 1, "motor_vehicle").verdict is Verdict.unknown


# ---------------------------------------------------------------- reserved lanes (R.412, D.14)

def test_a_bus_and_coach_lane_is_reserved_for_every_kind_of_bus(engine):
    """"làn này chỉ dành cho xe buýt": R.412a is for coaches "kể cả ô tô buýt", so every kind of
    bus counts as one (owner, 2026-11-20); a truck is closed out."""
    sc = scene(S("s1", "R.412a", lanes=[(1, ["bus"]), (2, [])], **BLUE))
    for cls in ("city_bus", "coach", "bus"):
        a = ask(engine, sc, 1, cls)
        assert a.verdict is Verdict.yes and a.value["open_to_others"] == [], cls
        assert "D.14" in articles(a)
    a = ask(engine, sc, 1, "truck")
    assert a.verdict is Verdict.no and set(a.value["open_to_others"]) == {"bus", "city_bus", "coach"}


def test_the_bus_group_is_only_for_reserved_lanes(engine):
    """A lane board (R.415a) for buses keeps the narrower-class reading: a coach may use it too."""
    sc = scene(S("s1", "R.415a", lanes=[(1, ["bus"]), (2, ["car"])], **BLUE))
    a = ask(engine, sc, 1, "city_bus")
    assert a.verdict is Verdict.no and "coach" in a.value["open_to_others"]


def test_a_car_lane_stays_not_reserved_for_passenger_cars(engine):
    """R.412f (all cars): no for "ô tô con" (the owner's reading in tests/test_fixes50.py)."""
    sc = scene(S("s1", "R.412f", lanes=[(1, ["car"])], **BLUE))
    a = ask(engine, sc, 1, "passenger_car")
    assert a.verdict is Verdict.no and "truck" in a.value["open_to_others"]


def test_a_reserved_lane_listed_without_vehicles_takes_the_catalog_classes(engine):
    """An R.412c (truck lane) row with no vehicles is still the truck lane, not a lane open to all."""
    sc = scene(S("s1", "R.412c", lanes=[(1, [])], **BLUE))
    assert ask(engine, sc, 1, "truck").verdict is Verdict.yes
    a = ask(engine, sc, 1, "bus")
    assert a.verdict is Verdict.no and a.value["open_to_others"] == ["truck"]


def test_the_bare_row_gets_lane_vehicle_facts(engine):
    facts = [str(t) for t in scene_facts(scene(S("s1", "R.412c", lanes=[(1, [])], **BLUE)), engine.catalog)]
    assert any(f.startswith("lane_vehicle(") and "truck" in f for f in facts)


# ---------------------------------------------------------------- closed world and edges

def test_unknown_without_a_lane_count_or_outside_it(engine):
    assert ask(engine, scene(S("s1", "P.127", 60)), 1, "car").verdict is Verdict.unknown
    a = ask(engine, scene(BOARD), 5, "car")
    assert a.verdict is Verdict.unknown and "4 lanes" in a.note


def test_an_unreadable_sign_that_could_bear_on_lanes_makes_a_yes_unknown(engine):
    unread = S("s2", "UNKNOWN", shape="circle", border="red")
    a = ask(engine, scene(BOARD, unread), 1, "car")
    assert a.verdict is Verdict.unknown and a.uncertain_signs == ["s2"]


def test_wire_form_and_vehicle_default():
    q = to_query(from_wire({"program": {"intent": "lane_reserved_is", "lane": 1,
                                        "vehicle": {"vehicle_class": "car"}}}), 2026)
    assert isinstance(q.program, LaneReservedIs) and q.program.lane == 1
    q = to_query(from_wire({"program": {"intent": "lane_reserved_is", "lane": 2}}), 2026)
    assert q.defaults_applied == ["vehicle"]
