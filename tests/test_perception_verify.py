"""vqa/perception/verify.py and vqa/perception/matching.py: one test per rule.
Scenes are hand-written, modelled on train scenes."""

import pytest

from vqa.kb import load_catalog
from vqa.perception.matching import match, visual_category
from vqa.perception.verify import merge_rerun, needs_rerun, verify
from vqa.schemas import Confidence, SceneGraph, Sign


def scene(*signs, lanes=None):
    return SceneGraph(scene_id="t", signs=list(signs), road={"lanes": lanes})


def sign(sid, code, rank, **kw):
    kw.setdefault("shape", "circle"); kw.setdefault("border", "red"); kw.setdefault("background", "white")
    return Sign(id=sid, code=code, position={"rank_top_down": rank, "side": kw.pop("side", "right")}, **kw)


# ---------------------------------------------------------------- values

@pytest.mark.parametrize("v, ok", [(50, True), (5, True), (120, True), (55, True),
                                   (52, False), (0, False), (130, False)])
def test_speed_values(v, ok):
    sc, issues = verify(scene(sign("s1", "P.127", 1, value=v, unit="km/h")))
    s = sc.signs[0]
    assert (s.value == v and s.confidence == Confidence.high) if ok else \
        (s.value is None and s.confidence == Confidence.low and "out of range" in issues[0])


@pytest.mark.parametrize("code, v, ok", [("P.115", 30, True), ("P.115", 75, False), ("P.117", 4.2, True),
                                         ("P.117", 12, False), ("P.119", 25, True), ("P.119", 35, False),
                                         ("P.107a", 29, True), ("P.115", 0, False)])
def test_weight_height_length_seat_values(code, v, ok):
    sc, issues = verify(scene(sign("s1", code, 1, value=v)))
    assert (sc.signs[0].value == v) is ok


def test_value_bearing_row_without_value_is_lowered():
    sc, issues = verify(scene(sign("s1", "P.127", 1)))
    assert sc.signs[0].confidence == Confidence.low and "no speed value" in issues[0]


def test_value_on_a_rule_row_that_takes_none_is_dropped():
    sc, issues = verify(scene(sign("s1", "P.123a", 1, value=40)))
    assert sc.signs[0].value is None and "takes no value" in issues[0]


def test_lane_row_speeds_are_checked():
    s = sign("s1", "P.127b", 1, shape="rectangle", border="none", background="blue",
             lanes=[{"lane": 1, "max_speed": 80}, {"lane": 2, "max_speed": 83}])
    sc, issues = verify(scene(s))
    assert [ln.max_speed for ln in sc.signs[0].lanes] == [80, None] and "lane 2" in issues[0]


# ---------------------------------------------------------------- look vs catalog (D10)

def test_look_mismatch_lowers_only_on_human_reviewed_rows():
    cat = load_catalog()
    assert cat.get("P.123b").visual_reviewed_by == "human"
    sc, issues = verify(scene(sign("s1", "P.123b", 1, background="blue")))
    assert sc.signs[0].confidence == Confidence.low and "lowered to low" in issues[0]
    assert sc.signs[0].background.value == "blue"                  # the reported look is kept
    unreviewed = next(s for s in cat.signs if s.visual_reviewed_by != "human" and s.code.startswith("P."))
    sc, issues = verify(scene(sign("s1", unreviewed.code, 1, shape="triangle")))
    assert sc.signs[0].confidence == Confidence.high and "recorded only" in issues[0]


# ---------------------------------------------------------------- plates, lanes, ids

def test_a_plate_listed_as_a_sign_goes_under_the_sign_above_it_on_the_same_side():
    sc, issues = verify(scene(sign("s1", "P.123a", 1, side="left"), sign("s2", "P.104", 2, side="right"),
                              sign("s3", "S.508a", 3, side="right", shape="rectangle")))
    assert [s.code for s in sc.signs] == ["P.123a", "P.104"]
    assert sc.signs[1].plates[0].code == "S.508a" and sc.signs[1].plates[0].kind.value == "time"
    assert "attached to s2 P.104" in issues[0]


