"""Meaning-only catalog rows (W.2xx, I.4xx, IE.4xx): naming, identity, categories."""

from vqa.kb import load_catalog
from vqa.schemas import IsSign, Meaning, Permitted, Selector, Verdict

from conftest import V, articles, scene, sign


def test_meaning_rows_loaded():
    cat = load_catalog()
    rows = [s for s in cat.signs if s.meaning_only]
    assert len(rows) >= 140
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
