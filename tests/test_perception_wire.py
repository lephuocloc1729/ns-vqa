"""vqa/perception/wire.py: scene-call replies to SceneGraph, checked against the
catalog and the schema enums. Replies are hand-written, modelled on train scenes."""

import pytest

from vqa.perception.wire import resolve_code, to_scene
from vqa.kb import load_catalog
from vqa.schemas import PlateKind, Shape, VehicleClass


def reply(*signs, **top):
    return {"signs": list(signs), **top}


def sign(**kw):
    s = {"code": "P.127", "value": 50, "unit": "km/h", "shape": "circle", "border": "red",
         "background": "white", "rank": 1, "side": "right", "confidence": "high"}
    s.update(kw)
    return s


def test_a_good_reply_becomes_a_scene_graph():
    r = to_scene(reply(
        sign(plates=[{"kind": "time", "text": "6h-22h", "time_windows": [{"start": "06:00", "end": "22:00"}]}]),
        sign(code="P.123a", value=None, unit=None, rank=2, box=[10, 20, 60, 70]),
        road={"type": "urban", "lanes": 3, "intersection_ahead": False},
        vehicles=[{"class": "truck", "lane": 2, "action": "overtake", "target": "motorbike"}]), "scene-a")
    assert r.ok and r.errors == [] and r.dropped == [] and r.raw_codes == {}
    s1, s2 = r.scene.signs
    assert (s1.id, s1.code, s1.value, s1.shape) == ("s1", "P.127", 50, Shape.circle)
    assert s1.plates[0].kind == PlateKind.time and s1.plates[0].time_windows[0].start == "06:00"
    assert s2.position.rank_top_down == 2 and s2.position.box == (10, 20, 60, 70)
    assert r.scene.road.lanes == 3
    assert r.scene.vehicles[0].cls == VehicleClass.truck and r.scene.vehicles[0].id == "v1"


@pytest.mark.parametrize("code, kept", [
    ("W.207c", "W.207c"),                                  # a variant, kept as written
    ("W.207", "W.207(a,b,c,d,e,f,g,h,i,k,l)"),             # a stem of one row -> the row code
    ("R.302a", "R.302a"),
    ("UNKNOWN", "UNKNOWN"),
])
def test_codes_resolve_through_the_catalog(code, kept):
    assert resolve_code(code, load_catalog()) == (kept, None)
    r = to_scene(reply(sign(code=code, value=None, unit=None)), "x")
    assert r.ok and r.scene.signs[0].code == kept
    if kept != "UNKNOWN":
        assert load_catalog().has(kept) or load_catalog().get(kept)


@pytest.mark.parametrize("code, msg", [
    ("P.999", "unknown sign code"), ("LOCAL", "unknown sign code"), ("", "missing"),
    ("W.221", "several catalog rows"), (None, "missing"),
])
def test_invalid_codes_are_errors_in_strict_mode(code, msg):
    r = to_scene(reply(sign(code=code)), "x")
    assert r.scene is None and any(msg in e for e in r.errors)


def test_invalid_code_becomes_unknown_in_final_mode_with_the_raw_reading_kept():
    r = to_scene(reply(sign(), sign(code="P.999", rank=2)), "x", final=True)
    assert r.ok and [s.code for s in r.scene.signs] == ["P.127", "UNKNOWN"]
    assert r.raw_codes == {"s2": "P.999"}
    assert "P.999" not in r.scene.model_dump_json()        # the raw reading stays out of the scene
    assert r.scene.signs[1].shape == Shape.circle           # the look is kept


def test_bad_enum_values_are_errors_then_dropped():
    bad = reply(sign(shape="hexagon", border="dark"))
    strict = to_scene(bad, "x")
    assert strict.scene is None and any("shape" in e for e in strict.errors) \
        and any("border" in e for e in strict.errors)
    final = to_scene(bad, "x", final=True)
    s = final.scene.signs[0]
    assert s.shape is None and s.border is None and s.code == "P.127"
    assert any("shape dropped" in d for d in final.dropped)


def test_bad_plate_and_vehicle_are_dropped_in_final_mode():
    raw = reply(sign(plates=[{"kind": "sticker"}, {"kind": "time", "text": "6-22",
                                                     "time_windows": [{"start": "06:00", "end": "22:00"}]}]),
                vehicles=[{"class": "spaceship"}, {"class": "car", "action": "park"}])
    assert to_scene(raw, "x").scene is None
    r = to_scene(raw, "x", final=True)
    assert len(r.scene.signs[0].plates) == 1 and [v.cls.value for v in r.scene.vehicles] == ["car"]
    assert any("plate dropped" in d for d in r.dropped) and any("vehicle dropped" in d for d in r.dropped)


def test_bare_vehicle_class_names_are_accepted():
    r = to_scene(reply(sign(code="P.106a", value=None, unit=None,
                            plates=[{"kind": "exception", "vehicles": ["car", "coach"]}],
                            lanes=[{"lane": 1, "vehicles": ["truck"], "max_speed": 60}])), "x")
    assert r.ok
    assert [v.cls.value for v in r.scene.signs[0].plates[0].vehicles] == ["car", "coach"]
    assert r.scene.signs[0].lanes[0].vehicles[0].cls == VehicleClass.truck


def test_alternative_reading_and_unknown_fields():
    r = to_scene(reply(sign(confidence="low", alt={"code": "P.127b", "value": 60})), "x")
    assert r.ok and r.scene.signs[0].alternatives[0].code == "P.127b"
    assert to_scene(reply(sign(notes="mờ")), "x").scene is None          # unknown field: an error
    assert to_scene(reply(sign(notes="mờ")), "x", final=True).ok          # ... dropped in final mode


def test_cross_field_rules_from_the_schema_apply():
    groups = [{"vehicles": ["truck"], "time_windows": [{"start": "06:00", "end": "09:00"}]}]
    raw = reply(sign(code="P.106a", value=None, unit=None, rules=groups,
                     plates=[{"kind": "time", "time_windows": [{"start": "06:00", "end": "22:00"}]}]))
    assert to_scene(raw, "x").scene is None


def test_the_reply_must_be_an_object_with_a_sign_list():
    assert to_scene([1, 2], "x").errors == ["the reply must be a JSON object"]
    assert to_scene({"signs": "P.127"}, "x").errors == ["signs must be a list"]
    assert to_scene({}, "x").ok and to_scene({}, "x").scene.signs == []
