"""The readable proof view (app/api/proof_view.py): real proofs from the engine, no API calls."""

from __future__ import annotations

import re

import pytest

from app.api import proof_view as pv
from tests.conftest import scene, sign, times
from vqa.schemas import QueryProgram


def answer(engine, sc, program: dict):
    return engine.answer(sc, QueryProgram.model_validate({"program": program}))


def view(engine, sc, program: dict, signs=None):
    a = answer(engine, sc, program)
    signs = signs or [{"id": s.id, "code": s.code, "name": None} for s in sc.signs]
    return a, pv.explain(a.model_dump(mode="json"), signs)


# ---------------------------------------------------------------------- reading the Prolog
@pytest.mark.parametrize("goal", [
    "forbids(turn_left,veh(motor_vehicle,[]),ctx(unknown,unknown,unknown),s2,true)",
    "assess(s1,p106a,[spec(truck,[])],veh(truck,[a(load_t,iv(5,false,1000000000000000000,false))]),"
    "ctx(360,unknown,1),[vehicle-true,exception-false,plate-true])",
    "catalog_sign(p127,prohibitory,'QCVN 41:2024/BGTVT','B.27')",
    "\\+restricting_scene_sign(A)",
    "local_plate(s1,'CẤM XE 2 VÀ 3 BÁNH')",
    "cmp_truth(gt,90.5,80,true)",
])
def test_every_kind_of_goal_is_read(goal):
    assert pv.parse(goal) is not None


def test_terms_are_shortened():
    t = pv.parse("veh(truck,[a(load_t,iv(5,false,1000000000000000000,false))])")
    assert pv.pretty(t) == "truck(load_t > 5)"
    assert pv.veh_text(t) == "xe ô tô tải (tải > 5 t)"
    assert pv.pretty(pv.parse("ctx(unknown,unknown,unknown)")) == ""
    assert pv.pretty(pv.parse("ctx(480,unknown,2)")) == "ctx(phút=480, làn=2)"
    assert pv.code_of("p123a") == "P.123a"


# ---------------------------------------------------------------------- steps from real proofs
def test_a_ban_that_applies(engine):
    sc = scene(sign("s1", "P.123a", confidence="medium"))
    a, views = view(engine, sc, {"intent": "permitted", "action": "turn_left", "vehicle": {"class": "motor_vehicle"}})
    assert a.verdict.value == "no"
    steps = views[0]["steps"]
    texts = [s["text"] for s in steps]
    assert texts[0] == "Biển 1 trong ảnh được đọc là P.123a (Cấm rẽ trái), độ tin cậy trung bình"
    assert "P.123a cấm mọi loại xe rẽ trái" in texts[1] and steps[1]["cite"] == ["QCVN 41:2024/BGTVT B.23"]
    assert steps[2]["rule"] == "vehicle-true"
    folded = steps[3]
    assert folded["result"] == "✓ 6/6" and len(folded["detail"]) == 6       # the routine conditions, folded
    assert steps[-1]["result"] == "Cấm" and steps[-1]["rule"].startswith("⇒ forbids(")
    assert "QCVN 41:2024/BGTVT 22" in steps[-1]["cite"]
    assert not any(s.get("decisive") for s in steps)
    names = [c["name"] for c in views[0]["rules"]]
    assert names[:3] == ["forbids", "applies", "assess"]
    assert views[0]["rules"][0]["clause"].startswith("forbids(Action, Veh, Ctx, S, T) :-")


def test_a_ban_on_another_action_names_why(engine):
    sc = scene(sign("s1", "P.123a"))
    a, views = view(engine, sc, {"intent": "permitted", "action": "turn_right", "vehicle": {"class": "motor_vehicle"}})
    assert a.verdict.value == "yes"
    decisive = [s for s in views[0]["steps"] if s.get("decisive")]
    assert [s["text"] for s in decisive] == ["P.123a không có quy định cấm rẽ phải"]
    assert views[0]["steps"][-1]["text"] == "Biển không quy định việc rẽ phải ⇒ không cấm"


def test_a_vehicle_outside_the_ban(engine):
    sc = scene(sign("s1", "P.106a"))
    _, views = view(engine, sc, {"intent": "permitted", "action": "enter", "vehicle": {"class": "motorbike"}})
    decisive = [s for s in views[0]["steps"] if s.get("decisive")]
    assert decisive[0]["rule"] == "vehicle-false" and "không thuộc nhóm" in decisive[0]["text"]
    assert "loại xe được hỏi không thuộc nhóm biển cấm" in views[0]["steps"][-1]["text"]


