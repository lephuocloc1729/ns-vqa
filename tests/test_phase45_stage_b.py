"""Phase 4.5 stage B (owner, 2026-11-17): B1 types, in build order: sign group, conduct + STOP,
presence, divided road and several-vehicle speed, scope and placement, guide content. Hand-made
scenes modelled on train questions; no API call."""

from __future__ import annotations

import pytest

from vqa.reasoning.engine import Engine
from vqa.schemas import (AltReading, Choose, ChoiceOption, Meaning, Position, SceneGraph, Selector,
                         Sign, Verdict)


@pytest.fixture(scope="module")
def engine():
    return Engine()


def S(sid, code, rank=1, value=None, shape="circle", border="red", background="white", alts=(), plates=()):
    return Sign(id=sid, code=code, value=value, confidence="low" if alts else "high", shape=shape, border=border,
                background=background, position=Position(rank_top_down=rank, side="right"),
                alternatives=[AltReading(code=c) for c in alts], plates=list(plates))


def ONLY(aspect):
    return Meaning(sign=Selector(only=True), aspect=aspect)


# ---------------------------------------------------------------- 1. sign group (art. 11)

def test_group_is_decided_when_two_readings_share_a_group(engine):
    """Modelled on "Biển báo trong ảnh thuộc nhóm nào?" over two P.131 discs read as P.131c or
    P.131b: the readings differ, the group doesn't."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.131c", background="blue", alts=["P.131b"]),
                                            S("s2", "P.131c", rank=2, background="blue", alts=["P.131b"])])
    a = engine.answer(scene, ONLY("group"))
    assert a.verdict is Verdict.value and a.value == {"group": "biển báo cấm"}
    assert any(c.article_id == "11" for c in a.citations)


def test_group_over_several_guide_boards(engine):
    """Several boards, different codes, one group: "biển chỉ dẫn" (I and IE rows)."""
    scene = SceneGraph(scene_id="x", signs=[
        S("s1", "IE.471", shape="rectangle", border="black", background="yellow"),
        S("s2", "I.419a", rank=2, shape="rectangle", border="none", background="blue"),
        S("s3", "IE.454", rank=3, shape="rectangle", border="none", background="green")])
    a = engine.answer(scene, ONLY("group"))
    assert a.verdict is Verdict.value and a.value["group"] == "biển chỉ dẫn"


def test_group_drops_an_unreadable_candidate_and_lists_it(engine):
    """Single-sign convention: the unreadable board is dropped and named as uncertain."""
    scene = SceneGraph(scene_id="x", signs=[
        S("s1", "I.409", shape="square", border="none", background="blue"),
        S("s2", "UNKNOWN", rank=2, shape="square", border="none", background="blue", alts=["I.407a"])])
    a = engine.answer(scene, ONLY("group"))
    assert a.verdict is Verdict.value and a.value["group"] == "biển chỉ dẫn"
    assert "s2" in a.uncertain_signs


def test_group_is_unknown_when_groups_differ(engine):
    scene = SceneGraph(scene_id="x", signs=[
        S("s1", "I.414(a,b,c,d)", shape="rectangle", border="none", background="blue"),
        S("s2", "W.221b", rank=2, shape="triangle", border="red", background="yellow")])
    a = engine.answer(scene, ONLY("group"))
    assert a.verdict is Verdict.unknown and set(a.value["groups"]) == {"biển chỉ dẫn", "biển báo nguy hiểm và cảnh báo"}


def test_group_is_uncertain_when_a_reading_changes_the_group(engine):
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.102", alts=["R.302a"])])
    assert engine.answer(scene, ONLY("group")).verdict is Verdict.uncertain


# ---------------------------------------------------------------- 2. conduct + STOP

def _conduct(a):
    return {o["code"]: o["conduct"] for o in a.value["conduct"]}


def test_conduct_after_a_warning_sign_follows_art_27_and_the_sign(engine):
    """Modelled on "Biển trong ảnh cảnh báo gì? Người lái xe cần làm gì?" (W.203a): art. 27's
    duties plus C.3 d)'s oncoming-traffic duty."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", "W.203a", shape="triangle", background="yellow")])
    a = engine.answer(scene, ONLY("conduct"))
    assert a.verdict is Verdict.value
    items = _conduct(a)["W.203(a,b,c)"]
    assert items[0] == "giảm tốc độ đến mức cần thiết" and any("ngược chiều" in i for i in items)
    assert {c.article_id for c in a.citations} >= {"C.3", "27"}
    assert a.value["conduct"][0]["name_vi"]


def test_a_warning_row_without_items_gets_art_27(engine):
    scene = SceneGraph(scene_id="x", signs=[S("s1", "W.221b", shape="triangle", background="yellow")])
    items = _conduct(engine.answer(scene, ONLY("conduct")))["W.221b"]
    assert items == ["giảm tốc độ đến mức cần thiết", "chú ý quan sát", "chuẩn bị sẵn sàng xử lý tình huống"]


