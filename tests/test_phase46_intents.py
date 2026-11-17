"""Phase 4.6 step 4 (owner, 2026-11-17): F1, F2, the day-parity slot, and intents I1-I4.
Hand-made scenes modelled on train questions (not copied); no API call."""

from __future__ import annotations

import pytest

from vqa.answer.digest import build as digest
from vqa.answer.template import template_answer
from vqa.parsing import validator
from vqa.parsing.wire import from_wire, to_query
from vqa.reasoning.engine import Engine
from vqa.schemas import (AllOf, Choose, ChoiceOption, Explain, Forbidden, Guide, GuideBoard, GuideClaim,
                         GuideEntry, IsSign, Meaning, Multi, Position, Present, QueryProgram, Road, SceneGraph,
                         Selector, Sign, SpeedLimit, SpeedLimitIs, SpeedOk, Verdict, Verify, When)

from conftest import V


@pytest.fixture(scope="module")
def engine():
    return Engine()


def S(sid, code, rank=1, value=None, shape="circle", border="red", background="white", conf="high"):
    return Sign(id=sid, code=code, value=value, confidence=conf, shape=shape, border=border,
                background=background, position=Position(rank_top_down=rank, side="right"))


def ONLY():
    return Selector(only=True)


def text(engine, scene, program, question="?"):
    a = engine.answer(scene, program)
    return a, template_answer(digest(a, scene, engine.catalog), question)


# ---------------------------------------------------------------- F1: is_sign with `only` over several signs

def test_f1_none_of_several_signs_is_the_named_one(engine):
    """Modelled on "Đây có phải là biển cấm đi ngược chiều không?" over a no-stopping disc and a
    blue board: neither is P.102, so no."""
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.130", background="blue"),
                                         S("s2", "I.408", rank=2, shape="square", border="none", background="blue")])
    a = engine.answer(sc, IsSign(sign=ONLY(), code="P.102"))
    assert a.verdict is Verdict.no


def test_f1_every_sign_is_one_of_the_named_family(engine):
    """Modelled on "Đây có phải là một trong các biển cấm đỗ xe không?" over three P.131 discs."""
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.131a", background="blue"), S("s2", "P.131b", 2, background="blue"),
                                         S("s3", "P.131c", 3, background="blue")])
    assert engine.answer(sc, IsSign(sign=ONLY(), meaning="parking_ban")).verdict is Verdict.yes


def test_f1_mixed_is_unknown_and_unreadable_signs_are_dropped(engine):
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.131a", background="blue"), S("s2", "P.102", 2),
                                         S("s3", "UNKNOWN", 3)])
    a = engine.answer(sc, IsSign(sign=ONLY(), meaning="parking_ban"))
    assert a.verdict is Verdict.unknown and a.uncertain_signs == ["s3"]
    sc2 = SceneGraph(scene_id="x", signs=[S("s1", "P.131a", background="blue"), S("s3", "UNKNOWN", 2)])
    assert engine.answer(sc2, IsSign(sign=ONLY(), meaning="parking_ban")).verdict is Verdict.yes


def test_f1_no_readable_sign_left_is_unknown(engine):
    sc = SceneGraph(scene_id="x", signs=[S("s1", "UNKNOWN"), S("s2", "UNKNOWN", 2)])
    assert engine.answer(sc, IsSign(sign=ONLY(), code="P.102")).verdict is Verdict.unknown


# ---------------------------------------------------------------- F2: negative presence and unreadable red boards

def test_f2_an_unread_red_board_keeps_a_no_unknown(engine):
    """Modelled on "Trong ảnh không có biển nào chỉ hướng ..., đúng không?" with warning signs and
    two red notice boards that could not be read: a local notice is free text, so it could be it."""
    sc = SceneGraph(scene_id="x", signs=[S("s1", "W.227", shape="triangle", background="yellow"),
                                         S("s2", "UNKNOWN", 2, shape="rectangle", border="none", background="red", conf="low")])
    a = engine.answer(sc, Verify(claim=Present(meaning="direction_order"), expect=False))
    assert a.verdict is Verdict.unknown and a.uncertain_signs == ["s2"]


