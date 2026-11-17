"""Phase 4.7 (owner, 2026-11-17: finish the matrix's "to build" cells, additive): R.415b's scope and
placement, R.411's addressees, pictured vehicles against zones, lane arrows, lights and markings,
turn lanes from arrows, and art. 51 for markings. Hand-made scenes; no API call."""

from __future__ import annotations

import pytest

from vqa.kb import load_catalog
from vqa.reasoning import sign_info as si
from vqa.reasoning.engine import Engine
from vqa.schemas import (AppliesTo, ChoiceOption, Choose, ExistsViolation, LaneSpec, MarkingMeaning, Meaning,
                         Permitted, Position, Road, RoadMarking, SceneGraph, SceneVehicle, Selector, Sign,
                         TrafficSignal, Vehicle, Verdict)


@pytest.fixture(scope="module")
def engine():
    return Engine()


def S(sid, code, shape="rectangle", border="none", bg="blue", lanes=()):
    return Sign(id=sid, code=code, confidence="high", shape=shape, border=border, background=bg,
                position=Position(rank_top_down=1, side="right"), lanes=list(lanes))


def veh(vid, cls, action, lane=None, speed=None):
    return SceneVehicle(**{"id": vid, "class": cls, "action": action, "lane": lane, "speed_kmh": speed})


def arts(a):
    return {c.article_id for c in a.citations}


# ---------------------------------------------------------------- R.415b, R.411

def test_end_of_lanes_by_vehicle_scope_and_placement_cite_d16(engine):
    scene = SceneGraph(scene_id="x", signs=[S("s1", "R.415b")])
    for aspect in ("scope", "placement"):
        a = engine.answer(scene, Meaning(sign=Selector(only=True), aspect=aspect))
        assert a.verdict is Verdict.value and "D.16" in arts(a), aspect
    assert si.conduct_out("R.415b")


def test_lane_arrow_board_is_addressed_to_every_road_user(engine):
    a = engine.answer(SceneGraph(scene_id="x", signs=[S("s1", "R.411")]), AppliesTo())
    assert a.verdict is Verdict.value and "vehicle" in a.value["applies_to"] and "31" in arts(a)


# ---------------------------------------------------------------- vehicles in the photo

def test_a_pictured_motorbike_driving_onto_an_expressway(engine):
    """Law 36 art. 25 entry ban via the IE.452 zone (KB-4)."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", "IE.452", bg="green")], vehicles=[veh("v1", "motorbike", "driving")])
    a = engine.answer(scene, ExistsViolation())
    assert a.verdict is Verdict.yes and any("zone" in d for d in a.value["violations"])
    ok = SceneGraph(scene_id="x", signs=[S("s1", "IE.452", bg="green")], vehicles=[veh("v1", "passenger_car", "driving")])
    assert engine.answer(ok, ExistsViolation()).verdict is not Verdict.yes


def test_a_pictured_vehicle_against_the_lane_arrows(engine):
    board = S("s1", "R.411", lanes=[LaneSpec(lane=1, directions=["left"]), LaneSpec(lane=2, directions=["straight"])])
    bad = SceneGraph(scene_id="x", road=Road(lanes=2), signs=[board], vehicles=[veh("v1", "car", "go_straight", lane=1)])
    a = engine.answer(bad, ExistsViolation())
    assert a.verdict is Verdict.yes and "D.13" in arts(a)
    good = SceneGraph(scene_id="x", road=Road(lanes=2), signs=[board], vehicles=[veh("v1", "car", "go_straight", lane=2)])
    assert engine.answer(good, ExistsViolation()).verdict is Verdict.no


def test_a_pictured_vehicle_at_a_red_light_is_unknown_not_a_violation(engine):
    """6.3.2: a photo doesn't show whether it passed the stop line before the light changed."""
    red = SceneGraph(scene_id="x", signals=[TrafficSignal(colour="red")], vehicles=[veh("v1", "car", "go_straight")])
    assert engine.answer(red, ExistsViolation()).verdict is Verdict.unknown
    green = SceneGraph(scene_id="x", signals=[TrafficSignal(colour="green")], vehicles=[veh("v1", "car", "go_straight")])
    assert engine.answer(green, ExistsViolation()).verdict is Verdict.no


def test_a_pictured_vehicle_crossing_a_line(engine):
    """G.1 1.3: no crossing a double solid centre line; 1.1: a dashed one may be crossed."""
    solid = SceneGraph(scene_id="x", road=Road(markings=[RoadMarking(kind="center", pattern="double_solid")]),
                       vehicles=[veh("v1", "car", "crossing_line")])
    a = engine.answer(solid, ExistsViolation())
    assert a.verdict is Verdict.yes and "G.1" in arts(a)
    dashed = SceneGraph(scene_id="x", road=Road(markings=[RoadMarking(kind="center", pattern="dashed")]),
                        vehicles=[veh("v1", "car", "crossing_line")])
    assert engine.answer(dashed, ExistsViolation()).verdict is Verdict.no


def test_a_pictured_vehicle_over_the_residential_default(engine):
    """R.420 starts the residential zone; Circular 38's default (interpretation r_c38_residential)."""
    scene = SceneGraph(scene_id="x", road=Road(divided=False), signs=[S("s1", "R.420", bg="white")],
                       vehicles=[veh("v1", "passenger_car", "driving", speed=70)])
    assert engine.answer(scene, ExistsViolation()).verdict is Verdict.yes


# ---------------------------------------------------------------- turn lanes, art. 51

def test_which_lane_to_turn_from_is_a_choice_over_lanes(engine):
    """"Muốn rẽ trái phải đi làn nào?" as a choose over the lanes with R.411 arrows (D.13)."""
    board = S("s1", "R.411", lanes=[LaneSpec(lane=1, directions=["left"]), LaneSpec(lane=2, directions=["straight"]),
                                    LaneSpec(lane=3, directions=["straight", "right"])])
    scene = SceneGraph(scene_id="x", road=Road(lanes=3), signs=[board])
    opts = [ChoiceOption(label=f"làn {i}", claim=Permitted(action="turn_left", vehicle=Vehicle(**{"class": "car"}), lane=i))
            for i in (1, 2, 3)]
    a = engine.answer(scene, Choose(options=opts))
    assert a.verdict is Verdict.value and a.value["holding"] == ["làn 1"]


def test_marking_meaning_states_art51(engine):
    scene = SceneGraph(scene_id="x", road=Road(markings=[RoadMarking(kind="center", pattern="solid")]))
    a = engine.answer(scene, MarkingMeaning())
    assert "Điều 4" in a.value["effect"] and "51" in arts(a)


def test_r415b_is_a_catalog_row():
    assert load_catalog().get("R.415b").source.article_id == "D.16"
