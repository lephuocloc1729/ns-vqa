"""Phase 4.7 step 1a (owner, 2026-11-17: additive only): scope, placement and conduct lines from
kb/sign_info_47.yaml for stage-A rows that had none. The overlay is read only when no selected
sign has a line from kb/sign_info.yaml or the catalog. Hand-made scenes; no API call."""

from __future__ import annotations

import pytest

from vqa.kb import load_catalog
from vqa.reasoning import sign_info as si
from vqa.reasoning.engine import Engine
from vqa.schemas import Meaning, Position, SceneGraph, Selector, Sign, Verdict


@pytest.fixture(scope="module")
def engine():
    return Engine()


def S(sid, code, rank=1, shape="rectangle", border="none", background="blue"):
    return Sign(id=sid, code=code, confidence="high", shape=shape, border=border, background=background,
                position=Position(rank_top_down=rank, side="right"))


def ASK(aspect, only=True):
    return Meaning(sign=Selector(only=only), aspect=aspect)


def arts(a):
    return {c.article_id for c in a.citations}


def test_u_turn_place_conduct_comes_from_e9(engine):
    """"Gặp biển I.409, người lái xe được làm gì?": E.9 a) "vị trí được phép quay đầu xe"."""
    a = engine.answer(SceneGraph(scene_id="x", signs=[S("s1", "I.409", shape="square")]), ASK("conduct"))
    assert a.verdict is Verdict.value
    assert a.value["conduct"][0]["conduct"] == ["được phép quay đầu xe tại vị trí này"]
    assert "E.9" in arts(a)


def test_lane_reservation_conduct_quotes_d14(engine):
    a = engine.answer(SceneGraph(scene_id="x", signs=[S("s1", "R.412b")]), ASK("conduct"))
    assert a.verdict is Verdict.value and "D.14" in arts(a)
    assert "không được đi vào làn đường" in a.value["conduct"][0]["conduct"][0]


def test_guide_board_conduct_cites_art35(engine):
    a = engine.answer(SceneGraph(scene_id="x", signs=[S("s1", "I.414a", background="blue")]), ASK("conduct"))
    assert a.verdict is Verdict.value and "35" in arts(a)


def test_overlay_is_not_added_beside_a_sign_that_already_has_conduct(engine):
    """Additive rule: a two-sign answer decided before phase 4.7 (W.227 has catalog conduct) keeps
    exactly its old lines; the I.409 overlay line is not added."""
    scene = SceneGraph(scene_id="x", signs=[S("s1", "W.227", shape="triangle", border="red", background="yellow"),
                                            S("s2", "I.409", rank=2, shape="square")])
    a = engine.answer(scene, ASK("conduct", only=False))
    assert [o["code"] for o in a.value["conduct"]] == ["W.227"]


def test_end_of_speed_limit_scope_and_placement_cite_b34(engine):
    scene = SceneGraph(scene_id="x", signs=[S("s1", "DP.134", shape="circle", border="black", background="white")])
    sc = engine.answer(scene, ASK("scope"))
    pl = engine.answer(scene, ASK("placement"))
    assert sc.verdict is Verdict.value and "P.127" in sc.value["scope"][0]["scope"] and "B.34" in arts(sc)
    assert pl.verdict is Verdict.value and "B.34" in arts(pl)


def test_information_scope_falls_back_to_art15(engine):
    a = engine.answer(SceneGraph(scene_id="x", signs=[S("s1", "IE.454", background="green")]), ASK("scope"))
    assert a.verdict is Verdict.value and "15" in arts(a)


def test_lookup_without_extended_is_unchanged():
    assert si.lookup("scope", "DP.134", "end_of_restriction") is None
    assert si.lookup("scope", "DP.134", "end_of_restriction", extended=True) is not None
    cat = load_catalog()
    assert si.conduct_items(cat.get("I.409"), cat)[0] == []


def test_rows_without_a_conduct_line_are_named():
    assert si.conduct_out("R.404a") and si.conduct_out("IE.453b") and si.conduct_out("P.127") is None


def test_every_overlay_source_is_a_law_db_article():
    """Each line cites an article the dataset's law_db has (read by the tests only)."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "VLSP2025-MLQA-Natural/dataset/law_db/vlsp2025_law.json"
    if not p.exists():
        pytest.skip("law_db not available")
    db = {law["id"]: {a["id"] for a in law["articles"]} for law in json.loads(p.read_text(encoding="utf-8"))}
    for kind in ("scope", "placement", "conduct"):
        for row in si.info47()[kind]:
            src = row["source"]
            assert src["article_id"] in db[src["law_id"]], (kind, row)