def test_f2_an_unread_warning_sign_still_cannot_be_a_blue_disc(engine):
    sc = SceneGraph(scene_id="x", signs=[S("s1", "W.227", shape="triangle", background="yellow"),
                                         S("s2", "UNKNOWN", 2, shape="triangle", background="yellow", conf="low")])
    assert engine.answer(sc, Verify(claim=Present(meaning="direction_order"), expect=False)).verdict is Verdict.yes


# ---------------------------------------------------------------- day parity (D3, the even-day ban)

def test_day_parity_decides_an_even_day_parking_ban(engine):
    """Modelled on "Biển này có cấm đỗ xe vào ngày chẵn không?" under P.131c (even days)."""
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.131c", background="blue")])
    car = V("passenger_car")
    assert engine.answer(sc, Forbidden(action="park", vehicle=car, when=When(day_parity="even"))).verdict is Verdict.yes
    assert engine.answer(sc, Forbidden(action="park", vehicle=car, when=When(day_parity="odd"))).verdict is Verdict.no


def test_day_parity_and_weight_bounds_parse(engine):
    q = to_query(from_wire({"program": {"intent": "forbidden", "action": "park", "when": {"day_parity": "even"}}}), 2025)
    assert q.program.when.day_parity == "even" and validator.check(q, engine) == []
    q = to_query(from_wire({"program": {"intent": "permitted", "action": "enter", "lane": -1,
                                        "vehicle": {"vehicle_class": "motor_vehicle", "gross_gt": 3}}}), 2025)
    assert q.program.vehicle.gross_gt == 3 and validator.check(q, engine) == []


# ---------------------------------------------------------------- I1: multi, and the article aspect

def _board_scene():
    return SceneGraph(scene_id="x", signs=[S("s1", "P.127", value=40),
                                           S("s2", "I.414a", 2, shape="rectangle", border="none", background="blue")],
                      guide_boards=[GuideBoard(entries=[GuideEntry(text="Đường Tránh", direction="left"),
                                                        GuideEntry(text="Đường Hoa Sen", direction="straight", distance_m=500)])])


def test_multi_answers_each_part_and_is_decided_when_all_are(engine):
    """Modelled on "Tốc độ tối đa là bao nhiêu? Đi hướng nào đến ...?" (two asks)."""
    sc = _board_scene()
    p = Multi(parts=[SpeedLimit(), Guide(ask="direction", destination="Đường Tránh")])
    a, t = text(engine, sc, p)
    assert a.verdict is Verdict.value and [x["verdict"] for x in a.value["parts"]] == ["value", "value"]
    assert "40 km/h" in t and "trái" in t.lower()
    p2 = Multi(parts=[SpeedLimit(), Guide(ask="direction", destination="Sân bay")])
    assert engine.answer(sc, p2).verdict is Verdict.unknown


def test_article_aspect_names_the_group_article(engine):
    """Modelled on "Biển cấm trong ảnh có mã gì? ... quy định ở điều nào?"."""
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.110a")])
    a, t = text(engine, sc, Meaning(sign=Selector(category="prohibitory"), aspect="article"))
    assert a.verdict is Verdict.value and a.value["article"][0]["article"] == "22.1"
    assert {c.article_id for c in a.citations} >= {"22"} and "Điều 22.1" in t


def test_multi_parses_and_validates(engine):
    w = {"program": {"intent": "multi", "parts": [
        {"intent": "meaning", "sign": {"category": "prohibitory"}},
        {"intent": "meaning", "sign": {"category": "prohibitory"}, "aspect": "article"}]}}
    q = to_query(from_wire(w), 2025)
    assert isinstance(q.program, Multi) and validator.check(q, engine) == []


# ---------------------------------------------------------------- I2: guide claims and lookups

