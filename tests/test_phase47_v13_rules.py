"""Parser v13 (owner, 2026-11-18: additive only): the rules for the new types, on hand-made scenes.
kb/rules/v13_47.pl: the officer's gestures (Law 36 art. 11.3), which signalling means wins (11.2,
11.12; QCVN 41 art. 4), who yields (Law 36 art. 22; QCVN 41 D.1, C.7, C.8, E.1), vehicle classes
(art. 34); plus count bounds, relative selectors, P.116 and the joining-road duties. No API call."""

from __future__ import annotations

import pytest

from vqa.reasoning.engine import Engine
from vqa.schemas import (Anchor, CountIs, Duties, Forbidden, Meaning, MustYield, OfficerPermits, OfficerSignal,
                         Permitted, Position, Precedence, PrecedenceIs, RightOfWay, RulePermitted, SceneGraph,
                         Selector, Sign, TrafficSignal, Vehicle, VehicleClassIs, VehicleClassOf, Verdict, Verify)

L36, Q41 = "36/2024/QH15", "QCVN 41:2024/BGTVT"
EMPTY = SceneGraph(scene_id="x", signs=[])


@pytest.fixture(scope="module")
def engine():
    # every scene v6 field on: these test the rules; the owner's switch (kb/v6_fields_47.yaml,
    # signals off since 2026-11-18) is tested in test_phase47_v6_fields.py
    return Engine(v6_fields_off=())


def V(c, **kw):
    return Vehicle(**{"class": c, **kw})


def arts(a):
    return {(c.law_id, c.article_id) for c in a.citations}


def scene(*codes, signals=()):
    return SceneGraph(scene_id="s", signs=[Sign(id=f"s{i}", code=c) for i, c in enumerate(codes)],
                      signals=list(signals))


# ---------------------------------------------------------------- 6. the officer (Law 36 art. 11.3)

@pytest.mark.parametrize("gesture,side,action,want", [
    ("right_arm_up", None, "go_straight", Verdict.no),           # a) every direction stops
    ("right_arm_up", "left", "turn_right", Verdict.no),
    ("arms_sideways", "front", "go_straight", Verdict.no),       # b) front and back stop
    ("arms_sideways", "back", "turn_left", Verdict.no),
    ("arms_sideways", "left", "go_straight", Verdict.yes),       # b) the sides "được đi"
    ("arms_sideways", "right", "turn_left", Verdict.unknown),    # "được đi" names no direction
    ("arms_sideways", None, "go_straight", Verdict.unknown),     # side not stated
    ("right_arm_forward", "front", "turn_right", Verdict.yes),   # c) "được rẽ phải"
    ("right_arm_forward", "front", "go_straight", Verdict.no),   # interpretation: only the right turn
    ("right_arm_forward", "left", "u_turn", Verdict.yes),        # c) "đi tất cả các hướng"
    ("right_arm_forward", "back", "go_straight", Verdict.no),
    ("right_arm_forward", "right", "turn_right", Verdict.no),
])
def test_officer_gestures(engine, gesture, side, action, want):
    a = engine.answer(EMPTY, OfficerPermits(gesture=gesture, side=side, action=action))
    assert a.verdict is want
    if want is not Verdict.unknown or side:
        assert (L36, "11") in arts(a)


def test_officer_front_only_right_cites_the_interpretation(engine):
    a = engine.answer(EMPTY, OfficerPermits(gesture="right_arm_forward", side="front", action="go_straight"))
    assert a.verdict is Verdict.no
    assert any("r_officer_right_turn_only" in str(r.proof) for r in a.reasons)
    assert all(c.law_id != "interpretation" for c in a.citations)


def test_officer_meaning_and_an_obligation_asked_yes_no(engine):
    m = engine.answer(EMPTY, OfficerSignal(gesture="arms_sideways", side="back"))
    assert m.verdict is Verdict.value and m.value["your_side"]["says"] == "stop"
    assert m.value["by_side"] == {"front": "stop", "back": "stop", "left": "go", "right": "go"}
    must_stop = Verify(claim=OfficerPermits(gesture="arms_sideways", side="front"), expect=False)
    assert engine.answer(EMPTY, must_stop).verdict is Verdict.yes


# ---------------------------------------------------------------- 9. precedence (11.2, 11.12; QCVN art. 4)

