"""Rule family: prohibitions (QCVN 41:2024 art. 22, appendix B) and mandatory directions."""

from vqa.schemas import ExistsViolation, Permitted, Selector, Verdict, Verify

from conftest import V, articles, except_for, only_for, scene, sign, spec


def permitted(engine, sc, action, vehicle, **kw):
    return engine.answer(sc, Permitted(action=action, vehicle=vehicle, **kw))


# ---------------------------------------------------------------- vehicle classes

def test_no_motorbikes_bans_motorbikes_and_mopeds(engine):
    sc = scene(sign("s1", "P.104"))
    a = permitted(engine, sc, "enter", V("motorbike"))
    assert a.verdict == Verdict.no
    assert {"B.4", "22"} <= articles(a)
    assert permitted(engine, sc, "enter", V("moped")).verdict == Verdict.no
    assert permitted(engine, sc, "enter", V("passenger_car")).verdict == Verdict.yes


def test_no_motorbikes_does_not_cover_motor_tricycles(engine):
    # xe lam / xích lô máy have their own sign P.111b (B.11)
    sc = scene(sign("s1", "P.104"))
    assert permitted(engine, sc, "enter", V("motor_tricycle")).verdict == Verdict.yes
    sc = scene(sign("s1", "P.111b"))
    a = permitted(engine, sc, "enter", V("motor_tricycle"))
    assert a.verdict == Verdict.no and "B.11" in articles(a)


def test_no_cars_excepts_two_wheelers(engine):
    sc = scene(sign("s1", "P.103a"))
    assert permitted(engine, sc, "enter", V("truck")).verdict == Verdict.no
    assert permitted(engine, sc, "enter", V("motorcycle")).verdict == Verdict.yes
    assert permitted(engine, sc, "enter", V("moped")).verdict == Verdict.yes
    # "kể cả xe máy 3 bánh có thùng"
    assert permitted(engine, sc, "enter", V("sidecar")).verdict == Verdict.no
    # "xe máy" in general: two-wheelers pass, sidecars do not -> depends on the vehicle
    assert permitted(engine, sc, "enter", V("motorbike")).verdict == Verdict.unknown


def test_broader_class_than_the_ban_is_unknown(engine):
    sc = scene(sign("s1", "P.106a"))
    assert permitted(engine, sc, "enter", V("car")).verdict == Verdict.unknown
    assert permitted(engine, sc, "enter", V("passenger_car")).verdict == Verdict.yes
    # B.6 a: also tractors and special machines
    assert permitted(engine, sc, "enter", V("tractor")).verdict == Verdict.no


def test_truck_load_limit_from_sign_value(engine):
    sc = scene(sign("s1", "P.106b", value=2.5, unit="t"))
    assert permitted(engine, sc, "enter", V("truck", load_t=3.4)).verdict == Verdict.no
    assert permitted(engine, sc, "enter", V("truck", load_t=2.0)).verdict == Verdict.yes
    assert permitted(engine, sc, "enter", V("truck")).verdict == Verdict.unknown


def test_bus_ban_by_seats_and_city_bus_exception(engine):
    sc = scene(sign("s1", "P.107a", value=29))
    a = permitted(engine, sc, "enter", V("coach", seats=45))
    assert a.verdict == Verdict.no and "B.7a" in articles(a)
    assert permitted(engine, sc, "enter", V("coach", seats=16)).verdict == Verdict.yes
    # "Biển này không cấm xe buýt"
    assert permitted(engine, sc, "enter", V("city_bus", seats=60)).verdict == Verdict.yes
    # "ô tô khách" without saying whether it is a city bus: depends
    assert permitted(engine, sc, "enter", V("bus", seats=45)).verdict == Verdict.unknown


# ---------------------------------------------------------------- actions

def test_no_left_turn_does_not_ban_u_turn(engine):
    sc = scene(sign("s1", "P.123a"))
    assert permitted(engine, sc, "turn_left", V("passenger_car")).verdict == Verdict.no
    assert permitted(engine, sc, "u_turn", V("passenger_car")).verdict == Verdict.yes
    assert permitted(engine, sc, "turn_right", V("passenger_car")).verdict == Verdict.yes


def test_no_u_turn_does_not_ban_left_turn(engine):
    sc = scene(sign("s1", "P.124a"))
    assert permitted(engine, sc, "u_turn", V("bicycle")).verdict == Verdict.no
    assert permitted(engine, sc, "turn_left", V("bicycle")).verdict == Verdict.yes


def test_no_left_turn_and_u_turn(engine):
    sc = scene(sign("s1", "P.124c"))
    assert permitted(engine, sc, "turn_left", V("truck")).verdict == Verdict.no
    assert permitted(engine, sc, "u_turn", V("truck")).verdict == Verdict.no
    assert permitted(engine, sc, "turn_right", V("truck")).verdict == Verdict.yes


