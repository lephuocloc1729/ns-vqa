from __future__ import annotations

import datetime as dt

from conftest import V, at, lane, scene, sign, times
from vqa.reasoning.facts import allows, except_days, text_vehicles
from vqa.schemas import (AppliesTo, IsSign, LanesWhere, Permitted, Plate, Position, RulePermitted, Selector,
                         Verdict)


def _permitted(engine, sc, action, cls, when=None):
    return engine.answer(sc, Permitted(action=action, vehicle=V(cls), when=when)).verdict


# ---------------------------------------------------------------- R.412 reserved lanes

def test_a_reserved_lane_sign_applies_to_the_vehicles_it_names(engine):
    sc = scene(sign("s1", "R.412g", shape="rectangle", border="none", background="blue"))
    a = engine.answer(sc, AppliesTo(sign=Selector(only=True)))
    assert a.verdict is Verdict.value and set(a.value["applies_to"]) == {"motorbike", "rudimentary"}


# ---------------------------------------------------------------- exception days

def _banned_left_turn_with_exceptions():
    plates = [times(("06:00", "09:00"), ("16:00", "19:30")),
              Plate(kind="exception", text="(TRỪ NGÀY LỄ THỨ 7, CHỦ NHẬT)", code="S.H,6")]
    return scene(sign("s1", "P.123a", plates=plates))


def test_the_plates_exception_days_are_read():
    assert except_days("(TRỪ NGÀY LỄ THỨ 7, CHỦ NHẬT)") == ["sat", "sun", "holiday"]
    assert except_days("6:00 - 22:00") == [] and except_days("CẤM THỨ 7") == []


def test_an_excepted_day_lifts_the_ban(engine):
    sc = _banned_left_turn_with_exceptions()
    assert _permitted(engine, sc, "turn_left", "passenger_car", at(8, date=dt.date(2025, 10, 7))) is Verdict.no   # Tue
    assert _permitted(engine, sc, "turn_left", "passenger_car", at(8, date=dt.date(2025, 10, 11))) is Verdict.yes  # Sat
    assert _permitted(engine, sc, "turn_left", "passenger_car", at(8, date=dt.date(2025, 9, 2))) is Verdict.yes   # 2/9
    assert _permitted(engine, sc, "turn_left", "passenger_car", at(8, date=dt.date(2026, 2, 17))) is Verdict.unknown


def test_without_a_date_the_exception_days_change_nothing(engine):
    assert _permitted(engine, _banned_left_turn_with_exceptions(), "turn_left", "passenger_car", at(8)) is Verdict.no


# ---------------------------------------------------------------- non-standard plates

def test_plate_text_names_vehicles():
    assert text_vehicles("CẤM XE 2 VÀ 3 BÁNH") == ["motorbike", "motor_tricycle", "cyclo"]
    assert text_vehicles("CẤM XE 3 BÁNH & 4 BÁNH THÔ SƠ 16:00 - 22:00") == ["cyclo", "similar_rudimentary"]
    assert text_vehicles("LÒNG ĐƯỜNG / VỈA HÈ") == []
    assert allows("XE BUÝT ĐƯỢC PHÉP HOẠT ĐỘNG") and not allows("CẤM XE TẢI")


def test_a_plate_naming_two_and_three_wheelers_bans_tricycles(engine):
    sc = scene(sign("s1", "P.104", plates=[Plate(kind="local", text="CẤM XE 2 VÀ 3 BÁNH")]))
    assert _permitted(engine, sc, "enter", "motor_tricycle") is Verdict.no
    assert _permitted(engine, sc, "enter", "passenger_car") is Verdict.yes


def test_a_plate_that_allows_buses_excepts_them(engine):
    sc = scene(sign("s1", "P.107", plates=[Plate(kind="local", text="XE BUÝT ĐƯỢC PHÉP HOẠT ĐỘNG")]))
    assert _permitted(engine, sc, "enter", "city_bus") is Verdict.yes
    assert _permitted(engine, sc, "enter", "truck") is Verdict.no


# ---------------------------------------------------------------- guide discs over lane rows

def test_a_guide_disc_repeating_a_lane_row_applies_to_that_lane_only(engine):
    board = sign("s1", "IE.452", shape="rectangle", background="green",
                 lanes=[lane(1, max_speed=90), lane(2, max_speed=70), lane(3, max_speed=50)])
    discs = [sign(f"g{i}", "P.127", value=v, confidence="high") for i, v in ((1, 90), (2, 70), (3, 50))]
    a = engine.answer(scene(board, *discs, lanes=3), LanesWhere(vehicle=V("car"), speed_kmh=65, ok=False))
    assert a.value["lanes"] == [3]


# ---------------------------------------------------------------- sign identity

