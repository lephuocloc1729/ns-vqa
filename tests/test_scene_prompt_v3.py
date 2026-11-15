"""Scene prompt v3: reference pictograms (CLAUDE.md exception), the manifest, the
confusion-pair rule, the leakage rules, and the request layout."""

import hashlib
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from PIL import Image

import vqa.perception.prompt as sp

ROOT = Path(__file__).resolve().parent.parent
V3 = sp.PROMPTS_DIR / "v3"
MANIFEST = yaml.safe_load((V3 / "pictograms.yaml").read_text(encoding="utf-8"))
CODES = {r["code"] for r in MANIFEST["rows"]}
HAVE_COPIES = (V3 / "pictograms").is_dir()

# Every look-alike pair (gold row, predicted row) in the set-T errors of Haiku v1,
# Haiku v2 and Sonnet v2 (re-verified), 2026-11-15. Owner's rule: both pictured or neither.
CONFUSION_PAIRS = [
    ("I.401", "I.409"), ("I.407(a,b,c)", "I.415"), ("I.409", "I.444(a,b,c,d,e,f,g,h,i,j,k,l,m)"),
    ("I.414(a,b,c,d)", "I.444(a,b,c,d,e,f,g,h,i,j,k,l,m)"), ("I.414(a,b,c,d)", "IE.466"),
    ("I.414(a,b,c,d)", "W.244"), ("I.417(a,b,c)", "R.415a"), ("I.444(a,b,c,d,e,f,g,h,i,j,k,l,m)", "IE.452"),
    ("I.444(a,b,c,d,e,f,g,h,i,j,k,l,m)", "R.403a"), ("I.444(a,b,c,d,e,f,g,h,i,j,k,l,m)", "W.244"),
    ("IE.451b", "IE.452"), ("IE.454", "IE.466"), ("IE.464", "IE.464b"), ("IE.464", "IE.465"),
    ("IE.464", "IE.466"), ("IE.465", "IE.466"), ("IE.466", "IE.474"), ("P.103a", "P.111b"),
    ("P.103a", "P.124a"), ("P.103a", "P.125"), ("P.103a", "P.131a"), ("P.103c", "P.124b"),
    ("P.104", "P.110a"), ("P.104", "P.111a"), ("P.104", "P.111b"), ("P.104", "P.125"),
    ("P.106a", "P.111b"), ("P.106a", "P.125"), ("P.106b", "P.107"), ("P.111b", "P.123a"),
    ("P.111b", "P.124b"), ("P.111b", "P.131a"), ("P.115", "P.125"), ("P.117", "P.118"),
    ("P.123a", "P.123b"), ("P.123a", "P.124c"), ("P.123b", "P.124a"), ("P.123b", "R.404a"),
    ("P.124a", "P.124c"), ("P.127b", "P.127c"), ("P.127c", "R.415a"), ("P.130", "P.131a"),
    ("P.131a", "R.404a"), ("R.403a", "R.412b"), ("W.203(a,b,c)", "W.246(a,b,c)"),
    ("W.205(a,b,c,d,e)", "W.207(a,b,c,d,e,f,g,h,i,k,l)"), ("W.205(a,b,c,d,e)", "W.233"),
    ("W.207(a,b,c,d,e,f,g,h,i,k,l)", "W.233"), ("W.233", "W.245a"),
]


def test_no_confusion_pair_is_half_pictured():
    half = [(a, b) for a, b in CONFUSION_PAIRS if (a in CODES) != (b in CODES)]
    assert not half, f"half-pictured pairs: {half}"


def test_manifest_rows_and_figures():
    assert MANIFEST["version"] == "v3" and MANIFEST["max_long_edge"] == 320 and len(MANIFEST["rows"]) == 53
    assert {"P.106b", "P.107", "P.127", "R.306", "IE.464b", "R.403a", "R.412b"} <= CODES   # owner's additions
    cat = sp.load_catalog()
    for r in MANIFEST["rows"]:
        assert cat.get(r["code"]).name_vi == r["name_vi"] and r["figures"]
        for f in r["figures"]:
            assert len(f["sha256"]) == 64 and f["file"].endswith(".png")
    text = (V3 / "pictograms.yaml").read_text(encoding="utf-8")
    assert "public_test" not in text and "private_test" not in text
    ie452 = next(r for r in MANIFEST["rows"] if r["code"] == "IE.452")
    assert [f["source"] for f in ie452["figures"]] == ["image026.jpg"]        # chosen by hand


