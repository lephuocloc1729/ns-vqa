"""The sign catalog: shape of every row and its citation against law_db."""

import json

import pytest

from vqa.kb import code_atom, load_catalog

from conftest import DATASET_DIR

LAW_FILE = DATASET_DIR / "dataset" / "law_db" / "vlsp2025_law.json"


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def test_size_and_unique_codes(catalog):
    assert len(catalog.signs) >= 40
    assert len({s.code for s in catalog.signs}) == len(catalog.signs)


def test_every_row_has_an_effect_or_is_auxiliary(catalog):
    for s in catalog.signs:
        e = s.effect
        has_effect = any([e.prohibits, e.max_speed, e.min_speed, e.lane_board,
                          e.lane_reserved, e.only_directions, e.ends])
        assert has_effect or s.category == "auxiliary", s.code


def test_code_atoms():
    assert code_atom("P.127b") == "p127b"
    assert code_atom("DP.133") == "dp133"
    assert code_atom("S.H,6") == "sh_6"


@pytest.mark.skipif(not LAW_FILE.exists(), reason="dataset not available (set VQA_DATASET_DIR)")
def test_every_source_exists_in_law_db(catalog):
    laws = json.loads(LAW_FILE.read_text(encoding="utf-8"))
    articles = {(law["id"], a["id"]): a for law in laws for a in law["articles"]}
    for s in catalog.signs:
        key = (s.source.law_id, s.source.article_id)
        assert key in articles, f"{s.code}: {key} not in law_db"
        # Appendix articles name the code they describe ("Biển số P.104 ...").
        if s.source.article_id[0] in "BCDEF":
            base = s.code.rstrip("abcdefgh") if s.code[-1].isalpha() else s.code
            text = articles[key]["title"] + articles[key]["text"]
            assert base.replace(" ", "") in text.replace(" ", ""), \
                f"{s.code} not mentioned in {key}"


def test_catalog_facts_cover_effects(catalog):
    facts = {str(f) for f in catalog.facts()}
    assert "prohibits(p104, enter, spec(motorbike, []))" in facts
    assert "catalog_except(p107a, city_bus)" in facts
    assert "value_cond(p106b, truck, load_t, gt)" in facts
    assert "catalog_days(p131c, even)" in facts
    assert "no_priority_exempt(p125)" in facts
