"""Schema 1.2: vehicle bounds, meaning selectors, time intervals with a quantifier,
Forbidden, condition groups, and Choose."""

import datetime as dt

import pytest
from pydantic import ValidationError

from vqa.parsing.dsl import normalize
from vqa.reasoning.engine import EngineError
from vqa.schemas import (
    BanTimes, ChoiceOption, Choose, Forbidden, Meaning, Permitted, Selector, Sign,
    SpeedOk, Verdict, Verify, When,
)

from conftest import V, articles, scene, sign, spec, times


def permitted(engine, sc, action, vehicle, when=None, **kw):
    return engine.answer(sc, Permitted(action=action, vehicle=vehicle, when=when, **kw))


def forbidden(engine, sc, action, vehicle, when):
    return engine.answer(sc, Forbidden(action=action, vehicle=vehicle, when=when))


def iv(start, end, q, date=None):
    return When(start=start, end=end, quantifier=q, date=date)


# ---------------------------------------------------------------- vehicle bounds

def test_bounds_validation():
    with pytest.raises(ValidationError):
        V("coach", seats=30, seats_gt=29)
    with pytest.raises(ValidationError):
        V("truck", load_gt=5, load_lt=3)


def test_seat_bounds(engine):
    sc = scene(sign("s1", "P.107a", value=29))  # bans coaches with more than 29 seats
    assert permitted(engine, sc, "enter", V("coach", seats_gt=29)).verdict == Verdict.no
    assert permitted(engine, sc, "enter", V("coach", seats_gt=16)).verdict == Verdict.unknown
    assert permitted(engine, sc, "enter", V("coach", seats_lt=16)).verdict == Verdict.yes
    # integer seats: "more than 28" includes 29, which the sign does not ban
    assert permitted(engine, sc, "enter", V("coach", seats_gt=28)).verdict == Verdict.unknown


def test_load_bounds(engine):
    sc = scene(sign("s1", "P.106b", value=2.5))
    assert permitted(engine, sc, "enter", V("truck", load_gt=3.5)).verdict == Verdict.no
    assert permitted(engine, sc, "enter", V("truck", load_lt=2)).verdict == Verdict.yes
    assert permitted(engine, sc, "enter", V("truck", load_gt=2, load_lt=3)).verdict == Verdict.unknown
    # "more than 2.5 t" against "more than 2.5 t is banned": every such truck is banned
    assert permitted(engine, sc, "enter", V("truck", load_gt=2.5)).verdict == Verdict.no


def test_gross_bounds(engine):
    sc = scene(sign("s1", "P.115", value=10))
    assert permitted(engine, sc, "enter", V("truck", gross_gt=12)).verdict == Verdict.no
    assert permitted(engine, sc, "enter", V("truck", gross_lt=10)).verdict == Verdict.yes


# ---------------------------------------------------------------- meaning selector

def test_select_by_meaning(engine):
    # "Biển cấm xe máy trong ảnh có cho phép xe ba bánh đi qua không?"
    sc = scene(sign("s1", "P.104"), sign("s2", "P.111b"))
    a = permitted(engine, sc, "enter", V("motor_tricycle"), sign=Selector(meaning="no_motorbikes"))
    assert a.verdict == Verdict.yes


def test_meaning_tag(engine):
    sc = scene(sign("s1", "P.127", value=60), sign("s2", "P.124a"))
    a = engine.answer(sc, Meaning(sign=Selector(meaning="speed_limit")))
    assert [v["code"] for v in a.value] == ["P.127"]


def test_unknown_meaning_is_rejected(engine):
    with pytest.raises(EngineError):
        engine.answer(scene(sign("s1", "P.104")), Meaning(sign=Selector(meaning="no_dragons")))


# ---------------------------------------------------------------- intervals and Forbidden

def test_when_validation():
    with pytest.raises(ValidationError):
        When(start=dt.time(6), end=dt.time(9))  # quantifier missing
    with pytest.raises(ValidationError):
        When(time=dt.time(7), start=dt.time(6), end=dt.time(9), quantifier="all")
    with pytest.raises(ValidationError):
        When(time=dt.time(7), quantifier="all")


