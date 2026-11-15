"""prompts/scene/v1 and vqa/perception/prompt.py: contents, hash, and no public or
private ids."""

import json
import re
from pathlib import Path

import pytest

import vqa.perception.prompt as sp
from vqa.perception import image
from vqa.perception.wire import to_scene

V1 = sp.PROMPTS_DIR / "v1"
SPLIT = Path(__file__).resolve().parent.parent / "data" / "splits"


def test_v1_has_spec_config_and_examples():
    assert {p.name for p in V1.iterdir()} == {"spec.md", "config.yaml", "examples.jsonl"}
    cfg = sp.config("v1")
    assert cfg["max_tokens"] >= 4096 and cfg["retry"] == 1
    assert sp.effort_for("claude-haiku-5-5") == "medium"


def test_config_image_prep_matches_the_code():
    img = sp.config("v1")["image"]
    assert (img["prep_version"], img["long_edge"], img["max_pixels"], img["jpeg_quality"]) == \
        (image.PREP_VERSION, image.LONG_EDGE, image.MAX_PIXELS, image.JPEG_QUALITY)


def test_system_prompt_holds_the_spec_the_catalog_and_the_examples():
    s = sp.system_prompt("v1")
    assert "# What counts as a sign" in s and "standalone local notices" in s
    assert '"UNKNOWN"' in s and "Reply with only one JSON object" in s
    assert "P.127 | " in s and "| value" in s.split("P.127 | ", 1)[1].split("\n", 1)[0]
    assert "R.303 | Nơi giao nhau chạy theo vòng xuyến | circle / none / blue" in s
    assert "P.102 | " in s and "circle / none / red" in s.split("P.102 | ", 1)[1].split("\n", 1)[0]
    assert s.count("Example (") == len(sp.examples("v1")) >= 1


def test_every_example_is_a_valid_reply_from_a_train_image():
    for ex in sp.examples("v1"):
        assert re.fullmatch(r"train_\d+_\d+", ex["image"]), ex["image"]
        r = to_scene(ex["output"], ex["image"])
        assert r.ok, r.errors


def test_examples_are_not_set_t_images_nor_public_or_private_duplicates():
    t = set(json.loads((SPLIT / "gold_signs_set_t.json").read_text())["images"])
    groups = json.loads((SPLIT / "duplicates.json").read_text())["groups"]
    for ex in sp.examples("v1"):
        assert ex["image"] not in t
        for g in groups:
            ids = {i["image_id"] for i in g["images"]}
            if ex["image"] in ids:
                assert all(i["split"] == "train" for i in g["images"]), ex["image"]


def test_no_public_or_private_ids_in_the_prompt_files():
    for p in V1.iterdir():
        text = p.read_text(encoding="utf-8")
        assert not re.search(r"public_(test|natural)_\d|private_test", text), p.name


def test_prompt_hash_covers_the_catalog(monkeypatch):
    before = sp.prompt_hash("v1")
    assert sp.prompt_id("v1") == f"scene/v1@{before[:12]}"
    monkeypatch.setattr(sp, "catalog_listing", lambda: "P.999 | changed | circle / red / white")
    sp.system_prompt.cache_clear()
    try:
        assert sp.prompt_hash("v1") != before
    finally:
        sp.system_prompt.cache_clear()


def test_unknown_version_is_an_error():
    with pytest.raises(FileNotFoundError):
        sp.system_prompt("v999")
