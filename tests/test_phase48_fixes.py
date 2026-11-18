"""Phase 4.8 step 1 (owner, 2026-11-18): rule-only fixes for wrong dev2 answers
(kb/rules/fixes48.pl and the engine's violation check). Hand-made scenes modelled on train
questions (an expressway with P.127 90 / R.306 60; R.415a boards; a lone P.103a); no API call."""

from __future__ import annotations

import pytest

from vqa.reasoning.engine import Engine
from vqa.schemas import (AllOf, ExistsViolation, LanesFor, LaneSpec, Permitted, Position, Road, SceneGraph,
                         SceneVehicle, Sign, SpeedOk, Vehicle, VehicleClass, VehicleSpec, Verdict, WhichVehicles)


@pytest.fixture(scope="module")
def engine():
    return Engine(reading_policy="higher_confidence")


def S(sid, code, value=None, shape="circle", border="red", background="white", lanes=(), rank=1, side="right"):
    return Sign(id=sid, code=code, value=value, confidence="high", shape=shape, border=border,
                background=background, position=Position(rank_top_down=rank, side=side),
                lanes=[LaneSpec(lane=n, vehicles=[VehicleSpec(cls=VehicleClass(c)) for c in cs]) for n, cs in lanes])


def V(c):
    return Vehicle(cls=VehicleClass(c))


def scene(*signs, vehicles=()):
    return SceneGraph(scene_id="x", signs=list(signs), road=Road(), vehicles=list(vehicles))


def cites(a):
    return {(c.law_id, c.article_id) for c in a.citations}


# ---------------------------------------------------------------- expressway ban and speed (Law 36 art. 25.3)

EXPRESSWAY = scene(S("s1", "IE.452", shape="rectangle", border="none", background="green"),
                   S("s2", "P.127", value=90), S("s3", "R.306", value=60, border="none", background="blue"))


def test_a_motorbike_may_not_drive_on_an_expressway_at_any_speed(engine):
    """train_466-like: "xe máy có được chạy từ 60 đến 90 km/h không?" was yes; Law 36 art. 25.3
    keeps motorbikes off the expressway, so no, citing art. 25."""
    a = engine.answer(EXPRESSWAY, AllOf(claims=[SpeedOk(vehicle=V("motorbike"), speed_kmh=60),
                                                SpeedOk(vehicle=V("motorbike"), speed_kmh=90)]))
    assert a.verdict is Verdict.no
    one = engine.answer(EXPRESSWAY, SpeedOk(vehicle=V("motorbike"), speed_kmh=70))
    assert one.verdict is Verdict.no and ("36/2024/QH15", "25") in cites(one)


def test_a_car_on_an_expressway_keeps_its_speed_answer(engine):
    assert engine.answer(EXPRESSWAY, SpeedOk(vehicle=V("car"), speed_kmh=70)).verdict is Verdict.yes
    assert engine.answer(EXPRESSWAY, SpeedOk(vehicle=V("car"), speed_kmh=100)).verdict is Verdict.no


def test_a_broader_or_open_class_keeps_the_speed_signs_answer(engine):
    """"xe" (motor_vehicle, the parser's default) includes motorbikes, and art. 25.3's "các loại xe
    tương tự xe mô tô" leaves three-wheelers open: the speed signs decide (dev train_352, 381)."""
    for c in ("motor_vehicle", "motor_tricycle"):
        assert engine.answer(EXPRESSWAY, SpeedOk(vehicle=V(c), speed_kmh=70)).verdict is Verdict.yes, c


def test_off_the_expressway_a_motorbike_keeps_its_speed_answer(engine):
    sc = scene(S("s2", "P.127", value=60))
    assert engine.answer(sc, SpeedOk(vehicle=V("motorbike"), speed_kmh=50)).verdict is Verdict.yes


# ---------------------------------------------------------------- R.415a: vehicles on no lane (QCVN 41 D.16 a)

R415 = S("s1", "R.415a", shape="rectangle", border="none", background="blue",
         lanes=[(1, ["car"]), (2, ["car", "motorbike"]), (3, ["motorbike", "motor_tricycle", "bicycle"])])


def test_the_vehicles_allowed_on_an_r415a_board_are_the_ones_it_shows(engine):
    """train_121-like: "những loại xe nào được đi trên các làn?" answered every vehicle; D.16 a
    says the board shows the vehicles allowed on each lane."""
    a = engine.answer(scene(R415), WhichVehicles(action="enter", status="allowed"))
    assert a.verdict is Verdict.value
    allowed = set(a.value["allowed"])
    assert {"car", "motorbike", "motor_tricycle", "bicycle"} <= allowed
    assert a.value["per_class"]["truck"] == "yes"                 # a truck is an ô tô
    assert a.value["per_class"]["pedestrian"] == "yes"            # D.16 is about "loại xe": not covered
    # a vehicle that isn't a motor vehicle may have its own lane (D.16 d): unknown
    assert a.value["per_class"]["cyclo"] == "unknown" and a.value["per_class"]["special_machine"] == "unknown"
    assert ("QCVN 41:2024/BGTVT", "D.16") in cites(a)


