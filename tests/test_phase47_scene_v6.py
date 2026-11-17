"""Phase 4.7 step 1d (owner, 2026-11-17: additive only): scene v6 fields (R.411 lane arrows, traffic
lights, road markings), their rules (kb/rules/signals47.pl: D.13, art. 6, G.1) and the v6 prompts.
Hand-made scenes; no API call."""

from __future__ import annotations

import json

import pytest

from vqa.kb import load_catalog, listed_signs
from vqa.perception import prompt as scene_prompt
from vqa.perception.wire import to_scene
from vqa.reasoning.engine import Engine
from vqa.schemas import (LaneSpec, MarkingIs, MarkingMeaning, Permitted, Position, Road, RoadMarking,
                         RulePermitted, SceneGraph, Sign, SignalMeaning, TrafficSignal, Vehicle, Verdict)


@pytest.fixture(scope="module")
def engine():
    return Engine()


def V(c="motor_vehicle", **kw):
    return Vehicle(**{"class": c, **kw})


def arts(a):
    return {c.article_id for c in a.citations}


def R411(*rows):
    return Sign(id="s1", code="R.411", confidence="high", shape="rectangle", border="none", background="blue",
                position=Position(rank_top_down=1, side="center"),
                lanes=[LaneSpec(lane=i, directions=d) for i, d in enumerate(rows, 1)])


# ---------------------------------------------------------------- R.411 (D.13)

ARROWS = SceneGraph(scene_id="x", road=Road(lanes=3),
                    signs=[R411(["left", "u_turn"], ["straight"], ["straight", "right"])])


@pytest.mark.parametrize("action,lane,verdict", [
    ("turn_left", 1, Verdict.yes), ("u_turn", 1, Verdict.yes), ("go_straight", 1, Verdict.no),
    ("go_straight", 2, Verdict.yes), ("turn_left", 2, Verdict.no), ("turn_right", 3, Verdict.yes),
    ("turn_right", -1, Verdict.yes), ("turn_left", -1, Verdict.no),
])
def test_lane_arrows_decide_direction_claims_on_a_lane(engine, action, lane, verdict):
    """Modelled on "Theo biển, làn phải cho rẽ phải không?" (D.13)."""
    a = engine.answer(ARROWS, Permitted(action=action, vehicle=V(), lane=lane))
    assert a.verdict is verdict and "D.13" in arts(a)


def test_without_a_lane_the_board_stays_unmodelled(engine):
    a = engine.answer(ARROWS, Permitted(action="turn_left", vehicle=V()))
    assert a.verdict is Verdict.unknown


def test_without_arrows_r411_behaves_as_before(engine):
    scene = SceneGraph(scene_id="x", signs=[R411()])
    assert engine.answer(scene, Permitted(action="turn_left", vehicle=V(), lane=1)).verdict is Verdict.unknown


# ---------------------------------------------------------------- lights (art. 6)

def L(*signals):
    return SceneGraph(scene_id="x", signals=list(signals))


@pytest.mark.parametrize("signals,action,past,verdict", [
    ([TrafficSignal(colour="green")], "go_straight", None, Verdict.yes),
    ([TrafficSignal(colour="red")], "go_straight", None, Verdict.no),
    ([TrafficSignal(colour="yellow")], "go_straight", None, Verdict.unknown),
    ([TrafficSignal(colour="yellow")], "go_straight", True, Verdict.yes),
    ([TrafficSignal(colour="yellow")], "go_straight", False, Verdict.no),
    ([TrafficSignal(colour="yellow", flashing=True)], "go_straight", None, Verdict.yes),
    ([TrafficSignal(colour="red"), TrafficSignal(colour="green", arrow="left")], "turn_left", None, Verdict.yes),
    ([TrafficSignal(colour="red"), TrafficSignal(colour="green", arrow="left")], "u_turn", None, Verdict.yes),
    ([TrafficSignal(colour="red"), TrafficSignal(colour="green", arrow="left")], "go_straight", None, Verdict.no),
    ([TrafficSignal(colour="green"), TrafficSignal(colour="red", arrow="right")], "turn_right", None, Verdict.no),
])
def test_lights(engine, signals, action, past, verdict):
    """"Gặp đèn tín hiệu như trong ảnh, xe có được đi tiếp không?" (6.3, 6.4)."""
    a = engine.answer(L(*signals), RulePermitted(action=action, past_stop_line=past))
    assert a.verdict is verdict and "6" in arts(a)


def test_priority_vehicles_go_regardless_of_lights(engine):
    a = engine.answer(L(TrafficSignal(colour="red")), RulePermitted(action="go_straight", vehicle=V(priority=True)))
    assert a.verdict is Verdict.yes


def test_signal_meaning(engine):
    a = engine.answer(L(TrafficSignal(colour="red")), SignalMeaning())
    assert a.verdict is Verdict.value and a.value["signals"][0]["meaning"].startswith("cấm đi")
    assert engine.answer(L(), SignalMeaning()).verdict is Verdict.unknown


# ---------------------------------------------------------------- markings (G.1)

def M(*marks):
    return SceneGraph(scene_id="x", road=Road(lanes=2, markings=list(marks)), signs=[])