def test_lane_rows_are_sorted_and_renumbered():
    s = sign("s1", "R.415a", 1, shape="rectangle", border="white", background="blue",
             lanes=[{"lane": 3, "vehicles": [{"class": "car"}]}, {"lane": 2, "vehicles": [{"class": "motorbike"}]}])
    sc, issues = verify(scene(s, lanes=1))
    assert [ln.lane for ln in sc.signs[0].lanes] == [1, 2]
    assert any("renumbered 1..2" in i for i in issues) and any("road has 1 lanes" in i for i in issues)


def test_ids_are_renumbered_top_down():
    sc, issues = verify(scene(sign("s1", "P.104", 2), sign("s2", "P.123a", 1), sign("s3", "P.112", None)))
    assert [(s.id, s.code) for s in sc.signs] == [("s1", "P.123a"), ("s2", "P.104"), ("s3", "P.112")]
    assert "s2->s1" in issues[-1]


# ---------------------------------------------------------------- re-run pairing

def test_needs_rerun():
    assert needs_rerun(scene(sign("s1", "UNKNOWN", 1)))
    assert needs_rerun(scene(sign("s1", "P.104", 1, confidence="low")))
    assert not needs_rerun(scene(sign("s1", "P.104", 1)))


def test_merge_rerun_agreement_disagreement_and_singletons():
    first = scene(sign("s1", "P.104", 1, confidence="low"), sign("s2", "P.127", 2, value=50, unit="km/h"),
                  sign("s3", "P.112", 3))
    second = scene(sign("s1", "P.104", 1), sign("s2", "P.127", 2, value=60, unit="km/h"),
                   sign("s3", "W.207c", 4, shape="triangle", border="red", background="yellow"))
    merged, issues = merge_rerun(first, second)
    by = {s.code: s for s in merged.signs}
    assert by["P.104"].confidence == Confidence.high and by["P.104"].alternatives == []
    assert [(a.code, a.value) for a in by["P.127"].alternatives] == [("P.127", 60)]
    assert by["P.112"].confidence == Confidence.low                  # first reading only
    assert by["W.207c"].confidence == Confidence.low                 # re-run only
    assert [s.id for s in merged.signs] == ["s1", "s2", "s3", "s4"]


# ---------------------------------------------------------------- matching

def test_visual_category_agrees_with_the_engine():
    from types import SimpleNamespace as N
    from vqa.reasoning.engine import Engine
    for shape, border, bg in [("circle", "red", "white"), ("circle", "none", "blue"), ("rectangle", "white", "blue"),
                              ("triangle", "red", "yellow"), ("octagon", "white", "red"),
                              ("circle", "black", "white"), (None, None, None), ("circle", "none", "red")]:
        e = N(shape=N(value=shape) if shape else None, border=N(value=border) if border else None,
              background=N(value=bg) if bg else None)
        assert visual_category(shape, border, bg) == Engine.visual_category(e)


def test_match_prefers_same_row_then_category_then_rank():
    g = [{"code": "P.123a", "shape": "circle", "border": "red", "background": "white", "rank": 1, "side": "left"},
         {"code": "P.123a", "shape": "circle", "border": "red", "background": "white", "rank": 2, "side": "right"}]
    p = [{"code": "P.123a", "shape": "circle", "border": "red", "background": "white", "rank": 2, "side": "right"}]
    assert match(g, p) == [(1, 0)]


def test_a_border_only_mismatch_is_recorded_not_lowered():
    """Owner's change (2026-11-15): on a human-reviewed row only a shape or background
    difference lowers; a border difference (e.g. a white rim) is recorded."""
    assert load_catalog().get("P.123b").visual_reviewed_by == "human"
    sc, issues = verify(scene(sign("s1", "P.123b", 1, border="white")))
    assert sc.signs[0].confidence == Confidence.high and "border only; recorded only" in issues[0]
    sc, issues = verify(scene(sign("s1", "P.123b", 1, shape="triangle")))
    assert sc.signs[0].confidence == Confidence.low and "lowered to low" in issues[0]
    sc, issues = verify(scene(sign("s1", "P.123b", 1, border="white", background="blue")))
    assert sc.signs[0].confidence == Confidence.low
