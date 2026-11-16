"""Plan item 1b.3 (owner, 2026-11-16): the interpretation load_implies_gross. QCVN 41
B.15 defines the gross mass as own mass + people, luggage and goods, so a load above
x t means a gross mass above x t. Shown in the proof (cite r_load_implies_gross),
never counted as a law citation. Scenes modelled on train_41 ("Biển 10t ... Xe nào
không được đi qua?")."""

from vqa.kb import load_catalog
from vqa.reasoning.explain import walk
from vqa.schemas import Permitted, Verdict

from conftest import V, articles, scene, sign

P115 = scene(sign("s1", "P.115", value=10, unit="t", shape="circle", border="red", background="white"))


def permitted(engine, veh):
    return engine.answer(P115, Permitted(action="enter", vehicle=veh))


def cited_rules(a):
    return {n.rule for r in a.reasons if r.proof for n in walk(r.proof) if n.type == "cite"}


def test_a_load_above_the_limit_is_a_gross_mass_above_it(engine):
    a = permitted(engine, V("truck", load_gt=10))
    assert a.verdict == Verdict.no
    assert "r_load_implies_gross" in cited_rules(a)
    assert "B.15" in articles(a)
    assert "interpretation" not in {c.law_id for c in a.citations}        # not a law citation


def test_an_exact_load_above_the_limit(engine):
    assert permitted(engine, V("truck", load_t=12)).verdict == Verdict.no


def test_a_load_below_the_limit_says_nothing_about_the_gross_mass(engine):
    a = permitted(engine, V("truck", load_t=8))
    assert a.verdict == Verdict.unknown                                    # gross >= 8 only


def test_a_stated_gross_mass_wins(engine):
    a = permitted(engine, V("truck", gross_t=9, load_t=12))  # inconsistent on purpose
    assert a.verdict == Verdict.yes and "r_load_implies_gross" not in cited_rules(a)


def test_no_load_no_interpretation(engine):
    a = permitted(engine, V("truck"))
    assert a.verdict == Verdict.unknown and "r_load_implies_gross" not in cited_rules(a)


def test_recorded_in_the_catalog_as_an_interpretation():
    vis = load_catalog().vehicle_interpretations
    [vi] = [v for v in vis if v.attribute_rule == "load_implies_gross"]
    assert vi.cls is None and "Interpretation" in vi.note
    assert (vi.source.law_id, vi.source.article_id) == ("QCVN 41:2024/BGTVT", "B.15")


def test_the_rule_source_marks_it_as_an_interpretation():
    import janus_swi as janus
    r = janus.query_once("rule_source(r_load_implies_gross, L, A)")
    assert (r["L"], r["A"]) == ("interpretation", "load_implies_gross")