def test_no_u_turn_for_cars_only(engine):
    sc = scene(sign("s1", "P.124b"))
    assert permitted(engine, sc, "u_turn", V("passenger_car")).verdict == Verdict.no
    assert permitted(engine, sc, "u_turn", V("motorcycle")).verdict == Verdict.yes


def test_mandatory_direction_forbids_other_directions(engine):
    sc = scene(sign("s1", "R.301g"))  # straight or left only
    assert permitted(engine, sc, "go_straight", V("car")).verdict == Verdict.yes
    assert permitted(engine, sc, "turn_left", V("car")).verdict == Verdict.yes
    a = permitted(engine, sc, "turn_right", V("car"))
    assert a.verdict == Verdict.no and {"D.1a", "32"} <= articles(a)


# ---------------------------------------------------------------- exemptions and plates

def test_priority_vehicles_exempt_except_where_the_article_says_not(engine):
    sc = scene(sign("s1", "P.104"))
    assert permitted(engine, sc, "enter", V("motorbike", priority=True)).verdict == Verdict.yes
    # B.25 b: no overtaking applies "kể cả xe được ưu tiên"
    sc = scene(sign("s1", "P.125"))
    assert permitted(engine, sc, "overtake", V("passenger_car", priority=True)).verdict == Verdict.no


def test_truck_overtaking_ban_threshold(engine):
    sc = scene(sign("s1", "P.126"))
    assert permitted(engine, sc, "overtake", V("truck", load_t=5)).verdict == Verdict.no
    assert permitted(engine, sc, "overtake", V("truck", load_t=2)).verdict == Verdict.yes
    assert permitted(engine, sc, "overtake", V("passenger_car")).verdict == Verdict.yes


def test_vehicle_plate_narrows_sign(engine):
    sc = scene(sign("s1", "P.123a", plates=[only_for(spec("truck"))]))
    a = permitted(engine, sc, "turn_left", V("truck"))
    assert a.verdict == Verdict.no and "F.5" in articles(a)
    assert permitted(engine, sc, "turn_left", V("passenger_car")).verdict == Verdict.yes


def test_exception_plate(engine):
    sc = scene(sign("s1", "P.101", plates=[except_for(spec("city_bus"))]))
    assert permitted(engine, sc, "enter", V("city_bus")).verdict == Verdict.yes
    assert permitted(engine, sc, "enter", V("passenger_car")).verdict == Verdict.no
    # "ô tô khách" may or may not be a city bus
    assert permitted(engine, sc, "enter", V("bus")).verdict == Verdict.unknown


def test_selector_restricts_to_one_sign(engine):
    # "Biển cấm xe máy trong ảnh có cho phép xe ba bánh đi qua không?"
    sc = scene(sign("s1", "P.104"), sign("s2", "P.111b"))
    a = permitted(engine, sc, "enter", V("motor_tricycle"), sign=Selector(code="P.104"))
    assert a.verdict == Verdict.yes
    assert permitted(engine, sc, "enter", V("motor_tricycle")).verdict == Verdict.no


def test_end_of_restriction_in_same_image_is_unknown(engine):
    sc = scene(sign("s1", "P.125"), sign("s2", "DP.133"))
    assert permitted(engine, sc, "overtake", V("passenger_car")).verdict == Verdict.unknown
    sc = scene(sign("s2", "DP.133"))
    assert permitted(engine, sc, "overtake", V("passenger_car")).verdict == Verdict.yes


# ---------------------------------------------------------------- violations

def test_violation_from_observed_action(engine):
    sc = scene(sign("s1", "P.123a"),
               vehicles=[{"id": "v1", "class": "passenger_car", "action": "turn_left"}])
    a = engine.answer(sc, ExistsViolation())
    assert a.verdict == Verdict.yes and a.value["violations"] == ["v1:action"]
    # "Trong hình không phát hiện hành vi vi phạm, đúng hay sai?" -> Sai
    v = engine.answer(sc, Verify(claim=ExistsViolation(), expect=False))
    assert v.verdict == Verdict.no


def test_no_violation_and_unknown_action(engine):
    sc = scene(sign("s1", "P.123a"),
               vehicles=[{"id": "v1", "class": "passenger_car", "action": "go_straight"}])
    assert engine.answer(sc, ExistsViolation()).verdict == Verdict.no
    sc = scene(sign("s1", "P.123a"),
               vehicles=[{"id": "v1", "class": "passenger_car", "action": "unknown"}])
    assert engine.answer(sc, ExistsViolation()).verdict == Verdict.unknown
