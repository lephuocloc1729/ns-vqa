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


# ---------------------------------------------------------------- 6. guide content (B6, schema 1.3)

import io  # noqa: E402
import json  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from vqa.llm.client import LLMBadJSON  # noqa: E402
from vqa.perception import guide as gd  # noqa: E402
from vqa.perception.cache import SceneCache  # noqa: E402
from vqa.perception.image import prepare  # noqa: E402
from vqa.schemas import Guide, GuideBoard, GuideEntry, SpeedOk as _SpeedOk  # noqa: E402

REPLY = {"boards": [
    {"entries": [{"text": "QUỐC LỘ 1A", "distance": "5 KM", "direction": "left"},
                 {"text": "ĐÔNG HÀ", "distance": "61 KM", "direction": "straight"},
                 {"text": "CẦU BIÊU", "direction": "sideways"}]},
    {"route": "CT.01", "entries": [{"text": "PHAN THIẾT", "distance": "204 km", "direction": "none"}],
     "speeds": [{"kind": "max", "value": 80}, {"kind": "min", "value": 60}, {"kind": "max", "value": 999}],
     "other": ["EXPRESSWAY"]}]}


def _jpeg(w=320, h=200) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (40, 90, 160)).save(buf, format="JPEG")
    return buf.getvalue()


class GuideClient:
    model = "claude-haiku-5-5"

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def json_reply(self, **kw):
        self.calls.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(data=r, raw_text=json.dumps(r, ensure_ascii=False), cost_usd=0.002,
                               usage={"output_tokens": 50}, request_id="r")


def test_the_guide_prompt_is_the_tested_one():
    """Variant A as tested: the trial's spec and examples byte for byte; only the config's
    comments differ, and its settings are the trial's minus the crop block."""
    import yaml
    trial = gd.PROMPT_DIR.parent / "v5-guide-trial"
    for f in ("spec.md", "examples.jsonl"):
        assert (gd.PROMPT_DIR / f).read_bytes() == (trial / f).read_bytes()
    t = yaml.safe_load((trial / "config.yaml").read_text(encoding="utf-8"))
    t.pop("crop")
    assert gd.config() == t
    assert gd.prompt_id().startswith("scene/v5-guide@") and "catalog" not in gd.system_prompt().lower()


def test_reply_to_boards_converts_distances_and_drops_bad_items():
    boards, issues = gd.to_boards(REPLY)
    e = boards[0].entries
    assert [(x.text, x.distance_m, x.direction) for x in e] == [
        ("QUỐC LỘ 1A", 5000.0, "left"), ("ĐÔNG HÀ", 61000.0, "straight"), ("CẦU BIÊU", None, "none")]
    assert [(s.kind, s.value) for s in boards[1].speeds] == [("max", 80.0), ("min", 60.0)]
    assert boards[1].route == "CT.01" and boards[1].other == ["EXPRESSWAY"]
    assert any("sideways" in i for i in issues) and any("999" in i for i in issues)
    assert gd.to_boards({"nope": 1}) == ([], ["the reply has no `boards` list"])


def test_apply_adds_board_speed_discs_once_and_marks_schema_1_3():
    scene = SceneGraph(scene_id="x", signs=[S("s1", "IE.452", shape="rectangle", border="none", background="green"),
                                            S("s2", "P.127", rank=2, value=80)])
    boards, _ = gd.to_boards(REPLY)
    out = gd.apply(scene, boards)
    assert out.schema_version == "1.3" and len(out.guide_boards) == 2
    added = [s for s in out.signs if s.id.startswith("g")]
    assert [(s.code, s.value) for s in added] == [("R.306", 60.0)]       # the 80 was already posted
    assert gd.apply(scene, []) is scene


def test_schema_1_2_scenes_dump_without_boards():
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.127", value=50)])
    d = scene.model_dump(mode="json")
    assert "guide_boards" not in d and d["schema_version"] == "1.2"
    out = gd.apply(scene, [GuideBoard(entries=[GuideEntry(text="A")])])
    d2 = out.model_dump(mode="json")
    assert d2["guide_boards"][0]["entries"][0]["text"] == "A"
    assert SceneGraph.model_validate(d2) == out


