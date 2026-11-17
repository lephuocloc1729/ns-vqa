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
    human = [s.code for s in cat.signs if s.reviewed_by == "human"]
    # 39 meaning rows plus the owner's review of rule rows P.118 and P.119
    assert len(human) == 41 and "IE.473" in human and "IE.472b" in human
    assert {"P.118", "P.119"} <= set(human)
    # rule rows nobody has checked; rows added in phase 4.5 are assistant-checked (owner, 2026-11-17)
    new45 = {s.code for s in cat.signs if s.listed_from == "phase45"}
    assert new45 == {"R.421", "R.122", "S.501"} and all(by[c].reviewed_by == "assistant" for c in new45)
    assert all(s.reviewed_by in ("none", "human") for s in cat.signs if not s.meaning_only and s.code not in {"P.118", "P.119"} | new45)
    visual = sorted(s.code for s in cat.signs if s.visual_reviewed_by == "assistant" and not s.listed_from)
    assert visual == ["IE.451a", "IE.471", "IE.473", "W.242(a,b)", "W.243(a,b,c)"]
    assert all(by[c].visual_reviewed_by == "assistant" for c in new45)
    assert by["IE.471"].visual.background == "yellow"
    # The owner's D10 visual check (2026-11-15): all 55 rows on the list, 35 rule rows
    # and 20 meaning rows; four of them fixed.
    seen = [s for s in cat.signs if s.visual_reviewed_by == "human"]
    assert len(seen) == 55
    # counted by the file a row comes from (phase 4.5 gave some meaning rows effects)
    import yaml
    from vqa.kb import MEANING_PATH
    meaning_codes = {r["code"] for r in yaml.safe_load(MEANING_PATH.read_text(encoding="utf-8"))["signs"]}
    assert sum(s.code not in meaning_codes for s in seen) == 35 and sum(s.code in meaning_codes for s in seen) == 20
    assert by["P.102"].visual.border == "none" and by["P.102"].visual.background == "red"
    assert by["I.415"].visual.shape == "other"
    assert by["IE.451b"].visual.background == "blue"
    assert by["IE.464"].visual.shape == "other"
