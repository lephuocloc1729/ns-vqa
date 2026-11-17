"""The two-pass perception trial (owner, 2026-11-16; eval/two_pass_trial.py): coarse types
and candidate lists, the escape, find parsing, crop geometry, plate assignment, assembly
through the unchanged wire conversion and verification, the retry, the run file, and the
pins. Hand-made scenes and synthetic images; a fake client answers; no API call."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

import eval.two_pass_trial as tp
from vqa.kb import load_catalog
from vqa.llm.client import LLMBadJSON
from vqa.perception.image import prepare
from vqa.perception.wire import PLACEHOLDER

CAT = load_catalog()


# ---------------------------------------------------------------- coarse types and candidate lists

@pytest.mark.parametrize("look, expected", [
    (("circle", "red", "white"), "red_circle"),
    (("circle", "red", "blue"), "red_circle"),          # no stopping: red rim, blue face
    (("circle", "none", "red"), "red_circle"),          # no entry: red face
    (("circle", "none", "blue"), "blue_circle"),
    (("circle", "black", "white"), "other"),            # end of restriction
    (("triangle", "red", "yellow"), "yellow_triangle"),
    (("rectangle", "none", "red"), "red_rect"),
    (("rectangle", "red", "white"), "red_rect"),
    (("rectangle", "white", "blue"), "blue_rect"),
    (("square", "none", "green"), "green_rect"),
    (("rectangle", "black", "white"), "white_rect"),
    (("rectangle", "black", "yellow"), "white_rect"),
    (("octagon", "white", "red"), "other"),
    (("diamond", "white", "yellow"), "other"),
    ((None, None, None), "other"),
])
def test_coarse_of(look, expected):
    assert tp.coarse_of(*look) == expected


def test_the_candidate_lists_partition_the_catalog():
    c = tp.candidates(CAT)
    assert set(c) == set(tp.COARSE_TYPES)
    codes = [x for v in c.values() for x in v]
    assert sorted(codes) == sorted(s.code for s in CAT.signs if not s.listed_from) and len(codes) == len(set(codes))


def test_auxiliary_rows_are_the_plate_list():
    assert tp.candidates(CAT)["plate"] == [s.code for s in CAT.signs if s.category == "auxiliary" and not s.listed_from]
    assert "P.127" in tp.candidates(CAT)["red_circle"] and "W.207a" not in tp.candidates(CAT)["red_circle"]


def test_in_list_resolves_variants_to_their_row():
    fam = next(s.code for s in CAT.signs if "(" in s.code)            # a family row such as W.207(a,b,...)
    t = tp.row_type(CAT.get(fam))
    stem = fam.split("(")[0]
    variant = stem + fam.split("(")[1].split(",")[0].strip(")")
    assert tp.in_list(variant, t, CAT) and not tp.in_list(variant, "plate", CAT)
    assert not tp.in_list("UNKNOWN", t, CAT)


def test_the_read_prompt_lists_every_type_and_the_full_catalog():
    text = tp.system_prompt(tp.READ)
    for t in tp.COARSE_TYPES:
        assert f"## {t}" in text
    for s in CAT.signs:
        if not s.listed_from:                       # rows added in phase 4.5 postdate the pinned trial
            assert f"{s.code} | {s.name_vi}" in text
    assert "escape" in text and "UNKNOWN" in text


def test_the_find_prompt_carries_no_catalog_and_asks_for_no_codes():
    text = tp.system_prompt(tp.FIND)
    assert "P.127 |" not in text and "Sign catalog" not in text
    out = json.loads(text.split("Example (", 1)[1].split("):\n", 1)[1].splitlines()[0])
    assert all("code" not in o for o in out["objects"])


# ---------------------------------------------------------------- find parsing

def test_parse_find_keeps_valid_objects_and_clips_boxes():
    data = {"objects": [{"type": "red_circle", "shape": "circle", "border": "red", "background": "white",
                         "box": [-5, 10, 60, 70], "rank": 1, "side": "right"},
                        {"type": "plate", "box": [0, 72, 60, 300]}],
            "road": {"type": "urban"}, "vehicles": []}
    objs, road, veh, errors = tp.parse_find(data, (200, 100))
    assert not errors and [o.oid for o in objs] == ["c1", "c2"]
    assert objs[0].box == (0, 10, 60, 70) and objs[1].box == (0, 72, 60, 100)
    assert objs[0].look == {"shape": "circle", "border": "red", "background": "white", "rank": 1, "side": "right"}
    assert road == {"type": "urban"}


@pytest.mark.parametrize("obj, msg", [
    ({"type": "red_square", "box": [0, 0, 5, 5]}, "type must be one of"),
    ({"type": "plate", "box": [0, 0, 5]}, "box must be"),
    ({"type": "plate", "box": [5, 5, 5, 9]}, "x1 > x0"),
    ({"type": "plate", "box": [300, 0, 400, 9]}, "inside the image"),
])
def test_parse_find_errors_are_for_the_retry(obj, msg):
    assert any(msg in e for e in tp.parse_find({"objects": [obj]}, (200, 100))[3])
    assert tp.parse_find({"signs": []}, (9, 9))[3] == ["`objects` must be a list"]


# ---------------------------------------------------------------- crop geometry

def test_pad_box_adds_20_percent_each_side():
    assert tp.pad_box((100, 100, 200, 150), 1000, 1000, 0.2, 10) == (80, 90, 220, 160)


def test_pad_box_clips_to_the_image():
    assert tp.pad_box((0, 0, 100, 100), 110, 105, 0.2, 10) == (0, 0, 110, 105)


def test_a_tiny_box_grows_to_the_minimum_around_its_centre_and_stays_inside():
    x0, y0, x1, y1 = tp.pad_box((500, 500, 510, 504), 1000, 1000, 0.2, 48)
    assert x1 - x0 >= 48 and y1 - y0 >= 48 and abs((x0 + x1) / 2 - 505) <= 1
    x0, y0, x1, y1 = tp.pad_box((0, 0, 4, 4), 1000, 1000, 0.2, 48)
    assert (x0, y0) == (0, 0) and x1 >= 48 and y1 >= 48


def test_crop_scale_enlarges_small_and_shrinks_large():
    assert tp.crop_scale(64, 128, 256, 768) == 4.0
    assert tp.crop_scale(1000, 2000, 256, 768) == pytest.approx(768 / 2000)
    assert tp.crop_scale(300, 500, 256, 768) == 1.0


def _jpeg(w=800, h=600):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (90, 120, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def test_crop_boxes_map_the_sent_box_onto_the_original():
    data = _jpeg(3136, 1000)                          # sent at half size (long edge 1568)
    img = prepare(data)
    assert img.scale == pytest.approx(0.5)
    found = [tp.Found("c1", "red_circle", (100, 100, 150, 150))]
    pad = tp.config(tp.READ)["crop"]["pad"]
    x0, y0, x1, y1 = tp.crop_boxes(found, img)["c1"]
    assert (x0, y0, x1, y1) == (200 - 20, 200 - 20, 300 + 20, 300 + 20) and pad == 0.20


# ---------------------------------------------------------------- read parsing and plates

def test_every_crop_needs_an_entry():
    got, errors = tp.parse_read({"crops": [{"id": "c1", "code": "P.104"}, {"id": "c9"}]}, ["c1", "c2"])
    assert set(got) == {"c1"} and errors == ["no entry for crops c2; every crop needs one"]
    assert tp.parse_read({"signs": []}, ["c1"])[1]


def F(oid, t, box, **look):
    return tp.Found(oid, t, box, look)


def test_a_plate_goes_to_the_sign_the_read_pass_names():
    found = [F("c1", "red_circle", (0, 0, 50, 50)), F("c2", "red_circle", (100, 0, 150, 50)),
             F("c3", "plate", (0, 55, 50, 70))]
    owner, how = tp.assign_plates(found, {"c3": {"id": "c3", "belongs_to": "c2"}})
    assert owner == {"c3": "c2"} and how["model"] == 1


def test_without_a_valid_owner_a_plate_goes_to_the_sign_directly_above():
    found = [F("c1", "red_circle", (0, 0, 50, 50)), F("c2", "red_circle", (100, 0, 150, 50)),
             F("c3", "red_circle", (100, 200, 150, 250)), F("c4", "plate", (105, 55, 145, 70))]
    for reading in ({}, {"c4": {"belongs_to": "c4"}}, {"c4": {"belongs_to": "c99"}}):
        owner, how = tp.assign_plates(found, reading)
        assert owner == {"c4": "c2"} and how["geometry"] == 1


def test_a_plate_with_nothing_above_goes_to_the_nearest_sign_and_with_no_sign_nowhere():
    found = [F("c1", "red_circle", (300, 300, 350, 350)), F("c2", "plate", (0, 0, 40, 20))]
    assert tp.assign_plates(found, {})[0] == {"c2": "c1"}
    owner, how = tp.assign_plates([F("c1", "plate", (0, 0, 9, 9))], {})
    assert owner == {} and how["no_sign"] == 1


# ---------------------------------------------------------------- assembly, conversion, verification

def _scene_from(found, readings):
    wire, stats = tp.assemble(found, readings, {"type": "urban"}, [], CAT)
    from vqa.perception.verify import verify
    from vqa.perception.wire import to_scene
    w = to_scene(wire, "abc", final=True, catalog=CAT)
    return verify(w.scene, CAT)[0], stats, wire


def test_assembly_goes_through_the_unchanged_conversion():
    found = [F("c1", "red_circle", (10, 10, 60, 60), shape="circle", border="red", background="white",
               rank=1, side="right"),
             F("c2", "plate", (10, 62, 60, 80))]
    readings = {"c1": {"id": "c1", "code": "P.127", "confidence": "high", "value": 50, "unit": "km/h"},
                "c2": {"id": "c2", "plate": {"kind": "time", "text": "6h-22h",
                                             "time_windows": [{"start": "06:00", "end": "22:00"}]},
                       "belongs_to": "c1"}}
    scene, stats, wire = _scene_from(found, readings)
    [s] = scene.signs
    assert s.code == "P.127" and s.value == 50 and s.position.side.value == "right"
    assert len(s.plates) == 1 and s.plates[0].kind.value == "time"
    assert tuple(s.position.box) == (10, 10, 60, 60)
    assert stats["signs"] == 1 and stats["plates"] == 1 and stats["plates_by_model"] == 1 and stats.get("escape", 0) == 0


def test_an_unread_crop_is_unknown_and_low():
    scene, stats, _ = _scene_from([F("c1", "blue_circle", (0, 0, 9, 9), shape="circle")], {})
    assert scene.signs[0].code == "UNKNOWN" and scene.signs[0].confidence.value == "low" and stats["unread"] == 1


def test_the_escape_is_counted_from_the_code():
    found = [F("c1", "blue_rect", (0, 0, 9, 9)), F("c2", "red_circle", (20, 0, 29, 9))]
    readings = {"c1": {"id": "c1", "code": "P.104", "confidence": "high", "escape": True},
                "c2": {"id": "c2", "code": "P.104", "confidence": "high"}}
    _, stats, _ = _scene_from(found, readings)
    assert stats["escape"] == 1 and stats["escape_flagged"] == 1


def test_an_invalid_code_becomes_unknown_with_the_raw_reading_kept():
    replies = [{"pass": "find", "raw_text": json.dumps({"objects": [{"type": "red_circle", "box": [0, 0, 9, 9]}]})},
               {"pass": "read", "raw_text": json.dumps({"crops": [{"id": "c1", "code": "P.999", "confidence": "high"}]})}]
    scene, issues, raw_codes, _ = tp.build_scene(replies, "abc", (100, 100), CAT)
    assert scene.signs[0].code == "UNKNOWN" and raw_codes == {"s1": "P.999"}


# ---------------------------------------------------------------- the calls (fake client)

class FakeClient:
    model = "claude-haiku-5-5"
    guard = SimpleNamespace(spent=0.0)

    def __init__(self, find=None, read=None, bad_first=()):
        self.calls, self.bad_first = [], set(bad_first)
        self.find = find or {"objects": [{"type": "red_circle", "shape": "circle", "border": "red",
                                          "background": "white", "box": [100, 100, 160, 160], "rank": 1,
                                          "side": "right"},
                                         {"type": "plate", "box": [100, 165, 160, 190]}],
                             "road": {"type": "urban"}, "vehicles": []}
        self.read = read or {"crops": [{"id": "c1", "code": "P.104", "confidence": "high"},
                                       {"id": "c2", "plate": {"kind": "text", "text": "6h-22h"}, "belongs_to": "c1"}]}

    def json_reply(self, **kw):
        self.calls.append(kw)
        which = "find" if kw["purpose"].startswith("trial find") else "read"
        if which in self.bad_first and kw.get("extra_messages") is None:
            e = LLMBadJSON("the reply must be only a JSON object")
            e.raw_text, e.cost_usd = "Here you go: {", 0.0001
            raise e
        data = self.find if which == "find" else self.read
        return SimpleNamespace(data=data, raw_text=json.dumps(data), cost_usd=0.0002,
                               usage={"input_tokens": 1}, request_id=None)


@pytest.fixture
def no_pictograms(monkeypatch):
    blocks = [{"type": "text", "text": "Reference figures:"}, {"type": "text", "text": "The photo:"}]
    monkeypatch.setattr(tp.scene_prompt, "pictogram_blocks", lambda v: list(blocks))


def test_one_find_and_one_read_call_per_image_with_all_crops(no_pictograms):
    c = FakeClient()
    row = tp.perceive_trial(_jpeg(), c, CAT)
    assert [k["purpose"] for k in c.calls] == ["trial find", "trial read"]
    assert row["ok"] and row["calls"] == 2 and row["retries"] == 0
    read_user = c.calls[1]["user"]
    labels = [b["text"] for b in read_user if b["type"] == "text"]
    assert "Crop c1 (red_circle)" in labels and "Crop c2 (plate)" in labels and "The crops:" in labels
    assert sum(b["type"] == "image" for b in read_user) == 2
    assert sum(b["type"] == "image" for b in c.calls[0]["user"]) == 1          # find: the photo only
    [s] = row["scene"]["signs"]
    assert s["code"] == "P.104" and s["plates"][0]["text"] == "6h-22h"
    assert [r["pass"] for r in row["replies"]] == ["find", "read"] and row["crop_boxes"]["c1"]


def test_the_retry_sends_only_the_error(no_pictograms):
    c = FakeClient(bad_first={"find", "read"})
    row = tp.perceive_trial(_jpeg(), c, CAT)
    assert [k["purpose"] for k in c.calls] == ["trial find", "trial find retry", "trial read", "trial read retry"]
    for k in (c.calls[1], c.calls[3]):
        assert k["extra_messages"][0] == {"role": "assistant", "content": PLACEHOLDER}
        assert "Here you go" not in json.dumps(k["extra_messages"])
    assert row["ok"] and row["retries"] == 2 and row["scene"]["signs"][0]["code"] == "P.104"


def test_a_missing_crop_entry_is_retried(no_pictograms):
    c = FakeClient(read={"crops": [{"id": "c1", "code": "P.104", "confidence": "high"}]})
    row = tp.perceive_trial(_jpeg(), c, CAT)
    assert c.calls[-1]["purpose"] == "trial read retry"
    assert "no entry for crops c2" in c.calls[-1]["extra_messages"][1]["content"]
    assert row["scene"]["signs"][0]["plates"][0]["kind"] == "text"           # geometry, default kind


def test_no_objects_means_no_read_call(no_pictograms):
    c = FakeClient(find={"objects": [], "road": {}, "vehicles": []})
    row = tp.perceive_trial(_jpeg(), c, CAT)
    assert [k["purpose"] for k in c.calls] == ["trial find"] and row["scene"]["signs"] == []


def test_the_run_file_keeps_raw_replies_and_rebuilds_with_no_call(no_pictograms, tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    (tmp_path / "train_9_9.jpg").write_bytes(_jpeg())
    monkeypatch.setattr(tp, "PINNED", {v: tp.prompt_hash(v) for v in (tp.FIND, tp.READ)})
    c = FakeClient()

    class SDK:                                         # LLMClient needs an sdk; the fake client is used instead
        pass

    monkeypatch.setattr("vqa.llm.client.LLMClient", lambda **kw: c)
    out = tp.run("T", 0.1, sdk=SDK(), out_dir=tmp_path, images=[("train_9_9", "train")],
                 image_path=lambda i, s: tmp_path / f"{i}.jpg")
    head, rows = tp.pe.load_run(out)
    assert head["trial"]["find_sha256"] == tp.prompt_hash(tp.FIND) and head["label"] == "development"
    assert head["trial"]["use_cache"] is False and head["model"] == "claude-haiku-5-5"
    assert rows[0]["replies"][0]["raw_text"]
    reb = tp.rebuild(out, tmp_path / "rebuilt.jsonl")
    assert tp.pe.load_run(reb)[1][0]["scene"] == rows[0]["scene"]
    assert len(c.calls) == 2                                              # rebuild made none


def test_the_run_refuses_unpinned_prompts_and_other_sets(monkeypatch):
    monkeypatch.setattr(tp, "PINNED", {tp.FIND: "0" * 64, tp.READ: "0" * 64})
    with pytest.raises(SystemExit, match="differ from their pins"):
        tp.run("T", 0.1, sdk=object())
    with pytest.raises(SystemExit, match="--set must be"):
        tp.run("public_holdout", 0.1, sdk=object())


def test_the_trial_prompts_are_pinned():
    assert tp.check_pins() == [], "a trial prompt changed after it was pinned"


def test_the_trial_prompts_name_no_dataset_image():
    for v in (tp.FIND, tp.READ):
        for p in tp._dir(v).iterdir():
            if p.is_file():
                t = p.read_text(encoding="utf-8")
                assert "public_test" not in t and "private_test" not in t and "train_" not in t, p
        for line in (tp._dir(v) / "examples.jsonl").read_text(encoding="utf-8").splitlines():
            assert "image" not in json.loads(line)


def test_the_trial_uses_v4s_pictograms_unchanged():
    assert tp.config(tp.READ)["pictograms_from"] == "v4"
    assert "pictograms" not in tp.config(tp.FIND)


# ---------------------------------------------------------------- analysis

def G(code, **kw):
    return {"readable": True, "id": "g", "code": code, "shape": kw.pop("shape", "circle"),
            "border": kw.pop("border", "red"), "background": kw.pop("background", "white"),
            "position": {"rank_top_down": kw.pop("rank", 1), "side": kw.pop("side", "right")}, **kw}


def P(code, conf="high", **kw):
    g = G(code, **kw)
    g["confidence"] = conf
    return g


def test_classify_names_each_kind_of_error():
    gold = [G("P.104", rank=1), G("P.123a", rank=2), G("P.127", rank=3, value=50),
            G("P.106a", rank=4), G("P.125", rank=5, readable=False)]
    pred = [P("P.104", rank=1), P("P.123b", rank=2), P("P.127", rank=3, value=60), P("UNKNOWN", "low", rank=4)]
    st = tp.classify(gold, pred, CAT)
    assert st[0] == {"status": "tp"}
    assert st[1]["status"] == "wrong_confident" and st[1]["same_type"]
    assert st[2] == {"status": "tp", "value_wrong": True}
    assert st[3] == {"status": "wrong_unsure"} and st[4] is None
    assert tp.classify([G("P.104")], [], CAT) == [{"status": "miss"}]


def test_plates_compare_kinds_and_time_windows():
    tw = [{"start": "06:00", "end": "22:00"}]
    g = [G("P.104", plates=[{"kind": "time", "time_windows": tw}])]
    assert tp.classify(g, [P("P.104", plates=[{"kind": "time", "time_windows": tw, "text": "x"}])], CAT)[0] == \
        {"status": "tp", "plates_wrong": False, "plates_missing": False}
    assert tp.classify(g, [P("P.104")], CAT)[0] == {"status": "tp", "plates_wrong": True, "plates_missing": True}


def test_the_frozen_runs_are_the_checkpoint_runs():
    assert tp.FROZEN["T"] == ["T_claude-haiku-5-5_v4+fb_d1ff09db5bf4.jsonl"]
    assert len(tp.FROZEN["public_dev"]) == 3 and tp.SETS == ("T", "public_dev")