@pytest.mark.skipif(not HAVE_COPIES, reason="pictogram copies not built (tools/build_scene_pictograms.py)")
def test_local_copies_match_the_manifest_and_are_small():
    files = sp.check_pictograms("v3")
    assert len(files) == 51
    for p in files:
        with Image.open(p) as im:
            assert max(im.size) <= 320


def test_a_missing_or_changed_copy_refuses_to_build(tmp_path, monkeypatch):
    d = tmp_path / "v3"
    d.mkdir()
    for name in ("spec.md", "config.yaml", "examples.jsonl", "pictograms.yaml"):
        (d / name).write_bytes((V3 / name).read_bytes())
    monkeypatch.setattr(sp, "_dir", lambda version: d)
    sp.config.cache_clear()
    try:
        with pytest.raises(sp.PictogramError, match="is missing"):
            sp.check_pictograms("v3")
        (d / "pictograms").mkdir()
        first = MANIFEST["rows"][0]["figures"][0]["file"]
        (d / "pictograms" / first).write_bytes(b"not the figure")
        with pytest.raises(sp.PictogramError, match="does not match"):
            sp.check_pictograms("v3")
    finally:
        sp.config.cache_clear()


def test_v1_and_v2_prompt_ids_are_unchanged():
    assert sp.prompt_id("v1") == "scene/v1@d6be305ababc"
    assert sp.prompt_id("v2") == "scene/v2@26be620fb386"
    assert sp.pictogram_blocks("v2") == []


def test_v3_hash_covers_the_manifest_and_v3_text_changes():
    assert sp.prompt_id("v3") != sp.prompt_id("v2")
    s = sp.system_prompt("v3")
    assert "# Reference figures" in s and "The photo is always the last image" in s
    assert "give `left`, `center` or `right` by where the sign sits across the road" in s
    assert "never separate signs" in s
    assert "Don't guess a code for a sign whose pictogram you can't see" in s
    assert "always give your best code" not in s                     # v2's rule is softened


# ---------------------------------------------------------------- leakage

def test_pictogram_copies_are_gitignored_and_no_image_under_prompts_is_tracked():
    r = subprocess.run(["git", "check-ignore", "-q", str(V3 / "pictograms" / "x.png")], cwd=ROOT)
    assert r.returncode == 0
    tracked = subprocess.run(["git", "ls-files", "prompts"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert not [t for t in tracked if t.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))]


def test_only_the_builder_in_tools_reads_law_db_figures():
    from tests.test_leakage_guard import inference_files
    for p in inference_files():
        src = p.read_text(encoding="utf-8")
        assert "law_db" not in src and "images.fld" not in src, p.name
    assert "vrs.FIGURES" in (ROOT / "tools" / "build_scene_pictograms.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------- request layout

@pytest.mark.skipif(not HAVE_COPIES, reason="pictogram copies not built")
def test_figures_come_before_the_photo_with_cache_control_on_the_last(tmp_path, monkeypatch):
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.perception.cache import SceneCache
    from vqa.perception.scene import perceive
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path))
    good = json.dumps({"signs": [{"code": "P.104", "shape": "circle", "border": "red", "background": "white",
                                  "rank": 1, "side": "right", "confidence": "high"}]})

    class SDK:
        def __init__(self):
            self.messages, self.created = self, []

        def count_tokens(self, **kw):
            return SimpleNamespace(input_tokens=14_000)

        def create(self, **kw):
            self.created.append(kw)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=good)], stop_reason="end_turn",
                                   stop_details=None, _request_id="r",
                                   usage=SimpleNamespace(input_tokens=700, output_tokens=200,
                                                         cache_read_input_tokens=13_000, cache_creation_input_tokens=0))
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (10, 10, 200)).save(buf, format="JPEG")
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(buf.getvalue())
    sdk = SDK()
    res = perceive(photo, version="v3", client=LLMClient(model="claude-haiku-5-5", sdk=sdk, guard=SpendGuard(1.0)),
                   cache=SceneCache(tmp_path / "cache"))
    assert res.ok
    content = sdk.created[0]["messages"][0]["content"]
    images = [i for i, b in enumerate(content) if b["type"] == "image"]
    assert content[0] == {"type": "text", "text": "Reference figures:"}
    assert len(images) == 52                                                # 51 figures + the photo
    assert content[images[-2]]["cache_control"] == {"type": "ephemeral"}    # last figure
    assert content[images[-1]]["source"]["media_type"] == "image/jpeg"      # the photo, last
    assert "cache_control" not in content[images[-1]]
