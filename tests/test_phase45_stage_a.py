"""Phase 4.5 stage A (owner, 2026-11-17): family templates F3-F7, the new rows, the expressway
and residential zones (Law 36 art. 25; Circular 38/2024 speeds as interpretations), the
pick-up point (Law 36 art. 18.4 i), and the rank-3 selector and lane fixes. Hand-made scenes
modelled on train questions; no API call."""

from __future__ import annotations

import pytest
import yaml

from vqa.kb import EFFECTS_PATH, load_catalog, merge_effects
from vqa.reasoning.engine import Engine
from vqa.schemas import (Meaning, Permitted, Position, Road, SceneGraph, Selector, Sign, SpeedLimit, SpeedOk,
                         Vehicle, VehicleClass, Verdict)

CAT = load_catalog()


@pytest.fixture(scope="module")
def engine():
    return Engine()


def S(sid, code, rank=1, value=None, shape="circle", border="red", background="white", lane=None, conf="high"):
    return Sign(id=sid, code=code, value=value, confidence=conf, shape=shape, border=border, background=background,
                position=Position(rank_top_down=rank, side="right", lane=lane))


def V(c, **kw):
    return Vehicle(cls=VehicleClass(c), **kw)


def scene(*signs, divided=None, lanes=None):
    return SceneGraph(scene_id="x", signs=list(signs), road=Road(divided=divided, lanes=lanes))


EXPRESSWAY = S("s1", "IE.452", shape="rectangle", border="none", background="green")


# ---------------------------------------------------------------- the catalog

def test_new_rows_exist_with_their_sources():
    assert CAT.get("R.122").source.article_id == "D.1" and CAT.get("R.122").effect.priority_exempt is False
    assert CAT.get("S.501").source.article_id == "F.1" and CAT.get("S.501").category == "auxiliary"
    assert CAT.get("R.421").effect.zone.at == "end" and CAT.get("R.421").source.article_id == "D.18"
    assert CAT.codes_matching("R.415") == ["R.415a", "R.415b"]          # "R.415" names two existing rows


def test_every_effect_overlay_row_is_assistant_checked_and_not_meaning_only():
    rows = yaml.safe_load(EFFECTS_PATH.read_text(encoding="utf-8"))["effects"]
    for r in rows:
        s = CAT.get(r["code"])
        assert s.effect_reviewed_by == "assistant" and not s.meaning_only and not s.effect_unmodelled, r["code"]


def test_the_overlay_refuses_an_unknown_code():
    with pytest.raises(ValueError, match="no catalog row"):
        merge_effects([{"code": "P.104"}], [{"code": "P.999", "effect": {}}])


def test_the_formerly_unmodelled_rows_are_modelled_and_r411_is_not():
    for c in ("R.302(a,b,c)", "R.303", "R.420"):
        assert not CAT.get(c).effect_unmodelled and CAT.get(c).effect_reviewed_by == "assistant"
    assert CAT.get("R.411").effect_unmodelled


# ---------------------------------------------------------------- F3b / F3c (KB-1, KB-2)

def test_r302_and_r303_no_longer_block_a_direction_claim(engine):
    """Modelled on train questions with a keep-right disc or a roundabout sign before a turn."""
    for code, why in (("R.302a", "pass_side_only"), ("R.303", "yield_only")):
        a = engine.answer(scene(S("s1", code, border="none", background="blue")),
                          Permitted(action="turn_left", vehicle=V("car")))
        assert a.verdict is Verdict.yes, code
        assert any(r.detail == why for r in a.reasons), code


# ---------------------------------------------------------------- F4 expressway (Law 36 art. 25)

@pytest.mark.parametrize("cls, verdict", [("moped", Verdict.no), ("motorcycle", Verdict.no),
                                          ("bicycle", Verdict.no), ("car", Verdict.yes),
                                          ("motor_tricycle", Verdict.unknown), ("motorbike", Verdict.no)])