def test_distance_claims_against_the_board(engine):
    """Modelled on "Tôi đọc biển thế này có đúng không: X cách đây 30 km, còn Y cách 34 km?"."""
    sc = SceneGraph(scene_id="x", guide_boards=[GuideBoard(entries=[
        GuideEntry(text="Phủ Lý", distance_m=30000, direction="straight"),
        GuideEntry(text="Hưng Yên", distance_m=36000, direction="right")])])
    both = AllOf(claims=[GuideClaim(about="distance", destination="Phủ Lý", distance_m=30000),
                         GuideClaim(about="distance", destination="Hưng Yên", distance_m=34000)])
    assert engine.answer(sc, both).verdict is Verdict.no
    one = GuideClaim(about="distance", destination="Phủ Lý", distance_m=30000)
    assert engine.answer(sc, one).verdict is Verdict.yes
    assert engine.answer(sc, GuideClaim(about="distance", destination="Thái Bình", distance_m=5000)).verdict is Verdict.unknown


def test_direction_and_listed_claims(engine):
    sc = SceneGraph(scene_id="x", guide_boards=[GuideBoard(entries=[
        GuideEntry(text="Bến xe Nước Ngầm", direction="slight_right")], route="QL.1A")])
    assert engine.answer(sc, GuideClaim(about="direction", destination="Bến xe Nước Ngầm",
                                        direction="right")).verdict is Verdict.yes
    assert engine.answer(sc, GuideClaim(about="direction", destination="Bến xe Nước Ngầm",
                                        direction="left")).verdict is Verdict.no
    assert engine.answer(sc, GuideClaim(about="listed", destination="cao tốc Pháp Vân")).verdict is Verdict.no
    assert engine.answer(sc, GuideClaim(about="listed", destination="QL.1A")).verdict is Verdict.yes


def test_road_type_from_expressway_signs_and_route_plates(engine):
    """Modelled on "Đường trong ảnh có phải là đường cao tốc không?"."""
    ie = SceneGraph(scene_id="x", signs=[S("s1", "IE.452", shape="rectangle", border="white", background="green")])
    a = engine.answer(ie, GuideClaim(about="road_type", road_type="expressway"))
    assert a.verdict is Verdict.yes and any(c.article_id == "45" for c in a.citations)
    ql = SceneGraph(scene_id="x", road=Road(type="rural"), guide_boards=[GuideBoard(route="QL.10")])
    assert engine.answer(ql, GuideClaim(about="road_type", road_type="expressway")).verdict is Verdict.no
    assert engine.answer(ql, Guide(ask="road_type")).value == {"road_type": "national_road"}
    assert engine.answer(SceneGraph(scene_id="x"), GuideClaim(about="road_type",
                                                              road_type="expressway")).verdict is Verdict.unknown


def test_what_lies_ahead(engine):
    """Modelled on "Đường phía trước dẫn vào hầm ... phải không?" and "Phía trước có phải là lối ra ... không?"."""
    tunnel = SceneGraph(scene_id="x", signs=[S("s1", "W.240", shape="triangle", background="yellow")])
    a = engine.answer(tunnel, GuideClaim(about="ahead", feature="tunnel"))
    assert a.verdict is Verdict.yes and any(c.article_id == "C.40" for c in a.citations)
    plain = SceneGraph(scene_id="x", signs=[S("s1", "P.127", value=80)])
    assert engine.answer(plain, GuideClaim(about="ahead", feature="exit")).verdict is Verdict.no
    board = SceneGraph(scene_id="x", guide_boards=[GuideBoard(entries=[GuideEntry(text="LỐI RA Phú Mỹ", distance_m=500)])])
    assert engine.answer(board, GuideClaim(about="ahead", feature="exit")).verdict is Verdict.yes
    # whole words: "Phạm" is not "hầm"
    pham = SceneGraph(scene_id="x", guide_boards=[GuideBoard(entries=[GuideEntry(text="Phạm Văn Đồng")])])
    assert engine.answer(pham, GuideClaim(about="ahead", feature="tunnel")).verdict is Verdict.no
    unread = SceneGraph(scene_id="x", signs=[S("s1", "UNKNOWN", shape="triangle", background="yellow", conf="low")])
    assert engine.answer(unread, GuideClaim(about="ahead", feature="tunnel")).verdict is Verdict.unknown


