"""Phase 4.7 step 1e (owner, 2026-11-17: additive only): parser v12 = v11 plus the phase-4.7 forms.
v11's spec lines and few-shots stay (train_94, marked out of scope in v11, now shows `marking_is`);
seven few-shots are appended from the train working set (outside dev and validation and their
images), exact text. No API call."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from vqa.parsing import validator
from vqa.parsing.prompt import examples, system_prompt
from vqa.parsing.wire import WParse, to_query
from vqa.reasoning.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
NEW = ["train_172", "train_332", "train_469", "train_50", "train_312", "train_113", "train_383"]


def test_v12_keeps_v11_lines_and_adds_the_new_forms():
    a = (ROOT / "prompts/parser/v11/spec.md").read_text().splitlines()
    b = (ROOT / "prompts/parser/v12/spec.md").read_text()
    kept = [x for x in a if x not in b]
    # the only v11 lines not kept verbatim: the yes/no line's last sentence, and the out-of-scope
    # list's lights / markings / counting lines (now in scope)
    assert len(kept) == 4, kept
    for form in ("`count_is`", "`sign_applies`", "`rule_permitted`", "`marking_is`", "`count`", "`applies_to`",
                 "`duties`", "`signal_meaning`", "`marking_meaning`"):
        assert form in b, form
    assert "fine amounts" in b and "keep `permitted` / `speed_ok` otherwise" in b


def test_v12_fewshots_are_v11_plus_seven():
    e11, e12 = examples("v11"), examples("v12")
    assert [e["id"] for e in e12][:len(e11)] == [e["id"] for e in e11]
    assert [e["id"] for a, e in zip(e11, e12) if a != e] == ["train_94"]
    assert [e["id"] for e in e12[len(e11):]] == NEW


def test_v12_fewshots_are_valid_and_from_train_outside_dev_and_validation():
    engine = Engine()
    for ex in examples("v12"):
        assert validator.check(to_query(WParse.model_validate(ex["output"]), 2026), engine) == [], ex["id"]
    dev = json.loads((ROOT / "data/splits/train_dev.json").read_text())
    val = json.loads((ROOT / "data/splits/train_validation.json").read_text())
    ids = {e["id"] for e in examples("v12")}
    assert not ids & (set(dev["questions"]) | set(val["questions"]))
    train = (Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural"))
             / "dataset" / "train data" / "vlsp_2025_train.json")
    if not train.exists():
        pytest.skip("train data not available")
    rows = {t["id"]: t for t in json.loads(train.read_text(encoding="utf-8"))}
    for e in examples("v12")[len(examples("v11")):]:
        assert e["split"] == "train" and rows[e["id"]]["question"] == e["question"], e["id"]
        assert rows[e["id"]]["image_id"] not in set(dev["images"]) | set(val["images"]), e["id"]


def test_v12_prompt_builds_and_differs_from_v11():
    assert system_prompt("v12") != system_prompt("v11") and "rule_permitted" in system_prompt("v12")
