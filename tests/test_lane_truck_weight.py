"""Post-benchmark fix (owner, 2026-11-21): a weight on a truck in a lane sign's rows is the truck's
permitted payload, not its gross mass. QCVN 41 D.14: "ghi trị số khối lượng chuyên chở cho phép
của xe tải lên thân xe trong hình vẽ của biển (Ví dụ: "<3,5t")". Perception records "3,5t" on a
lane-board truck as gross_t; on R.412c and R.415a (catalog `lane_truck_weight: load_t`) it is read
as load_t. Hand-made scenes modelled on R.415a lane boards; no API call."""

from __future__ import annotations

import pytest

from vqa.kb import load_catalog
from vqa.reasoning.engine import Engine
from vqa.reasoning.facts import _lane_vehicles
from vqa.schemas import (Condition, LanesFor, LaneSpec, Permitted, Position, Road, SceneGraph, Sign, Vehicle,
                         VehicleClass, VehicleSpec, Verdict)


@pytest.fixture(scope="module")
def engine():
    return Engine(reading_policy="higher_confidence")


def truck_under(t, attr="gross_t"):
    return VehicleSpec(cls=VehicleClass.truck, conditions=[Condition(attr=attr, op="lt", value=t)])


def board(code="R.415a", attr="gross_t"):
    return Sign(id="s1", code=code, confidence="high", shape="rectangle", border="none", background="blue",
                position=Position(rank_top_down=1, side="right"),
                lanes=[LaneSpec(lane=1, vehicles=[VehicleSpec(cls=VehicleClass.passenger_car)]),
                       LaneSpec(lane=2, vehicles=[VehicleSpec(cls=VehicleClass.passenger_car), truck_under(3.5, attr)])])


def scene(*signs):
    return SceneGraph(scene_id="x", signs=list(signs), road=Road(), vehicles=[])


def truck(**kw):
    return Vehicle(cls=VehicleClass.truck, **kw)


def test_the_catalog_reads_lane_truck_weights_as_payload_on_r412c_and_r415a():
    cat = load_catalog()
    assert cat.get("R.415a").effect.lane_truck_weight == "load_t"
    assert cat.get("R.412c").effect.lane_truck_weight == "load_t"
    assert cat.get("R.412a").effect.lane_truck_weight is None      # only signs whose lanes carry truck weights


def test_a_gross_condition_on_a_lane_board_truck_becomes_a_payload_condition():
    entry = load_catalog().get("R.415a")
    out = _lane_vehicles([truck_under(3.5), VehicleSpec(cls=VehicleClass.car)], entry)
    assert [c.attr.value for c in out[0].conditions] == ["load_t"] and out[0].conditions[0].value == 3.5
    assert out[1].cls is VehicleClass.car and out[1].conditions == []
    # a sign without the field keeps what perception read
    assert _lane_vehicles([truck_under(3.5)], None)[0].conditions[0].attr.value == "gross_t"


def test_a_truck_with_a_3t_payload_may_use_the_under_3_5t_lane(engine):
    """Before the fix the board's "<3,5t" was a gross-mass limit: a 3 t payload says the gross mass
    is over 3 t, so the lane was unknown. As a payload limit, 3 t < 3.5 t: lane 2 is open."""
    a = engine.answer(scene(board()), LanesFor(vehicle=truck(load_t=3)))
    per = {p["lane"]: p["verdict"] for p in a.value["per_lane"]}
    assert per == {1: "no", 2: "yes"}


def test_a_truck_with_a_5t_payload_may_not(engine):
    a = engine.answer(scene(board()), LanesFor(vehicle=truck(load_t=5)))
    per = {p["lane"]: p["verdict"] for p in a.value["per_lane"]}
    assert per[2] == "no"


def test_the_payload_reading_matches_a_board_read_as_payload(engine):
    """The board read with gross_t now answers as the same board read with load_t."""
    for kw in ({"load_t": 3}, {"load_t": 5}, {"load_gt": 4}):
        g = engine.answer(scene(board(attr="gross_t")), Permitted(action="enter", vehicle=truck(**kw), lane=2))
        l = engine.answer(scene(board(attr="load_t")), Permitted(action="enter", vehicle=truck(**kw), lane=2))
        assert g.verdict == l.verdict, kw
    assert engine.answer(scene(board()), Permitted(action="enter", vehicle=truck(load_t=3), lane=2)).verdict \
        is Verdict.yes