def test_forbidden_compiles_to_verify_with_flipped_quantifier():
    f = Forbidden(action="enter", vehicle=V("car"), when=iv(dt.time(6), dt.time(9), "all"))
    v = normalize(f)
    assert isinstance(v, Verify) and v.expect is False
    assert v.claim.intent == "permitted" and v.claim.when.quantifier.value == "any"
    v = normalize(Verify(claim=f, expect=False))
    assert v.expect is True and v.claim.when.quantifier.value == "any"


def test_interval_inside_and_across_a_window(engine):
    sc = scene(sign("s1", "P.104", plates=[times(("06:00", "09:00"))]))
    mb = V("motorbike")
    assert forbidden(engine, sc, "enter", mb, iv(dt.time(7), dt.time(8), "all")).verdict == Verdict.yes
    a = forbidden(engine, sc, "enter", mb, iv(dt.time(5), dt.time(8), "all"))
    assert a.verdict == Verdict.no and a.value["decided_at"] == "05:00"
    assert forbidden(engine, sc, "enter", mb, iv(dt.time(5), dt.time(8), "any")).verdict == Verdict.yes
    assert forbidden(engine, sc, "enter", mb, iv(dt.time(10), dt.time(12), "any")).verdict == Verdict.no
    assert permitted(engine, sc, "enter", mb, iv(dt.time(5), dt.time(8), "any")).verdict == Verdict.yes
    assert permitted(engine, sc, "enter", mb, iv(dt.time(5), dt.time(8), "all")).verdict == Verdict.no


def test_time_window_across_midnight(engine):
    sc = scene(sign("s1", "P.106a", plates=[times(("22:00", "06:00"))]))
    tr = V("truck")
    assert forbidden(engine, sc, "enter", tr, iv(dt.time(23), dt.time(5), "all")).verdict == Verdict.yes
    assert forbidden(engine, sc, "enter", tr, iv(dt.time(22), dt.time(6), "all")).verdict == Verdict.yes
    assert forbidden(engine, sc, "enter", tr, iv(dt.time(21), dt.time(23), "all")).verdict == Verdict.no
    assert forbidden(engine, sc, "enter", tr, iv(dt.time(21), dt.time(23), "any")).verdict == Verdict.yes
    a = forbidden(engine, sc, "enter", tr, iv(dt.time(5), dt.time(7), "all"))
    assert a.verdict == Verdict.no and a.value["decided_at"] == "06:01"
    assert forbidden(engine, sc, "enter", tr, iv(dt.time(7), dt.time(21), "any")).verdict == Verdict.no
    assert {"41", "F.10"} <= articles(forbidden(engine, sc, "enter", tr,
                                                iv(dt.time(23), dt.time(5), "all")))


def test_day_parity_across_midnight(engine):
    sc = scene(sign("s1", "P.131c"))  # no parking on even days
    car = V("passenger_car")
    night = lambda d, q: iv(dt.time(22), dt.time(2), q, date=d)
    # starts on the 2nd (even), after midnight it is the 3rd (odd)
    assert forbidden(engine, sc, "park", car, night(dt.date(2025, 9, 2), "all")).verdict == Verdict.no
    assert forbidden(engine, sc, "park", car, night(dt.date(2025, 9, 2), "any")).verdict == Verdict.yes
    # starts on the 1st (odd), after midnight it is the 2nd (even)
    a = forbidden(engine, sc, "park", car, night(dt.date(2025, 9, 1), "any"))
    assert a.verdict == Verdict.yes and a.value["decided_at"] == "00:00"
    # no date: depends on the day
    assert forbidden(engine, sc, "park", car, night(None, "any")).verdict == Verdict.unknown


def test_day_parity_across_month_end(engine):
    # 31 Aug and 1 Sep are both odd days
    sc = scene(sign("s1", "P.131b"))  # no parking on odd days
    w = iv(dt.time(22), dt.time(2), "all", date=dt.date(2025, 8, 31))
    assert forbidden(engine, sc, "park", V("passenger_car"), w).verdict == Verdict.yes


def test_interval_on_other_intents_is_unknown(engine):
    a = engine.answer(scene(sign("s1", "P.127", value=50)),
                      SpeedOk(vehicle=V("car"), speed_kmh=60,
                              when=iv(dt.time(6), dt.time(9), "all")))
    assert a.verdict == Verdict.unknown


# ---------------------------------------------------------------- condition groups