@pytest.mark.parametrize("a,b,winner", [("light", "officer", "officer"), ("sign", "light", "light"),
                                        ("marking", "sign", "sign"), ("roadside_device", "marking", "marking"),
                                        ("sound_device", "roadside_device", "roadside_device"),
                                        ("permanent_sign", "temporary_sign", "temporary_sign")])
def test_precedence_order(engine, a, b, winner):
    ans = engine.answer(EMPTY, Precedence(between=[a, b]))
    assert ans.verdict is Verdict.value and ans.value["follow"] == winner
    assert (L36, "11") in arts(ans) and (Q41, "4") in arts(ans)
    assert engine.answer(EMPTY, PrecedenceIs(winner=winner, over=a if winner == b else b)).verdict is Verdict.yes
    assert engine.answer(EMPTY, PrecedenceIs(winner=a if winner == b else b, over=winner)).verdict is Verdict.no


def test_precedence_unranked_pair_is_unknown(engine):
    assert engine.answer(EMPTY, PrecedenceIs(winner="sign", over="temporary_sign")).verdict is Verdict.unknown
    assert engine.answer(EMPTY, Precedence(between=["sign", "permanent_sign"])).verdict is Verdict.unknown


def test_a_green_arrow_overrides_a_turn_ban_but_a_round_green_does_not(engine):
    arrow = scene("P.123a", signals=[TrafficSignal(colour="green", arrow="left")])
    a = engine.answer(arrow, RulePermitted(action="turn_left", at_signal=True))
    assert a.verdict is Verdict.yes and (Q41, "4") in arts(a)
    round_green = scene("P.123a", signals=[TrafficSignal(colour="green")])
    assert engine.answer(round_green, RulePermitted(action="turn_left", at_signal=True)).verdict is Verdict.no
    red_arrow = scene("P.123a", signals=[TrafficSignal(colour="red", arrow="left")])
    assert engine.answer(red_arrow, RulePermitted(action="turn_left", at_signal=True)).verdict is Verdict.no
    # an arrow for another direction overrides nothing
    other = scene("P.123a", signals=[TrafficSignal(colour="green", arrow="right")])
    assert engine.answer(other, RulePermitted(action="turn_left", at_signal=True)).verdict is not Verdict.yes
    # permitted reads the signs only, as before
    assert engine.answer(arrow, Permitted(action="turn_left", vehicle=V("car"))).verdict is Verdict.no


# ---------------------------------------------------------------- 8. who yields (Law 36 art. 22)

@pytest.mark.parametrize("codes,other,want,art", [
    (("R.122",), "cross_road", Verdict.yes, (Q41, "D.1")),
    (("W.208",), "right", Verdict.yes, (Q41, "C.8")),
    (("W.208",), "branch_road", Verdict.unknown, (Q41, "C.8")),
    (("I.401",), "right", Verdict.no, (Q41, "E.1")),
    (("W.207c",), "cross_road", Verdict.no, (Q41, "C.7")),
    (("W.207c",), "main_road", Verdict.unknown, (Q41, "C.7")),
    ((), "right", Verdict.yes, (L36, "22")),              # 22.2: yield to the right
    ((), "left", Verdict.no, (L36, "22")),
    ((), None, Verdict.unknown, (L36, "22")),
    (("R.303",), "left", Verdict.yes, (L36, "22")),       # 22.3: a roundabout, yield to the left
    (("W.206",), "right", Verdict.no, (L36, "22")),
])
def test_must_yield_from_the_approach_signs(engine, codes, other, want, art):
    a = engine.answer(scene(*codes), MustYield(other_from=other))
    assert a.verdict is want and art in arts(a)


def test_must_yield_from_the_question_facts(engine):
    assert engine.answer(EMPTY, MustYield(other_from="main_road", my_road="branch")).verdict is Verdict.yes
    assert engine.answer(EMPTY, MustYield(other_from="branch_road", my_road="main")).verdict is Verdict.no
    assert engine.answer(EMPTY, MustYield(other_from="left", roundabout=True)).verdict is Verdict.yes
    # facts that disagree with the signs, or a light that decides instead: unknown
    assert engine.answer(scene("R.122"), MustYield(other_from="right", my_road="main")).verdict is Verdict.unknown
    assert engine.answer(scene("R.122", "I.401"), MustYield(other_from="right")).verdict is Verdict.unknown
    lit = scene("W.208", signals=[TrafficSignal(colour="red")])
    a = engine.answer(lit, MustYield(other_from="right"))
    assert a.verdict is Verdict.unknown and (Q41, "E.1") in arts(a)


