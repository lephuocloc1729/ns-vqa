"""Train questions run end to end through the engine, with hand-written scenes.

Fixtures live in tests/fixtures/train_*.json (format in tests/fixtures/README.md).
For each question:

* test_answer: every program gives the expected verdict (and value subset).
* test_citations: the articles cited across all its answers contain the
  question's core relevant_articles.
* test_core_articles_match_dataset: the fixture's core + not_core equals the
  dataset's relevant_articles (skipped when the dataset is not available).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from vqa.schemas import Answer, Program, SceneGraph

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = sorted((ROOT / "tests" / "fixtures").glob("train_*.json"))
DATASET_DIR = Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural"))
TRAIN_FILE = DATASET_DIR / "dataset" / "train data" / "vlsp_2025_train.json"

_program = TypeAdapter(Program)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


CASES = {p.stem: _load(p) for p in FIXTURES}


def _run(engine, fx: dict[str, Any]) -> list[tuple[dict[str, Any], Answer]]:
    scene = SceneGraph.model_validate(fx["scene"])
    return [(c, engine.answer(scene, _program.validate_python(c["program"])))
            for c in fx["cases"]]


def _matches(expected: Any, actual: Any) -> bool:
    """Dicts match on the expected keys; lists match element-wise with equal length."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and _matches(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        return (isinstance(actual, list) and len(expected) == len(actual)
                and all(_matches(e, a) for e, a in zip(expected, actual)))
    return expected == actual


def test_six_fixtures_present():
    assert len(CASES) == 6, sorted(CASES)


@pytest.mark.parametrize("qid", sorted(CASES))
def test_answer(engine, qid):
    for case, answer in _run(engine, CASES[qid]):
        exp = case["expect"]
        where = f"{qid} {case['program']}"
        assert answer.verdict.value == exp["verdict"], f"{where}: got {answer.verdict.value}"
        if "value" in exp:
            assert _matches(exp["value"], answer.value), f"{where}: value {answer.value}"


def _citation_params():
    for qid in sorted(CASES):
        reason = CASES[qid].get("citation_xfail")
        marks = [pytest.mark.xfail(reason=reason, strict=True)] if reason else []
        yield pytest.param(qid, marks=marks, id=qid)


@pytest.mark.parametrize("qid", list(_citation_params()))
def test_citations(engine, qid):
    fx = CASES[qid]
    cited = {c.article_id for _, a in _run(engine, fx) for c in a.citations}
    missing = set(fx["core_articles"]) - cited
    assert not missing, f"{qid}: cited {sorted(cited)}, missing core {sorted(missing)}"


@pytest.mark.skipif(not TRAIN_FILE.exists(), reason="dataset not available (set VQA_DATASET_DIR)")
@pytest.mark.parametrize("qid", sorted(CASES))
def test_core_articles_match_dataset(qid):
    fx = CASES[qid]
    gold = {t["id"]: t for t in json.loads(TRAIN_FILE.read_text(encoding="utf-8"))}[qid]
    assert gold["image_id"] == fx["image_id"]
    relevant = {r["article_id"] for r in gold["relevant_articles"]}
    assert set(fx["core_articles"]) | set(fx["not_core"]) == relevant
    assert not set(fx["core_articles"]) & set(fx["not_core"])
