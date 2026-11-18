"""Phase 4.7: scene v6 field measurement (eval/v6_fields.py) and the switch (kb/v6_fields_47.yaml,
Engine.v6_fields_off): a switched-off field's rules give unknown. No API call."""

from __future__ import annotations

import pytest

from eval import v6_fields as vf
from vqa.reasoning.engine import Engine, v6_fields_off_from_kb
from vqa.schemas import (LaneSpec, Permitted, Position, Road, RoadMarking, RulePermitted, SceneGraph, Sign,
                         TrafficSignal, Vehicle, Verdict)

CAR = Vehicle(**{"class": "car"})


def test_all_fields_are_on_until_measured():
    assert v6_fields_off_from_kb() == () and Engine().v6_fields_off == ()


def test_unknown_field_name_is_refused():
    with pytest.raises(ValueError):
        Engine(v6_fields_off=("lights",))


def test_switched_off_signals_give_unknown():
    red = SceneGraph(scene_id="x", signals=[TrafficSignal(colour="red")])
    q = RulePermitted(action="go_straight", at_signal=True)
    assert Engine().answer(red, q).verdict is Verdict.no
    assert Engine(v6_fields_off=("signals",)).answer(red, q).verdict is Verdict.unknown


def test_switched_off_markings_give_unknown():
    s = SceneGraph(scene_id="x", road=Road(markings=[RoadMarking(kind="center", pattern="double_solid")]))
    q = RulePermitted(maneuver="cross_center")
    assert Engine().answer(s, q).verdict is Verdict.no
    assert Engine(v6_fields_off=("markings",)).answer(s, q).verdict is Verdict.unknown


def test_switched_off_arrows_leave_r411_unmodelled():
    board = Sign(id="s1", code="R.411", confidence="high", shape="rectangle", border="none", background="blue",
                 position=Position(rank_top_down=1, side="center"),
                 lanes=[LaneSpec(lane=1, directions=["left"]), LaneSpec(lane=2, directions=["straight"])])
    s = SceneGraph(scene_id="x", road=Road(lanes=2), signs=[board])
    q = Permitted(action="turn_left", vehicle=CAR, lane=1)
    assert Engine().answer(s, q).verdict is Verdict.yes
    assert Engine(v6_fields_off=("arrows",)).answer(s, q).verdict is Verdict.unknown


def test_score_applies_the_70_percent_rule():
    labels = [{"image_id": "a", "checked": True, "signals": [{"colour": "red", "arrow": "none"}],
               "markings": [{"kind": "center", "pattern": "solid"}], "r411": []},
              {"image_id": "b", "checked": False, "signals": [], "markings": [], "r411": []}]
    rows = [{"image_id": "a", "scene": {"signals": [{"colour": "red"}, {"colour": "green"}, {"colour": "yellow"}],
                                         "road": {"markings": [{"kind": "center", "pattern": "solid"}]}, "signs": []}},
            {"image_id": "b", "scene": {"signals": [{"colour": "red"}]}}]
    r = vf.score(rows, labels)
    assert r["checked_images"] == 1
    assert r["fields"]["signals"]["precision"] == pytest.approx(1 / 3, abs=1e-3) and r["switch_off"] == ["signals"]
    assert r["fields"]["markings"]["precision"] == 1.0 and r["fields"]["markings"]["decision"] == "keep on"
    assert r["fields"]["arrows"]["precision"] is None


def test_the_sheet_lists_every_set_t_image_reviewed():
    import yaml
    from eval import gold_signs as gs
    rows = yaml.safe_load(vf.SHEET.read_text(encoding="utf-8"))["images"]
    assert [r["image_id"] for r in rows] == gs.set_t_images()
    assert all(r["checked"] for r in rows)
    assert all(r["reviewed_by"] == "owner" for r in rows)
    assert all(set(r) >= {"signals", "markings", "r411"} for r in rows)


def test_incomplete_arrows_do_not_count_as_false_positives():
    labels = [{"image_id": "a", "checked": True, "r411_complete": False, "r411": []}]
    run = [{"image_id": "a", "scene": {"signs": [{"code": "R.411", "lanes": [
        {"lane": 1, "directions": ["straight"]}]}]}}]
    result = vf.score(run, labels)
    assert result["fields"]["arrows"]["fp"] == 0
    assert result["fields"]["arrows"]["precision"] is None
    assert result["fields"]["arrows"]["skipped_incomplete"] == 1
