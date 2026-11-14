"""Leakage guard (CLAUDE.md, "Leakage guard").

Inference code (vqa/, app/) must never read hand-made scene graphs, fixtures,
gold annotations, audits, split/duplicate files or the dataset's QA files.
This test scans its source for imports and path strings that would do so.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from eval.report import duplicated_images, format_report, score_report, wilson_ci

ROOT = Path(__file__).resolve().parent.parent
INFERENCE_DIRS = [ROOT / "vqa", ROOT / "app"]

FORBIDDEN_MODULES = ("tests", "conftest", "eval")
FORBIDDEN_STRINGS = (
    "tests/fixtures", "fixtures/", "data/annotations", "annotations/", "eval/audits",
    "data/splits", "duplicates.json", "public_split", "vlsp_2025_train",
    "vlsp_2025_public_test", "vlsp_2025_private_test", "train_images",
    "VLSP2025-MLQA-Natural", "VQA_DATASET_DIR",
)


def violations(source: str, filename: str = "<src>") -> list[str]:
    out = []
    tree = ast.parse(source, filename)
    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods = [node.module]
        for m in mods:
            if m.split(".")[0] in FORBIDDEN_MODULES:
                out.append(f"{filename}:{node.lineno} imports {m}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for s in FORBIDDEN_STRINGS:
                if s.lower() in node.value.lower():
                    out.append(f"{filename}:{node.lineno} mentions {s!r}")
    return out


def inference_files() -> list[Path]:
    return [p for d in INFERENCE_DIRS if d.exists() for p in sorted(d.rglob("*.py"))]


def test_inference_code_does_not_touch_gold_data():
    found = []
    for p in inference_files():
        found += violations(p.read_text(encoding="utf-8"), str(p.relative_to(ROOT)))
    assert not found, "inference code reaches gold/fixture data:\n" + "\n".join(found)


@pytest.mark.parametrize("snippet", [
    "from tests.conftest import scene",
    "import eval.report",
    "open('tests/fixtures/train_1.json')",
    "path = ROOT / 'data/annotations/gold_signs.json'",
    "json.load(open('dataset/train data/vlsp_2025_train.json'))",
    "dup = 'data/splits/duplicates.json'",
])
def test_guard_catches_violations(snippet):
    assert violations(snippet)


def test_guard_allows_normal_code():
    assert not violations("from vqa.schemas import SceneGraph\nimport janus_swi\nx = 'kb/load.pl'")


# ---------------------------------------------------------------- eval reports

DUPS = {"groups": [
    {"images": [{"split": "public", "image_id": "p1"}, {"split": "train", "image_id": "t1"}]},
    {"images": [{"split": "private", "image_id": "q1"}, {"split": "public", "image_id": "p2"}]},
    {"images": [{"split": "train", "image_id": "t2"}, {"split": "train", "image_id": "t3"}]},
]}


def test_duplicated_images_by_split():
    assert duplicated_images("public", DUPS) == {"p1"}         # private does not count for public
    assert duplicated_images("private", DUPS) == {"q1"}        # public counts for private
    assert duplicated_images("train", DUPS) == set()


def test_score_report_splits_and_ci():
    results = [{"question_id": f"q{i}", "image_id": img, "correct": c}
               for i, (img, c) in enumerate([("p1", True), ("p1", True), ("p2", False),
                                             ("p3", True), ("p4", True)])]
    rep = score_report(results, "public", DUPS)
    assert rep["all_images"]["n"] == 5 and rep["all_images"]["accuracy"] == 0.8
    nd = rep["non_duplicate_images"]
    assert nd["n"] == 3 and abs(nd["accuracy"] - 2 / 3) < 1e-9
    lo, hi = nd["ci95"]
    assert 0 < lo < 2 / 3 < hi < 1
    assert rep["duplicate_images"]["n"] == 2
    assert "95% CI" in format_report(rep)


def test_wilson_ci_known_value():
    lo, hi = wilson_ci(8, 10)
    assert round(lo, 3) == 0.490 and round(hi, 3) == 0.943
