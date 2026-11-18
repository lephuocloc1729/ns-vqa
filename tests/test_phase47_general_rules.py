"""Phase 4.7 step 1c (owner, 2026-11-17: additive only): Law 36/2024's general rules through
`rule_permitted` (kb/rules/general47.pl): art. 13.3 lanes, 14.6 overtaking, 15.4 U-turns, 18.4
stopping and parking, 25 expressways, 27.4 priority vehicles, and Circular 38 art. 7 (interpretation).
Hand-made scenes modelled on train question forms; no API call."""

from __future__ import annotations

import pytest

from vqa.parsing.wire import from_wire, to_query
from vqa.reasoning.engine import Engine
from vqa.schemas import Position, Road, RulePermitted, SceneGraph, Sign, Vehicle, Verdict, Verify

EMPTY = SceneGraph(scene_id="x", signs=[])


@pytest.fixture(scope="module")
def engine():
    return Engine()


def V(c, **kw):
    return Vehicle(**{"class": c, **kw})


def S(sid, code, value=None, shape="circle", border="red", bg="white"):
    return Sign(id=sid, code=code, value=value, confidence="high", shape=shape, border=border, background=bg,
                position=Position(rank_top_down=1, side="right"))


def arts(a):
    return {(c.law_id, c.article_id) for c in a.citations}


L36 = "36/2024/QH15"


@pytest.mark.parametrize("action,place,art", [
    ("u_turn", "bridge", "15"), ("u_turn", "tunnel", "15"), ("u_turn", "expressway", "15"),
    ("u_turn", "one_way_road", "15"), ("u_turn", "pedestrian_crossing", "15"),
    ("overtake", "tunnel", "14"), ("overtake", "intersection", "14"), ("overtake", "narrow_one_lane_bridge", "14"),
    ("stop", "bridge", "18"), ("park", "under_overpass", "18"), ("stop", "pedestrian_crossing", "18"),
    ("park", "intersection", "18"), ("stop", "pickup_point", "18"), ("park", "one_way_road_left_side", "18"),
    ("enter", "emergency_lane", "25"),
])
def test_the_law_lists_these_places(engine, action, place, art):
    a = engine.answer(EMPTY, RulePermitted(action=action, place=place))
    assert a.verdict is Verdict.no and (L36, art) in arts(a)


def test_a_place_outside_the_list_is_allowed_with_its_article(engine):
    """Turning left in a tunnel: art. 15.4 bans U-turns there, not turns."""
    a = engine.answer(EMPTY, RulePermitted(action="turn_left", place="tunnel"))
    assert a.verdict is Verdict.yes
    a = engine.answer(EMPTY, RulePermitted(action="u_turn", place="intersection"))
    assert a.verdict is Verdict.yes and (L36, "15") in arts(a)


def test_a_sign_ban_still_says_no(engine):
    """P.124a at a place the law doesn't list: the sign decides (B.24)."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.124a")])
    assert engine.answer(scene, RulePermitted(action="u_turn", place="intersection")).verdict is Verdict.no


def test_a_permitting_sign_makes_the_ban_unknown(engine):
    """18.4 c "trừ những trường hợp tổ chức giao thông cho phép": an I.408 parking sign on a bridge."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", "I.408", shape="square", border="none", bg="blue")])
    assert engine.answer(scene, RulePermitted(action="park", place="bridge")).verdict is Verdict.unknown


def test_emergency_lane_stop_depends_on_the_reason(engine):
    """Art. 25.2: only on a breakdown ("dừng ở làn khẩn cấp để nghe điện thoại" is a violation)."""
    assert engine.answer(EMPTY, RulePermitted(action="stop", place="emergency_lane",
                                              stop_reason="other")).verdict is Verdict.no
    assert engine.answer(EMPTY, RulePermitted(action="stop", place="emergency_lane",
                                              stop_reason="breakdown")).verdict is Verdict.yes
    assert engine.answer(EMPTY, RulePermitted(action="stop", place="emergency_lane")).verdict is Verdict.unknown