def test_a_motor_vehicle_missing_from_the_board_may_not_enter(engine):
    sc = scene(S("s1", "R.415a", shape="rectangle", border="none", background="blue",
                 lanes=[(1, ["motorbike"]), (2, ["motorbike", "bicycle"])]))
    no = engine.answer(sc, Permitted(action="enter", vehicle=V("truck")))
    assert no.verdict is Verdict.no and ("QCVN 41:2024/BGTVT", "D.16") in cites(no)
    assert engine.answer(sc, Permitted(action="enter", vehicle=V("moped"))).verdict is Verdict.yes
    assert engine.answer(sc, Permitted(action="enter", vehicle=V("pedestrian"))).verdict is Verdict.yes


def test_a_board_with_no_lane_rows_bans_nothing(engine):
    sc = scene(S("s1", "R.415a", shape="rectangle", border="none", background="blue"))
    assert engine.answer(sc, Permitted(action="enter", vehicle=V("truck"))).verdict is Verdict.yes


# ---------------------------------------------------------------- two lane boards that disagree

def test_two_boards_that_disagree_about_a_lane_leave_it_unknown(engine):
    """train_516-like: the left board shows cars on lanes 1-3, the right one motorbikes on 2-3;
    the answer was "no lane"; a photo can't show which carriageway each covers."""
    left = S("s2", "R.415a", shape="rectangle", border="none", background="blue", side="left", rank=2,
             lanes=[(1, ["car"]), (2, ["car"]), (3, ["car"])])
    right = S("s3", "R.415a", shape="rectangle", border="none", background="blue", side="right", rank=3,
              lanes=[(1, ["car"]), (2, ["motorbike"]), (3, ["motorbike"])])
    a = engine.answer(scene(left, right), LanesFor(vehicle=V("motorbike")))
    per = {p["lane"]: p["verdict"] for p in a.value["per_lane"]}
    assert per[1] == "no" and per[2] == "unknown" and per[3] == "unknown"


def test_one_board_still_closes_a_lane(engine):
    one = S("s3", "R.415a", shape="rectangle", border="none", background="blue",
            lanes=[(1, ["car"]), (2, ["motorbike"]), (3, ["motorbike"])])
    a = engine.answer(scene(one), LanesFor(vehicle=V("motorbike")))
    per = {p["lane"]: p["verdict"] for p in a.value["per_lane"]}
    assert per == {1: "no", 2: "yes", 3: "yes"}


# ---------------------------------------------------------------- no vehicle read: no "no violation"

def test_no_vehicle_read_makes_exists_violation_unknown(engine):
    """train_502-like: "Ô tô trong ảnh vi phạm lỗi gì?" with P.103a and no vehicle read was "no"."""
    a = engine.answer(scene(S("s1", "P.103a")), ExistsViolation())
    assert a.verdict is Verdict.unknown and a.note == "no vehicle was read in the photo"


def test_a_read_vehicle_still_decides(engine):
    car = SceneVehicle(id="v1", cls=VehicleClass("car"), action="go_straight")
    a = engine.answer(scene(S("s1", "P.103a"), vehicles=[car]), ExistsViolation())
    assert a.note != "no vehicle was read in the photo"           # the check only applies with no vehicle read
    bike = SceneVehicle(id="v1", cls=VehicleClass("bicycle"), action="go_straight")
    assert engine.answer(scene(S("s1", "P.103a"), vehicles=[bike]), ExistsViolation()).verdict is Verdict.no


# ---------------------------------------------------------------- G1: several readable signs (switch)

from vqa.schemas import AnyOf, Confidence, IsSign, Meaning, Selector  # noqa: E402

SEVERAL = scene(S("s1", "IE.452", shape="rectangle", border="none", background="green"),
                S("s2", "P.127", value=90, rank=2), S("s3", "R.306", value=60, border="none", background="blue", rank=3))


def test_the_switch_is_on_in_the_kb_and_can_be_turned_off():
    from vqa.reasoning.engine import switches_from_kb
    assert switches_from_kb()["several_signs"] is True and Engine().several_signs is True
    assert Engine(several_signs=False).several_signs is False


def test_meaning_of_the_only_sign_over_several_lists_each_with_the_switch(engine):
    a = engine.answer(SEVERAL, Meaning(sign=Selector(only=True)))
    assert a.verdict is Verdict.value and [o["code"] for o in a.value] == ["IE.452", "P.127", "R.306"]
    assert a.note == "several signs in the scene: the meaning of each is given"
    off = Engine(reading_policy="higher_confidence", several_signs=False).answer(SEVERAL, Meaning(sign=Selector(only=True)))
    assert off.verdict is Verdict.unknown and off.note == "expected exactly one sign in the scene"


