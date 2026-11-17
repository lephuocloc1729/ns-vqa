"""Phase 4.5 stage A, rank 1 (owner, 2026-11-17): accuracy fixes. Hand-made scenes modelled
on train questions (dev 451, 352/381, 308); no API call."""

from __future__ import annotations

import pytest

from vqa.reasoning.engine import Engine, sign_group_vi
from vqa.schemas import (Choose, ChoiceOption, Meaning, Permitted, Position, SceneGraph, Selector, Sign,
                         SpeedOk, Vehicle, VehicleClass, Verdict, Verify)


@pytest.fixture(scope="module")
def engine():
    return Engine()


def S(sid, code, rank=1, value=None, shape="circle", border="red", background="white", lanes=(), lane=None):
    return Sign(id=sid, code=code, value=value, confidence="high", shape=shape, border=border,
                background=background, position=Position(rank_top_down=rank, side="right", lane=lane),
                lanes=list(lanes))


CAR = Vehicle(cls=VehicleClass.motor_vehicle)


def test_a_choose_with_an_unknown_option_is_unknown(engine):
    """Modelled on train_352: a red disc that could not be read may be a speed limit, so the
    speed option is unknown, while the stopping option is decided by P.130."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.130"), S("s2", "UNKNOWN", rank=2)])
    p = Choose(options=[ChoiceOption(label="85 km/h", claim=SpeedOk(vehicle=CAR, speed_kmh=85), expect=True),
                        ChoiceOption(label="dừng xe", claim=Permitted(action="stop", vehicle=CAR), expect=True)])
    a = engine.answer(scene, p)
    assert a.verdict is Verdict.unknown and a.value["unknown"] == ["85 km/h"] and a.value["not_holding"] == ["dừng xe"]


def test_a_choose_with_every_option_decided_is_still_a_value(engine):
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.127", value=50)])
    p = Choose(options=[ChoiceOption(label="40", claim=SpeedOk(vehicle=CAR, speed_kmh=40), expect=True),
                        ChoiceOption(label="60", claim=SpeedOk(vehicle=CAR, speed_kmh=60), expect=True)])
    a = engine.answer(scene, p)
    assert a.verdict is Verdict.value and a.value["holding"] == ["40"] and a.value["not_holding"] == ["60"]


def test_an_r411_board_without_lane_rows_leaves_direction_claims_unknown(engine):
    """Modelled on train_451: R.411 seen, its lane arrows not read; the claim names no lane."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", "R.411", shape="rectangle", border="white", background="blue")])
    a = engine.answer(scene, Permitted(action="go_straight", vehicle=CAR))
    assert a.verdict is Verdict.unknown and a.uncertain_signs == ["s1"]
    p = Choose(options=[ChoiceOption(label="làn giữa cho đi thẳng",
                                     claim=Permitted(action="go_straight", vehicle=CAR), expect=False)])
    assert engine.answer(scene, p).verdict is Verdict.unknown


def test_an_r411_board_does_not_bear_on_a_parking_claim(engine):
    scene = SceneGraph(scene_id="x", signs=[S("s1", "R.411", shape="rectangle", border="white", background="blue")])
    assert engine.answer(scene, Permitted(action="park", vehicle=CAR)).verdict is Verdict.yes


@pytest.mark.parametrize("code, group", [
    ("P.130", "biển báo cấm"), ("DP.134", "biển báo cấm"), ("R.301b", "biển hiệu lệnh"),
    ("R.404a", "biển hiệu lệnh"), ("W.227", "biển báo nguy hiểm và cảnh báo"), ("I.414(a,b,c,d)", "biển chỉ dẫn"),
    ("IE.452", "biển chỉ dẫn"), ("S.508a", "biển phụ, biển viết bằng chữ"),
])
def test_group_names_follow_art_11(code, group):
    assert sign_group_vi(code) == group


def test_a_meaning_answer_names_the_art_11_group(engine):
    """Modelled on train_308 ("Biển trong ảnh thuộc nhóm nào?", R.301b): the group is
    "biển hiệu lệnh", never a made-up name."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", "R.301b", background="blue", border="none")])
    a = engine.answer(scene, Meaning(sign=Selector(only=True)))
    assert a.value[0]["group_vi"] == "biển hiệu lệnh"
