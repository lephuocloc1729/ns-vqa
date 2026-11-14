"""Rule family: time-window plates (S.508, QCVN 41:2024 F.10) and day parity (B.31)."""

import datetime as dt

from vqa.schemas import BanTimes, Permitted, Verdict, Verify, When

from conftest import V, articles, at, scene, sign, times


def permitted(engine, sc, action, vehicle, when=None):
    return engine.answer(sc, Permitted(action=action, vehicle=vehicle, when=when))


def test_bus_ban_times(engine):
    # "xe khách trên 29 chỗ bị cấm lưu thông vào những khoảng thời gian nào?"
    sc = scene(sign("s1", "P.107a", value=29,
                    plates=[times(("06:30", "08:00"), ("16:30", "18:30"))]))
    a = engine.answer(sc, BanTimes(vehicle=V("coach", seats=45)))
    assert a.verdict == Verdict.value
    [ban] = a.value["bans"]
    assert ban["windows"] == [["06:30", "08:00"], ["16:30", "18:30"]]
    assert ban["truth"] == "true" and not ban["always"]
    assert {"22", "B.7a", "F.10"} <= articles(a)
    # a 16-seat bus is not covered at any time
    assert engine.answer(sc, BanTimes(vehicle=V("coach", seats=16))).value["banned"] is False


def test_ban_without_time_plate_is_always(engine):
    sc = scene(sign("s1", "P.104"))
    [ban] = engine.answer(sc, BanTimes(vehicle=V("motorbike"))).value["bans"]
    assert ban["always"] is True


def test_inside_outside_and_unknown_time(engine):
    sc = scene(sign("s1", "P.104", plates=[times(("06:00", "09:00"), ("16:30", "19:30"))]))
    assert permitted(engine, sc, "enter", V("motorbike"), at(7)).verdict == Verdict.no
    assert permitted(engine, sc, "enter", V("motorbike"), at(17)).verdict == Verdict.no
    assert permitted(engine, sc, "enter", V("motorbike"), at(12)).verdict == Verdict.yes
    a = permitted(engine, sc, "enter", V("motorbike"))
    assert a.verdict == Verdict.unknown  # depends on time, never a guess
    assert a.reasons[0].truth == "unknown"


def test_verify_claim_inside_window(engine):
    # "Xe máy có được phép lưu thông ... từ 6:00 đến 9:00 ... đúng hay sai?" -> Sai
    sc = scene(sign("s1", "P.104", plates=[times(("06:00", "09:00"), ("16:30", "19:30"))]))
    claim = Permitted(action="enter", vehicle=V("motorbike"), when=at(6))
    assert engine.answer(sc, Verify(claim=claim)).verdict == Verdict.no


def test_several_times_asked(engine):
    # "xe ba bánh ... có được lưu thông vào 5 giờ, 12 giờ, 15 giờ và 19 giờ không?"
    sc = scene(sign("s1", "P.111d", plates=[times(("05:00", "13:00"), ("17:00", "21:00"))]))
    got = {h: permitted(engine, sc, "enter", V("cyclo"), at(h)).verdict for h in (5, 12, 15, 19)}
    assert got == {5: Verdict.no, 12: Verdict.no, 15: Verdict.yes, 19: Verdict.no}


def test_window_ends_are_inclusive(engine):
    sc = scene(sign("s1", "P.103a", plates=[times(("06:00", "22:00"))]))
    assert permitted(engine, sc, "enter", V("passenger_car"), at(22)).verdict == Verdict.no
    assert permitted(engine, sc, "enter", V("passenger_car"), at(22, 1)).verdict == Verdict.yes
    assert permitted(engine, sc, "enter", V("passenger_car"), at(5, 59)).verdict == Verdict.yes


def test_overnight_window(engine):
    sc = scene(sign("s1", "P.106a", plates=[times(("22:00", "05:00"))]))
    assert permitted(engine, sc, "enter", V("truck"), at(23)).verdict == Verdict.no
    assert permitted(engine, sc, "enter", V("truck"), at(4)).verdict == Verdict.no
    assert permitted(engine, sc, "enter", V("truck"), at(6)).verdict == Verdict.yes


def test_even_day_parking_ban(engine):
    sc = scene(sign("s1", "P.131c"))
    on = lambda d: When(date=dt.date(2025, 9, d), time=dt.time(8, 0))
    a = permitted(engine, sc, "park", V("passenger_car"), on(2))
    assert a.verdict == Verdict.no and "B.31" in articles(a)
    assert permitted(engine, sc, "park", V("passenger_car"), on(3)).verdict == Verdict.yes
    assert permitted(engine, sc, "park", V("passenger_car"), at(8)).verdict == Verdict.unknown
    # stopping is not parking
    assert permitted(engine, sc, "stop", V("passenger_car"), on(2)).verdict == Verdict.yes


def test_scene_datetime_used_when_question_has_none(engine):
    sc = scene(sign("s1", "P.104", plates=[times(("06:00", "09:00"))]),
               context={"datetime": "2025-09-02T07:30:00"})
    assert permitted(engine, sc, "enter", V("motorbike")).verdict == Verdict.no
