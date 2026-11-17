"""Phase 4.7 step 1b (owner, 2026-11-17: additive only): `count` / `count_is` (art. 11 groups) and
`applies_to` / `sign_applies` (kb/rules/coverage47.pl). Hand-made scenes modelled on train question
forms ("Trong ảnh có bao nhiêu biển cấm?", "Biển ... áp dụng cho những loại xe nào?"); no API call."""

from __future__ import annotations

import pytest

from vqa.parsing.wire import from_wire, to_query
from vqa.reasoning.engine import Engine
from vqa.schemas import (AppliesTo, Count, CountIs, Plate, Position, SceneGraph, Selector, Sign, SignApplies,
                         Vehicle, VehicleSpec, Verdict, Verify)


@pytest.fixture(scope="module")
def engine():
    return Engine()


def S(sid, code, rank=1, shape="circle", border="red", bg="white", plates=()):
    return Sign(id=sid, code=code, confidence="high", shape=shape, border=border, background=bg,
                position=Position(rank_top_down=rank, side="right"), plates=list(plates))


def V(c, **kw):
    return Vehicle(**{"class": c, **kw})


def arts(a):
    return {c.article_id for c in a.citations}


THREE_BANS = [S("s1", "P.104"), S("s2", "P.123a", 2), S("s3", "P.131a", 3, bg="blue"),
              S("s4", "W.227", 4, "triangle", "red", "yellow"), S("s5", "I.409", 5, "square", "none", "blue")]


# ---------------------------------------------------------------- count

def test_count_by_group_cites_art11(engine):
    a = engine.answer(SceneGraph(scene_id="x", signs=THREE_BANS), Count(sign=Selector(category="prohibitory")))
    assert a.verdict is Verdict.value and a.value["count"] == 3 and "11" in arts(a)


def test_count_by_look(engine):
    """"bao nhiêu biển cấm hình tròn, nền trắng, viền đỏ": P.131a's blue face is left out."""
    sel = Selector(category="prohibitory", shape="circle", border="red", background="white")
    a = engine.answer(SceneGraph(scene_id="x", signs=THREE_BANS), Count(sign=sel))
    assert a.value["count"] == 2


def test_an_unread_red_disc_makes_the_count_a_range(engine):
    scene = SceneGraph(scene_id="x", signs=THREE_BANS + [S("s6", "UNKNOWN", 6)])
    a = engine.answer(scene, Count(sign=Selector(category="prohibitory")))
    assert a.verdict is Verdict.unknown and a.value["at_least"] == 3 and a.value["at_most"] == 4
    assert "s6" in a.uncertain_signs


def test_an_unread_triangle_does_not_change_a_count_of_bans(engine):
    scene = SceneGraph(scene_id="x", signs=THREE_BANS + [S("s6", "UNKNOWN", 6, "triangle", "red", "yellow")])
    assert engine.answer(scene, Count(sign=Selector(category="prohibitory"))).value["count"] == 3


def test_plates_are_not_counted_as_signs(engine):
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.104", plates=[Plate(kind="distance", distance_m=300)])])
    assert engine.answer(scene, Count()).value["count"] == 1


def test_count_is_claim(engine):
    """"Tôi đếm được hai biển cấm và một biển chỉ dẫn, có đúng không?" (an all_of of two)."""
    scene = SceneGraph(scene_id="x", signs=THREE_BANS)
    assert engine.answer(scene, CountIs(sign=Selector(category="prohibitory"), n=2)).verdict is Verdict.no
    assert engine.answer(scene, CountIs(sign=Selector(category="information"), n=1)).verdict is Verdict.yes
    range_scene = SceneGraph(scene_id="x", signs=THREE_BANS + [S("s6", "UNKNOWN", 6)])
    assert engine.answer(range_scene, CountIs(sign=Selector(category="prohibitory"), n=4)).verdict is Verdict.unknown
    assert engine.answer(range_scene, CountIs(sign=Selector(category="prohibitory"), n=5)).verdict is Verdict.no


def test_count_signs_addressed_to_a_vehicle(engine):
    """"Có bao nhiêu biển áp dụng cho xe máy?": P.104, P.123a, P.131a and the W.227 warning (art. 27:
    every road user) and the I.409 guide sign (art. 35)."""
    a = engine.answer(SceneGraph(scene_id="x", signs=THREE_BANS), Count(vehicle=V("motorbike")))
    assert a.verdict is Verdict.value and a.value["count"] == 5
    a = engine.answer(SceneGraph(scene_id="x", signs=THREE_BANS), Count(vehicle=V("car")))
    assert a.value["signs"] == ["s2", "s3", "s4", "s5"]


# ---------------------------------------------------------------- applies_to

