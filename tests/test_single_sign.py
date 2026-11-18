"""Plan item 1b.1 (owner, 2026-11-16): the selector for single-sign questions
("Đây là biển gì?"). Unreadable candidates are dropped; readable candidates with one
code decide, with the unreadable ones in uncertain_signs; different readable codes
stay unknown. Scenes are hand-made, modelled on train questions."""

import pytest

from vqa.schemas import IsSign, Meaning, Selector, Verdict

from conftest import articles, scene, sign

ONLY = Selector(only=True)


def unread(sid, **kw):
    return sign(sid, "UNKNOWN", shape=kw.pop("shape", "rectangle"), border="none", background="blue", **kw)


def test_meaning_with_one_readable_sign_and_unreadable_ones(engine):
    # train_89 "Biển trong ảnh có ý nghĩa gì?" -> "Cấm dừng và đỗ xe." (P.130), with a
    # far board nobody can read
    a = engine.answer(scene(sign("s1", "P.130"), unread("s2")), Meaning(sign=ONLY))
    assert a.verdict == Verdict.value
    assert [x["code"] for x in a.value] == ["P.130"] and a.uncertain_signs == ["s2"]
    assert "B.30" in articles(a)


def test_meaning_with_identical_readable_signs(engine):
    # train_122 "Hai biển trong ảnh cùng có ý nghĩa gì?" -> "Cấm vượt." (two P.125)
    a = engine.answer(scene(sign("s1", "P.125"), sign("s2", "P.125"), unread("s3")), Meaning(sign=ONLY))
    assert a.verdict == Verdict.value and len(a.value) == 1 and a.value[0]["code"] == "P.125"
    assert a.uncertain_signs == ["s3"]


@pytest.fixture(scope="module")
def engine_g1_off():
    """Phase 4.8 (owner, 2026-11-18): the G1 switch (kb/switches_48.yaml) off: the plan-item-1b rule."""
    from vqa.reasoning.engine import Engine
    return Engine(several_signs=False)


def test_meaning_with_different_readable_codes_stays_unknown(engine_g1_off):
    engine = engine_g1_off
    # train_64-like: a no-left-turn and a no-U-turn sign side by side
    a = engine.answer(scene(sign("s1", "P.123a"), sign("s2", "P.124a"), unread("s3")), Meaning(sign=ONLY))
    assert a.verdict == Verdict.unknown and a.value == {"candidates": ["s1", "s2", "s3"]}
    assert a.uncertain_signs == ["s3"]


def test_meaning_with_different_readable_codes_lists_each_with_g1_on():
    """Phase 4.8 G1 switch on: one meaning per readable code, the unreadable sign uncertain."""
    from vqa.reasoning.engine import Engine
    a = Engine(several_signs=True).answer(scene(sign("s1", "P.123a"), sign("s2", "P.124a"), unread("s3")),
                                          Meaning(sign=ONLY))
    assert a.verdict == Verdict.value and [x["code"] for x in a.value] == ["P.123a", "P.124a"]
    assert a.uncertain_signs == ["s3"] and a.note == "several signs in the scene: the meaning of each is given"


def test_only_unreadable_candidates_stay_unknown(engine):
    a = engine.answer(scene(unread("s1"), unread("s2")), Meaning(sign=ONLY))
    assert a.verdict == Verdict.unknown


def test_is_sign_decides_with_the_readable_sign(engine):
    # train_200 "Đây có phải là biển cấm đỗ xe không?" -> Sai, for a P.130 sign
    sc = scene(sign("s1", "P.130"), unread("s2"))
    a = engine.answer(sc, IsSign(sign=ONLY, code="P.131a"))
    assert a.verdict == Verdict.no and a.uncertain_signs == ["s2"]
    assert engine.answer(sc, IsSign(sign=ONLY, code="P.130")).verdict == Verdict.yes


def test_is_sign_with_different_readable_codes_stays_unknown(engine):
    a = engine.answer(scene(sign("s1", "P.123a"), sign("s2", "P.124a")), IsSign(sign=ONLY, code="P.123a"))
    assert a.verdict == Verdict.unknown and a.uncertain_signs == []


def test_a_lone_unreadable_sign_is_unchanged(engine):
    a = engine.answer(scene(unread("s1", shape="circle")), IsSign(sign=ONLY, code="P.125"))
    assert a.verdict == Verdict.unknown and a.uncertain_signs == ["s1"]


# ---------------------------------------------------------------- 1b.2: meaning over several signs

def test_meaning_over_several_signs_answers_for_the_readable_ones(engine):
    # train_410-like "Các biển trong ảnh có ý nghĩa gì?": a no-overtaking-for-trucks sign,
    # a speed limit, and one board too far to read
    sc = scene(sign("s1", "P.125"), sign("s2", "P.127", value=60, unit="km/h"), unread("s3"))
    a = engine.answer(sc, Meaning(sign=Selector()))
    assert a.verdict == Verdict.value
    assert [(x["sign_id"], x["known"]) for x in a.value] == [("s1", True), ("s2", True), ("s3", False)]
    assert a.uncertain_signs == ["s3"] and {"B.25", "B.27"} <= articles(a)


def test_meaning_over_only_unreadable_signs_stays_unknown(engine):
    a = engine.answer(scene(unread("s1"), unread("s2")), Meaning(sign=Selector()))
    assert a.verdict == Verdict.unknown and a.uncertain_signs == ["s1", "s2"]