def test_conduct_over_several_signs_names_banned_vehicles(engine):
    """Modelled on "Gặp các biển trong ảnh, người lái xe cần xử lý thế nào?" (a parking ban and
    a pedestrian-crossing warning)."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.131a", background="blue"),
                                            S("s2", "W.224", rank=2, shape="triangle", background="yellow"),
                                            S("s3", "P.104", rank=3)])
    c = _conduct(engine.answer(scene, ONLY("conduct")))
    assert c["P.131a"] == ["xe cơ giới không được đỗ xe"]
    assert "nhường đường cho người đi bộ" in c["W.224"]
    assert c["P.104"] == ["xe máy không được đi vào"]


def test_conduct_of_a_prohibitory_sign_cites_art_21(engine):
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.124a")])
    a = engine.answer(scene, Meaning(sign=Selector(category="prohibitory"), aspect="conduct"))
    assert _conduct(a)["P.124a"] == ["không được quay đầu xe"]
    assert {c.article_id for c in a.citations} == {"B.24", "21"}


def test_stop_sign_binds_every_vehicle_priority_included(engine):
    """Modelled on "Gặp biển STOP trong ảnh, xe cơ giới, xe thô sơ và cả xe ưu tiên phải làm
    gì?": R.122, D.1 b)."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", "R.122", shape="octagon", border="white", background="red")])
    a = engine.answer(scene, ONLY("conduct"))
    item = _conduct(a)["R.122"][0]
    assert item.startswith("dừng lại") and "kể cả xe ưu tiên" in item
    assert {c.article_id for c in a.citations} == {"D.1", "31"}


def test_conduct_with_an_unread_sign_lists_it(engine):
    scene = SceneGraph(scene_id="x", signs=[S("s1", "W.227", shape="triangle", background="yellow"),
                                            S("s2", "UNKNOWN", rank=2)])
    a = engine.answer(scene, ONLY("conduct"))
    assert a.verdict is Verdict.value and a.uncertain_signs == ["s2"]


# ---------------------------------------------------------------- 3. presence

from vqa.reasoning.engine import EngineError  # noqa: E402
from vqa.schemas import Present  # noqa: E402


def _absent(code=None, meaning=None, category=None, label=None):
    return ChoiceOption(label=label or code or meaning or category,
                        claim=Present(code=code, meaning=meaning, category=category), expect=False)


ROUNDABOUT_SCENE = [S("s1", "P.124a"), S("s2", "R.303", rank=2, border="none", background="blue"),
                    S("s3", "W.245a", rank=3, shape="triangle", background="yellow")]


def test_which_sign_is_not_in_the_photo(engine):
    """Modelled on "Trong các biển cấm quay đầu, cấm ô tô quay đầu, đi chậm và vòng xuyến, biển
    nào không có trong ảnh?": P.124b is absent; P.124a, its neighbour row, does not stand for it."""
    scene = SceneGraph(scene_id="x", signs=ROUNDABOUT_SCENE)
    p = Choose(options=[_absent("P.124a"), _absent("P.124b"), _absent("W.245a"), _absent("R.303")])
    a = engine.answer(scene, p)
    assert a.verdict is Verdict.value and a.value["holding"] == ["P.124b"]


def test_presence_by_category_and_meaning(engine):
    scene = SceneGraph(scene_id="x", signs=ROUNDABOUT_SCENE)
    assert engine.answer(scene, Present(category="warning")).verdict is Verdict.yes
    assert engine.answer(scene, Present(category="information")).verdict is Verdict.no
    assert engine.answer(scene, Present(meaning="speed_limit")).verdict is Verdict.no


def test_an_unread_sign_of_the_same_look_makes_absence_unknown(engine):
    scene = SceneGraph(scene_id="x", signs=ROUNDABOUT_SCENE + [S("s4", "UNKNOWN", rank=4)])
    a = engine.answer(scene, Present(code="P.124b"))
    assert a.verdict is Verdict.unknown and a.uncertain_signs == ["s4"]
    # a red disc can't be the warning triangle asked about
    scene2 = SceneGraph(scene_id="x", signs=[S("s1", "P.124a"), S("s4", "UNKNOWN", rank=2)])
    assert engine.answer(scene2, Present(code="W.245a")).verdict is Verdict.no


def test_presence_rejects_an_unknown_code(engine):
    with pytest.raises(EngineError):
        engine.answer(SceneGraph(scene_id="x", signs=ROUNDABOUT_SCENE), Present(code="P.999"))


def test_present_needs_exactly_one_target():
    with pytest.raises(ValueError):
        Present(code="P.124a", category="prohibitory")


# ---------------------------------------------------------------- 4. divided road, several vehicles

from vqa.schemas import SpeedLimit, SpeedOk, Vehicle, VehicleClass  # noqa: E402

R420 = [S("s1", "R.420", shape="rectangle", border="white", background="blue")]


@pytest.mark.parametrize("divided, limit", [(True, 60), (False, 50)])
def test_residential_limit_from_the_question_divider(engine, divided, limit):
    """Modelled on "Sau biển này, ô tô được chạy tối đa bao nhiêu trên đường có (không có) dải
    phân cách?" (Circular 38 residential defaults, interpretations)."""
    scene = SceneGraph(scene_id="x", signs=R420)
    a = engine.answer(scene, SpeedLimit(vehicle=Vehicle(cls=VehicleClass.car), road_divided=divided))
    assert a.verdict is Verdict.value and a.value["limit"] == limit