def test_who_a_motorbike_ban_is_addressed_to(engine):
    a = engine.answer(SceneGraph(scene_id="x", signs=[S("s1", "P.104")]), AppliesTo())
    assert a.verdict is Verdict.value and a.value["applies_to"] == ["motorbike"]
    assert {"B.4", "22"} <= arts(a) and a.value["priority_exempt"] is True


def test_no_entry_one_way_covers_every_vehicle(engine):
    """B.2 (P.102) bans every vehicle from entering against the flow ("Tất cả các loại xe")."""
    a = engine.answer(SceneGraph(scene_id="x", signs=[S("s1", "P.102", bg="red")]), AppliesTo())
    assert a.value["applies_to"] == ["vehicle"]


def test_a_vehicle_plate_narrows_who(engine):
    """S.505a "Loại xe" under P.130: the ban is addressed only to the plate's vehicles (F.5)."""
    plate = Plate(kind="vehicle", vehicles=[VehicleSpec(**{"class": "truck"})])
    a = engine.answer(SceneGraph(scene_id="x", signs=[S("s1", "P.130", bg="blue", plates=[plate])]), AppliesTo())
    assert a.value["applies_to"] == ["truck"]


def test_sign_applies_claim(engine):
    """"Biển ... áp dụng cho cả ô tô lẫn xe máy, đúng không?" over P.104 (motorbikes only): no."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", "P.104")])
    a = engine.answer(scene, SignApplies(vehicles=[V("car"), V("motorbike")]))
    assert a.verdict is Verdict.no and a.value["per_vehicle"] == {"car": "no", "motorbike": "yes"}
    assert engine.answer(scene, SignApplies(vehicles=[V("motorbike")])).verdict is Verdict.yes
    assert engine.answer(scene, Verify(claim=SignApplies(vehicles=[V("car")]), expect=False)).verdict is Verdict.yes


def test_a_warning_is_addressed_to_every_road_user(engine):
    scene = SceneGraph(scene_id="x", signs=[S("s1", "W.227", shape="triangle", bg="yellow")])
    a = engine.answer(scene, SignApplies(vehicles=[V("car"), V("bicycle")]))
    assert a.verdict is Verdict.yes and "27" in arts(a)


# ---------------------------------------------------------------- wire

def test_wire_forms_convert():
    q = to_query(from_wire({"program": {"intent": "count_is", "sign": {"category": "prohibitory"}, "n": 2}}), 2025)
    assert isinstance(q.program, CountIs) and q.program.n == 2
    q = to_query(from_wire({"program": {"intent": "applies_to", "sign": {"code": "P.104", "only": True}}}), 2025)
    assert isinstance(q.program, AppliesTo) and q.program.sign.only
    q = to_query(from_wire({"program": {"intent": "all_of", "claims": [
        {"intent": "count_is", "sign": {"category": "prohibitory"}, "n": 2},
        {"intent": "sign_applies", "vehicles": [{"vehicle_class": "car"}]}]}}), 2025)
    assert [c.intent for c in q.program.claims] == ["count_is", "sign_applies"]


def test_mandatory_and_guide_signs_are_addressed_to_every_road_user(engine):
    """Art. 31 ("báo cho người tham gia giao thông biết các điều bắt buộc") for R.303; art. 35 for I.409."""
    r303 = SceneGraph(scene_id="x", signs=[S("s1", "R.303", border="none", bg="blue")])
    a = engine.answer(r303, AppliesTo())
    assert "vehicle" in a.value["applies_to"] and "31" in arts(a)
    i409 = SceneGraph(scene_id="x", signs=[S("s1", "I.409", shape="square", border="none", bg="blue")])
    assert "35" in arts(engine.answer(i409, SignApplies(vehicles=[V("car")])))


def test_lane_board_rows_say_who(engine):
    """P.127c (B.27c): a row for cars at 80 and one for trucks at 60 address cars and trucks only."""
    from vqa.schemas import LaneSpec
    board = Sign(id="s1", code="P.127c", confidence="high", shape="rectangle", border="none", background="blue",
                 position=Position(rank_top_down=1, side="right"),
                 lanes=[LaneSpec(lane=1, vehicles=[VehicleSpec(**{"class": "car"})], max_speed=80),
                        LaneSpec(lane=2, vehicles=[VehicleSpec(**{"class": "truck"})], max_speed=60)])
    a = engine.answer(SceneGraph(scene_id="x", signs=[board]), SignApplies(vehicles=[V("car"), V("motorbike")]))
    assert a.value["per_vehicle"] == {"car": "yes", "motorbike": "no"} and a.verdict is Verdict.no


def test_an_unreadable_sign_gives_unknown(engine):
    """R.411, the only effect_unmodelled row, is addressed to every road user since the matrix's last
    cells (D.13; tests/test_phase47_remaining_cells.py); an unread sign still gives unknown."""
    unread = SceneGraph(scene_id="x", signs=[S("s1", "UNKNOWN")])
    assert engine.answer(unread, AppliesTo()).verdict is Verdict.unknown