def test_right_of_way_value(engine):
    assert engine.answer(scene("R.122"), RightOfWay()).value["rule"] == "you_yield_to_the_major_road"
    assert engine.answer(scene("I.401"), RightOfWay()).value["rule"] == "others_yield_to_you"
    assert engine.answer(EMPTY, RightOfWay()).value["rule"] == "yield_to_vehicles_from_the_right"
    assert engine.answer(EMPTY, RightOfWay(roundabout=True)).value["rule"] == "yield_to_vehicles_from_the_left"
    assert engine.answer(scene("W.208", "W.207c"), RightOfWay()).verdict is Verdict.unknown


# ---------------------------------------------------------------- 10. vehicle classes (Law 36 art. 34)

@pytest.mark.parametrize("veh,target,want", [
    (V("motorbike", design_speed_kmh=45, motor_kw=3), "moped", Verdict.yes),
    (V("motorbike", design_speed_kmh=45, motor_kw=5), "moped", Verdict.no),
    (V("motorbike", design_speed_kmh=60, engine_cc=110), "moped", Verdict.no),
    (V("motorbike", design_speed_kmh=60, engine_cc=110), "motorcycle", Verdict.yes),
    (V("motorbike", design_speed_kmh=45, engine_cc=50), "moped", Verdict.yes),
    (V("motorbike", design_speed_kmh=45), "moped", Verdict.unknown),       # the engine is not stated
    (V("motorbike"), "motorcycle", Verdict.unknown),
    (V("truck"), "car", Verdict.yes),
    (V("truck"), "motor_vehicle", Verdict.yes),
    (V("car"), "motorbike", Verdict.no),
    (V("car"), "taxi", Verdict.unknown),                                   # a broader class
    (V("bicycle"), "rudimentary", Verdict.yes),
])
def test_vehicle_class_is(engine, veh, target, want):
    a = engine.answer(EMPTY, VehicleClassIs(vehicle=veh, of_class=target))
    assert a.verdict is want and (L36, "34") in arts(a)


def test_vehicle_class_value(engine):
    a = engine.answer(EMPTY, VehicleClassOf(vehicle=V("car", seats=16)))
    assert a.value["classes"] == ["car", "motor_vehicle", "vehicle"] and (L36, "34") in arts(a)
    m = engine.answer(EMPTY, VehicleClassOf(vehicle=V("motorbike", design_speed_kmh=40, motor_kw=2)))
    assert m.value["classes"][0] == "moped"


# ---------------------------------------------------------------- 11. size checks

@pytest.mark.parametrize("code,attr,value,ok,bad", [
    ("P.116", "axle_t", 10, 8, 12),        # B.16 (new row)
    ("P.118", "width_m", 2.2, 2.0, 2.4),   # B.18 (already modelled)
    ("P.119", "length_m", 12, 10, 14),     # B.19 (already modelled)
    ("P.117", "height_m", 3.5, 3.0, 4.0),  # B.17 (already modelled)
])
def test_does_my_vehicle_fit(engine, code, attr, value, ok, bad):
    sc = SceneGraph(scene_id="z", signs=[Sign(id="s", code=code, value=value)])
    p = lambda **kw: Permitted(action="enter", vehicle=V("truck", **kw))
    assert engine.answer(sc, p(**{attr: ok})).verdict is Verdict.yes
    a = engine.answer(sc, p(**{attr: bad}))
    assert a.verdict is Verdict.no and any(c.article_id == {"P.116": "B.16", "P.118": "B.18", "P.119": "B.19",
                                                            "P.117": "B.17"}[code] for c in a.citations)
    assert engine.answer(sc, p()).verdict is Verdict.unknown


# ---------------------------------------------------------------- 4. counts with a bound

def test_count_bounds(engine):
    sc = scene("P.102", "P.123a", "P.131a", "W.201a")
    pro = Selector(category="prohibitory")
    for op, n, want in [("ge", 3, Verdict.yes), ("ge", 4, Verdict.no), ("gt", 2, Verdict.yes), ("gt", 3, Verdict.no),
                        ("le", 3, Verdict.yes), ("le", 2, Verdict.no), ("lt", 4, Verdict.yes), ("lt", 3, Verdict.no),
                        ("eq", 3, Verdict.yes)]:
        assert engine.answer(sc, CountIs(sign=pro, n=n, op=op)).verdict is want, (op, n)
    # an unread red circle may be a fourth prohibitory sign
    unread = SceneGraph(scene_id="u", signs=sc.signs + [Sign(id="q", code="UNKNOWN", shape="circle", border="red")])
    assert engine.answer(unread, CountIs(sign=pro, n=3, op="ge")).verdict is Verdict.yes
    assert engine.answer(unread, CountIs(sign=pro, n=3, op="le")).verdict is Verdict.unknown