def test_rudimentary_vehicles_keep_to_the_rightmost_lane(engine):
    """Art. 13.3 "xe thô sơ phải đi trên làn đường bên phải trong cùng"."""
    three = SceneGraph(scene_id="x", road=Road(lanes=3), signs=[])
    assert engine.answer(three, RulePermitted(vehicle=V("bicycle"), lane=1)).verdict is Verdict.no
    assert engine.answer(three, RulePermitted(vehicle=V("bicycle"), lane=-1)).verdict is Verdict.yes
    assert engine.answer(three, RulePermitted(vehicle=V("car"), lane=1)).verdict is Verdict.yes
    no_count = RulePermitted(vehicle=V("bicycle"), lane=-1)
    assert engine.answer(EMPTY, no_count).verdict is Verdict.unknown


def test_priority_vehicles_on_duty_are_not_speed_limited(engine):
    """Art. 27.4 "không bị hạn chế tốc độ": an ambulance on duty at 70 under a 50 limit."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.127", value=50)])
    a = engine.answer(scene, RulePermitted(speed_kmh=70, vehicle=V("motor_vehicle", priority=True)))
    assert a.verdict is Verdict.yes and (L36, "27") in arts(a)
    assert engine.answer(scene, RulePermitted(speed_kmh=70)).verdict is Verdict.no


def test_circular38_outside_residential_limits(engine):
    """Interpretation r_c38_outside: a car at 85 on an undivided road (80) breaks it, on a divided
    road (90) does not. Shown in the proof, never cited as law."""
    car = V("passenger_car")
    a = engine.answer(EMPTY, RulePermitted(speed_kmh=85, vehicle=car, area="outside_residential", road_divided=False))
    assert a.verdict is Verdict.no and not a.citations
    assert any("c38_outside_limit" in (r.proof.goal or "") for r in a.reasons)
    ok = RulePermitted(speed_kmh=85, vehicle=car, area="outside_residential", road_divided=True)
    assert engine.answer(EMPTY, ok).verdict is Verdict.yes


def test_circular38_needs_the_vehicle_group(engine):
    """A truck of unstated payload: the group (up to / over 3.5 t) is unknown, so the answer is."""
    p = RulePermitted(speed_kmh=85, vehicle=V("truck"), area="outside_residential", road_divided=True)
    assert engine.answer(EMPTY, p).verdict is Verdict.unknown
    # owner's check (2026-11-17): the group goes by payload, so a 10 t payload (not gross mass) is group 2
    p = RulePermitted(speed_kmh=85, vehicle=V("truck", load_t=10), area="outside_residential", road_divided=True)
    assert engine.answer(EMPTY, p).verdict is Verdict.no


def test_a_posted_limit_overrides_circular38(engine):
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.127", value=100)])
    p = RulePermitted(speed_kmh=85, vehicle=V("passenger_car"), area="outside_residential", road_divided=False)
    assert engine.answer(scene, p).verdict is Verdict.yes


def test_wire_form_and_verify(engine):
    q = to_query(from_wire({"program": {"intent": "rule_permitted", "action": "u_turn", "place": "bridge"}}), 2025)
    assert isinstance(q.program, RulePermitted) and q.defaults_applied == ["vehicle"]
    assert engine.answer(EMPTY, Verify(claim=q.program, expect=False)).verdict is Verdict.yes


@pytest.mark.parametrize("topic,art", [("lane_change", "13"), ("overtaking", "14"), ("turning", "15"),
                                       ("stopping_parking", "18"), ("expressway", "25"),
                                       ("priority_vehicle_signal", "27"), ("speed_and_distance", "12")])
def test_duties_cite_their_article(engine, topic, art):
    from vqa.schemas import Duties
    a = engine.answer(EMPTY, Duties(topic=topic))
    assert a.verdict is Verdict.value and a.value["duties"] and (L36, art) in arts(a)


# ---------------------------------------------------------------- Circular 38 groups (owner's check)

def _c38(engine, veh, speed=75, divided=True):
    p = RulePermitted(speed_kmh=speed, vehicle=veh, area="outside_residential", road_divided=divided)
    return engine.answer(EMPTY, p).verdict


def test_circular38_trucks_go_by_payload_not_gross_mass(engine):
    """Art. 7 (believed) groups trucks by "khối lượng hàng chuyên chở" (payload). 85 km/h on a divided
    road: payload 3 t is group 1 (90) -> yes; payload 5 t is group 2 (80) -> no."""
    assert _c38(engine, V("truck", load_t=3), 85) is Verdict.yes
    assert _c38(engine, V("truck", load_t=5), 85) is Verdict.no
    assert _c38(engine, V("truck", load_gt=3.5), 85) is Verdict.no


def test_circular38_gross_mass_only_bounds_the_payload(engine):
    """Gross 3 t means payload at most 3 t (B.15): group 1. Gross 10 t says nothing about payload."""
    assert _c38(engine, V("truck", gross_t=3), 85) is Verdict.yes
    assert _c38(engine, V("truck", gross_t=10), 85) is Verdict.unknown


def test_circular38_coaches_need_their_seat_count(engine):
    assert _c38(engine, V("coach"), 85) is Verdict.unknown
    assert _c38(engine, V("coach", seats=45), 85) is Verdict.no          # > 28 seats: group 2, 80
    assert _c38(engine, V("coach", seats=16), 85) is Verdict.yes         # <= 28 seats: group 1, 90
    assert _c38(engine, V("coach", seats_gt=29), 85) is Verdict.no


def test_circular38_ambiguous_classes_stay_unknown(engine):
    """`bus` may be a coach or a city bus; group 4's vehicles (tankers, mixers, trailer towing) have
    no class, so nothing is placed in group 4."""
    assert _c38(engine, V("bus"), 65) is Verdict.unknown
    assert _c38(engine, V("city_bus"), 75) is Verdict.no                 # group 3, 70
    assert _c38(engine, V("motorbike"), 65, divided=False) is Verdict.no  # group 3 undivided, 60


# ---------------------------------------------------------------- tunnel stops, reversing (owner, 2026-11-18)

@pytest.mark.parametrize("action", ["stop", "park"])
def test_no_stopping_or_parking_in_a_tunnel(engine, action):
    """Law 36 art. 26.2 "Không dừng xe, đỗ xe trong hầm đường bộ", unless a breakdown or force majeure
    forces it (the emergency-lane pattern: no reason stated gives unknown)."""
    other = engine.answer(EMPTY, RulePermitted(action=action, place="tunnel", stop_reason="other"))
    assert other.verdict is Verdict.no and (L36, "26") in arts(other)
    breakdown = engine.answer(EMPTY, RulePermitted(action=action, place="tunnel", stop_reason="breakdown"))
    assert breakdown.verdict is Verdict.yes and (L36, "26") in arts(breakdown)
    assert engine.answer(EMPTY, RulePermitted(action=action, place="tunnel")).verdict is Verdict.unknown


@pytest.mark.parametrize("place", ["one_way_road", "no_stopping_zone", "pedestrian_crossing", "intersection",
                                   "railway_crossing", "limited_view", "tunnel", "expressway",
                                   "curve_limited_view", "hill_crest_limited_view"])
def test_reversing_is_banned_where_art16_lists(engine, place):
    """Art. 16.2 "Không được lùi xe ở đường một chiều, khu vực cấm dừng, ... trong hầm đường bộ, trên đường
    cao tốc"."""
    a = engine.answer(EMPTY, RulePermitted(maneuver="reverse", place=place, vehicle=V("car")))
    assert a.verdict is Verdict.no and (L36, "16") in arts(a)


def test_reversing_elsewhere_is_allowed_and_needs_a_place(engine):
    a = engine.answer(EMPTY, RulePermitted(maneuver="reverse", place="bridge"))
    assert a.verdict is Verdict.yes and (L36, "16") in arts(a)
    assert engine.answer(EMPTY, RulePermitted(maneuver="reverse")).verdict is Verdict.unknown


def test_reverse_ignores_markings_and_lights(engine):
    from vqa.schemas import RoadMarking, TrafficSignal
    scene = SceneGraph(scene_id="x", road=Road(markings=[RoadMarking(kind="center", pattern="double_solid")]),
                       signals=[TrafficSignal(colour="red")], signs=[])
    assert engine.answer(scene, RulePermitted(maneuver="reverse", place="bridge")).verdict is Verdict.yes


def test_wire_reverse():
    q = to_query(from_wire({"program": {"intent": "rule_permitted", "maneuver": "reverse", "place": "intersection",
                                        "vehicle": {"vehicle_class": "car"}}}), 2025)
    assert q.program.maneuver == "reverse" and q.program.place.value == "intersection"