def test_the_guide_call_is_cached_as_a_region_record(tmp_path):
    img, cache = prepare(_jpeg()), SceneCache(tmp_path)
    client = GuideClient([REPLY])
    r1 = gd.read_boards(img, model=client.model, client=client, cache=cache)
    assert r1.ok and r1.called and len(r1.boards) == 2 and len(client.calls) == 1
    assert client.calls[0]["purpose"] == "guide boards" and client.calls[0]["effort"] == "medium"
    r2 = gd.read_boards(img, model=client.model, client=None, cache=cache)
    assert r2.ok and r2.cache_hit and not r2.called and r2.boards == r1.boards
    rec = cache.get_region(img.sha256, client.model, "medium", gd.prompt_id(), (0, 0, 320, 200))
    assert rec is not None and set(rec.replies[0]) <= {"pass", "raw_text", "stop_reason", "usage", "cost_usd", "request_id"}


def test_the_guide_call_retries_once_then_gives_up(tmp_path):
    img = prepare(_jpeg())
    bad = LLMBadJSON("not json")
    ok = gd.read_boards(img, model="claude-haiku-5-5", client=GuideClient([bad, REPLY]), cache=SceneCache(tmp_path))
    assert ok.ok and len(ok.boards) == 2
    c = GuideClient([{"x": 1}, {"y": 2}])
    r = gd.read_boards(img, model="claude-haiku-5-5", client=c, cache=SceneCache(tmp_path / "b"))
    assert not r.ok and r.boards == [] and len(c.calls) == 2
    assert c.calls[1]["extra_messages"][1]["content"].startswith("That reply was not valid")
    assert gd.read_boards(img, model="claude-haiku-5-5", client=None, cache=SceneCache(tmp_path / "c")).ok is False


def test_the_call_is_made_only_when_the_scene_lists_a_guide_board(engine):
    cat = engine.catalog
    board = S("s1", "I.414(a,b,c,d)", shape="rectangle", border="none", background="blue")
    unread_blue = S("s2", "UNKNOWN", shape="rectangle", border="none", background="blue")
    unread_red = S("s3", "UNKNOWN", shape="rectangle", border="none", background="red")
    assert gd.needs_boards(SceneGraph(scene_id="x", signs=[board]), cat)
    assert gd.needs_boards(SceneGraph(scene_id="x", signs=[unread_blue]), cat)
    assert not gd.needs_boards(SceneGraph(scene_id="x", signs=[unread_red, S("s4", "P.127", value=50)]), cat)


def _board_scene():
    scene = SceneGraph(scene_id="x", signs=[S("s1", "I.414(a,b,c,d)", shape="rectangle", border="none", background="blue")])
    return gd.apply(scene, gd.to_boards(REPLY)[0])


def test_guide_direction_and_distance_come_from_the_board(engine):
    """Modelled on "Theo biển chỉ dẫn, đi hướng nào để đến Quốc lộ 1A và còn bao xa?"."""
    scene = _board_scene()
    a = engine.answer(scene, Guide(ask="direction", destination="Quốc lộ 1A"))
    assert a.verdict is Verdict.value and a.value["direction"] == "left" and a.value["distance_m"] == 5000
    assert a.citations
    d = engine.answer(scene, Guide(ask="distance", destination="Phan Thiết"))
    assert d.value["distance_m"] == 204000


def test_guide_unknowns(engine):
    scene = _board_scene()
    assert engine.answer(scene, Guide(ask="distance", destination="Cầu Biêu")).verdict is Verdict.unknown
    assert engine.answer(scene, Guide(ask="direction", destination="Hà Nội")).verdict is Verdict.unknown
    bare = SceneGraph(scene_id="x", signs=[S("s1", "I.414(a,b,c,d)", shape="rectangle", border="none", background="blue")])
    assert engine.answer(bare, Guide(ask="destinations")).verdict is Verdict.unknown


def test_guide_lists_destinations_and_routes(engine):
    scene = _board_scene()
    a = engine.answer(scene, Guide(ask="destinations"))
    assert [x["text"] for x in a.value["destinations"]] == ["QUỐC LỘ 1A", "ĐÔNG HÀ", "CẦU BIÊU", "PHAN THIẾT"]
    assert engine.answer(scene, Guide(ask="route")).value == {"routes": ["CT.01"]}