# ---------------------------------------------------------------- 7. relative selectors

def _post(*codes, side="right"):
    return SceneGraph(scene_id="p", signs=[Sign(id=c, code=c, position=Position(rank_top_down=i + 1, side=side))
                                           for i, c in enumerate(codes)])


def test_relative_selector_below_and_above(engine):
    sc = _post("P.131a", "P.123a", "W.201a")
    below = engine.answer(sc, Meaning(sign=Selector(relative="below", anchor=Anchor(meaning="no_parking"))))
    assert [x["code"] for x in below.value] == ["P.123a"]
    above = engine.answer(sc, Meaning(sign=Selector(relative="above", anchor=Anchor(code="W.201a"))))
    assert [x["code"] for x in above.value] == ["P.123a"]


@pytest.mark.parametrize("sel", [
    Selector(relative="below", anchor=Anchor(code="W.201a")),           # nothing below the last sign
    Selector(relative="left_of", anchor=Anchor(code="P.131a")),         # left / right are not recorded
    Selector(relative="next_to", anchor=Anchor(light=True)),            # lights have no position
    Selector(relative="below", anchor=Anchor(category="prohibitory")),  # two anchors
])
def test_relative_selector_unknown_when_positions_dont_decide(engine, sel):
    sc = _post("P.131a", "P.123a", "W.201a")
    assert engine.answer(sc, Meaning(sign=sel)).verdict is Verdict.unknown
    a = engine.answer(sc, Forbidden(action="enter", vehicle=V("coach"), sign=sel))
    assert a.verdict is Verdict.unknown


def test_relative_selector_without_ranks_is_unknown(engine):
    sc = scene("P.131a", "P.123a")
    sel = Selector(relative="below", anchor=Anchor(meaning="no_parking"))
    assert engine.answer(sc, Meaning(sign=sel)).verdict is Verdict.unknown


# ---------------------------------------------------------------- 5. joining a road

def test_joining_road_duties(engine):
    a = engine.answer(EMPTY, Duties(topic="joining_road"))
    assert a.verdict is Verdict.value and len(a.value["duties"]) == 3
    assert arts(a) == {(L36, "22"), (L36, "25")}


# ---------------------------------------------------------------- marking_meaning with no marking named
# (owner, 2026-11-18, rule-only after the v14 new-types run: the own_58 / own_62 class, painted arrows
# parsed with no kind)

def _marked(*marks):
    from vqa.schemas import Road, RoadMarking
    return SceneGraph(scene_id="m", signs=[], road=Road(markings=[RoadMarking(kind=k, pattern=p) for k, p in marks]))


def test_marking_meaning_without_kind_answers_only_for_one_marking(engine):
    from vqa.schemas import MarkingMeaning
    one = engine.answer(_marked(("center", "double_solid")), MarkingMeaning())
    assert one.verdict is Verdict.value and [m["kind"] for m in one.value["markings"]] == ["center"]
    two = engine.answer(_marked(("center", "double_solid"), ("lane_line", "dashed")), MarkingMeaning())
    assert two.verdict is Verdict.unknown and "did not say which marking" in two.note
    assert engine.answer(_marked(), MarkingMeaning()).verdict is Verdict.unknown


def test_marking_meaning_naming_a_marking_is_unchanged(engine):
    from vqa.schemas import MarkingMeaning
    sc = _marked(("center", "double_solid"), ("lane_line", "dashed"), ("hatched", "solid"))
    by_kind = engine.answer(sc, MarkingMeaning(kind="hatched"))
    assert by_kind.verdict is Verdict.value and [m["kind"] for m in by_kind.value["markings"]] == ["hatched"]
    by_pattern = engine.answer(sc, MarkingMeaning(pattern="dashed"))
    assert by_pattern.verdict is Verdict.value and [m["kind"] for m in by_pattern.value["markings"]] == ["lane_line"]
