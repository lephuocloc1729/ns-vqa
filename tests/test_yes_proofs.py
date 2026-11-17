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


def test_unreadable_sign_turns_closed_world_answers_unknown(engine):
    from vqa.schemas import Required
    # an unreadable red-bordered circle could be a prohibition
    sc = scene(sign("s1", "P.104"), sign("s2", "UNKNOWN", shape="circle", border="red"))
    a = permitted(engine, sc, "enter", V("passenger_car"))
    assert a.verdict == Verdict.unknown and a.uncertain_signs == ["s2"]
    # a ban the engine can read stands
    assert permitted(engine, sc, "enter", V("motorbike")).verdict == Verdict.no
    assert engine.answer(sc, SpeedOk(vehicle=V("car"), speed_kmh=50)).verdict == Verdict.unknown
    # nothing recorded about how it looks: assume it could matter
    bare = scene(sign("s1", "P.104"), sign("s2", "UNKNOWN"))
    assert permitted(engine, bare, "enter", V("passenger_car")).verdict == Verdict.unknown


def test_unreadable_sign_that_cannot_matter_is_ignored(engine):
    from vqa.schemas import Required
    board = sign("s2", "UNKNOWN", shape="rectangle", background="blue")
    sc = scene(sign("s1", "P.104"), board, lanes=2)
    # a blue rectangular board cannot ban turning or entering the road ...
    assert permitted(engine, sc, "enter", V("passenger_car")).verdict == Verdict.yes
    assert permitted(engine, sc, "turn_left", V("passenger_car")).verdict == Verdict.yes
    # ... but it could be a lane board, so it matters for a lane or a speed
    assert engine.answer(sc, Permitted(action="enter", vehicle=V("passenger_car"),
                                       lane=1)).verdict == Verdict.unknown
    assert engine.answer(sc, SpeedOk(vehicle=V("car"), speed_kmh=50)).verdict == Verdict.unknown
    # a warning triangle never restricts
    tri = scene(sign("s1", "P.104"), sign("s2", "UNKNOWN", shape="triangle", border="red"))
    assert permitted(engine, tri, "enter", V("passenger_car")).verdict == Verdict.yes
    # a blue circle (mandatory) matters for directions and "required", not for parking
    blue = scene(sign("s2", "UNKNOWN", shape="circle", background="blue"))
    assert permitted(engine, blue, "turn_left", V("car")).verdict == Verdict.unknown
    assert permitted(engine, blue, "park", V("car")).verdict == Verdict.yes
    assert engine.answer(blue, Required(action="turn_right")).verdict == Verdict.unknown
    assert engine.answer(scene(sign("s1", "P.104")),
                         Required(action="turn_right")).verdict == Verdict.no


def test_sign_with_unmodelled_effect_acts_like_an_unreadable_sign(engine):
    """effect_unmodelled rows (R.302, R.303, R.411, R.420): known by code and meaning,
    but a closed-world "yes" they could overturn becomes unknown."""
    from vqa.schemas import IsSign, Meaning, Required, Selector
    rb = scene(sign("s1", "R.303", shape="circle", background="blue"))
    a = permitted(engine, rb, "turn_left", V("car"))
    assert a.verdict == Verdict.unknown and a.uncertain_signs == ["s1"]
    assert "don't model" in a.note
    assert engine.answer(rb, Required(action="turn_right")).verdict == Verdict.unknown
    assert permitted(engine, rb, "park", V("car")).verdict == Verdict.yes      # can't bear on parking
    # identity and meaning still work
    assert engine.answer(rb, IsSign(sign=Selector(only=True), code="R.303")).verdict == Verdict.yes
    m = engine.answer(rb, Meaning(sign=Selector(only=True)))
    assert m.value[0]["name_vi"] == "Nơi giao nhau chạy theo vòng xuyến"
    # a family variant resolves to the family row
    keep = scene(sign("s1", "R.302a", shape="circle", background="blue"))
    assert engine.answer(keep, IsSign(sign=Selector(only=True), code="R.302a")).verdict == Verdict.yes
    assert permitted(engine, keep, "go_straight", V("car")).verdict == Verdict.unknown
    # a board (R.411) orders the direction on every lane (D.13), so it bears on direction
    # claims with or without a lane (phase 4.5 rank 1, owner 2026-11-17); not on parking
    lanes = scene(sign("s1", "R.411", shape="rectangle", background="blue"), lanes=2)
    assert permitted(engine, lanes, "turn_left", V("car")).verdict == Verdict.unknown
    assert permitted(engine, lanes, "park", V("car")).verdict == Verdict.yes
    assert engine.answer(lanes, Permitted(action="turn_left", vehicle=V("car"),
                                          lane=1)).verdict == Verdict.unknown
    # R.420 (built-up area speed rules are not modelled): a speed claim becomes unknown
    town = scene(sign("s1", "R.420", shape="rectangle", background="blue"))
    assert engine.answer(town, SpeedOk(vehicle=V("car"), speed_kmh=70)).verdict == Verdict.unknown
    # a ban the engine can read still stands next to it
    both = scene(sign("s1", "P.123a"), sign("s2", "R.303", shape="circle", background="blue"))
    assert permitted(engine, both, "turn_left", V("car")).verdict == Verdict.no


def test_effect_unmodelled_rows_have_no_effect():
    from vqa.kb import load_catalog
    rows = [s for s in load_catalog().signs if s.effect_unmodelled]
    assert {s.code for s in rows} == {"R.302(a,b,c)", "R.303", "R.411", "R.420"}
    assert all(s.category == "mandatory" and not s.meaning_only for s in rows)
