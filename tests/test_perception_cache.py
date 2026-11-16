"""vqa/perception/cache.py: key = image sha256 + model + effort + prompt version;
records hold model outputs only; cache/scenes/ is gitignored."""

import dataclasses
import io
import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from vqa.perception.cache import (
    CACHE_DIR, RECORD_FIELDS, REPLY_FIELDS, CacheRecord, SceneCache, scene_key,
)
from vqa.perception.image import prepare_file

ROOT = Path(__file__).resolve().parent.parent
SHA = "a" * 64


def reply(**over):
    r = {"pass": "first", "raw_text": '{"signs": []}', "stop_reason": "end_turn",
         "usage": {"input_tokens": 700, "output_tokens": 300}, "cost_usd": 0.0009,
         "request_id": "req_1"}
    r.update(over)
    return r


def test_key_changes_with_each_part_and_nothing_else():
    base = scene_key(SHA, "claude-haiku-5-5", "medium", "v1")
    assert len({base,
                scene_key("b" * 64, "claude-haiku-5-5", "medium", "v1"),
                scene_key(SHA, "claude-sonnet-5-5", "medium", "v1"),
                scene_key(SHA, "claude-haiku-5-5", "low", "v1"),
                scene_key(SHA, "claude-haiku-5-5", "medium", "v2")}) == 5
    assert scene_key(SHA, "claude-haiku-5-5", None, "v1") == scene_key(SHA, "claude-haiku-5-5", "default", "v1")
    assert [f.name for f in dataclasses.fields(CacheRecord) if f.name in
            ("image_sha256", "model", "effort", "prompt_version")] == \
        ["image_sha256", "model", "effort", "prompt_version"]
    import inspect
    assert list(inspect.signature(scene_key).parameters) == ["image_sha256", "model", "effort", "prompt_version"]


def test_key_rejects_anything_but_a_sha256():
    for bad in ("public_test_1_1.jpg", "a" * 63, "Z" * 64):
        with pytest.raises(ValueError):
            scene_key(bad, "claude-haiku-5-5", "medium", "v1")


def test_key_ignores_file_names(tmp_path):
    buf = io.BytesIO()
    Image.new("RGB", (50, 40), (10, 200, 10)).save(buf, format="PNG")
    a, b = tmp_path / "train_1_3.png", tmp_path / "renamed.png"
    a.write_bytes(buf.getvalue())
    b.write_bytes(buf.getvalue())
    ka = scene_key(prepare_file(a).sha256, "claude-haiku-5-5", "medium", "v1")
    assert ka == scene_key(prepare_file(b).sha256, "claude-haiku-5-5", "medium", "v1")


def test_round_trip_and_atomic_write(tmp_path):
    cache = SceneCache(tmp_path)
    rec = CacheRecord(SHA, "claude-haiku-5-5", "medium", "v1",
                      replies=[reply(), reply(**{"pass": "rerun", "request_id": "req_2"})])
    p = cache.put(rec)
    assert p.parent.parent == tmp_path and not list(p.parent.glob("*.tmp"))
    got = cache.get(SHA, "claude-haiku-5-5", "medium", "v1")
    assert got.replies == rec.replies and got.key == rec.key
    assert cache.get(SHA, "claude-haiku-5-5", "low", "v1") is None
    assert set(json.loads(p.read_text())) == RECORD_FIELDS


@pytest.mark.parametrize("extra", [{"scene_id": "public_test_1_1"}, {"image_path": "x.jpg"},
                                   {"gold": []}, {"scene": {}}])
def test_records_hold_model_outputs_only(tmp_path, extra):
    rec = CacheRecord(SHA, "claude-haiku-5-5", "medium", "v1", replies=[reply(**extra)])
    with pytest.raises(ValueError, match="model outputs only"):
        SceneCache(tmp_path).put(rec)
    assert not list(tmp_path.rglob("*.json"))


def test_a_tampered_record_is_refused_on_read(tmp_path):
    cache = SceneCache(tmp_path)
    p = cache.put(CacheRecord(SHA, "claude-haiku-5-5", "medium", "v1", replies=[reply()]))
    data = json.loads(p.read_text())
    data["image_id"] = "train_1_3"
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="may not hold"):
        cache.get(SHA, "claude-haiku-5-5", "medium", "v1")


def test_reply_fields_are_the_model_output():
    assert REPLY_FIELDS == {"pass", "raw_text", "stop_reason", "usage", "cost_usd", "request_id"}


def test_cache_dir_is_gitignored():
    r = subprocess.run(["git", "check-ignore", "-q", str(CACHE_DIR / "ab" / ("ab" * 32 + ".json"))], cwd=ROOT)
    assert r.returncode == 0
