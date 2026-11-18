"""Phase 4.8c (owner, 2026-11-18): parser v17's two new question types (`lanes_only`,
`violation_kind`) and the absence wording, and the free batch B behind its switches in
kb/switches_48.yaml (sign charts, one sign under G1, only what was asked, stated exceptions).
Hand-made scenes modelled on train questions; no API call."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from vqa.answer.asked import prune_unasked
from vqa.answer.digest import build
from vqa.answer.template import template_answer
from vqa.parsing.prompt import examples, system_prompt
from vqa.parsing.wire import from_wire, to_query
from vqa.reasoning.engine import Engine, stated_exceptions_from_kb, switches_from_kb
from vqa.schemas import (Answer, Choose, ChoiceOption, Count, Guide, GuideBoard, GuideEntry, LaneSpec, LanesOnly,
                         Meaning, Permitted, Position, Present, Road, SceneGraph, Selector, Sign, Vehicle,
                         VehicleClass, VehicleSpec, Verdict, Verify, ViolationKind, WhichVehicles)

ROOT = Path(__file__).resolve().parents[1]
DATASET = Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural")) / "dataset"


@pytest.fixture(scope="module")
def engine():
    return Engine(reading_policy="higher_confidence")


def S(sid, code, value=None, shape="circle", border="red", background="white", lanes=(), conf="high"):
    return Sign(id=sid, code=code, value=value, confidence=conf, shape=shape, border=border,
                background=background, position=Position(rank_top_down=1, side="right"),
                lanes=[LaneSpec(lane=n, vehicles=[VehicleSpec(cls=VehicleClass(c)) for c in cs]) for n, cs in lanes])


def V(c):
    return Vehicle(cls=VehicleClass(c))


def scene(*signs, **kw):
    return SceneGraph(scene_id="x", signs=list(signs), road=Road(), **kw)


def cites(a):
    return {(c.law_id, c.article_id) for c in a.citations}


# four lanes: cars on the two left lanes, motorbikes and three-wheelers on the two right ones (D.16)
BOARD = S("s1", "R.415a", shape="rectangle", border="none", background="blue",
          lanes=[(1, ["car"]), (2, ["car"]), (3, ["motorbike", "motor_tricycle"]), (4, ["motorbike", "motor_tricycle"])])


# ---------------------------------------------------------------- A: lanes_only

def test_lanes_only_yes_when_the_vehicle_keeps_to_the_set(engine):
    a = engine.answer(scene(BOARD), LanesOnly(vehicle=V("passenger_car"), lanes=[1, 2]))
    assert a.verdict is Verdict.yes and ("QCVN 41:2024/BGTVT", "D.16") in cites(a)
    assert engine.answer(scene(BOARD), LanesOnly(vehicle=V("motorbike"), lanes=[-2, -1])).verdict is Verdict.yes


def test_lanes_only_no_when_a_lane_outside_is_open_or_every_lane_inside_is_closed(engine):
    assert engine.answer(scene(BOARD), LanesOnly(vehicle=V("motorbike"), lanes=[4])).verdict is Verdict.no
    assert engine.answer(scene(BOARD), LanesOnly(vehicle=V("motor_tricycle"), lanes=[1, 2])).verdict is Verdict.no


def test_lanes_only_unknown_without_a_lane_count_or_with_an_unread_board(engine):
    assert engine.answer(scene(S("s1", "P.127", 60)), LanesOnly(vehicle=V("car"), lanes=[1])).verdict is Verdict.unknown
    unread = S("s2", "UNKNOWN", shape="rectangle", border="none", background="blue", conf="low")
    a = engine.answer(scene(BOARD, unread), LanesOnly(vehicle=V("passenger_car"), lanes=[1, 2]))
    assert a.verdict is Verdict.unknown and "s2" in a.uncertain_signs


def test_which_vehicle_is_in_the_wrong_lane_is_a_choose_of_lanes_only(engine):
    """train_438's form: each vehicle put in one of two lanes; the wrong one is listed."""
    opts = [ChoiceOption(label="xe lam", claim=LanesOnly(vehicle=V("motor_tricycle"), lanes=[1, 2]), expect=False),
            ChoiceOption(label="xe máy", claim=LanesOnly(vehicle=V("motorbike"), lanes=[-2, -1]), expect=False),
            ChoiceOption(label="ô tô con", claim=LanesOnly(vehicle=V("passenger_car"), lanes=[1, 2]), expect=False)]
    a = engine.answer(scene(BOARD), Choose(options=opts))
    assert a.value["holding"] == ["xe lam"]