def test_expressway_entry(engine, cls, verdict):
    """Modelled on train_81 ("Xe thô sơ, xe gắn máy và mô tô có được vào cao tốc ... không?")."""
    a = engine.answer(scene(EXPRESSWAY), Permitted(action="enter", vehicle=V(cls)))
    assert a.verdict is verdict
    if verdict is Verdict.no:
        assert any(c.law_id == "36/2024/QH15" and c.article_id == "25" for c in a.citations)


def test_no_stopping_on_the_expressway(engine):
    a = engine.answer(scene(EXPRESSWAY), Permitted(action="stop", vehicle=V("car")))
    assert a.verdict is Verdict.no


def test_an_end_sign_in_the_same_photo_makes_the_zone_unknown(engine):
    end = S("s2", "IE.453c", rank=2, shape="rectangle", border="none", background="green")
    assert engine.answer(scene(EXPRESSWAY, end), Permitted(action="enter", vehicle=V("moped"))).verdict is Verdict.unknown


# ---------------------------------------------------------------- Circular 38 speeds (interpretations)

@pytest.mark.parametrize("speed, verdict", [(100, Verdict.yes), (130, Verdict.no), (50, Verdict.no)])
def test_expressway_default_speeds(engine, speed, verdict):
    assert engine.answer(scene(EXPRESSWAY), SpeedOk(vehicle=V("car"), speed_kmh=speed)).verdict is verdict


def test_a_posted_limit_overrides_the_expressway_default(engine):
    p127 = S("s2", "P.127", rank=2, value=80)
    assert engine.answer(scene(EXPRESSWAY, p127), SpeedOk(vehicle=V("car"), speed_kmh=100)).verdict is Verdict.no
    assert engine.answer(scene(EXPRESSWAY, p127), SpeedOk(vehicle=V("car"), speed_kmh=75)).verdict is Verdict.yes


def test_an_unread_sign_blocks_a_default(engine):
    """Modelled on train_413: an unread board may be the posted limit."""
    unread = S("s2", "UNKNOWN", rank=2, shape="rectangle", border="none", background="white", conf="low")
    a = engine.answer(scene(EXPRESSWAY, unread), SpeedLimit(vehicle=V("motor_vehicle"), kind="max"))
    assert a.verdict is Verdict.unknown
    assert engine.answer(scene(EXPRESSWAY), SpeedLimit(vehicle=V("motor_vehicle"), kind="max")).value["limit"] == 120


def test_default_speeds_cite_an_interpretation_never_a_law(engine):
    a = engine.answer(scene(EXPRESSWAY), SpeedOk(vehicle=V("car"), speed_kmh=130))
    assert a.verdict is Verdict.no and not any(c.law_id == "interpretation" for c in a.citations)
    proof_text = str([r.proof for r in a.reasons])
    assert "r_c38_expressway" in proof_text


RES = S("s1", "R.420", shape="rectangle", border="white", background="blue")


@pytest.mark.parametrize("divided, speed, verdict", [(None, 45, Verdict.yes), (None, 55, Verdict.unknown),
                                                     (None, 65, Verdict.no), (True, 55, Verdict.yes),
                                                     (False, 55, Verdict.no)])
def test_residential_speeds(engine, divided, speed, verdict):
    """Modelled on train_54/55 ("Sau biển này, ô tô được chạy tối đa bao nhiêu ... dải phân cách?")."""
    assert engine.answer(scene(RES, divided=divided), SpeedOk(vehicle=V("car"), speed_kmh=speed)).verdict is verdict


def test_residential_limit_value_needs_the_divider(engine):
    assert engine.answer(scene(RES), SpeedLimit(vehicle=V("car"), kind="max")).verdict is Verdict.unknown
    assert engine.answer(scene(RES, divided=True), SpeedLimit(vehicle=V("car"), kind="max")).value["limit"] == 60
    assert engine.answer(scene(RES, divided=False), SpeedLimit(vehicle=V("car"), kind="max")).value["limit"] == 50