def test_board_speed_discs_feed_the_speed_rules(engine):
    """An expressway board posting 80 / 60: the added P.127 and R.306 decide speed claims."""
    scene = _board_scene()
    car = Vehicle(cls=VehicleClass.car)
    assert engine.answer(scene, _SpeedOk(vehicle=car, speed_kmh=90)).verdict is Verdict.no
    assert engine.answer(scene, _SpeedOk(vehicle=car, speed_kmh=50)).verdict is Verdict.no
    assert engine.answer(scene, _SpeedOk(vehicle=car, speed_kmh=70)).verdict is Verdict.yes
    assert engine.answer(scene, SpeedLimit(vehicle=car)).value["limit"] == 80


def test_a_read_board_no_longer_counts_as_unreadable(engine):
    """Once the guide call read the photo, an unread blue board is one it transcribed; a red
    one (a local ban notice) still counts."""
    blue = S("s2", "UNKNOWN", rank=2, shape="rectangle", border="none", background="blue")
    red = S("s3", "UNKNOWN", rank=3, shape="rectangle", border="none", background="red")
    scene = SceneGraph(scene_id="x", signs=[blue, red])
    assert engine.unreadable_signs(scene) == ["s2", "s3"]
    read = gd.apply(scene, gd.to_boards(REPLY)[0])
    assert engine.unreadable_signs(read) == ["s3"]


# ---------------------------------------------------------------- template answers for the new values

from vqa.answer.digest import build as build_digest  # noqa: E402
from vqa.answer.faithfulness import check as guard  # noqa: E402
from vqa.answer.template import template_answer, template_reply  # noqa: E402

_P131 = SceneGraph(scene_id="x", signs=[S("s1", "P.131a", background="blue"),
                                        S("s2", "W.224", rank=2, shape="triangle", background="yellow")])


def _cases():
    car, truck = Vehicle(cls=VehicleClass.passenger_car), Vehicle(cls=VehicleClass.truck)
    from vqa.schemas import VehicleSpec
    tp = Plate(kind="vehicle", vehicles=[VehicleSpec(cls=VehicleClass.truck)])
    speeds = SceneGraph(scene_id="x", signs=[S("s1", "P.127", value=90), S("s2", "P.127", rank=2, value=70, plates=[tp])])
    return [
        (SceneGraph(scene_id="x", signs=[S("s1", "P.131a", background="blue")]), ONLY("group"), "Câu hỏi?",
         "Thuộc nhóm biển báo cấm."),
        (_P131, ONLY("conduct"), "Người lái xe cần làm gì?", "Cấm đỗ xe (P.131a): xe cơ giới không được đỗ xe"),
        (SceneGraph(scene_id="x", signs=[S("s1", "P.104")]), ONLY("scope"), "?", "Cấm xe máy (P.104): từ vị trí"),
        (SceneGraph(scene_id="x", signs=R420), ONLY("placement"), "?", "Bắt đầu khu đông dân cư (R.420): ở nơi"),
        (_board_scene(), Guide(ask="direction", destination="Quốc lộ 1A"), "Đi hướng nào?", "Rẽ trái để đến QUỐC LỘ 1A, còn 5 km."),
        (_board_scene(), Guide(ask="distance", destination="Phan Thiết"), "Còn bao xa?", "Đến PHAN THIẾT, còn 204 km."),
        (_board_scene(), Guide(ask="destinations"), "?", "Biển chỉ dẫn ghi: QUỐC LỘ 1A 5 km (rẽ trái); ĐÔNG HÀ 61 km"),
        (_board_scene(), Guide(ask="route"), "?", "Tuyến CT.01."),
        (speeds, SpeedLimit(vehicles=[car, truck]), "?", "Tốc độ tối đa: xe ô tô con 90 km/h; xe ô tô tải 70 km/h."),
        (SceneGraph(scene_id="x", signs=R420), SpeedLimit(vehicle=Vehicle(cls=VehicleClass.motorbike), road_divided=True),
         "?", "Tốc độ tối đa 60 km/h, còn tùy điều kiện."),
    ]


@pytest.mark.parametrize("i", range(10))
def test_new_value_templates_pass_the_guard(engine, i):
    scene, prog, q, start = _cases()[i]
    a = engine.answer(scene, prog)
    assert a.verdict is Verdict.value, a
    d = build_digest(a, scene, engine.catalog)
    assert guard(template_reply(d, q), d, q) == []
    if start:
        assert template_answer(d, q).startswith(start), template_answer(d, q)