def test_lanes_only_counts_from_the_right_with_the_lane_count(engine):
    a = engine.answer(scene(BOARD), Verify(claim=LanesOnly(vehicle=V("passenger_car"), lanes=[-2, -1]), expect=False))
    assert a.verdict is Verdict.yes


# ---------------------------------------------------------------- A: violation_kind

def test_violation_kind_names_the_banned_action_and_its_sign(engine):
    sc = scene(S("s1", "P.103a"))
    a = engine.answer(sc, ViolationKind(vehicle=V("car")))
    assert a.verdict is Verdict.value and a.value["violations"] == [{"action": "enter", "sign_ids": ["s1"]}]
    assert ("QCVN 41:2024/BGTVT", "B.3") in cites(a)
    text = template_answer(build(a, sc), "Ô tô trong ảnh vi phạm lỗi gì?")
    assert "đi vào" in text and "P.103a" in text


def test_violation_kind_is_unknown_when_no_sign_bans_the_vehicle(engine):
    a = engine.answer(scene(S("s1", "P.104")), ViolationKind(vehicle=V("car")))
    assert a.verdict is Verdict.unknown


# ---------------------------------------------------------------- A: the wire and parser v17

def test_wire_forms_and_vehicle_default():
    q = to_query(from_wire({"program": {"intent": "lanes_only", "vehicle": {"vehicle_class": "passenger_car"},
                                        "lanes": [1, 2]}}), 2026)
    assert isinstance(q.program, LanesOnly) and q.program.lanes == [1, 2]
    q = to_query(from_wire({"program": {"intent": "violation_kind"}}), 2026)
    assert isinstance(q.program, ViolationKind) and q.defaults_applied == ["vehicle"]
    q = to_query(from_wire({"program": {"intent": "any_of", "claims": [
        {"intent": "lanes_only", "vehicle": {"vehicle_class": "car"}, "lanes": [1]},
        {"intent": "lanes_only", "vehicle": {"vehicle_class": "car"}, "lanes": [2]}]}}), 2026)
    assert [c.intent for c in q.program.claims] == ["lanes_only", "lanes_only"]


def test_v17_is_v16_plus_one_section_and_one_narrowed_sentence():
    a = (ROOT / "prompts/parser/v16/spec.md").read_text(encoding="utf-8").splitlines()
    b = (ROOT / "prompts/parser/v17/spec.md").read_text(encoding="utf-8").splitlines()
    added = [l for l in b if l not in a]
    removed = [l for l in a if l not in b]
    assert len(removed) == 1 and "a set of lanes" in removed[0]
    assert removed[0].replace("; a set of lanes", "") in added
    new = [l for l in added if l != removed[0].replace("; a set of lanes", "")]
    assert new[0] == "# Parser v17 additions"
    assert sum(l.startswith("- ") for l in new) == 3
    assert any("`lanes_only`" in l for l in new) and any("`violation_kind`" in l for l in new)
    assert any("`present`" in l and "`expect: false`" in l for l in new)


