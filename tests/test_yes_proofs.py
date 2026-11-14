"""Every answer has a proof: "yes" answers are backed by clears/5 and friends,
naming why each relevant sign does not go against the claim."""

import datetime as dt

from vqa.schemas import (
    BanTimes, ExistsViolation, LanesFor, Permitted, SpeedOk, Verdict, When,
)

from conftest import V, articles, at, except_for, lane, only_for, scene, sign, spec, times


def why(answer):
    return {r.sign_id: r.detail for r in answer.reasons if r.truth == "false"}


def permitted(engine, sc, action, vehicle, when=None):
    return engine.answer(sc, Permitted(action=action, vehicle=vehicle, when=when))


def test_outside_time_window(engine):
    sc = scene(sign("s1", "P.104", plates=[times(("06:00", "09:00"))]))
    a = permitted(engine, sc, "enter", V("motorbike"), at(12))
    assert a.verdict == Verdict.yes
    assert why(a) == {"s1": "outside_time_window"}
    assert {"22", "B.4", "41", "F.10"} <= articles(a)


def test_vehicle_not_covered_and_excepted(engine):
    sc = scene(sign("s1", "P.106a"), sign("s2", "P.103a"))
    a = permitted(engine, sc, "enter", V("motorcycle"))
    assert a.verdict == Verdict.yes
    assert why(a) == {"s1": "vehicle_not_covered", "s2": "excepted"}
    assert {"22", "B.6", "B.3"} <= articles(a)


def test_priority_vehicle_excepted(engine):
    a = permitted(engine, scene(sign("s1", "P.104")), "enter", V("motorbike", priority=True))
    assert why(a) == {"s1": "excepted"}


def test_plate_vehicle_not_covered(engine):
    sc = scene(sign("s1", "P.123a", plates=[only_for(spec("truck"))]))
    a = permitted(engine, sc, "turn_left", V("passenger_car"))
    assert why(a) == {"s1": "plate_vehicle_not_covered"}
    assert {"22", "B.23", "41", "F.5"} <= articles(a)


def test_exception_plate_cites_41(engine):
    sc = scene(sign("s1", "P.101", plates=[except_for(spec("city_bus"))]))
    a = permitted(engine, sc, "enter", V("city_bus"))
    assert why(a) == {"s1": "excepted"}
    assert {"22", "B.1", "41", "F.17"} <= articles(a)


def test_wrong_day(engine):
    a = permitted(engine, scene(sign("s1", "P.131c")), "park", V("passenger_car"),
                  When(date=dt.date(2025, 9, 3), time=dt.time(8)))
    assert why(a) == {"s1": "wrong_day"} and "B.31" in articles(a)


def test_direction_allowed(engine):
    a = permitted(engine, scene(sign("s1", "R.301g")), "turn_left", V("car"))
    assert why(a) == {"s1": "direction_allowed"}
    assert {"32", "D.1a"} <= articles(a)


def test_sign_about_another_action(engine):
    # P.104 says nothing about turning left: listed as not covering the action
    a = permitted(engine, scene(sign("s1", "P.104")), "turn_left", V("motorbike"))
    assert a.verdict == Verdict.yes
    assert why(a) == {"s1": "action_not_covered"} and "B.4" in articles(a)


def test_no_restricting_sign_at_all(engine):
    a = permitted(engine, scene(), "enter", V("truck"))
    assert a.verdict == Verdict.yes
    [r] = a.reasons
    assert r.detail == "no_restricting_sign" and r.proof is not None
    assert a.citations == []


def test_forbidding_sign_is_not_also_a_clearing_one(engine):
    sc = scene(sign("s1", "P.106a"), sign("s2", "P.104"))
    a = permitted(engine, sc, "enter", V("truck"))
    assert a.verdict == Verdict.no
    assert {r.sign_id: r.truth for r in a.reasons} == {"s1": "true", "s2": "false"}
    assert "B.4" not in articles(a)  # only the deciding sign is cited


def test_speed_within_limit(engine):
    a = engine.answer(scene(sign("s1", "P.127", value=50)),
                      SpeedOk(vehicle=V("passenger_car"), speed_kmh=45))
    assert a.verdict == Verdict.yes and why(a) == {"s1": "within_limit"}
    assert {"22", "B.27"} <= articles(a)


def test_speed_sign_on_another_lane(engine):
    sc = scene(sign("s1", "P.127", value=80, plates=[{"kind": "lane", "lanes": [2]}]), lanes=2)
    a = engine.answer(sc, SpeedOk(vehicle=V("passenger_car"), speed_kmh=100, lane=1))
    assert a.verdict == Verdict.yes and why(a) == {"s1": "lane_not_covered"}
    assert {"41", "F.4"} <= articles(a)


def test_lane_answers_cite_each_lane(engine):
    sc = scene(sign("s1", "R.412d", position={"lane": 2}), lanes=2)
    a = engine.answer(sc, LanesFor(vehicle=V("motorbike")))
    assert a.value["lanes"] == [1, 2]
    assert {"D.14", "32"} - {"32"} <= articles(a)
    details = {r.detail for r in a.reasons}
    assert {"lane_not_covered", "vehicle_allowed_on_lane"} <= details


def test_ban_times_nothing_banned(engine):
    a = engine.answer(scene(sign("s1", "P.107a", value=29)),
                      BanTimes(vehicle=V("coach", seats=16)))
    assert a.value["banned"] is False
    assert why(a) == {"s1": "vehicle_not_covered"} and "B.7a" in articles(a)


def test_no_violation_has_a_proof(engine):
    sc = scene(sign("s1", "P.123a"),
               vehicles=[{"id": "v1", "class": "passenger_car", "action": "go_straight"}])
    a = engine.answer(sc, ExistsViolation())
    assert a.verdict == Verdict.no
    assert "v1:action:action_not_covered" in {r.detail for r in a.reasons}
    assert "B.23" in articles(a)


def test_day_plate_cites_41(engine):
    sc = scene(sign("s1", "P.131a", plates=[{"kind": "time", "days": "odd"}]))
    a = permitted(engine, sc, "park", V("passenger_car"),
                  When(date=dt.date(2025, 9, 3), time=dt.time(8)))
    assert a.verdict == Verdict.no and {"41", "F.10", "B.31"} <= articles(a)
