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
    # phase 3 (plan item 8): gold labels, split halves, and the law_db figures, which
    # stay out of the scene prompt until an approved ablation
    "gold_signs", "gold_intents", "public_dev", "public_holdout", "images.fld", "law_db",
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


# Eval tools that read dataset questions may read public_dev and train only:
# never public_holdout or private questions (CLAUDE.md, "Dataset rules").
EVAL_QUESTION_READERS = [ROOT / "eval" / "parser_eval.py", ROOT / "eval" / "gold_intents.py",
                         ROOT / "eval" / "gold_signs.py", ROOT / "eval" / "perception_eval.py",
                         # phase 4: the public_dev end-to-end eval and the judge (the one
                         # holdout run is eval/e2e_holdout.py, aggregate only)
                         ROOT / "eval" / "e2e_eval.py", ROOT / "eval" / "judge.py",
                         # the two-pass perception trial (set T and public_dev only)
                         ROOT / "eval" / "two_pass_trial.py", ROOT / "eval" / "two_pass_variants.py",
                         # phase 4.5: the validation set and its aggregate-only runs (train only)
                         ROOT / "eval" / "make_validation_split.py", ROOT / "eval" / "e2e_validation.py",
                         ROOT / "eval" / "e2e_dev.py"]
HOLDOUT_OR_PRIVATE = ("public_holdout", "holdout", "private_test", "vlsp_2025_private")


def _code_strings(source: str) -> list[tuple[int, str]]:
    """String constants in code, leaving out docstrings (which may explain the rule)."""
    tree = ast.parse(source)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docs.add(id(body[0].value))
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]


@pytest.mark.parametrize("path", EVAL_QUESTION_READERS, ids=lambda p: p.name)
def test_eval_question_readers_never_name_holdout_or_private(path):
    found = [f"{path.name}:{line} {s!r}" for line, s in _code_strings(path.read_text(encoding="utf-8"))
             for bad in HOLDOUT_OR_PRIVATE if bad in s.lower()]
    assert not found, "eval code names holdout/private data:\n" + "\n".join(found)


def test_the_holdout_check_catches_a_subscript():
    assert any("holdout" in s for _, s in _code_strings('x = split["public_holdout"]'))
    assert not _code_strings('"""Never reads public_holdout."""')


# ---------------------------------------------------------------- phase 3: perception

@pytest.mark.parametrize("snippet", [
    "path = 'data/annotations/gold_signs_v1/gold_signs_v1.jsonl'",
    "ids = split['public_dev']['images']",
    "x = 'public_holdout'",
    "fig = law_dir / 'images.fld' / 'image092.jpg'",
    "g = 'gold_intents_v1.jsonl'",
])
def test_guard_catches_phase3_strings(snippet):
    assert violations(snippet)


def test_scene_cache_key_takes_no_file_name_or_scene_id():
    import inspect
    from vqa.perception.cache import scene_key
    assert list(inspect.signature(scene_key).parameters) == \
        ["image_sha256", "model", "effort", "prompt_version"]
    with pytest.raises(ValueError):
        scene_key("public_test_1_1.jpg", "claude-haiku-5-5", "medium", "v1")


def test_scene_cache_records_hold_model_outputs_only():
    from vqa.perception.cache import RECORD_FIELDS, REPLY_FIELDS
    assert REPLY_FIELDS == {"pass", "raw_text", "stop_reason", "usage", "cost_usd", "request_id"}
    assert RECORD_FIELDS == {"key", "image_sha256", "model", "effort", "prompt_version",
                             "replies", "created"}


def test_perception_code_is_scanned():
    names = {p.name for p in inference_files()}
    assert {"image.py", "wire.py", "cache.py"} <= names


# ---------------------------------------------------------------- phase 3: the two-pass fallback (plan item 7)


def test_the_fallback_is_scanned_and_clean():
    p = ROOT / "vqa" / "perception" / "fallback.py"
    assert p in inference_files()
    assert not violations(p.read_text(encoding="utf-8"), "fallback.py")


def test_tile_and_crop_records_are_keyed_by_bytes_model_effort_prompt_and_box_only():
    import inspect
    from vqa.perception.cache import REGION_RECORD_FIELDS, region_key
    assert list(inspect.signature(region_key).parameters) == \
        ["image_sha256", "model", "effort", "prompt_version", "box"]
    assert REGION_RECORD_FIELDS == {"key", "image_sha256", "model", "effort", "prompt_version", "box",
                                    "replies", "created"}
    with pytest.raises(ValueError):
        region_key("public_test_1_1.jpg", "claude-haiku-5-5", "medium", "v4-crop", (0, 0, 9, 9))