def test_v17_fewshots_are_v16_plus_two_train_working_set_questions():
    old = examples("v16")
    new = examples("v17")
    assert new[:len(old)] == old
    added = new[len(old):]
    assert [x["id"] for x in added] == ["train_438", "train_468"] and all(x["split"] == "train" for x in added)
    used = {json.loads(l)["id"] for v in range(1, 17) for l in
            (ROOT / "prompts/parser" / f"v{v}" / "fewshot.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    splits = ROOT / "data" / "splits"
    held = set()
    for f in ("train_dev.json", "train_dev2.json", "train_validation.json"):
        held |= set(json.loads((splits / f).read_text(encoding="utf-8"))["questions"])
    val_images = set(json.loads((splits / "train_validation.json").read_text(encoding="utf-8"))["images"])
    for x in added:
        assert x["id"] not in used and x["id"] not in held
        assert {i["intent"] for i in [x["output"]["program"]]} <= {"choose", "violation_kind"}
    train = DATASET / "train data" / "vlsp_2025_train.json"
    if train.exists():
        rows = {t["id"]: t for t in json.loads(train.read_text(encoding="utf-8"))}
        for x in added:
            assert rows[x["id"]]["question"] == x["question"] and rows[x["id"]]["image_id"] not in val_images
    assert "lanes_only" in system_prompt("v17") and "violation_kind" in system_prompt("v17")


def _grams(t, n=4):
    w = re.findall(r"\w+", t.lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def test_v17_new_lines_copy_no_owner_dev_or_dev2_question_text():
    a = (ROOT / "prompts/parser/v16/spec.md").read_text(encoding="utf-8").splitlines()
    new = " ".join(l for l in (ROOT / "prompts/parser/v17/spec.md").read_text(encoding="utf-8").splitlines()
                   if l not in a)
    owner = [l.split("|")[-1] for l in (ROOT / "data/annotations/gold_v12_new/owner_questions.txt")
             .read_text(encoding="utf-8").splitlines() if "|" in l and not l.startswith("#")]
    assert not any(_grams(new) & _grams(q) for q in owner)
    train = DATASET / "train data" / "vlsp_2025_train.json"
    if not train.exists():
        pytest.skip("dataset not available")
    ids = set()
    for f in ("train_dev.json", "train_dev2.json"):     # ids only; validation text is never loaded
        ids |= set(json.loads((ROOT / "data/splits" / f).read_text(encoding="utf-8"))["questions"])
    qs = [t["question"] for t in json.loads(train.read_text(encoding="utf-8")) if t["id"] in ids]
    assert not any(_grams(new, 5) & _grams(q, 5) for q in qs)   # 5 words: past stock phrases ("tốc độ tối đa")


# ---------------------------------------------------------------- B1: sign charts

def _chart(n):
    return scene(*[S(f"s{i}", "P.123a") for i in range(1, n + 1)])


def test_a_claim_on_a_sign_chart_is_unknown_with_a_note(engine):
    a = engine.answer(_chart(21), Permitted(action="turn_left", vehicle=V("car")))
    assert a.verdict is Verdict.unknown and "sign chart" in a.note
    assert engine.answer(_chart(21), Present(code="P.123a")).verdict is Verdict.unknown


def test_a_road_with_twenty_signs_or_a_count_is_still_decided(engine):
    assert engine.answer(_chart(20), Permitted(action="turn_left", vehicle=V("car"))).verdict is Verdict.no
    assert engine.answer(_chart(21), Count(sign=Selector(code="P.123a"))).value["count"] == 21


def test_the_sign_chart_switch(engine):
    sw = switches_from_kb()
    assert sw["sign_charts"] is True and sw["sign_chart_signs"] == 20 and engine.sign_chart_n == 20
    off = Engine(reading_policy="higher_confidence", sign_charts=False)
    assert off.answer(_chart(21), Permitted(action="turn_left", vehicle=V("car"))).verdict is Verdict.no


# ---------------------------------------------------------------- B2: one sign under G1

THREE = scene(S("s1", "P.130", border="red", background="blue"),
              S("s2", "I.415", shape="rectangle", border="none", background="blue", conf="low"),
              S("s3", "W.207a", shape="triangle", background="yellow", conf="low"))


def test_the_sign_read_most_surely_is_the_one_named(engine):
    a = engine.answer(THREE, Meaning(sign=Selector(only=True)))
    assert [x["code"] for x in a.value] == ["P.130"]
    off = Engine(reading_policy="higher_confidence", one_sign_g1=False).answer(THREE, Meaning(sign=Selector(only=True)))
    assert len(off.value) == 3


def test_board_discs_are_part_of_the_board(engine):
    """train_315-like: IE.452 with the 90 / 60 discs the board call added (g1, g2)."""
    sc = scene(S("s1", "IE.452", shape="rectangle", border="none", background="green"),
               S("g1", "P.127", 90), S("g2", "R.306", 60, border="none", background="blue"),
               guide_boards=[GuideBoard(other=["CAO TỐC"])])
    assert [x["code"] for x in engine.answer(sc, Meaning(sign=Selector(only=True))).value] == ["IE.452"]


def test_a_tie_keeps_every_sign(engine):
    sc = scene(S("s1", "P.101", conf="low"), S("s2", "I.423a", shape="rectangle", border="none",
                                              background="blue", conf="low"))
    assert len(engine.answer(sc, Meaning(sign=Selector(only=True))).value) == 2


# ---------------------------------------------------------------- B2: only what was asked

def test_pedestrians_are_dropped_unless_asked():
    a = Answer(verdict=Verdict.value, value={"banned": ["car", "pedestrian"], "conditional": ["pedestrian"],
                                             "per_class": {"car": "no", "pedestrian": "no"}})
    p = prune_unasked(a, "Đoạn đường này cấm loại xe nào đi vào?", on=True)
    assert p.value["banned"] == ["car"] and p.value["conditional"] == [] and "pedestrian" not in p.value["per_class"]
    assert prune_unasked(a, "Người đi bộ có bị cấm không?", on=True).value == a.value
    assert prune_unasked(a, "Đoạn đường này cấm loại xe nào đi vào?", on=False) is a


def test_per_lane_rows_are_dropped_when_no_lane_was_asked():
    a = Answer(verdict=Verdict.value, value={"kind": "max", "lane": None, "limit": 60,
                                             "per_lane": [{"lane": 1, "limit": 60}], "conditional": []})
    assert "per_lane" not in prune_unasked(a, "Tốc độ tối đa ở đây là bao nhiêu?", on=True).value
    assert "per_lane" in prune_unasked(a, "Mỗi làn chạy tối đa bao nhiêu?", on=True).value
    multi = Answer(verdict=Verdict.value, value={"parts": [{"verdict": "value", "value": a.value}]})
    assert "per_lane" not in prune_unasked(multi, "Tốc độ tối đa là bao nhiêu?", on=True).value["parts"][0]["value"]


# ---------------------------------------------------------------- B3: stated exceptions and board steps

def test_stated_exception_articles_name_catalog_sources_and_quote_law_db():
    import yaml
    from vqa.kb import load_catalog
    rows = yaml.safe_load((ROOT / "kb/stated_exceptions_48.yaml").read_text(encoding="utf-8"))["articles"]
    sources = {s.source.article_id for s in load_catalog().signs}
    assert {r["article_id"] for r in rows} == stated_exceptions_from_kb() and stated_exceptions_from_kb() <= sources
    assert "B.15" not in stated_exceptions_from_kb()      # P.115: "kể cả các xe được ưu tiên"
    law = DATASET / "law_db" / "vlsp2025_law.json"
    if law.exists():
        arts = {a["id"]: a["text"] for l in json.loads(law.read_text(encoding="utf-8")) if "QCVN" in l["id"]
                for a in l["articles"]}
        for r in rows:
            assert " ".join(r["quote"].split()) in " ".join(arts[r["article_id"]].split()), r["article_id"]


@pytest.fixture(scope="module")
def stated():
    """The switch on explicitly: the KB has it off since PAID 2 (dev2 342 and 356 judged no better)."""
    assert switches_from_kb()["stated_exceptions"] is False
    return Engine(reading_policy="higher_confidence", stated_exceptions=True)


def test_a_turn_ban_answer_names_the_priority_exception(stated):
    sc = scene(S("s1", "P.123a"))
    a = stated.answer(sc, WhichVehicles(action="turn_left"))
    assert a.value["except_priority"] is True and a.value["exception_articles"] == ["B.23"]
    assert "trừ các xe được ưu tiên" in template_answer(build(a, sc), "Những xe nào không được rẽ trái ở đây?")
    off = Engine(reading_policy="higher_confidence", stated_exceptions=False).answer(sc, WhichVehicles(action="turn_left"))
    assert "except_priority" not in off.value


def test_no_exception_for_a_ban_that_covers_priority_vehicles(stated):
    a = stated.answer(scene(S("s1", "P.115", 10)), WhichVehicles(action="enter"))
    assert "except_priority" not in (a.value or {})


def test_a_guide_direction_carries_the_boards_other_steps(stated):
    """train_342-like: a route diagram with "30M" beside the arrows."""
    sc = scene(S("s1", "I.414a", shape="rectangle", border="none", background="blue"),
               guide_boards=[GuideBoard(entries=[GuideEntry(text="ĐƯỜNG MAI HOA", direction="right")], other=["30M"])])
    a = stated.answer(sc, Guide(ask="direction", destination="đường Mai Hoa"))
    assert a.value["board_notes"] == ["30M"]
    assert "30M" in template_answer(build(a, sc), "Muốn vào đường Mai Hoa thì đi thế nào?")
    off = Engine(reading_policy="higher_confidence", stated_exceptions=False)
    assert "board_notes" not in off.answer(sc, Guide(ask="direction", destination="đường Mai Hoa")).value
