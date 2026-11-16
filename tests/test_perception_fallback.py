"""The two-pass fallback (docs/plans/phase-3.md, item 7; owner, 2026-11-16).

Hand-made scenes and synthetic images only; no API call (a fake client answers)."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

import vqa.perception.fallback as fb
from vqa.perception import prompt as sp
from vqa.perception.cache import REGION_RECORD_FIELDS, REPLY_FIELDS, RegionRecord, SceneCache, region_key, scene_key
from vqa.perception.image import LONG_EDGE, MAX_PIXELS, prepare
from vqa.schemas import AltReading, Confidence, Position, SceneGraph, Side, Sign

SHA = "a" * 64


def sign(sid, code="P.104", rank=None, side="right", box=None, conf="high", value=None, alts=()):
    return Sign(id=sid, code=code, value=value, confidence=conf,
                position=Position(rank_top_down=rank, side=side, box=box),
                alternatives=[AltReading(code=a) if isinstance(a, str) else a for a in alts])


def ranks_sides(signs):
    return [(s.id, s.position.rank_top_down, s.position.side.value) for s in signs]


# ---------------------------------------------------------------- triggers


def test_tiles_need_five_listed_signs():
    four = SceneGraph(scene_id="x", signs=[sign(f"s{k}", rank=k) for k in range(1, 5)])
    five = SceneGraph(scene_id="x", signs=[sign(f"s{k}", rank=k) for k in range(1, 6)])
    assert fb.DENSE_MIN_SIGNS == 5
    assert not fb.needs_tiles(four) and fb.needs_tiles(five)


@pytest.mark.parametrize("code,conf,want", [("P.104", "low", True), ("UNKNOWN", "high", True),
                                            ("UNKNOWN", "low", True), ("P.104", "medium", False),
                                            ("P.104", "high", False)])
def test_crops_are_for_low_or_unknown_signs(code, conf, want):
    assert fb.needs_crop(sign("s1", code=code, conf=conf)) is want


# ---------------------------------------------------------------- geometry


def test_tiles_cover_the_image_with_twenty_percent_overlap():
    tiles = fb.tile_boxes(1000, 600)
    assert len(tiles) == 4
    assert tiles[0][:2] == (0, 0) and tiles[-1][2:] == (1000, 600)
    (a, _, b, _), (c, _, d, _) = tiles[0], tiles[1]
    assert c < b                                         # they overlap
    assert (b - c) / (b - a) == pytest.approx(0.2, abs=0.01)
    assert {t[1] for t in tiles} == {0, tiles[2][1]} and tiles[2][1] < tiles[0][3]


def test_a_tile_is_enlarged_up_to_the_scene_prep_limits():
    s = fb.tile_scale(444, 333)
    assert s > 1
    assert 444 * s <= LONG_EDGE + 1 and 444 * 333 * s * s <= MAX_PIXELS * 1.001


def test_crop_widens_the_box_and_more_below():
    # a 100 x 100 box well inside: 50% each side and above, 100% below
    assert fb.crop_box((300, 300, 400, 400), 1000, 1000) == (250, 250, 450, 500)


def test_crop_is_at_least_128_px_each_way_and_stays_inside():
    assert fb.crop_box((100, 100, 124, 124), 600, 600) == (48, 54, 176, 182)
    assert fb.crop_box((0, 0, 24, 24), 600, 600) == (0, 0, 128, 128)          # shifted in at a corner
    x0, y0, x1, y1 = fb.crop_box((580, 590, 600, 600), 600, 600)
    assert (x1, y1) == (600, 600) and x1 - x0 == 128 and y1 - y0 == 128
    assert fb.crop_box((0, 0, 10, 10), 100, 80) == (0, 0, 100, 80)            # image smaller than 128


def test_crop_margins_are_clipped_not_shifted():
    assert fb.crop_box((10, 10, 200, 300), 600, 600) == (0, 0, 295, 590)


def test_crop_is_enlarged_to_384_on_its_short_side():
    assert fb.crop_scale(128, 160) == pytest.approx(3.0)
    assert fb.crop_scale(400, 500) == 1.0                                      # never shrunk
    assert 128 * fb.crop_scale(128, 1000) <= LONG_EDGE + 1                    # capped by the long edge


# ---------------------------------------------------------------- dedup


def test_a_tile_sign_over_a_pass1_sign_is_dropped():
    p1 = [(100, 100, 200, 200)]
    found = [(sign("t1"), (110, 110, 205, 205)),       # IoU >= 0.3
             (sign("t2"), (160, 160, 400, 400)),       # IoU < 0.3 and neither centre inside: new
             (sign("t3"), (90, 140, 400, 160))]        # its centre is outside p1, but p1's centre is inside it
    kept, dropped = fb.dedup(p1, found)
    assert [s.id for s, _ in kept] == ["t2"] and dropped == 2


def test_a_tile_sign_with_its_centre_inside_a_pass1_box_is_dropped():
    kept, dropped = fb.dedup([(0, 0, 300, 300)], [(sign("t1"), (250, 250, 320, 320))])
    assert kept == [] and dropped == 1


def test_overlapping_tiles_keep_the_more_confident_reading_then_the_earlier():
    a = (sign("t1", conf="low"), (500, 500, 560, 560))
    b = (sign("t2", conf="high"), (505, 505, 565, 565))
    c = (sign("t3", conf="high"), (800, 100, 860, 160))
    d = (sign("t4", conf="high"), (802, 102, 862, 162))
    kept, dropped = fb.dedup([], [a, b, c, d])
    assert [s.id for s, _ in kept] == ["t2", "t3"] and dropped == 2


# ---------------------------------------------------------------- ranks (owner's change 1, option B)


P1 = [sign("s1", rank=1, side="left", box=(10, 10, 50, 50)),
      sign("s2", rank=2, side="right", box=(600, 100, 650, 150)),
      sign("s3", rank=3, side="center", box=(300, 300, 350, 350))]
TOPS = [10.0, 100.0, 300.0]


def test_no_tile_additions_leaves_ranks_and_sides_identical():
    assert fb.place_ranks(P1, TOPS, [], 800) == P1


def test_a_sign_added_above_all_takes_rank_1_and_the_rest_shift():
    new = sign("t1", conf="low", box=(700, 2, 740, 8), side="unknown")
    out = fb.place_ranks(P1, TOPS, [(new, 2.0)], 800)
    assert ranks_sides(out) == [("s1", 2, "left"), ("s2", 3, "right"), ("s3", 4, "center"), ("t1", 1, "right")]


def test_a_sign_added_between_two_takes_its_place():
    new = sign("t1", conf="low", box=(100, 200, 140, 240), side="unknown")
    out = fb.place_ranks(P1, TOPS, [(new, 200.0)], 800)
    assert ranks_sides(out) == [("s1", 1, "left"), ("s2", 2, "right"), ("s3", 4, "center"), ("t1", 3, "left")]


def test_a_sign_added_below_all_takes_the_next_rank():
    new = sign("t1", conf="low", box=(500, 500, 540, 540), side="unknown")
    out = fb.place_ranks(P1, TOPS, [(new, 500.0)], 800)
    assert ranks_sides(out) == [("s1", 1, "left"), ("s2", 2, "right"), ("s3", 3, "center"), ("t1", 4, "right")]


def test_several_added_signs_keep_pass1_order():
    a = sign("t1", conf="low", box=(10, 150, 40, 180))
    b = sign("t2", conf="low", box=(10, 160, 40, 190))
    c = sign("t3", conf="low", box=(10, 0, 40, 5))
    out = fb.place_ranks(P1, TOPS, [(a, 150.0), (b, 160.0), (c, 0.0)], 800)
    r = {s.id: s.position.rank_top_down for s in out}
    assert r == {"t3": 1, "s1": 2, "s2": 3, "t1": 4, "t2": 5, "s3": 6}
    assert [s.position.side for s in out[:3]] == [Side.left, Side.right, Side.center]


def test_a_pass1_tie_is_kept_when_a_sign_is_added_below_it():
    tied = [sign("s1", rank=1, side="left", box=(10, 10, 50, 50)),
            sign("s2", rank=1, side="right", box=(600, 12, 650, 60)),
            sign("s3", rank=2, side="right", box=(600, 300, 650, 350))]
    new = sign("t1", conf="low", box=(100, 100, 140, 140))
    out = fb.place_ranks(tied, [10.0, 12.0, 300.0], [(new, 100.0)], 800)
    assert ranks_sides(out) == [("s1", 1, "left"), ("s2", 1, "right"), ("s3", 3, "right"), ("t1", 2, "left")]


def test_a_pass1_tie_stays_tied_when_a_sign_is_added_above_it():
    tied = [sign("s1", rank=1, box=(10, 100, 50, 150)), sign("s2", rank=1, box=(600, 105, 650, 150))]
    out = fb.place_ranks(tied, [100.0, 105.0], [(sign("t1", box=(300, 5, 330, 30)), 5.0)], 800)
    assert [s.position.rank_top_down for s in out] == [2, 2, 1]


def test_signs_without_a_rank_are_left_alone():
    loose = [*P1, sign("s4", rank=None, side="left")]
    out = fb.place_ranks(loose, [*TOPS, None], [(sign("t1", box=(5, 0, 9, 4)), 0.0)], 800)
    assert out[3] == loose[3]


# ---------------------------------------------------------------- combining crop readings


def crop(code, conf="high", value=None, alt=None):
    return fb.CropReading(code, Confidence(conf), value, None, AltReading(code=alt) if alt else None)


def test_a_crop_that_reads_unknown_changes_nothing():
    s = sign("s1", code="P.104", conf="low")
    for policy in fb.POLICIES:
        assert fb.combine(s, crop("UNKNOWN"), policy)[0] == s


def test_agreement_raises_to_medium_in_every_policy():
    s = sign("s1", code="P.127", conf="low", value=50)
    for policy in fb.POLICIES:
        out, _ = fb.combine(s, crop("P.127", "low", value=50), policy)
        assert out.code == "P.127" and out.confidence == Confidence.medium


def test_a_value_conflict_is_not_agreement():
    out, _ = fb.combine(sign("s1", code="P.127", conf="low", value=50), crop("P.127", "medium", value=60))
    assert out.code == "P.127" and out.value == 50 and out.alternatives[-1].value == 60


def test_rules_unknown_takes_the_crop_code_at_low():
    out, _ = fb.combine(sign("s1", code="UNKNOWN", conf="low"), crop("R.415a", "medium"))
    assert out.code == "R.415a" and out.confidence == Confidence.low and out.alternatives == []


def test_rules_crop_agreeing_with_the_alternative_swaps():
    s = sign("s1", code="P.124a", conf="low", alts=["P.123a", "P.123b"])
    out, what = fb.combine(s, crop("P.123b", "medium"))
    assert out.code == "P.123b" and out.confidence == Confidence.low
    assert [a.code for a in out.alternatives] == ["P.124a", "P.123a"] and "swapped" in what


def test_rules_other_disagreement_adds_an_alternative_unless_the_crop_is_high():
    s = sign("s1", code="P.103a", conf="low")
    out, _ = fb.combine(s, crop("P.111b", "medium"))
    assert out.code == "P.103a" and [a.code for a in out.alternatives] == ["P.111b"]
    out, _ = fb.combine(s, crop("P.111b", "high"))
    assert out.code == "P.111b" and [a.code for a in out.alternatives] == ["P.103a"]
    assert out.confidence == Confidence.low


def test_crop_always_crop_high_and_never():
    s = sign("s1", code="P.103a", conf="low")
    assert fb.combine(s, crop("P.111b", "low"), "crop_always")[0].code == "P.111b"
    assert fb.combine(s, crop("P.111b", "medium"), "crop_high")[0].code == "P.103a"
    assert fb.combine(s, crop("P.111b", "high"), "crop_high")[0].code == "P.111b"
    out = fb.combine(s, crop("P.111b", "high"), "never")[0]
    assert out.code == "P.103a" and out.alternatives[-1].code == "P.111b"
    u = sign("s2", code="UNKNOWN", conf="low")
    assert fb.combine(u, crop("P.104", "high"), "never")[0].code == "UNKNOWN"
    assert fb.combine(u, crop("P.104", "low"), "crop_always")[0].alternatives == []


def test_unknown_policy_is_refused():
    with pytest.raises(ValueError):
        fb.FallbackConfig(policy="best")


def test_crop_replies_are_checked_against_the_catalog():
    from vqa.kb import load_catalog
    cat = load_catalog()
    r = fb.parse_crop({"code": "P.999", "confidence": "sure", "value": "fifty"}, cat)
    assert (r.code, r.confidence, r.value, r.raw_code) == ("UNKNOWN", Confidence.low, None, "P.999")
    r = fb.parse_crop({"code": "W.207c", "confidence": "high", "alt": {"code": "W.207b"}}, cat)
    assert r.code == "W.207c" and r.alt.code == "W.207b"
    assert fb.parse_crop([], cat).code == "UNKNOWN"


# ---------------------------------------------------------------- the cache key (image + model + effort + prompt + box)


def test_region_key_changes_with_each_part_and_the_box():
    base = region_key(SHA, "claude-haiku-5-5", "medium", "v4-crop@x", (1, 2, 30, 40))
    assert len({base,
                region_key("b" * 64, "claude-haiku-5-5", "medium", "v4-crop@x", (1, 2, 30, 40)),
                region_key(SHA, "claude-sonnet-5-5", "medium", "v4-crop@x", (1, 2, 30, 40)),
                region_key(SHA, "claude-haiku-5-5", "low", "v4-crop@x", (1, 2, 30, 40)),
                region_key(SHA, "claude-haiku-5-5", "medium", "v4-tile@x", (1, 2, 30, 40)),
                region_key(SHA, "claude-haiku-5-5", "medium", "v4-crop@x", (1, 2, 30, 41)),
                scene_key(SHA, "claude-haiku-5-5", "medium", "v4-crop@x")}) == 7
    assert base == region_key(SHA, "claude-haiku-5-5", "medium", "v4-crop@x", [1, 2, 30, 40])


@pytest.mark.parametrize("box", [(1, 2, 3), (5, 5, 5, 9), (-1, 0, 4, 4), (0.5, 0, 4, 4), "1,2,3,4"])
def test_region_key_rejects_bad_boxes(box):
    with pytest.raises(ValueError):
        region_key(SHA, "claude-haiku-5-5", "medium", "v4-crop@x", box)


def test_region_records_hold_model_outputs_only(tmp_path):
    cache = SceneCache(tmp_path)
    ok = {"pass": "crop", "raw_text": "{}", "stop_reason": "end_turn", "usage": {}, "cost_usd": 0.0,
          "request_id": "r"}
    p = cache.put_region(RegionRecord(SHA, "m", "medium", "v4-crop@x", (1, 2, 30, 40), replies=[ok]))
    assert set(json.loads(p.read_text())) == REGION_RECORD_FIELDS
    assert REGION_RECORD_FIELDS == {"key", "image_sha256", "model", "effort", "prompt_version", "box",
                                    "replies", "created"}
    assert cache.get_region(SHA, "m", "medium", "v4-crop@x", (1, 2, 30, 40)).replies == [ok]
    assert cache.get(SHA, "m", "medium", "v4-crop@x") is None            # not a scene record
    with pytest.raises(ValueError):
        cache.put_region(RegionRecord(SHA, "m", "medium", "v4-crop@x", (1, 2, 30, 40),
                                      replies=[{**ok, "scene_id": "public_test_1_1"}]))
    assert set(ok) == REPLY_FIELDS


# ---------------------------------------------------------------- end to end, with a fake client

W, H = 800, 600


def image_bytes(colour=(90, 120, 150)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (W, H), colour).save(buf, format="JPEG")
    return buf.getvalue()


def dense_scene() -> SceneGraph:
    return SceneGraph(scene_id="x", signs=[
        sign("s1", rank=1, side="left", box=(20, 10, 60, 50)),
        sign("s2", rank=2, side="right", box=(700, 60, 740, 100)),
        sign("s3", code="UNKNOWN", conf="low", rank=3, side="left", box=(100, 110, 130, 140)),
        sign("s4", rank=4, side="right", box=(600, 160, 640, 200)),
        sign("s5", rank=5, side="center", box=(380, 400, 420, 440))])


class FakeClient:
    """Tile 1 sees one new sign (orig box 300,250,340,290) and repeats s1; the other
    tiles see nothing new. Every crop reads P.104 high."""

    model = "claude-haiku-5-5"

    def __init__(self):
        self.calls = []

    def json_reply(self, **kw):
        self.calls.append(kw)
        if kw["purpose"] == "scene tile":
            n = sum(c["purpose"] == "scene tile" for c in self.calls)
            if n == 1:
                tb = fb.tile_boxes(W, H)[0]
                sc = fb.tile_scale(tb[2] - tb[0], tb[3] - tb[1])
                to_tile = lambda b: [round(v * sc) for v in b]  # noqa: E731
                data = {"signs": [{"code": "P.123a", "confidence": "medium", "rank": 1, "side": "left",
                                   "box": to_tile((300, 250, 340, 290))},
                                  {"code": "P.104", "confidence": "high", "box": to_tile((20, 10, 60, 50))}]}
            else:
                data = {"signs": []}
        else:
            data = {"code": "P.104", "confidence": "high"}
        text = json.dumps(data)
        return SimpleNamespace(data=data, raw_text=text, cost_usd=0.001, usage={"output_tokens": 10},
                               request_id="r")


def test_the_fallback_adds_tile_signs_in_rank_order_and_crops_unsure_ones(tmp_path):
    data = image_bytes()
    client = FakeClient()
    res = fb.run_fallback(dense_scene(), data, prepare(data), model=client.model, client=client,
                          cache=SceneCache(tmp_path), use_cache=False)
    kinds = [c["purpose"] for c in client.calls]
    assert kinds.count("scene tile") == 4 and kinds.count("scene crop") == 2     # s3, and the added sign
    assert res.tiled and res.tiles_added == 1 and res.crops == 2
    by_box = {s.position.box: s for s in res.scene.signs}
    added = by_box[(300, 250, 340, 290)]
    assert added.position.rank_top_down == 5 and added.position.side == Side.left
    assert added.code == "P.104" and [a.code for a in added.alternatives] == ["P.123a"]   # crop high wins
    assert by_box[(380, 400, 420, 440)].position.rank_top_down == 6                 # s5 shifted
    assert by_box[(100, 110, 130, 140)].code == "P.104"                             # UNKNOWN filled
    assert [(s.position.rank_top_down, s.position.side) for s in res.scene.signs[:4]] == \
        [(1, Side.left), (2, Side.right), (3, Side.left), (4, Side.right)]
    assert res.cost_usd == pytest.approx(0.006) and len(res.replies) == 6
    assert [s.id for s in res.scene.signs] == [f"s{k}" for k in range(1, 7)]


def test_a_sparse_scene_with_sure_signs_makes_no_call(tmp_path):
    data = image_bytes()
    scene = SceneGraph(scene_id="x", signs=[sign("s1", rank=1, box=(10, 10, 50, 50))])
    client = FakeClient()
    res = fb.run_fallback(scene, data, prepare(data), model=client.model, client=client,
                          cache=SceneCache(tmp_path), use_cache=False)
    assert client.calls == [] and res.scene == scene and not res.tiled


def test_replay_makes_no_call_and_gives_the_same_scene(tmp_path):
    data = image_bytes()
    first = fb.run_fallback(dense_scene(), data, prepare(data), model="claude-haiku-5-5", client=FakeClient(),
                            cache=SceneCache(tmp_path), use_cache=False)
    stored = {(r["kind"], tuple(r["box"])): r["raw_text"] for r in first.replies}
    again = fb.run_fallback(dense_scene(), data, prepare(data), model="claude-haiku-5-5", client=None,
                            cache=SceneCache(tmp_path / "empty"), replay=lambda k, b: stored.get((k, tuple(b))))
    assert again.scene == first.scene and again.cost_usd == 0.0


def test_the_cache_answers_a_second_time(tmp_path):
    data = image_bytes()
    fb.run_fallback(dense_scene(), data, prepare(data), model="claude-haiku-5-5", client=FakeClient(),
                    cache=SceneCache(tmp_path), use_cache=False)
    client = FakeClient()
    res = fb.run_fallback(dense_scene(), data, prepare(data), model="claude-haiku-5-5", client=client,
                          cache=SceneCache(tmp_path), use_cache=True)
    assert client.calls == [] and res.cost_usd == 0.0 and res.tiles_added == 1


def test_a_failed_tile_or_crop_is_skipped(tmp_path):
    from vqa.llm.client import LLMRefusal

    class Refuses(FakeClient):
        def json_reply(self, **kw):
            self.calls.append(kw)
            raise LLMRefusal("no")

    data = image_bytes()
    res = fb.run_fallback(dense_scene(), data, prepare(data), model="claude-haiku-5-5", client=Refuses(),
                          cache=SceneCache(tmp_path), use_cache=False)
    assert res.scene == dense_scene() and sum("call failed" in i for i in res.issues) == 5


# ---------------------------------------------------------------- leakage guard


def test_the_request_depends_on_image_bytes_and_pass1_output_only(tmp_path):
    data = image_bytes()
    (tmp_path / "train_1_3.jpg").write_bytes(data)
    (tmp_path / "renamed.jpg").write_bytes(data)
    requests = []
    for name in ("train_1_3.jpg", "renamed.jpg"):
        b = (tmp_path / name).read_bytes()
        c = FakeClient()
        fb.run_fallback(dense_scene(), b, prepare(b), model=c.model, client=c,
                        cache=SceneCache(tmp_path / f"cache_{name}"), use_cache=False)
        requests.append(json.dumps(c.calls, sort_keys=True, default=str))
    assert requests[0] == requests[1]
    assert "train_1_3" not in requests[0] and "renamed" not in requests[0]


def test_run_fallback_takes_no_path_or_id():
    import inspect
    params = set(inspect.signature(fb.run_fallback).parameters)
    assert not params & {"image_path", "path", "image_id", "scene_id", "split", "name"}


# ---------------------------------------------------------------- prompts v4-tile and v4-crop


@pytest.mark.parametrize("version", ["v4-tile", "v4-crop"])
def test_fallback_prompts_hold_the_catalog_and_train_examples_only(version):
    d = sp.PROMPTS_DIR / version
    assert {"spec.md", "config.yaml", "examples.jsonl", "pictograms.yaml"} <= {p.name for p in d.iterdir()}
    system = sp.system_prompt(version)
    assert "P.127 | " in system and "# Sign catalog" in system
    for ex in sp.examples(version):
        assert ex["image"].startswith("train_")
    for p in d.iterdir():
        if p.is_file():
            t = p.read_text(encoding="utf-8")
            assert "public_test" not in t and "private_test" not in t
    assert sp.prompt_id(version).startswith(f"scene/{version}@")
    assert sp.user_text(version) != sp.user_text("v4")


def test_fallback_prompts_use_v4s_pictogram_rows():
    import yaml
    rows = lambda v: yaml.safe_load((sp.PROMPTS_DIR / v / "pictograms.yaml").read_text())["rows"]  # noqa: E731
    assert rows("v4-tile") == rows("v4") == rows("v4-crop")


def test_v4_tile_is_the_v4_spec_plus_the_tile_note():
    v4 = (sp.PROMPTS_DIR / "v4" / "spec.md").read_text(encoding="utf-8")
    tile = (sp.PROMPTS_DIR / "v4-tile" / "spec.md").read_text(encoding="utf-8")
    note = tile.replace(v4.split("# What counts as a sign")[0], "", 1)
    assert tile.startswith(v4.split("# What counts as a sign")[0])
    assert note.startswith("# This image is one part of a larger photo")
    assert tile.endswith(v4.split("# What counts as a sign")[1])


def test_the_crop_example_is_a_valid_crop_reply():
    from vqa.kb import load_catalog
    for ex in sp.examples("v4-crop"):
        r = fb.parse_crop(ex["output"], load_catalog())
        assert r.code != "UNKNOWN" and r.raw_code is None


# ---------------------------------------------------------------- frozen for checkpoint 2 (2026-11-16)

import hashlib  # noqa: E402

V4_TILE_SHA256 = {   # frozen after set-T development, before public_dev checkpoint 2
    "spec.md": "d9eb38db227c3b9bec497774e7ced2afc832e76f242332174218a74a619d1c11",
    "config.yaml": "26d51b4b7589145be3226bfde20c78e87e284aa2db1bb7f3a92612be6e65ac44",
    "examples.jsonl": "def4618eb96f35256472f5f7f35f6543622fa1b4e125471ab8fb69b45016eb6d",
    "pictograms.yaml": "040bfd12008a84863fcb733d7509ea3b0aeb851dcc7a448feb054a3ab2fb202b",
}
V4_CROP_SHA256 = {
    "spec.md": "d2fbec7247166134e9277717a36bd02ca3e8a3a91e896a709adecd7a52f2eaa4",
    "config.yaml": "8a58a28e347934b0c3161636f2284893b5c8a36de465c15f47969b5bbae41a5f",
    "examples.jsonl": "cd6e0aa50aa00e25ff9b48ccc908642cede6982894c481556645a41e4269f270",
    "pictograms.yaml": "2ca9fbc243e4b0366eb281dbc83ed63352c2d5ad76959231da5357a6559f0527",
}


@pytest.mark.parametrize("version,pins,pid", [("v4-tile", V4_TILE_SHA256, "scene/v4-tile@a052a9fc72f7"),
                                              ("v4-crop", V4_CROP_SHA256, "scene/v4-crop@30e2d18b84d9")])
def test_fallback_prompt_files_and_ids_are_frozen(version, pins, pid):
    d = sp.PROMPTS_DIR / version
    for name, digest in pins.items():
        assert hashlib.sha256((d / name).read_bytes()).hexdigest() == digest, f"{version}/{name} changed"
    assert sp.prompt_id(version) == pid


def test_the_combining_rule_is_frozen():
    assert fb.CHOSEN_POLICY == "rules"
    assert fb.FallbackConfig().policy == fb.CHOSEN_POLICY
    assert (fb.DENSE_MIN_SIGNS, fb.TILE_GRID, fb.TILE_OVERLAP, fb.DEDUP_IOU) == (5, 2, 0.20, 0.30)
    assert (fb.CROP_MARGIN, fb.CROP_MIN_SHORT, fb.CROP_UPSCALE_SHORT) == \
        ({"left": 0.5, "top": 0.5, "right": 0.5, "bottom": 1.0}, 128, 384)


# ---------------------------------------------------------------- one retry on bad JSON (D4; owner, 2026-11-16)


def bad_json(raw, cost=0.002):
    from vqa.llm.client import LLMBadJSON
    e = LLMBadJSON("the reply must be only a JSON object (optionally in a ```json fence), not prose")
    e.raw_text, e.cost_usd = raw, cost
    return e


class FlakyClient(FakeClient):
    """Crops: the first attempt is prose; the retry is good unless `retry_fails`."""

    def __init__(self, retry_fails=False):
        super().__init__()
        self.retry_fails = retry_fails

    def json_reply(self, **kw):
        if kw["purpose"].startswith("scene crop"):
            self.calls.append(kw)
            if kw.get("extra_messages") is None:
                raise bad_json('Looking at the crop, this is a no-motorbikes sign. {"code": "P.104"}')
            if self.retry_fails:
                raise bad_json("Still prose, sorry.")
            data = {"code": "P.104", "confidence": "high"}
            return SimpleNamespace(data=data, raw_text=json.dumps(data), cost_usd=0.001,
                                   usage={"output_tokens": 9}, request_id="r2")
        return super().json_reply(**kw)


def sparse_unsure():
    return SceneGraph(scene_id="x", signs=[sign("s1", code="UNKNOWN", conf="low", rank=1,
                                                box=(100, 110, 130, 140))])


def test_a_bad_json_crop_is_retried_with_only_the_error(tmp_path):
    from vqa.perception.wire import PLACEHOLDER
    data = image_bytes()
    c = FlakyClient()
    res = fb.run_fallback(sparse_unsure(), data, prepare(data), model=c.model, client=c,
                          cache=SceneCache(tmp_path), use_cache=False)
    first, retry = c.calls
    assert first.get("extra_messages") is None and retry["purpose"] == "scene crop retry"
    assistant, user = retry["extra_messages"]
    assert assistant == {"role": "assistant", "content": PLACEHOLDER}             # the reply is not echoed
    assert "not prose" in user["content"] and "no-motorbikes" not in user["content"]
    assert res.scene.signs[0].code == "P.104"                                     # the retry's reading
    failed = [r for r in res.replies if r.get("failed")]
    assert len(failed) == 1 and "no-motorbikes" in failed[0]["raw_text"] and failed[0]["attempt"] == 1
    assert any("retried" in i and "no-motorbikes" in i for i in res.issues)
    assert res.cost_usd == pytest.approx(0.002 + 0.001)


def test_a_crop_whose_retry_fails_too_is_skipped_with_both_replies_kept(tmp_path):
    data = image_bytes()
    c = FlakyClient(retry_fails=True)
    res = fb.run_fallback(sparse_unsure(), data, prepare(data), model=c.model, client=c,
                          cache=SceneCache(tmp_path), use_cache=False)
    assert len(c.calls) == 2 and res.scene == sparse_unsure()
    assert [r["raw_text"] for r in res.replies if r.get("failed")] == \
        ['Looking at the crop, this is a no-motorbikes sign. {"code": "P.104"}', "Still prose, sorry."]
    assert any("after the retry); skipped" in i and "Still prose" in i for i in res.issues)
    img = prepare(data)
    cb = fb.crop_box(fb._box_on_original(sparse_unsure().signs[0], img), W, H)
    effort = sp.effort_for(c.model, "v4-crop")
    assert SceneCache(tmp_path).get_region(img.sha256, c.model, effort, sp.prompt_id("v4-crop"), cb) is None


def test_a_bad_json_tile_is_retried_too(tmp_path):
    class FlakyTiles(FakeClient):
        def json_reply(self, **kw):
            if kw["purpose"] == "scene tile" and not any(c["purpose"] == "scene tile" for c in self.calls):
                self.calls.append(kw)
                raise bad_json("Here are the signs I see: ...")
            return super().json_reply(**kw)

    data = image_bytes()
    c = FlakyTiles()
    res = fb.run_fallback(dense_scene(), data, prepare(data), model=c.model, client=c,
                          cache=SceneCache(tmp_path), use_cache=False)
    purposes = [x["purpose"] for x in c.calls]
    assert purposes.count("scene tile retry") == 1 and purposes.count("scene tile") == 4
    assert res.tiles_added == 0 or res.tiled                                       # the retry's tile reply is used


def test_a_retried_reply_is_cached_and_a_cache_hit_makes_no_call(tmp_path):
    data = image_bytes()
    fb.run_fallback(sparse_unsure(), data, prepare(data), model="claude-haiku-5-5", client=FlakyClient(),
                    cache=SceneCache(tmp_path), use_cache=False)
    c = FlakyClient()
    res = fb.run_fallback(sparse_unsure(), data, prepare(data), model="claude-haiku-5-5", client=c,
                          cache=SceneCache(tmp_path), use_cache=True)
    assert c.calls == [] and res.cost_usd == 0.0 and res.scene.signs[0].code == "P.104"
    assert res.replies[0]["cache_hit"] is True


def test_with_the_cache_only_regions_without_a_usable_reply_are_paid(tmp_path):
    data = image_bytes()
    scene = SceneGraph(scene_id="x", signs=[sign("s1", code="UNKNOWN", conf="low", rank=1, box=(100, 110, 130, 140)),
                                            sign("s2", code="UNKNOWN", conf="low", rank=2, box=(500, 300, 530, 330))])

    class FirstFails(FakeClient):            # s1 is cropped first: its call and its retry fail
        def json_reply(self, **kw):
            self.calls.append(kw)
            if len(self.calls) <= 2:
                raise bad_json("prose")
            data = {"code": "P.104", "confidence": "high"}
            return SimpleNamespace(data=data, raw_text=json.dumps(data), cost_usd=0.001, usage={}, request_id="r")

    first = fb.run_fallback(scene, data, prepare(data), model="claude-haiku-5-5", client=FirstFails(),
                            cache=SceneCache(tmp_path), use_cache=False)
    assert [s.code for s in first.scene.signs] == ["UNKNOWN", "P.104"]
    c = FakeClient()
    again = fb.run_fallback(scene, data, prepare(data), model="claude-haiku-5-5", client=c,
                            cache=SceneCache(tmp_path), use_cache=True)
    assert len(c.calls) == 1                                                       # only s1's crop is paid
    assert [s.code for s in again.scene.signs] == ["P.104", "P.104"]