def test_a_side_selector_holds_when_one_of_its_signs_is_the_named_one(engine):
    right = Position(rank_top_down=1, side="right")
    sc = scene(sign("s1", "W.239a", position=right), sign("s2", "IE.464", position=right.model_copy(update={"rank_top_down": 2})))
    a = engine.answer(sc, IsSign(sign=Selector(side="right", only=False), meaning="duong_cap_dien_o_phia_tren"))
    assert a.verdict is Verdict.yes
    b = engine.answer(sc, IsSign(sign=Selector(side="right", only=False), meaning="no_parking"))
    assert b.verdict is Verdict.no


def test_no_stopping_and_parking_also_means_no_parking_but_not_the_reverse(engine):
    assert engine.answer(scene(sign("s1", "P.130")), IsSign(sign=Selector(only=True), meaning="no_parking")).verdict \
        is Verdict.yes
    assert engine.answer(scene(sign("s1", "P.131a")),
                         IsSign(sign=Selector(only=True), meaning="no_stopping_or_parking")).verdict is Verdict.no


# ---------------------------------------------------------------- buses at a pickup point

def test_a_bus_may_stop_at_a_pickup_point_other_vehicles_may_not(engine):
    empty = scene()
    bus = engine.answer(empty, RulePermitted(action="stop", vehicle=V("city_bus"), place="pickup_point"))
    car = engine.answer(empty, RulePermitted(action="stop", vehicle=V("passenger_car"), place="pickup_point"))
    assert bus.verdict is Verdict.yes and car.verdict is Verdict.no
    assert any(c.law_id == "interpretation" for c in bus.citations) or "interpretation" in str(bus.reasons)


# ---------------------------------------------------------------- parser v18: lane_reserved_is

def _reserved_lanes():
    from vqa.schemas import LaneReservedIs  # noqa: F401
    pos = lambda n: Position(rank_top_down=1, lane=n)
    blue = dict(shape="rectangle", border="none", background="blue")
    return scene(sign("s1", "R.412b", position=pos(1), **blue), sign("s2", "R.412f", position=pos(2), **blue),
                 sign("s3", "R.412f", position=pos(3), **blue), lanes=3)


def test_a_lane_reserved_for_passenger_cars(engine):
    from vqa.schemas import LaneReservedIs
    sc = _reserved_lanes()
    assert engine.answer(sc, LaneReservedIs(lane=1, vehicle=V("passenger_car"))).verdict is Verdict.yes
    a = engine.answer(sc, LaneReservedIs(lane=2, vehicle=V("passenger_car")))
    assert a.verdict is Verdict.no and "truck" in a.value["open_to_others"]
    assert engine.answer(sc, LaneReservedIs(lane=1, vehicle=V("motorbike"))).verdict is Verdict.no
    assert engine.answer(sc, LaneReservedIs(lane=-1, vehicle=V("car"))).verdict is Verdict.yes   # from the right


def test_lane_reserved_is_unknown_without_a_lane_count(engine):
    from vqa.schemas import LaneReservedIs
    assert engine.answer(scene(sign("s1", "R.412b")), LaneReservedIs(lane=1, vehicle=V("passenger_car"))).verdict \
        is Verdict.unknown


def test_lane_reserved_is_comes_through_the_wire():
    from vqa.parsing.wire import from_wire, to_query
    from vqa.schemas import LaneReservedIs
    q = to_query(from_wire({"program": {"intent": "lane_reserved_is", "lane": 1,
                                        "vehicle": {"vehicle_class": "passenger_car"}}}), 2025)
    assert isinstance(q.program, LaneReservedIs) and q.program.lane == 1


# ---------------------------------------------------------------- parser v18 prompt

def test_v18_is_v17_plus_three_sections_and_one_train_fewshot():
    """v18: v17 plus one section of nine rules and train_466 (owner, 2026-11-20)."""
    import hashlib
    from pathlib import Path
    from vqa.parsing.prompt import examples, system_prompt
    root = Path(__file__).resolve().parents[1]
    a = (root / "prompts/parser/v17/spec.md").read_text(encoding="utf-8").splitlines()
    b = (root / "prompts/parser/v18/spec.md").read_text(encoding="utf-8").splitlines()
    assert [l for l in a if l not in b] == []
    added = [l for l in b if l not in a and l]
    heads = [l for l in added if l.startswith("# ")]
    assert heads == ["# Parser v18 additions"] and not any("v19" in l or "v20" in l for l in b)
    assert sum(l.startswith("- ") for l in added) == 9
    assert any("`lane_reserved_is`" in l for l in added)
    old, new = examples("v17"), examples("v18")
    assert new[:len(old)] == old and [x["id"] for x in new[len(old):]] == ["train_466"]
    assert hashlib.sha256(system_prompt("v18").encode()).hexdigest()[:12] == "b370b923cccb"
    assert not (root / "prompts/parser/v19").exists() and not (root / "prompts/parser/v20").exists()