def test_an_open_time_window_says_what_is_missing(engine):
    sc = scene(sign("s1", "P.103a", plates=[times(("06:00", "09:00"))]))
    signs = [{"id": "s1", "code": "P.103a", "name": None, "plates": ["6h-9h"]}]    # the plate as read
    a, views = view(engine, sc, {"intent": "permitted", "action": "enter", "vehicle": {"class": "car"}}, signs)
    assert a.verdict.value == "unknown"
    decisive = [s for s in views[0]["steps"] if s.get("decisive")]
    assert decisive[0]["rule"] == "time-unknown" and decisive[0]["result"] == "?"
    assert "«6h-9h»" in decisive[0]["text"] and "không nói giờ" in decisive[0]["text"]
    assert views[0]["steps"][-1]["text"].startswith("Chưa đủ dữ kiện") and views[0]["steps"][-1]["result"] == "Chưa xác định"


def test_a_speed_limit(engine):
    sc = scene(sign("s1", "P.127", value=50))
    _, views = view(engine, sc, {"intent": "speed_ok", "vehicle": {"class": "passenger_car"}, "speed_kmh": 60})
    texts = " | ".join(s["text"] for v in views for s in v["steps"])
    assert "Tốc độ được hỏi 60 km/h > giới hạn 50 km/h" in texts
    assert "P.127 là biển tốc độ tối đa" in texts


def test_no_sign_in_the_way(engine):
    sc = scene(sign("s1", "W.207a"))
    a, views = view(engine, sc, {"intent": "permitted", "action": "turn_left", "vehicle": {"class": "car"}})
    assert views, "even a default 'yes' is explained"
    assert any("không có biển nào hạn chế" in s["text"] for v in views for s in v["steps"])


def test_every_row_has_text_and_a_result(engine):
    programs = [
        {"intent": "permitted", "action": "enter", "vehicle": {"class": "truck", "load_gt": 5}},
        {"intent": "permitted", "action": "park", "vehicle": {"class": "car"}},
        {"intent": "speed_limit", "kind": "max", "vehicle": {"class": "motor_vehicle"}},
    ]
    sc = scene(sign("s1", "P.106a"), sign("s2", "P.131a"), sign("s3", "P.127", value=60))
    for p in programs:
        _, views = view(engine, sc, p)
        for v in views or []:
            for s in v["steps"]:
                assert s["text"] and s["result"] and s["rule"]


def test_a_broken_proof_never_breaks_the_answer():
    assert pv.explain({"reasons": [{"truth": "true", "proof": {"type": "rule", "goal": "weird((("}}]}, []) is not None
    assert pv.explain(None, []) is None


# ---------------------------------------------------------------------- the templates stay complete
def test_every_reason_code_and_check_of_the_rules_has_words():
    text = (pv.ROOT / "kb" / "rules" / "common.pl").read_text(encoding="utf-8")
    pairs = re.findall(r"^why_name\((\w+),\s*(\w+)\)\.", text, re.M)
    assert pairs
    for check, why in pairs:
        assert check in pv.CHECK, check
        assert why in pv.WHY, why


def test_rule_cards_find_their_clause():
    for name in ("forbids", "applies", "assess", "speed_violation", "lane_block", "unrelated_sign"):
        assert pv._kb_clauses().get(name), name


@pytest.mark.parametrize("hour, verdict, want, never", [
    ("07:00:00", "no", "nằm trong khung giờ", "không có biển phụ"),
    ("10:00:00", "yes", "nằm ngoài khung giờ", "không có biển phụ"),
])
def test_a_time_plate_is_never_called_absent(engine, hour, verdict, want, never):
    sc = scene(sign("s1", "P.103a", plates=[times(("06:00", "09:00"))]))
    when = {"start": hour, "end": hour, "quantifier": "all"}
    a, views = view(engine, sc, {"intent": "permitted", "action": "enter", "vehicle": {"class": "car"}, "when": when})
    assert a.verdict.value == verdict
    rows = [x for st in views[0]["steps"] for x in [st, *st.get("detail", [])] if x["rule"].startswith("time")]
    assert want in rows[0]["text"] and never not in rows[0]["text"].lower()


def test_no_time_plate_is_said_only_when_the_proof_shows_it(engine):
    sc = scene(sign("s1", "P.103a"))
    _, views = view(engine, sc, {"intent": "permitted", "action": "enter", "vehicle": {"class": "car"}})
    rows = [x for st in views[0]["steps"] for x in [st, *st.get("detail", [])] if x["rule"].startswith("time")]
    assert rows[0]["text"] == "Không có biển phụ giới hạn giờ ⇒ biển áp dụng cả ngày"