def test_destinations_by_arrow(engine):
    """Modelled on "Làn có mũi tên xiên dẫn về đâu?"."""
    sc = _board_scene()
    a = engine.answer(sc, Guide(ask="destinations", direction="left"))
    assert [d["text"] for d in a.value["destinations"]] == ["Đường Tránh"]


def test_guide_claim_needs_its_slots():
    with pytest.raises(ValueError):
        GuideClaim(about="distance", destination="Phủ Lý")


# ---------------------------------------------------------------- I3: explain

def test_explain_names_the_rule_that_decides(engine):
    """Modelled on "... ô tô con chạy 95 km/h và xe tải chạy 85 km/h thì xe nào bị phạt? Vì sao?"."""
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.127", value=80)])
    p = Explain(program=Choose(options=[
        ChoiceOption(label="ô tô con", claim=SpeedOk(vehicle=V("passenger_car"), speed_kmh=95), expect=False),
        ChoiceOption(label="xe tải", claim=SpeedOk(vehicle=V("truck"), speed_kmh=85), expect=False)]))
    a, t = text(engine, sc, p)
    assert a.verdict is Verdict.value and a.value["inner"]["holding"] == ["ô tô con", "xe tải"]
    assert "ô tô con" in t.lower() and a.citations


def test_explain_passes_an_undecided_answer_through(engine):
    sc = SceneGraph(scene_id="x", signs=[S("s1", "UNKNOWN", conf="low")])      # could be a speed disc
    p = Explain(program=SpeedOk(vehicle=V("truck"), speed_kmh=85))
    assert engine.answer(sc, p).verdict is Verdict.unknown
    a = engine.answer(SceneGraph(scene_id="x"), p)                              # no sign: yes, explained
    assert a.verdict is Verdict.value and a.value["answer"] == "yes"


# ---------------------------------------------------------------- I4: speed range and stated limits

def test_speed_range_from_max_and_min_signs(engine):
    """Modelled on "Đoạn đường này cho phép chạy trong khoảng tốc độ nào?"."""
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.127", value=90), S("s2", "R.306", 2, value=60, background="blue",
                                                                       border="none")])
    a, t = text(engine, sc, SpeedLimit(kind="range"))
    assert a.verdict is Verdict.value and (a.value["max"], a.value["min"]) == (90, 60)
    assert "90 km/h" in t and "60 km/h" in t


def test_speed_range_without_a_minimum(engine):
    sc = SceneGraph(scene_id="x", road=Road(type="urban"), signs=[S("s1", "P.127", value=50)])
    a = engine.answer(sc, SpeedLimit(kind="range"))
    assert a.verdict is Verdict.value and a.value["min"] is None


def test_stated_speed_limits(engine):
    """Modelled on "Có phải tốc độ tối đa ... là X km/h và tối thiểu là Y km/h không?"."""
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.127", value=100), S("s2", "R.306", 2, value=60, background="blue",
                                                                        border="none")])
    claim = AllOf(claims=[SpeedLimitIs(kind="max", value_kmh=120), SpeedLimitIs(kind="min", value_kmh=60)])
    assert engine.answer(sc, claim).verdict is Verdict.no
    assert engine.answer(sc, SpeedLimitIs(kind="max", value_kmh=100)).verdict is Verdict.yes
    assert engine.answer(SceneGraph(scene_id="x"), SpeedLimitIs(kind="max", value_kmh=100)).verdict is Verdict.unknown


def test_range_with_a_vehicle_list_is_rejected(engine):
    q = QueryProgram(program=SpeedLimit(kind="range", vehicles=[V("car"), V("truck")]))
    assert validator.check(q, engine)
