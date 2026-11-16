"""Plan item 1b.1 (owner, 2026-11-16): the selector for single-sign questions
("Đây là biển gì?"). Unreadable candidates are dropped; readable candidates with one
code decide, with the unreadable ones in uncertain_signs; different readable codes
stay unknown. Scenes are hand-made, modelled on train questions."""

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


def test_meaning_with_different_readable_codes_stays_unknown(engine):
    # train_64-like: a no-left-turn and a no-U-turn sign side by side
    a = engine.answer(scene(sign("s1", "P.123a"), sign("s2", "P.124a"), unread("s3")), Meaning(sign=ONLY))
    assert a.verdict == Verdict.unknown and a.value == {"candidates": ["s1", "s2", "s3"]}
    assert a.uncertain_signs == ["s3"]


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
