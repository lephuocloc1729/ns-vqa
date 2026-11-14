"""Claim forms: sign identity (is_sign) and compound claims (all_of / any_of)."""

import datetime as dt

import pytest
from pydantic import ValidationError

from vqa.reasoning.engine import EngineError
from vqa.schemas import (
    AllOf, AnyOf, ChoiceOption, Choose, Forbidden, IsSign, Permitted, Selector, Verdict,
    Verify, When,
)

from conftest import V, articles, scene, sign, times


def is_sign(engine, sc, **kw):
    sel = kw.pop("sign", Selector(only=True))
    return engine.answer(sc, IsSign(sign=sel, **kw))


# ---------------------------------------------------------------- is_sign

def test_is_sign_needs_one_target():
    with pytest.raises(ValidationError):
        IsSign(sign=Selector(only=True))
    with pytest.raises(ValidationError):
        IsSign(sign=Selector(only=True), code="P.125", meaning="no_overtaking")


def test_identity_by_code_and_meaning(engine):
    # "Đây là biển báo cấm vượt. Đúng hay sai?" -> Đúng
    sc = scene(sign("s1", "P.125"))
    a = is_sign(engine, sc, meaning="no_overtaking")
    assert a.verdict == Verdict.yes and "B.25" in articles(a)
    assert is_sign(engine, sc, code="P.125").verdict == Verdict.yes
    assert is_sign(engine, sc, code="P.126").verdict == Verdict.no


def test_wrong_identity_cites_the_actual_sign(engine):
    # "Biển này là biển cấm chạy ngược chiều" for a no-overtaking sign -> Sai
    a = is_sign(engine, scene(sign("s1", "P.125")), meaning="no_entry_one_way")
    assert a.verdict == Verdict.no
    assert a.value["signs"][0]["code"] == "P.125" and "B.25" in articles(a)


def test_family_code_matches_variants(engine):
    sc = scene(sign("s1", "P.124c"))
    assert is_sign(engine, sc, code="P.124").verdict == Verdict.yes
    assert is_sign(engine, sc, code="P.123").verdict == Verdict.no


def test_identity_by_category_cites_art_11(engine):
    a = is_sign(engine, scene(sign("s1", "R.301b")), category="mandatory")
    assert a.verdict == Verdict.yes and {"11", "D.1a"} <= articles(a)
    assert is_sign(engine, scene(sign("s1", "R.301b")), category="prohibitory").verdict == Verdict.no


def test_tag_as_meaning(engine):
    assert is_sign(engine, scene(sign("s1", "P.127", value=50)),
                   meaning="speed_limit").verdict == Verdict.yes


def test_unreadable_sign_is_unknown(engine):
    a = is_sign(engine, scene(sign("s1", "UNKNOWN")), meaning="no_overtaking")
    assert a.verdict == Verdict.unknown and a.uncertain_signs == ["s1"]


def test_unknown_meaning_or_code_rejected(engine):
    with pytest.raises(EngineError):
        is_sign(engine, scene(sign("s1", "P.125")), meaning="no_dragons")
    with pytest.raises(EngineError):
        is_sign(engine, scene(sign("s1", "P.125")), code="P.999")


def test_identity_selected_by_appearance(engine):
    sc = scene(sign("s1", "P.104", border="red", position={"rank_top_down": 1}),
               sign("s2", "R.301b", background="blue", position={"rank_top_down": 2}))
    a = is_sign(engine, sc, sign=Selector(background="blue"), category="mandatory")
    assert a.verdict == Verdict.yes


def test_identity_in_verify_and_choose(engine):
    sc = scene(sign("s1", "P.125"))
    claim = IsSign(sign=Selector(only=True), meaning="no_overtaking")
    assert engine.answer(sc, Verify(claim=claim, expect=False)).verdict == Verdict.no
    a = engine.answer(sc, Choose(options=[
        ChoiceOption(label="cấm vượt", claim=claim),
        ChoiceOption(label="cấm xe tải vượt",
                     claim=IsSign(sign=Selector(only=True), code="P.126"))]))
    assert a.value["holding"] == ["cấm vượt"]


# ---------------------------------------------------------------- compound claims

def stop_and_park(at_hour, cls="motor_vehicle"):
    # "vehicle" means a vehicle of unknown kind (not "every vehicle"): against a
    # motor-vehicle ban it gives unknown, so the "no" cases use motor_vehicle.
    when = When(time=dt.time(at_hour))
    return AllOf(claims=[Permitted(action="stop", vehicle=V(cls), when=when),
                         Permitted(action="park", vehicle=V(cls), when=when)])


def test_all_of(engine):
    # "Các loại xe được dừng và đỗ vào lúc 12 giờ trưa đúng hay sai?" -> Đúng
    sc = scene(sign("s1", "P.130", plates=[times(("06:00", "09:00"), ("16:00", "19:00"))]))
    a = engine.answer(sc, Verify(claim=stop_and_park(12, "vehicle")))
    assert a.verdict == Verdict.yes and {"22", "B.30", "41", "F.10"} <= articles(a)
    b = engine.answer(sc, stop_and_park(7))
    assert b.verdict == Verdict.no and b.value["parts"] == ["no", "no"]


def test_all_of_with_one_false_part_cites_only_it(engine):
    sc = scene(sign("s1", "P.131a"))  # parking banned, stopping allowed
    a = engine.answer(sc, stop_and_park(12))
    assert a.verdict == Verdict.no and a.value["parts"] == ["yes", "no"]
    assert "B.31" in articles(a)


def test_any_of_and_unknown(engine):
    sc = scene(sign("s1", "P.104", plates=[times(("06:00", "09:00"))]))
    mb = V("motorbike")
    c = AnyOf(claims=[Permitted(action="enter", vehicle=mb),            # time unknown
                      Permitted(action="enter", vehicle=mb, when=When(time=dt.time(12)))])
    assert engine.answer(sc, c).verdict == Verdict.yes
    d = AllOf(claims=[Permitted(action="enter", vehicle=mb),
                      Permitted(action="enter", vehicle=mb, when=When(time=dt.time(12)))])
    assert engine.answer(sc, d).verdict == Verdict.unknown


def test_compound_with_forbidden_and_identity(engine):
    sc = scene(sign("s1", "P.104", plates=[times(("06:00", "09:00"))]))
    c = AllOf(claims=[IsSign(sign=Selector(only=True), meaning="no_motorbikes"),
                      Forbidden(action="enter", vehicle=V("motorbike"),
                                when=When(start=dt.time(6), end=dt.time(9), quantifier="all"))])
    assert engine.answer(sc, c).verdict == Verdict.yes
