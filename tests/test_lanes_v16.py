"""Lane family: R.415a lane board (D.16), the lane slot in permitted/forbidden,
"which vehicles may use lane N", and the speed-limit value query."""

import datetime as dt

from vqa.schemas import (
    Forbidden, LanesFor, LaneVehicles, Permitted, SpeedLimit, Verdict, When,
)

from conftest import V, articles, lane, only_for, scene, sign, spec, times


def at(h):
    return When(time=dt.time(h))


def r415_board():
    """public_test_5_4-style board: car, car, motorbike, bicycle."""
    return scene(sign("s1", "R.415a", lanes=[
        lane(1, vehicles=[spec("car")]), lane(2, vehicles=[spec("car")]),
        lane(3, vehicles=[spec("motorbike")]), lane(4, vehicles=[spec("bicycle")])]), lanes=4)


# ---------------------------------------------------------------- R.415a and lane_vehicles

def test_r415_lanes_for_car(engine):
    # "xe ô tô được phép đi vào mấy làn đường?" -> 2
    a = engine.answer(r415_board(), LanesFor(vehicle=V("passenger_car")))
    assert a.value["lanes"] == [1, 2] and "D.16" in articles(a)


def test_which_vehicles_may_use_a_lane(engine):
    sc = r415_board()
    a = engine.answer(sc, LaneVehicles(lane=1))
    assert a.value["allowed"] == ["car"]            # "chỉ dành cho xe ô tô"
    b = engine.answer(sc, LaneVehicles(lane=3))
    assert b.value["allowed"] == ["motorbike"]
    c = engine.answer(sc, LaneVehicles(lane=1, status="banned"))
    assert "motorbike" in c.value["banned"] and "D.16" in articles(c)


def test_lane_vehicles_at_a_speed(engine):
    sc = scene(sign("s1", "P.127c", lanes=[
        lane(1, 100, vehicles=[spec("passenger_car")]), lane(2, 80, vehicles=[spec("truck")])]))
    a = engine.answer(sc, LaneVehicles(lane=1, speed_kmh=90))
    assert a.value["allowed"] == ["passenger_car"]
    assert engine.answer(sc, LaneVehicles(lane=2, speed_kmh=90)).value["allowed"] == []


# ---------------------------------------------------------------- lane slot

def right_lanes_car_ban():
    """public_test_6_8-style: P.103a 6:00-22:00 over the two right lanes of four."""
    return scene(sign("s1", "P.103a", plates=[times(("06:00", "22:00")),
                                             {"kind": "lane", "lanes": [3, 4]}]), lanes=4)


def test_lane_slot_in_permitted(engine):
    # "Xe ô tô đi vào 2 làn bên phải lúc 10 giờ sáng có bị phạm luật không?" -> Có
    sc = right_lanes_car_ban()
    car = V("passenger_car")
    a = engine.answer(sc, Permitted(action="enter", vehicle=car, lane=3, when=at(10)))
    assert a.verdict == Verdict.no and {"22", "B.3", "41", "F.4", "F.10"} <= articles(a)
    b = engine.answer(sc, Permitted(action="enter", vehicle=car, lane=1, when=at(10)))
    assert b.verdict == Verdict.yes and b.reasons[0].detail == "lane_not_covered"
    # no lane given: depends on the lane
    assert engine.answer(sc, Permitted(action="enter", vehicle=car, when=at(10))).verdict == Verdict.unknown
    assert engine.answer(sc, Forbidden(action="enter", vehicle=car, lane=4, when=at(10))).verdict == Verdict.yes


def test_lane_slot_brings_in_lane_rules(engine):
    sc = scene(sign("s1", "R.412d", position={"lane": 3}), lanes=3)
    car = V("passenger_car")
    a = engine.answer(sc, Permitted(action="enter", vehicle=car, lane=3))
    assert a.verdict == Verdict.no and "D.14" in articles(a)
    b = engine.answer(sc, Permitted(action="enter", vehicle=car, lane=1))
    assert b.verdict == Verdict.yes
    assert engine.answer(sc, Permitted(action="enter", vehicle=V("moped"), lane=3)).verdict == Verdict.yes


# ---------------------------------------------------------------- speed_limit

def test_max_speed_value(engine):
    # "tốc độ tối đa trên đoạn đường phía trước là bao nhiêu?" -> 60
    a = engine.answer(scene(sign("s1", "P.127", value=60)), SpeedLimit())
    assert a.verdict == Verdict.value and a.value["limit"] == 60
    assert {"22", "B.27"} <= articles(a)


def test_speed_limit_per_lane_board(engine):
    # "Tốc độ tối đa trên cả 3 làn đường là bao nhiêu?" -> 40
    sc = scene(sign("s1", "P.127c", lanes=[lane(i, 40, vehicles=[spec("car")]) for i in (1, 2, 3)]))
    a = engine.answer(sc, SpeedLimit(vehicle=V("passenger_car")))
    assert [x["limit"] for x in a.value["per_lane"]] == [40, 40, 40]
    assert engine.answer(sc, SpeedLimit(vehicle=V("passenger_car"), lane=2)).value["limit"] == 40
    assert "B.27c" in articles(a)


def test_speed_limit_per_vehicle(engine):
    sc = scene(sign("s1", "P.127", value=90, plates=[only_for(spec("passenger_car"))]),
               sign("s2", "P.127", value=80, plates=[only_for(spec("truck"))]))
    assert engine.answer(sc, SpeedLimit(vehicle=V("truck"))).value["limit"] == 80
    assert engine.answer(sc, SpeedLimit(vehicle=V("passenger_car"))).value["limit"] == 90
    # vehicle not given: both limits may apply, none is certain
    a = engine.answer(sc, SpeedLimit())
    assert a.value["limit"] is None
    assert sorted(c["value"] for c in a.value["conditional"]) == [80, 90]


def test_lowest_certain_limit_wins(engine):
    sc = scene(sign("s1", "P.127", value=80), sign("s2", "P.127", value=60,
                                                   plates=[times(("06:00", "22:00"))]))
    assert engine.answer(sc, SpeedLimit(when=at(10))).value["limit"] == 60
    assert engine.answer(sc, SpeedLimit(when=at(23))).value["limit"] == 80
    a = engine.answer(sc, SpeedLimit())             # time unknown
    assert a.value["limit"] == 80 and a.value["conditional"] == [{"sign_id": "s2", "value": 60}]


def test_min_speed_value_and_no_sign(engine):
    assert engine.answer(scene(sign("s1", "R.306", value=60)),
                         SpeedLimit(kind="min")).value["limit"] == 60
    assert engine.answer(scene(sign("s1", "P.104")), SpeedLimit()).verdict == Verdict.unknown