def test_residential_limit_without_the_divider_is_unknown(engine):
    a = engine.answer(SceneGraph(scene_id="x", signs=R420), SpeedLimit(vehicle=Vehicle(cls=VehicleClass.car)))
    assert a.verdict is Verdict.unknown


def test_speed_ok_with_the_question_divider(engine):
    scene = SceneGraph(scene_id="x", signs=R420)
    car = Vehicle(cls=VehicleClass.car)
    assert engine.answer(scene, SpeedOk(vehicle=car, speed_kmh=55, road_divided=True)).verdict is Verdict.yes
    assert engine.answer(scene, SpeedOk(vehicle=car, speed_kmh=55, road_divided=False)).verdict is Verdict.no


def test_the_question_divider_overrides_the_scene(engine):
    scene = SceneGraph(scene_id="x", signs=R420, road={"divided": False})
    a = engine.answer(scene, SpeedLimit(vehicle=Vehicle(cls=VehicleClass.car), road_divided=True))
    assert a.value["limit"] == 60


def test_speed_limit_over_a_vehicle_list(engine):
    """Modelled on "Ô tô con và xe tải được chạy tối đa bao nhiêu theo biển trong ảnh?" with a
    P.127c-style truck limit: one value per vehicle."""
    from vqa.schemas import Plate, VehicleSpec
    truck_plate = Plate(kind="vehicle", vehicles=[VehicleSpec(cls=VehicleClass.truck)])
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.127", value=90),
                                            S("s2", "P.127", rank=2, value=70, plates=[truck_plate])])
    a = engine.answer(scene, SpeedLimit(vehicles=[Vehicle(cls=VehicleClass.passenger_car),
                                                  Vehicle(cls=VehicleClass.truck)]))
    assert a.verdict is Verdict.value
    assert [(x["vehicle"], x["limit"]) for x in a.value["per_vehicle"]] == [("passenger_car", 90), ("truck", 70)]


def test_a_vehicle_list_with_one_unknown_limit_is_unknown(engine):
    scene = SceneGraph(scene_id="x", signs=R420)
    a = engine.answer(scene, SpeedLimit(vehicles=[Vehicle(cls=VehicleClass.car), Vehicle(cls=VehicleClass.truck)]))
    assert a.verdict is Verdict.unknown


# ---------------------------------------------------------------- 5. scope and placement

from vqa.schemas import Plate  # noqa: E402


def _field(a, aspect):
    return {o["code"]: o[aspect] for o in a.value[aspect]}


def test_scope_of_a_p101_to_p120_ban_follows_art_26_3(engine):
    """Modelled on "Biển cấm mô tô có hiệu lực từ đâu đến đâu?"."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.104")])
    a = engine.answer(scene, Meaning(sign=Selector(code="P.104"), aspect="scope"))
    assert "không có biển hết cấm" in _field(a, "scope")["P.104"]
    assert {c.article_id for c in a.citations} == {"B.4", "26"}


def test_scope_with_an_s501_plate_gives_its_length(engine):
    """P.128 with an S.501 plate: art. 26.5 plus the plate's length (F.1)."""
    plate = Plate(kind="distance", code="S.501", distance_m=500)
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.128", plates=[plate])])
    a = engine.answer(scene, ONLY("scope"))
    assert _field(a, "scope")["P.128"].endswith("phạm vi 500 m")
    assert "F.1" in {c.article_id for c in a.citations}


def test_an_s502_distance_is_not_the_scope(engine):
    plate = Plate(kind="distance", code="S.502", distance_m=150)
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.128", plates=[plate])])
    assert "150" not in _field(engine.answer(scene, ONLY("scope")), "scope")["P.128"]


@pytest.mark.parametrize("code, kwargs, article, phrase", [
    ("W.239a", dict(shape="triangle", background="yellow"), "C.39", "đường dây điện"),
    ("R.420", dict(shape="rectangle", border="white", background="blue"), "D.17", "khu đông dân cư"),
    ("P.104", {}, "26", "đường giao nhau"),
    ("I.414(a,b,c,d)", dict(shape="rectangle", border="none", background="blue"), "39", "từ 20 m đến 50 m"),
])
def test_placement_lines(engine, code, kwargs, article, phrase):
    """Modelled on "Biển trong ảnh thường được đặt ở đâu?"."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", code, **kwargs)])
    a = engine.answer(scene, ONLY("placement"))
    assert phrase in next(iter(_field(a, "placement").values()))
    assert article in {c.article_id for c in a.citations}


def test_sign_info_lines_cite_articles_that_exist():
    """Every scope / placement / conduct-rule source names a QCVN 41 article id."""
    from vqa.reasoning import sign_info as si
    data = si.info()
    for kind in ("scope", "placement"):
        for row in data[kind]:
            assert row["source"]["law_id"] == "QCVN 41:2024/BGTVT" and row["source"]["article_id"]
            assert row["text"]
    assert set(data["conduct_rule"]) == {"warning", "mandatory", "prohibitory"}