def test_several_signs_of_one_code_give_one_meaning(engine):
    sc = scene(S("s1", "P.104"), S("s2", "P.104", rank=2), S("s3", "P.127", value=50, rank=3))
    a = engine.answer(sc, Meaning(sign=Selector(only=True)))
    assert [o["code"] for o in a.value] == ["P.104", "P.127"]


def test_an_unreadable_sign_is_listed_as_uncertain(engine):
    sc = scene(S("s1", "P.104"), S("s2", "UNKNOWN", rank=2), S("s3", "P.127", value=50, rank=3))
    a = engine.answer(sc, Meaning(sign=Selector(only=True)))
    assert a.verdict is Verdict.value and a.uncertain_signs == ["s2"]


NO_PARKING = scene(S("s1", "P.131a", background="blue"), S("s2", "P.131b", background="blue", rank=2),
                   S("s3", "P.131c", background="blue", rank=3))
ONE_OF = AnyOf(claims=[IsSign(sign=Selector(only=True), meaning=m)
                       for m in ("no_parking", "no_parking_on_odd_days", "no_parking_on_even_days")])


def test_one_of_these_signs_is_checked_sign_by_sign(engine):
    """train_498-like: "Đây có phải là một trong các biển cấm đỗ xe không?" over P.131a/b/c."""
    a = engine.answer(NO_PARKING, ONE_OF)
    assert a.verdict is Verdict.yes and {x["verdict"] for x in a.value["per_sign"]} == {"yes"}
    mixed = scene(S("s1", "P.131a", background="blue"), S("s2", "P.104", rank=2))
    assert engine.answer(mixed, ONE_OF).verdict is Verdict.unknown
    none = scene(S("s1", "P.104"), S("s2", "P.106a", rank=2))
    assert engine.answer(none, ONE_OF).verdict is Verdict.no
    off = Engine(reading_policy="higher_confidence", several_signs=False).answer(NO_PARKING, ONE_OF)
    assert off.verdict is Verdict.unknown


# ---------------------------------------------------------------- A2: a misplaced priority field (wire)

def test_a_priority_field_on_an_intent_node_is_dropped_not_rejected():
    """dev2 train_282-like: the parser put `priority` on `rule_permitted` itself; the parse was
    refused. Now that key is dropped and the vehicle's own `priority` is kept."""
    from vqa.parsing.wire import from_wire, to_query
    reply = {"program": {"intent": "all_of", "claims": [
        {"intent": "rule_permitted", "action": "enter", "speed_kmh": 60, "priority": True,
         "vehicle": {"vehicle_class": "car", "priority": True}},
        {"intent": "rule_permitted", "action": "enter", "speed_kmh": 60, "priority": True,
         "vehicle": {"vehicle_class": "truck"}}]}}
    q = to_query(from_wire(reply), 2025)
    claims = q.program.claims
    assert claims[0].vehicle.priority is True and claims[1].vehicle.priority is False


def test_other_unknown_fields_are_still_rejected():
    import pydantic
    from vqa.parsing.wire import from_wire
    with pytest.raises(pydantic.ValidationError):
        from_wire({"program": {"intent": "rule_permitted", "action": "enter", "colour": "red"}})


# ---------------------------------------------------------------- A1: the confusable-sign table (switch)

def test_the_table_is_read_from_the_kb_with_family_rows():
    from vqa.reasoning.engine import confusables_from_kb
    from vqa.kb import load_catalog
    t = confusables_from_kb(load_catalog())
    assert t["P.130"] == ["P.131a"] and t["P.131a"] == ["P.130"]
    assert set(t["P.103a"]) == {"P.125", "P.107"} and t["W.202(a,b)"] == ["W.228(a,b)"]


def test_a_medium_p130_whose_partner_answers_differently_is_unknown():
    """train_119-like: a far P.131a read as P.130 (medium); "có được dừng xe không?" depends on which."""
    from vqa.schemas import Permitted
    sc = scene(S("s1", "P.130", background="blue").model_copy(update={"confidence": Confidence.medium}))
    on = Engine(reading_policy="higher_confidence", confusable_pairs=True)
    off = Engine(reading_policy="higher_confidence", confusable_pairs=False)
    q = Permitted(action="stop", vehicle=V("car"))
    assert off.answer(sc, q).verdict is Verdict.no
    a = on.answer(sc, q)
    assert a.verdict is Verdict.unknown and a.uncertain_signs == ["s1"] and "often confused" in a.note


