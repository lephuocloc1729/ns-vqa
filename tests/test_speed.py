"""Rule family: speed limits, overall and by lane (QCVN 41:2024 B.27, B.27b, B.27c, D.6)
and lanes reserved for vehicle classes (D.14)."""

from vqa.schemas import (
    AltReading, ExistsViolation, LanesFor, LanesWhere, SpeedOk, Verdict,
)

from conftest import V, articles, lane, only_for, scene, sign, spec


def speed_ok(engine, sc, vehicle, kmh, lane=None):
    return engine.answer(sc, SpeedOk(vehicle=vehicle, speed_kmh=kmh, lane=lane))


def test_max_speed_sign(engine):
    sc = scene(sign("s1", "P.127", value=50))
    a = speed_ok(engine, sc, V("passenger_car"), 60)
    assert a.verdict == Verdict.no and "B.27" in articles(a)
    assert speed_ok(engine, sc, V("passenger_car"), 50).verdict == Verdict.yes
    assert speed_ok(engine, sc, V("passenger_car"), 45).verdict == Verdict.yes
    # P.127 is for xe cơ giới only
    assert speed_ok(engine, sc, V("bicycle"), 60).verdict == Verdict.yes


def test_which_speeds_violate(engine):
    # "trong các mức 30, 35, 40 và 45 km/h, mức nào vi phạm?"
    sc = scene(sign("s1", "P.127", value=40))
    bad = [k for k in (30, 35, 40, 45)
           if speed_ok(engine, sc, V("motor_vehicle"), k).verdict == Verdict.no]
    assert bad == [45]


def test_unread_value_is_unknown(engine):
    sc = scene(sign("s1", "P.127"))
    assert speed_ok(engine, sc, V("passenger_car"), 60).verdict == Verdict.unknown


def test_speed_per_vehicle_plate(engine):
    sc = scene(sign("s1", "P.127", value=90, plates=[only_for(spec("passenger_car"))]),
               sign("s2", "P.127", value=80, plates=[only_for(spec("truck"))]))
    assert speed_ok(engine, sc, V("passenger_car"), 95).verdict == Verdict.no
    assert speed_ok(engine, sc, V("passenger_car"), 85).verdict == Verdict.yes
    assert speed_ok(engine, sc, V("truck"), 85).verdict == Verdict.no
    assert speed_ok(engine, sc, V("truck"), 75).verdict == Verdict.yes


def test_min_speed(engine):
    sc = scene(sign("s1", "R.306", value=60))
    a = speed_ok(engine, sc, V("passenger_car"), 50)
    assert a.verdict == Verdict.no and "D.6" in articles(a)
    assert speed_ok(engine, sc, V("passenger_car"), 70).verdict == Verdict.yes


# ---------------------------------------------------------------- per-lane boards

def lane_board():
    # P.127b: lane 1 (left) 100, lane 2 80, lane 3 60
    return scene(sign("s1", "P.127b", lanes=[lane(1, 100), lane(2, 80), lane(3, 60)]))


def test_lane_board_speed(engine):
    sc = lane_board()
    assert speed_ok(engine, sc, V("passenger_car"), 90, lane=1).verdict == Verdict.yes
    a = speed_ok(engine, sc, V("passenger_car"), 90, lane=2)
    assert a.verdict == Verdict.no and "B.27b" in articles(a)
    # lane not given: depends on the lane
    assert speed_ok(engine, sc, V("passenger_car"), 90).verdict == Verdict.unknown


def test_lanes_for_speed(engine):
    sc = lane_board()
    # "Nếu muốn chạy với tốc độ tối đa 90 km/h, bạn phải di chuyển vào làn nào?"
    a = engine.answer(sc, LanesWhere(vehicle=V("passenger_car"), speed_kmh=90, ok=True))
    assert a.verdict == Verdict.value and a.value["lanes"] == [1]
    # "Ô tô chạy 65 km/h không được sử dụng làn nào?"
    a = engine.answer(sc, LanesWhere(vehicle=V("passenger_car"), speed_kmh=65, ok=False))
    assert a.value["lanes"] == [3]


def vehicle_lane_board():
    # P.127c: lane 1 cars and buses 100, lane 2 cars and trucks 80, lane 3 motorbikes 60
    return scene(sign("s1", "P.127c", lanes=[
        lane(1, 100, vehicles=[spec("passenger_car"), spec("bus")]),
        lane(2, 80, vehicles=[spec("passenger_car"), spec("truck")]),
        lane(3, 60, vehicles=[spec("motorbike")]),
    ]))