def test_mopeds_in_a_residential_area(engine):
    assert engine.answer(scene(RES), SpeedOk(vehicle=V("moped"), speed_kmh=45)).verdict is Verdict.no
    assert engine.answer(scene(RES), SpeedOk(vehicle=V("moped"), speed_kmh=35)).verdict is Verdict.yes


def test_the_residential_end_sign_ends_the_defaults(engine):
    end = S("s2", "R.421", rank=2, shape="rectangle", border="white", background="blue")
    assert engine.answer(scene(RES, end), SpeedOk(vehicle=V("car"), speed_kmh=65)).verdict is Verdict.unknown


# ---------------------------------------------------------------- F6 places

def test_u_turn_and_parking_places_are_cited(engine):
    a = engine.answer(scene(S("s1", "I.409", shape="rectangle", border="none", background="blue")),
                      Permitted(action="u_turn", vehicle=V("car")))
    assert a.verdict is Verdict.yes and any(r.detail == "permitted_here" for r in a.reasons)


def test_a_one_way_road_bans_u_turns_except_priority(engine):
    one_way = scene(S("s1", "I.407a", shape="rectangle", border="none", background="blue"))
    assert engine.answer(one_way, Permitted(action="u_turn", vehicle=V("car"))).verdict is Verdict.no
    assert engine.answer(one_way, Permitted(action="u_turn", vehicle=V("car", priority=True))).verdict is Verdict.yes


def test_a_bus_stop_bans_stopping_except_buses(engine):
    stop = scene(S("s1", "I.434a", shape="rectangle", border="none", background="blue"))
    a = engine.answer(stop, Permitted(action="park", vehicle=V("passenger_car")))
    assert a.verdict is Verdict.no and any(c.law_id == "36/2024/QH15" and c.article_id == "18" for c in a.citations)
    # "ô tô" might be the bus the stop serves (city_bus is a kind of car): unknown, not no
    assert engine.answer(stop, Permitted(action="park", vehicle=V("car"))).verdict is Verdict.unknown
    assert engine.answer(stop, Permitted(action="stop", vehicle=V("city_bus"))).verdict is Verdict.yes


# ---------------------------------------------------------------- rank 3

def test_a_colour_the_question_names_matches_border_or_background(engine):
    """Modelled on train_287 ("Biển đỏ có vạch ngang trắng ... có ý nghĩa gì?"): P.102 has a red
    face and no border; the question's "red border, red background" still finds it."""
    sc = scene(S("s1", "P.102", border="none", background="red"))
    a = engine.answer(sc, Meaning(sign=Selector(border="red", background="red", only=False)))
    assert a.verdict is Verdict.value and a.value[0]["code"] == "P.102"
    assert engine.answer(sc, Meaning(sign=Selector(background="blue", only=False))).verdict is Verdict.unknown


def test_kb6_lane_signs_that_agree_decide_a_claim_with_no_lane(engine):
    sc = scene(S("s1", "P.127", value=80, lane=1), S("s2", "P.127", rank=2, value=80, lane=2), lanes=2)
    a = engine.answer(sc, SpeedOk(vehicle=V("car"), speed_kmh=85))
    assert a.verdict is Verdict.no and a.value["rule"] == "kb6_every_lane_agrees"
    assert engine.answer(sc, SpeedOk(vehicle=V("car"), speed_kmh=70)).verdict is Verdict.yes
    differ = scene(S("s1", "P.127", value=80, lane=1), S("s2", "P.127", rank=2, value=60, lane=2), lanes=2)
    assert engine.answer(differ, SpeedOk(vehicle=V("car"), speed_kmh=70)).verdict is Verdict.unknown


def test_the_lane_count_comes_from_lane_board_rows():
    """KB-5: the scene's lane count falls back to the rows of a lane board (R.415a)."""
    from vqa.reasoning.engine import scene_lane_count
    from vqa.schemas import LaneSpec
    board = S("s1", "R.415a", shape="rectangle", border="none", background="blue")
    board = board.model_copy(update={"lanes": [LaneSpec(lane=1), LaneSpec(lane=2), LaneSpec(lane=3)]})
    assert scene_lane_count(scene(board)) == 3