def board_sign():
    """One P.107 with two (vehicle, time) groups, as on the train_2_25 board."""
    return sign("s1", "P.107", rules=[
        {"vehicles": [spec("truck", ("gross_t", "le", 1.5))],
         "time_windows": [{"start": "06:00", "end": "09:00"}, {"start": "16:00", "end": "19:30"}]},
        {"vehicles": [spec("truck", ("gross_t", "gt", 1.5))],
         "time_windows": [{"start": "06:00", "end": "21:00"}]},
    ])


def test_groups_validation():
    with pytest.raises(ValidationError):
        Sign(id="s1", code="P.107", rules=[{"vehicles": [spec("truck")]}],
             plates=[times(("06:00", "09:00"))])


def test_groups_ban_times(engine):
    sc = scene(board_sign())
    [ban] = engine.answer(sc, BanTimes(vehicle=V("truck", gross_t=2))).value["bans"]
    assert ban["windows"] == [["06:00", "21:00"]]
    [ban] = engine.answer(sc, BanTimes(vehicle=V("truck", gross_t=1))).value["bans"]
    assert ban["windows"] == [["06:00", "09:00"], ["16:00", "19:30"]]


def test_groups_pair_vehicle_with_time(engine):
    sc = scene(board_sign())
    at10 = When(time=dt.time(10))
    heavy = permitted(engine, sc, "enter", V("truck", gross_t=2), at10)
    assert heavy.verdict == Verdict.no and {"22", "B.7", "41", "F.5", "F.10"} <= articles(heavy)
    light = permitted(engine, sc, "enter", V("truck", gross_t=1), at10)
    assert light.verdict == Verdict.yes
    assert {r.sign_id: r.detail for r in light.reasons} == {"s1": "outside_time_window"}
    assert permitted(engine, sc, "enter", V("truck"), at10).verdict == Verdict.unknown
    bus = permitted(engine, sc, "enter", V("coach"), at10)
    assert bus.verdict == Verdict.yes and bus.reasons[0].detail == "plate_vehicle_not_covered"
    # "banned for the whole of 6h-21h": only the heavy truck
    whole = iv(dt.time(6), dt.time(21), "all")
    assert forbidden(engine, sc, "enter", V("truck", gross_t=2), whole).verdict == Verdict.yes
    assert forbidden(engine, sc, "enter", V("truck", gross_t=1), whole).verdict == Verdict.no


# ---------------------------------------------------------------- choose

def test_choose_speeds(engine):
    # "trong các mức 30, 35, 40 và 45 km/h, mức nào vi phạm?"
    sc = scene(sign("s1", "P.127", value=40))
    a = engine.answer(sc, Choose(options=[
        ChoiceOption(label=f"{k} km/h", expect=False,
                     claim=SpeedOk(vehicle=V("motor_vehicle"), speed_kmh=k))
        for k in (30, 35, 40, 45)]))
    assert a.verdict == Verdict.value
    assert a.value["holding"] == ["45 km/h"]
    assert a.value["not_holding"] == ["30 km/h", "35 km/h", "40 km/h"]
    assert {"22", "B.27"} <= articles(a)


def test_choose_with_forbidden_options(engine):
    sc = scene(sign("s1", "P.104", plates=[times(("06:00", "09:00"))]))
    a = engine.answer(sc, Choose(options=[
        ChoiceOption(label=f"{h}h", claim=Forbidden(action="enter", vehicle=V("motorbike"),
                                                    when=When(time=dt.time(h))))
        for h in (5, 7, 12)]))
    assert a.value["holding"] == ["7h"]
    assert a.value["not_holding"] == ["5h", "12h"]


def test_width_limit_p118(engine):
    """P.118 bans vehicles wider than the value, priority vehicles included (B.18 b)."""
    sc = scene(sign("s1", "P.118", value=2.5))
    wide = permitted(engine, sc, "enter", V("truck", width_m=2.8))
    assert wide.verdict == Verdict.no and "B.18" in articles(wide)
    assert permitted(engine, sc, "enter", V("car", width_m=1.8)).verdict == Verdict.yes
    assert permitted(engine, sc, "enter", V("truck", width_m=2.8, priority=True)).verdict == Verdict.no
    assert permitted(engine, sc, "enter", V("truck")).verdict == Verdict.unknown