def test_lanes_by_vehicle(engine):
    sc = vehicle_lane_board()
    # "Xe tải có khối lượng chuyên chở 3,4 tấn được đi ở làn nào?"
    a = engine.answer(sc, LanesFor(vehicle=V("truck", load_t=3.4)))
    assert a.value["lanes"] == [2]
    # a P.127c board cites its own article; D.14 is for R.412 signs
    assert "B.27c" in articles(a) and "D.14" not in articles(a)
    assert engine.answer(sc, LanesFor(vehicle=V("motorbike"))).value["lanes"] == [3]
    assert engine.answer(sc, LanesFor(vehicle=V("passenger_car"), speed_kmh=90)).value["lanes"] == [1]


def test_vehicle_board_speed_on_its_lane(engine):
    sc = vehicle_lane_board()
    assert speed_ok(engine, sc, V("truck"), 85, lane=2).verdict == Verdict.no
    assert speed_ok(engine, sc, V("truck"), 75, lane=2).verdict == Verdict.yes


def test_reserved_lane_sign(engine):
    sc = scene(sign("s1", "R.412d", position={"lane": 3}), lanes=3)
    assert engine.answer(sc, LanesFor(vehicle=V("passenger_car"))).value["lanes"] == [1, 2]
    assert engine.answer(sc, LanesFor(vehicle=V("moped"))).value["lanes"] == [1, 2, 3]


def test_reserved_truck_lane_with_load(engine):
    sc = scene(sign("s1", "R.412c", value=3.5, position={"lane": 2}), lanes=2)
    lanes = lambda v: engine.answer(sc, LanesFor(vehicle=v)).value
    assert lanes(V("truck", load_t=3.4))["lanes"] == [1, 2]
    assert lanes(V("truck", load_t=5))["lanes"] == [1]
    assert lanes(V("truck"))["conditional"] == [2]


def test_no_lane_count_is_unknown(engine):
    sc = scene(sign("s1", "P.127", value=50))
    assert engine.answer(sc, LanesFor(vehicle=V("car"))).verdict == Verdict.unknown


# ---------------------------------------------------------------- uncertainty and violations

def test_alternative_readings(engine):
    s = sign("s1", "P.127", value=50, confidence="low",
             alternatives=[AltReading(code="P.127", value=60)])
    sc = scene(s)
    a = speed_ok(engine, sc, V("passenger_car"), 55)
    assert a.verdict == Verdict.uncertain and a.uncertain_signs == ["s1"]
    # both readings agree
    assert speed_ok(engine, sc, V("passenger_car"), 70).verdict == Verdict.no


def test_speeding_vehicle_is_a_violation(engine):
    sc = scene(sign("s1", "P.127", value=50),
               vehicles=[{"id": "v1", "class": "passenger_car", "speed_kmh": 70}])
    a = engine.answer(sc, ExistsViolation())
    assert a.verdict == Verdict.yes and a.value["violations"] == ["v1:speed"]


def test_speed_citations_include_article_22(engine):
    # P.127, P.127b, P.127c are listed in QCVN 41 art. 22.1 (prohibitory signs)
    a = speed_ok(engine, scene(sign("s1", "P.127", value=50)), V("passenger_car"), 60)
    assert {"22", "B.27"} <= articles(a)
    a = speed_ok(engine, lane_board(), V("passenger_car"), 90, lane=2)
    assert {"22", "B.27b"} <= articles(a)


def test_lane_plate_cited_only_for_s504_plate(engine):
    over_lane = scene(sign("s1", "P.127", value=80, position={"lane": 2}), lanes=2)
    a = speed_ok(engine, over_lane, V("passenger_car"), 90, lane=2)
    assert a.verdict == Verdict.no and "F.4" not in articles(a)
    assert speed_ok(engine, over_lane, V("passenger_car"), 90, lane=1).verdict == Verdict.yes
    with_plate = scene(sign("s1", "P.127", value=80,
                            plates=[{"kind": "lane", "lanes": [2]}]), lanes=2)
    a = speed_ok(engine, with_plate, V("passenger_car"), 90, lane=2)
    assert a.verdict == Verdict.no and "F.4" in articles(a)