# ---------------------------------------------------------------- validator dry runs for the new intents

from vqa.parsing.validator import check as validate  # noqa: E402
from vqa.schemas import QueryProgram  # noqa: E402


def _q(program):
    return QueryProgram.model_validate({"program": program})


@pytest.mark.parametrize("program", [
    {"intent": "meaning", "sign": {"only": True}, "aspect": "group"},
    {"intent": "meaning", "sign": {"category": "prohibitory"}, "aspect": "conduct"},
    {"intent": "meaning", "sign": {"code": "P.104"}, "aspect": "scope"},
    {"intent": "meaning", "sign": {"only": True}, "aspect": "placement"},
    {"intent": "choose", "options": [{"label": "a", "claim": {"intent": "present", "code": "P.124b"}, "expect": False}]},
    {"intent": "present", "category": "warning"},
    {"intent": "speed_limit", "vehicle": {"class": "car"}, "road_divided": True},
    {"intent": "speed_limit", "vehicles": [{"class": "passenger_car"}, {"class": "truck"}]},
    {"intent": "speed_ok", "vehicle": {"class": "car"}, "speed_kmh": 55, "road_divided": False},
    {"intent": "guide", "ask": "direction", "destination": "Pháp Vân"},
    {"intent": "guide", "ask": "destinations"},
])
def test_new_programs_pass_the_validator(engine, program):
    assert validate(_q(program), engine) == []


@pytest.mark.parametrize("program, err", [
    ({"intent": "present", "code": "P.999"}, "present"),
    ({"intent": "speed_limit", "vehicles": [{"class": "every_vehicle"}]}, "every_vehicle"),
    ({"intent": "guide", "ask": "distance"}, "destination"),
])
def test_bad_new_programs_are_rejected(engine, program, err):
    errs = validate(_q(program), engine)
    assert errs and err in " ".join(errs)


# ---------------------------------------------------------------- lanes counted from the right (B2 lane fix)

from vqa.reasoning.engine import resolve_lanes  # noqa: E402
from vqa.schemas import LaneSpec, LaneVehicles, Permitted, VehicleSpec  # noqa: E402

CAR = Vehicle(cls=VehicleClass.car)


def test_negative_lanes_count_from_the_right():
    p = Choose(options=[ChoiceOption(label="làn phải", claim=Permitted(action="turn_right", vehicle=CAR, lane=-1), expect=True),
                        ChoiceOption(label="làn trái", claim=Permitted(action="turn_left", vehicle=CAR, lane=1), expect=True)])
    out, seen = resolve_lanes(p, 3)
    assert [o.claim.lane for o in out.options] == [3, 1] and seen == [-1]
    assert resolve_lanes(p, None) == (None, [-1])
    assert resolve_lanes(Permitted(action="park", vehicle=CAR, lane=-4), 3)[0] is None
    q = Permitted(action="park", vehicle=CAR, lane=2)
    assert resolve_lanes(q, None) == (q, [])


def test_lane_zero_is_rejected():
    with pytest.raises(ValueError):
        Permitted(action="park", vehicle=CAR, lane=0)


def test_rightmost_lane_from_a_lane_board(engine):
    """Modelled on "Xe tải được đi ở làn ngoài cùng bên phải không?" with an R.412 board whose
    rows give the lane count (3): the rightmost lane is lane 3."""
    rows = [LaneSpec(lane=1, vehicles=[VehicleSpec(cls=VehicleClass.passenger_car)]),
            LaneSpec(lane=2, vehicles=[VehicleSpec(cls=VehicleClass.car)]),
            LaneSpec(lane=3, vehicles=[VehicleSpec(cls=VehicleClass.truck)])]
    board = Sign(id="s1", code="R.415a", shape="rectangle", border="none", background="blue",
                 position=Position(rank_top_down=1), lanes=rows)
    scene = SceneGraph(scene_id="x", signs=[board])
    a = engine.answer(scene, LaneVehicles(lane=-1))
    b = engine.answer(scene, LaneVehicles(lane=3))
    assert a.verdict == b.verdict and a.value == b.value
    none = engine.answer(SceneGraph(scene_id="x", signs=[S("s1", "P.130")]), Permitted(action="park", vehicle=CAR, lane=-1))
    assert none.verdict is Verdict.unknown and "lanes from the right" in none.note