def test_the_partner_that_gives_the_same_answer_keeps_it_decided():
    from vqa.schemas import Permitted
    sc = scene(S("s1", "P.130", background="blue").model_copy(update={"confidence": Confidence.medium}))
    on = Engine(reading_policy="higher_confidence", confusable_pairs=True)
    assert on.answer(sc, Permitted(action="park", vehicle=V("car"))).verdict is Verdict.no   # both ban parking


def test_a_high_confidence_sign_or_one_with_alternatives_is_left_alone():
    from vqa.schemas import AltReading, Permitted
    on = Engine(reading_policy="higher_confidence", confusable_pairs=True)
    q = Permitted(action="stop", vehicle=V("car"))
    high = scene(S("s1", "P.130", background="blue"))
    assert on.answer(high, q).verdict is Verdict.no
    alt = scene(S("s1", "P.130", background="blue").model_copy(update={
        "confidence": Confidence.medium, "alternatives": [AltReading(code="P.104", confidence="low")]}))
    assert on.answer(alt, q).verdict is Verdict.no


# ---------------------------------------------------------------- B3: limit values; B6: loose group words

def _limit(engine, code, value):
    sc = scene(S("s1", code, value=value))
    return engine.answer(sc, Meaning(sign=Selector(only=True), aspect="limit"))


def test_the_limit_of_a_size_or_weight_sign_is_its_number_with_its_article(engine):
    from vqa.answer.template import _value_text
    a = _limit(engine, "P.117", 4.3)          # train_240-like: "Chiều cao giới hạn ... là bao nhiêu?"
    assert a.verdict is Verdict.value and a.value["limit"][0]["attr"] == "height_m"
    assert ("QCVN 41:2024/BGTVT", "B.17") in cites(a)
    assert "chiều cao (kể cả hàng) trên 4,3 m" in _value_text({"value": a.value})
    b = _limit(engine, "P.115", 13.0)
    assert b.value["limit"][0]["attr"] == "gross_t" and ("QCVN 41:2024/BGTVT", "B.15") in cites(b)
    c = _limit(engine, "P.106b", 1.25)
    assert c.value["limit"][0]["attr"] == "load_t" and ("QCVN 41:2024/BGTVT", "B.6") in cites(c)


def test_an_unread_number_or_a_sign_with_no_limit_is_unknown(engine):
    assert _limit(engine, "P.117", None).verdict is Verdict.unknown
    assert _limit(engine, "P.104", None).verdict is Verdict.unknown
    assert _limit(engine, "P.127", 60.0).verdict is Verdict.unknown          # speeds are speed_limit's


def test_a_group_word_that_selects_nothing_falls_back_to_the_look_for_value_questions(engine):
    """train_169-like: "Biển chỉ dẫn trong ảnh ..." over an R.403b board (a mandatory sign)."""
    from vqa.schemas import AppliesTo
    board = S("s1", "R.403b", shape="rectangle", border="none", background="blue")
    a = engine.answer(scene(board), Meaning(sign=Selector(category="information")))
    assert a.verdict is Verdict.value and a.value[0]["code"] == "R.403b"
    assert a.note.startswith("no sign of the group the question names (information)")
    assert engine.answer(scene(board), AppliesTo(sign=Selector(category="information"))).verdict is Verdict.value


def test_claims_about_a_group_keep_the_strict_selection(engine):
    board = S("s1", "R.403b", shape="rectangle", border="none", background="blue")
    a = engine.answer(scene(board), IsSign(sign=Selector(only=True), category="information"))
    assert a.verdict is Verdict.no


def test_parser_v15_is_v14_plus_its_lines_and_train_working_set_few_shots():
    import json as _json
    from pathlib import Path as _P
    root = _P(__file__).resolve().parents[1] / "prompts" / "parser"
    v14 = (root / "v14" / "spec.md").read_text(encoding="utf-8")
    v15 = (root / "v15" / "spec.md").read_text(encoding="utf-8")
    assert "`limit`: the number a size or weight limit sign sets" in v15 and "`limit`" not in v14
    assert "khi nào mới được vượt" in v15 and "giao với đường sắt" in v15
    old = (root / "v14" / "fewshot.jsonl").read_text(encoding="utf-8").splitlines()
    new = (root / "v15" / "fewshot.jsonl").read_text(encoding="utf-8").splitlines()
    assert new[:len(old)] == old
    added = [_json.loads(x) for x in new[len(old):]]
    assert [r["id"] for r in added] == ["train_240", "train_501", "train_153"]
    splits = _P(__file__).resolve().parents[1] / "data" / "splits"
    held = set()
    for f in ("train_validation.json", "train_dev.json", "train_dev2.json"):
        held |= set(_json.loads((splits / f).read_text(encoding="utf-8"))["questions"])
    assert not {r["id"] for r in added} & held
