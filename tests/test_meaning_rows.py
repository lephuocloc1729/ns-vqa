"""Meaning-only catalog rows (W.2xx, I.4xx, IE.4xx): naming, identity, categories."""

from vqa.kb import load_catalog
from vqa.schemas import IsSign, Meaning, Permitted, Selector, Verdict

from conftest import V, articles, scene, sign


def test_meaning_rows_loaded():
    cat = load_catalog()
    rows = [s for s in cat.signs if s.meaning_only]
    with_effects = [s for s in cat.signs if s.effect_reviewed_by == "assistant" and s.category in ("warning", "information")]
    assert len(rows) + len(with_effects) >= 140        # phase 4.5 gave 37 of them effects (kb/sign_catalog_effects.yaml)
    assert {s.category for s in rows} == {"warning", "information"}
    assert all(s.effect.prohibits == [] for s in rows)
    expressway = [s for s in rows if s.code.startswith("IE.")]
    assert expressway and all(s.source.article_id == "47" for s in expressway)


def test_variant_code_resolves_to_family_row():
    cat = load_catalog()
    assert cat.get("W.207c").code == "W.207(a,b,c,d,e,f,g,h,i,k,l)"
    assert cat.get("W.201a").name_vi == "Chỗ ngoặt nguy hiểm vòng bên trái"
    assert cat.codes_matching("W.221") == ["W.221a", "W.221b"]


def test_identity_claim_on_warning_sign(engine):
    # "Đây là biển báo 'Đường có ổ gà, lồi lõm', đúng hay sai?" for a speed bump -> Sai
    sc = scene(sign("s1", "W.221b"))
    a = engine.answer(sc, IsSign(sign=Selector(only=True), code="W.221a"))
    assert a.verdict == Verdict.no and "C.21" in articles(a)
    assert engine.answer(sc, IsSign(sign=Selector(only=True), code="W.221")).verdict == Verdict.yes


def test_meaning_of_warning_sign_by_shape(engine):
    # "Nội dung của biển báo nguy hiểm ở trong hình là gì?" -> Đường hầm
    sc = scene(sign("s1", "P.110a", shape="circle"), sign("s2", "W.240", shape="triangle"))
    a = engine.answer(sc, Meaning(sign=Selector(shape="triangle")))
    assert [v["name_vi"] for v in a.value] == ["Đường hầm"] and "C.40" in articles(a)


def test_category_of_information_sign(engine):
    # "Biển báo trong hình là loại biển báo gì?" (pedestrian crossing) -> biển chỉ dẫn
    sc = scene(sign("s1", "I.423a"))
    assert engine.answer(sc, Meaning(sign=Selector(only=True))).value[0]["category"] == "information"
    assert engine.answer(sc, IsSign(sign=Selector(only=True),
                                    category="information")).verdict == Verdict.yes


def test_expressway_sign_identity(engine):
    a = engine.answer(scene(sign("s1", "IE.465")),
                      IsSign(sign=Selector(only=True), category="information"))
    assert a.verdict == Verdict.yes and "47" in articles(a)


def test_meaning_rows_restrict_nothing(engine):
    a = engine.answer(scene(sign("s1", "W.225")), Permitted(action="enter", vehicle=V("truck")))
    assert a.verdict == Verdict.yes and a.reasons[0].detail == "no_restricting_sign"


def test_review_provenance():
    cat = load_catalog()
    by = {s.code: s for s in cat.signs}
    # The owner's full review (2026-11-27): every row, rule rows and meaning rows, was checked
    # by a person for name, letters, citation and look. Before it: 39 meaning rows and the rule
    # rows P.118 and P.119 had a human check; rows added in phase 4.5 (R.421, R.122, S.501) and
    # parser v13 (P.116) were assistant-checked; the D10 visual check covered 55 rows.
    assert len(cat.signs) == 233
    assert all(s.reviewed_by == "human" for s in cat.signs)
    assert all(s.visual_reviewed_by == "human" for s in cat.signs)
    assert {s.code for s in cat.signs if s.listed_from == "phase45"} == {"R.421", "R.122", "S.501"}
    assert {s.code for s in cat.signs if s.listed_from == "parser_v13"} == {"P.116"}
    import yaml
    from vqa.kb import MEANING_PATH
    meaning_codes = {r["code"] for r in yaml.safe_load(MEANING_PATH.read_text(encoding="utf-8"))["signs"]}
    assert sum(s.code not in meaning_codes for s in cat.signs) == 84 and len(meaning_codes) == 149
    # the visual fixes from the D10 check stay
    assert by["IE.471"].visual.background == "yellow"
    assert by["P.102"].visual.border == "none" and by["P.102"].visual.background == "red"
    assert by["I.415"].visual.shape == "other"
    assert by["IE.451b"].visual.background == "blue"
    assert by["IE.464"].visual.shape == "other"
