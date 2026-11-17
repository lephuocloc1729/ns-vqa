"""Phase 4.5 step 1 (owner, 2026-11-17): scene v5 (B3) and the B6 guide-board transcription
test. Hand-made images and boards; a fake client answers; no API call."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest
import yaml
from PIL import Image

import eval.guide_trial as gt
from vqa.perception import prompt as sp


# ---------------------------------------------------------------- scene v5

@pytest.mark.parametrize("v4, v5", [("v4", "v5"), ("v4-tile", "v5-tile"), ("v4-crop", "v5-crop")])
def test_v5_is_v4_plus_the_new_rows(v4, v5):
    for name in ("spec.md", "examples.jsonl"):
        assert (sp.PROMPTS_DIR / v4 / name).read_text() == (sp.PROMPTS_DIR / v5 / name).read_text()
    m4, m5 = (yaml.safe_load((sp.PROMPTS_DIR / v / "pictograms.yaml").read_text()) for v in (v4, v5))
    assert m4["rows"] == m5["rows"]
    l4, l5 = sp.catalog_listing(v4), sp.catalog_listing(v5)
    for code in ("R.122", "S.501", "R.421"):
        assert f"{code} |" in l5 and f"{code} |" not in l4
    assert set(l4.splitlines()) < set(l5.splitlines())


def test_the_frozen_ids_are_unchanged():
    assert sp.prompt_id("v4") == "scene/v4@153536ec5975"
    assert sp.prompt_id("v4-tile") == "scene/v4-tile@a052a9fc72f7" and sp.prompt_id("v4-crop") == "scene/v4-crop@30e2d18b84d9"


def test_a_v5_fallback_run_uses_the_v5_tiles_and_crops(tmp_path, monkeypatch):
    import eval.perception_eval as pe
    seen = {}

    def fake_run_fallback(scene, data, img, *, cfg, **kw):
        seen["cfg"] = cfg
        return SimpleNamespace(scene=scene, issues=[], cost_usd=0.0, replies=[], tiled=False, tiles_added=0,
                               crops=0, codes_changed=0)

    monkeypatch.setattr("vqa.perception.fallback.run_fallback", fake_run_fallback)
    buf = io.BytesIO()
    Image.new("RGB", (64, 48)).save(buf, format="JPEG")
    (tmp_path / "train_9_9.jpg").write_bytes(buf.getvalue())
    monkeypatch.setattr(pe.gs, "image_path", lambda i, s: tmp_path / f"{i}.jpg")
    monkeypatch.setattr(pe, "set_images", lambda name: [("train_9_9", "train")])
    run = tmp_path / "p1.jsonl"
    run.write_text(json.dumps({"run_id": "r1", "set": "T", "model": "claude-haiku-5-5", "prompt_id": sp.prompt_id("v5")})
                   + "\n" + json.dumps({"image_id": "train_9_9", "scene": {"scene_id": "x", "signs": []}, "issues": [],
                                        "cost_usd": 0.0}) + "\n")
    pe.fallback_run(run, 0.1, sdk=object(), out_dir=tmp_path, replay=None)
    assert seen["cfg"].tile_version == "v5-tile" and seen["cfg"].crop_version == "v5-crop"


# ---------------------------------------------------------------- the guide-board test

def test_the_guide_prompt_is_pinned():
    assert gt.prompt_hash() == gt.PINNED


def test_the_labels_are_dev_images_only():
    dev = set(json.loads((gt.ROOT / "data" / "splits" / "train_dev.json").read_text())["images"])
    val = set(json.loads((gt.ROOT / "data" / "splits" / "train_validation.json").read_text())["images"])
    ids = set(gt.labels())
    assert ids <= dev and not ids & val and len(ids) == 24


def test_fold_and_metres():
    assert gt.fold("Đông Hà") == gt.fold("DONG HA") == "DONG HA"
    assert gt.metres("61 KM") == 61000 and gt.metres("150 M") == 150 and gt.metres("5,8 km") == 5800
    assert gt.metres(None) is None and gt.metres("xa") is None


def test_score_image_matches_entries_distances_arrows_and_speeds():
    label = {"boards": [{"entries": [{"text": "ĐÔNG HÀ", "distance": "61 KM", "direction": "straight"},
                                     {"text": "QL 1A", "distance": "2 KM", "direction": "right"}],
                         "speeds": [{"kind": "max", "value": 80}]}]}
    read = [{"entries": [{"text": "Đông Hà", "distance": "61 km", "direction": "straight"},
                         {"text": "QL 1A", "distance": "5 km", "direction": "slight_right"},
                         {"text": "Bến xe", "direction": "left"}],
             "speeds": [{"kind": "max", "value": 80}]}]
    c = gt.score_image(label, read)
    assert (c["label_entries"], c["read_entries"], c["matched"]) == (2, 3, 2)
    assert (c["distance_ok"], c["distance_pairs"]) == (1, 2)
    assert (c["direction_ok"], c["direction_ok_lenient"]) == (1, 2)
    assert (c["speeds_found"], c["label_speeds"]) == (1, 1)


def test_a_no_text_image_counts_boards_read():
    c = gt.score_image({"boards": []}, [{"entries": [{"text": "X"}]}])
    assert c["no_text_images"] == 1 and c["no_text_boards_read"] == 1


class FakeClient:
    model = "claude-haiku-5-5"
    guard = SimpleNamespace(spent=0.0)

    def __init__(self):
        self.calls = []

    def json_reply(self, **kw):
        self.calls.append(kw)
        data = {"boards": [{"entries": [{"text": "ĐÔNG HÀ", "distance": "61 KM", "direction": "straight"}]}]}
        return SimpleNamespace(data=data, raw_text=json.dumps(data), cost_usd=0.001)


def test_a_run_makes_one_call_per_image_and_variant_with_crops_in_b(tmp_path, monkeypatch):
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (30, 60, 200)).save(buf, format="JPEG")
    img = tmp_path / "img.jpg"
    img.write_bytes(buf.getvalue())
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(gt, "labels", lambda: {"train_9_9": {"boards": [{"entries": [{"text": "ĐÔNG HÀ"}]}]}})
    monkeypatch.setattr(gt, "board_boxes", lambda: {"train_9_9": [[100, 100, 300, 200]]})
    c = FakeClient()
    monkeypatch.setattr("vqa.llm.client.LLMClient", lambda **kw: c)
    out = gt.run(0.1, sdk=object(), out_dir=tmp_path, image_path=lambda i: img)
    rows = [json.loads(l) for l in out.read_text().splitlines()][1:]
    assert [r["variant"] for r in rows] == ["A", "B"] and all(r["ok"] for r in rows)
    n_images = [sum(b["type"] == "image" for b in k["user"]) for k in c.calls]
    assert n_images == [1, 2]                               # B adds the board crop
    rep = gt.score(out)
    assert rep["variants"]["A"]["entry_recall"] == 1.0 and rep["variants"]["B"]["entry_precision"] == 1.0