@pytest.mark.parametrize("mark,maneuver,lane,verdict", [
    (RoadMarking(kind="center", pattern="double_solid"), "cross_center", None, Verdict.no),
    (RoadMarking(kind="center", pattern="solid"), "cross_center", None, Verdict.no),
    (RoadMarking(kind="center", pattern="dashed"), "cross_center", None, Verdict.yes),
    (RoadMarking(kind="center", pattern="solid_dashed"), "cross_center", None, Verdict.unknown),
    (RoadMarking(kind="lane_line", pattern="solid", between=[1, 2]), "change_lane", 1, Verdict.no),
    (RoadMarking(kind="lane_line", pattern="dashed", between=[1, 2]), "change_lane", 2, Verdict.yes),
])
def test_markings(engine, mark, maneuver, lane, verdict):
    """"Xe có được lấn sang làn ngược chiều và đè lên vạch đôi liền ở giữa đường không?" (G.1 1.3)."""
    a = engine.answer(M(mark), RulePermitted(maneuver=maneuver, lane=lane))
    assert a.verdict is verdict and "G.1" in arts(a)


def test_no_marking_read_gives_unknown(engine):
    assert engine.answer(M(), RulePermitted(maneuver="cross_center")).verdict is Verdict.unknown


def test_marking_meaning_and_claim(engine):
    """"Vạch liền trong ảnh có dùng để phân chia các làn xe cùng chiều không?" (G.1 2.2)."""
    scene = M(RoadMarking(kind="lane_line", pattern="solid", between=[1, 2]))
    assert engine.answer(scene, MarkingIs(pattern="solid", separates="same_direction_lanes")).verdict is Verdict.yes
    assert engine.answer(scene, MarkingIs(pattern="solid", separates="opposite_directions")).verdict is Verdict.no
    a = engine.answer(scene, MarkingMeaning(pattern="solid"))
    assert a.verdict is Verdict.value and "2.2" in a.value["markings"][0]["meaning"]


# ---------------------------------------------------------------- perception side

def test_wire_reads_the_v6_fields():
    reply = {"signs": [{"code": "R.411", "confidence": "high", "shape": "rectangle", "border": "none",
                        "background": "blue", "rank": 1, "side": "center",
                        "lanes": [{"lane": 1, "directions": ["left"]}, {"lane": 2, "directions": ["straight"]}]}],
             "road": {"type": "urban", "markings": [{"kind": "center", "pattern": "double_solid", "colour": "yellow"}]},
             "vehicles": [], "signals": [{"colour": "red"}]}
    w = to_scene(reply, "x")
    assert w.ok and w.scene.signs[0].lanes[0].directions == ["left"]
    assert w.scene.road.markings[0].pattern == "double_solid" and w.scene.signals[0].colour == "red"


def test_empty_v6_fields_leave_the_dump_as_before():
    d = SceneGraph(scene_id="x", signs=[Sign(id="s1", code="P.127", lanes=[LaneSpec(lane=1, max_speed=60)])]).model_dump(mode="json")
    assert "signals" not in d and "markings" not in d["road"] and "directions" not in d["signs"][0]["lanes"][0]


def test_v6_prompts_are_new_versions_and_v5_is_unchanged():
    for v in ("v6", "v6-tile", "v6-crop"):
        assert scene_prompt.prompt_id(v).startswith(f"scene/{v}@")
    spec = scene_prompt.system_prompt("v6")
    assert '"signals"' in spec and "directions" in spec and "markings" in spec
    assert "signals" not in scene_prompt.system_prompt("v5")
    cat = load_catalog()
    assert [s.code for s in listed_signs(cat, "scene", "v6")] == [s.code for s in listed_signs(cat, "scene", "v5")]
    json.dumps(scene_prompt.examples("v6"))


def test_a_light_question_without_a_light_read_is_unknown(engine):
    """"Gặp đèn tín hiệu như trong ảnh, xe có được đi tiếp không?" on a scene where perception read
    no light: art. 6 makes passing depend on the light, so the signs alone give no yes."""
    no_light = SceneGraph(scene_id="x", signs=[])
    a = engine.answer(no_light, RulePermitted(action="go_straight", at_signal=True))
    assert a.verdict is Verdict.unknown and "6" in arts(a) and "traffic light" in a.note
    # only a pedestrian lamp read: still no vehicle light
    ped = L(TrafficSignal(kind="pedestrian", colour="green"))
    assert engine.answer(ped, RulePermitted(action="go_straight", at_signal=True)).verdict is Verdict.unknown
    # with the light read, the light decides as before
    assert engine.answer(L(TrafficSignal(colour="green")),
                         RulePermitted(action="go_straight", at_signal=True)).verdict is Verdict.yes
    assert engine.answer(L(TrafficSignal(colour="red")),
                         RulePermitted(action="go_straight", at_signal=True)).verdict is Verdict.no
    # without the flag the old behaviour stays (signs only)
    assert engine.answer(no_light, RulePermitted(action="go_straight")).verdict is Verdict.yes


def test_the_wire_carries_at_signal():
    from vqa.parsing.wire import from_wire, to_query
    q = to_query(from_wire({"program": {"intent": "rule_permitted", "action": "go_straight", "at_signal": True}}), 2025)
    assert q.program.at_signal is True
