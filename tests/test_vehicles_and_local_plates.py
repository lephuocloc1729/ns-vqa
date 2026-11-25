"""Open "which vehicles are banned / allowed" queries, and non-standard (local) plates."""

import datetime as dt

import pytest
from pydantic import ValidationError

from vqa.reasoning import explain
from vqa.schemas import (
    BanTimes, ChoiceOption, Choose, Permitted, Plate, Sign, Verdict, When, WhichVehicles,
)

from conftest import V, articles, scene, sign, spec, times


def which(engine, sc, **kw):
    return engine.answer(sc, WhichVehicles(**kw))


def at(h, m=0):
    return When(time=dt.time(h, m))


# ---------------------------------------------------------------- which_vehicles

def test_pedestrian_ban(engine):
    # "đối tượng tham gia giao thông nào không được phép đi lại?" -> người đi bộ
    a = which(engine, scene(sign("s1", "P.112")))
    assert a.verdict == Verdict.value and a.value["banned"] == ["pedestrian"]
    assert "B.12" in articles(a)


def test_reported_at_the_broadest_level(engine):
    a = which(engine, scene(sign("s1", "P.104")))
    assert a.value["banned"] == ["motorbike"]          # not motorcycle or moped


def test_exceptions_split_the_class(engine):
    a = which(engine, scene(sign("s1", "P.103a")))
    assert set(a.value["banned"]) == {"car", "sidecar", "motor_tricycle"}
    allowed = which(engine, scene(sign("s1", "P.103a")), status="allowed").value["allowed"]
    # reported at the broadest level: "xe máy" (two-wheelers) is allowed as a whole
    assert {"motorbike", "rudimentary", "pedestrian"} <= set(allowed)


def test_conditional_classes(engine):
    a = which(engine, scene(sign("s1", "P.106b", value=2.5)))
    assert a.value["banned"] == ["special_machine"]    # includes tractors (B.6 b)
    assert a.value["conditional"] == ["truck"]         # depends on the load
    b = which(engine, scene(sign("s1", "P.107a", value=29)))
    assert b.value["banned"] == [] and b.value["conditional"] == ["coach"]


def test_which_vehicles_at_a_time(engine):
    sc = scene(sign("s1", "P.104", plates=[times(("06:00", "09:00"))]))
    assert which(engine, sc, when=at(7)).value["banned"] == ["motorbike"]
    assert which(engine, sc, when=at(12)).value["banned"] == []


# ---------------------------------------------------------------- local plates

def three_and_four_wheel_ban():
    """train_2_26 / public_test_8_9 site: P.111d with a red local plate
    'CẤM XE 3 BÁNH VÀ 4 BÁNH THÔ SƠ 05:00-13:00 16:00-22:00'."""
    return scene(sign("s1", "P.111d", plates=[Plate(
        kind="local", text="CẤM XE 3 BÁNH VÀ 4 BÁNH THÔ SƠ 05:00-13:00 16:00-22:00",
        vehicles=[spec("cyclo"), spec("similar_rudimentary")],
        time_windows=[{"start": "05:00", "end": "13:00"}, {"start": "16:00", "end": "22:00"}])]))


def test_local_plate_validation():
    with pytest.raises(ValidationError):
        Plate(kind="local")                                   # text is kept
    with pytest.raises(ValidationError):
        Plate(kind="time", actions=["go_straight"])           # only local plates carry actions


def test_local_plate_replaces_vehicles_and_is_marked(engine):
    sc = three_and_four_wheel_ban()
    a = which(engine, sc, when=at(5))
    assert set(a.value["banned"]) == {"cyclo", "similar_rudimentary"}
    assert a.basis == ["non_standard_plate"]
    goals = [n.goal or n.rule for r in a.reasons if r.proof for n in explain.walk(r.proof)]
    assert any(g.startswith("local_plate(s1,") for g in goals)
    assert "r_non_standard_plate_not_in_qcvn41" in goals
    assert {"22", "B.11", "34"} <= articles(a)  # similar_rudimentary cites Law 36 art. 34
    assert which(engine, sc, when=at(14)).value["banned"] == []


def test_local_plate_answers_carry_the_flag(engine):
    sc = three_and_four_wheel_ban()
    a = engine.answer(sc, Permitted(action="enter", vehicle=V("similar_rudimentary"), when=at(19)))
    assert a.verdict == Verdict.no and a.basis == ["non_standard_plate"]
    # a sign without a local plate gives no flag
    b = engine.answer(scene(sign("s1", "P.104")), Permitted(action="enter", vehicle=V("motorbike")))
    assert b.basis == []


def test_local_plate_narrows_the_action(engine):
    # public_test_5_6: "CẤM XE GẮN MÁY ĐI THẲNG" under the moped sign, 23:00-04:00
    sc = scene(sign("s1", "P.111a", plates=[Plate(
        kind="local", text="CẤM XE GẮN MÁY ĐI THẲNG 23:00-04:00", actions=["go_straight"],
        time_windows=[{"start": "23:00", "end": "04:00"}])]))
    moped = V("moped")
    assert engine.answer(sc, Permitted(action="go_straight", vehicle=moped, when=at(23, 30))).verdict == Verdict.no
    assert engine.answer(sc, Permitted(action="go_straight", vehicle=moped, when=at(12))).verdict == Verdict.yes
    assert engine.answer(sc, Permitted(action="turn_right", vehicle=moped, when=at(23, 30))).verdict == Verdict.yes
    [ban] = engine.answer(sc, BanTimes(action="go_straight", vehicle=moped)).value["bans"]
    assert ban["windows"] == [["23:00", "04:00"]]


def test_local_plate_condition_groups(engine):
    # train_7_15-style: red plate with two (weight, time) rules for trucks
    sc = scene(sign("s1", "P.106a", plates=[Plate(
        kind="local", text="CẤM XE TẢI ... 6:00-24:00; CẤM XE TẢI ... 6:00-8:00, 16:00-20:00",
        rules=[{"vehicles": [spec("truck", ("load_t", "ge", 2.5)), spec("truck", ("gross_t", "ge", 5))],
                "time_windows": [{"start": "06:00", "end": "23:59"}]},
               {"vehicles": [spec("truck", ("load_t", "lt", 2.5))],
                "time_windows": [{"start": "06:00", "end": "08:00"}, {"start": "16:00", "end": "20:00"}]}])]))
    a = engine.answer(sc, Choose(options=[
        ChoiceOption(label=lbl, claim=Permitted(action="enter", vehicle=v, when=at(7, 30)))
        for lbl, v in [("xe máy", V("motorbike")), ("tải 5t", V("truck", load_t=5)),
                       ("tải 1t", V("truck", load_t=1))]]))
    assert a.value["holding"] == ["xe máy"]
    # gross weight matters for the first rule, so it is given (otherwise: unknown)
    b = engine.answer(sc, Permitted(action="enter", vehicle=V("truck", load_t=1, gross_t=2),
                                    when=at(12)))
    assert b.verdict == Verdict.yes and b.basis == ["non_standard_plate"]


def test_local_rules_and_sign_rules_do_not_mix():
    with pytest.raises(ValidationError):
        Sign(id="s1", code="P.106a", rules=[{"vehicles": [spec("truck")]}],
             plates=[Plate(kind="local", text="x", rules=[{"vehicles": [spec("truck")]}])])