def test_the_fallback_prompts_name_no_public_or_private_image():
    for version in ("v4-tile", "v4-crop"):
        for p in (ROOT / "prompts" / "scene" / version).iterdir():
            if p.is_file():
                text = p.read_text(encoding="utf-8")
                assert "public_test" not in text and "private_test" not in text, p


# ---------------------------------------------------------------- phase 4 (plan item 5)

PHASE4_INFERENCE = ["vqa/pipeline.py", "vqa/answer/digest.py", "vqa/answer/faithfulness.py",
                    "vqa/answer/template.py", "vqa/answer/writer.py", "vqa/answer/prompt.py",
                    "vqa/answer/fallback.py"]
# Stored scenes reach inference only through the scene cache (owner, 2026-11-16):
# never from run files, the warm step or eval-side oracles and judges.
PHASE4_FORBIDDEN_TEXT = ("eval/runs", "runs/perception", "cache/warm", "WARMED_RUN", "warm_run",
                         "backfill", "run_file", "judge", "oracle", "e2e_")


def test_phase4_inference_code_is_scanned_and_clean():
    files = {str(p.relative_to(ROOT)) for p in inference_files()}
    assert set(PHASE4_INFERENCE) <= files
    found = []
    for rel in PHASE4_INFERENCE:
        found += violations((ROOT / rel).read_text(encoding="utf-8"), rel)
    assert not found, "\n".join(found)


def test_inference_code_never_reads_run_files_or_eval_side_scenes():
    found = [f"{p.relative_to(ROOT)} mentions {t!r}" for p in inference_files()
             for t in PHASE4_FORBIDDEN_TEXT if t.lower() in p.read_text(encoding="utf-8").lower()]
    assert not found, "\n".join(found)


def test_answer_takes_an_image_path_and_a_question_only():
    import inspect

    import vqa.pipeline as pl
    assert list(inspect.signature(pl.answer).parameters) == ["image_path", "question"]
    assert list(inspect.signature(pl.Pipeline.answer).parameters) == ["self", "image_path", "question"]


def test_oracles_call_engine_writer_and_fallback_directly_never_answer():
    import inspect

    import eval.e2e_eval as ee
    src = inspect.getsource(ee.run_oracle)
    tree = ast.parse(src.lstrip() if not src.startswith(" ") else "if 1:\n" + src)
    assert "vqa.pipeline" not in src and "Pipeline" not in src
    calls = {(n.func.value.id if isinstance(n.func.value, ast.Name) else "?")
             for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "answer"}
    assert calls <= {"engine", "fallback"}, calls


def test_the_judge_lives_in_eval_only():
    assert (ROOT / "eval" / "judge.py").exists()
    assert not [p for p in (ROOT / "vqa").rglob("*judge*")]


def test_answer_and_fallback_prompts_hold_train_examples_only():
    import json
    files = sorted((ROOT / "prompts").glob("answer*/*/examples.jsonl"))
    assert len(files) >= 3
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                assert json.loads(line)["question_id"].startswith("train_"), f


# ---------------------------------------------------------------- phase 5 (item 1): the private run

PRIVATE_QA_NAMES = ("vlsp_2025_private_test",)


def test_only_the_private_run_names_the_private_question_file():
    """eval/e2e_private.py is the scoring code: the only code that may read the private
    answers (CLAUDE.md, "Dataset rules"). Docstrings may explain the rule."""
    found = []
    for d in ("eval", "tools", "vqa", "app"):
        for p in sorted((ROOT / d).rglob("*.py")) if (ROOT / d).exists() else []:
            for line, s in _code_strings(p.read_text(encoding="utf-8")):
                if any(n in s.lower() for n in PRIVATE_QA_NAMES):
                    found.append(f"{p.relative_to(ROOT)}:{line}")
    assert found and all(f.startswith("eval/e2e_private.py:") for f in found), found


def test_the_private_run_prints_only_counters():
    """Every print in e2e_private.py is a counter, a count or the report path: none
    formats a question, an answer, a record or an image id."""
    src = (ROOT / "eval" / "e2e_private.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    prints = [ast.unparse(n) for n in ast.walk(tree)
              if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "print"]
    assert prints and all(not any(w in p for w in ("q[", "rec", "image_id", "answer", "text", "records"))
                          for p in prints), prints
