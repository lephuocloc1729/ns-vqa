import pytest
from pydantic import TypeAdapter, ValidationError

from vqa.reasoning.terms import Term, atom, to_prolog, vehicle_term
from vqa.schemas import Program, QueryProgram, SceneGraph, TimeWindow, Vehicle


def test_scene_graph_round_trip():
    raw = {
        "scene_id": "example_1",
        "road": {"type": "urban", "lanes": 3, "intersection_ahead": False},
        "signs": [
            {"id": "s1", "code": "P.125", "shape": "circle", "border": "red",
             "background": "white", "position": {"rank_top_down": 1, "side": "right"}},
            {"id": "s2", "code": "P.127", "value": 50, "unit": "km/h",
             "position": {"rank_top_down": 2, "side": "right", "lane": 3},
             "plates": [{"kind": "time", "text": "6h-22h",
                         "time_windows": [{"start": "06:00", "end": "22:00"}]}]},
        ],
        "vehicles": [{"id": "v1", "class": "truck", "lane": 2, "action": "overtake",
                      "target": "motorbike"}],
    }
    sg = SceneGraph.model_validate(raw)
    assert sg.sign("s2").plates[0].time_windows[0].minutes() == (360, 1320)
    assert SceneGraph.model_validate_json(sg.model_dump_json(by_alias=True)) == sg


def test_ids_must_be_unique():
    with pytest.raises(ValidationError):
        SceneGraph(scene_id="x", signs=[{"id": "a", "code": "P.101"}],
                   vehicles=[{"id": "a", "class": "car"}])


def test_bad_time_rejected():
    with pytest.raises(ValidationError):
        TimeWindow(start="6h", end="22:00")


def test_unknown_vehicle_class_rejected():
    with pytest.raises(ValidationError):
        Vehicle(**{"class": "spaceship"})


def test_program_union_parses_by_intent():
    p = TypeAdapter(Program).validate_python({
        "intent": "verify", "expect": False,
        "claim": {"intent": "permitted", "action": "turn_left",
                  "vehicle": {"class": "passenger_car"},
                  "when": {"date": "2025-09-02", "time": "08:00"}},
    })
    assert p.claim.action.value == "turn_left"
    assert p.claim.when.date.day == 2


def test_json_schemas_generate():
    # These schemas become Claude's structured-output schemas in later phases.
    assert "signs" in SceneGraph.model_json_schema()["properties"]
    qs = QueryProgram.model_json_schema()
    assert "program" in qs["properties"]


def test_prolog_term_writer_quotes():
    assert to_prolog(Term("f", atom("ok"), atom("Needs Quote"), 3.0, 2.5, None, [1, 2])) == \
        "f(ok, 'Needs Quote', 3, 2.5, unknown, [1, 2])"
    assert to_prolog(atom("it's")) == "'it\\'s'"
    assert to_prolog(vehicle_term(Vehicle(**{"class": "truck"}, load_t=3.4))) == \
        "veh(truck, [a(load_t, 3.4)])"


def test_vehicle_enum_matches_prolog_ontology(engine):
    import janus_swi as janus
    from vqa.schemas import VehicleClass

    in_prolog = {c for c in janus.query_once(
        "findall(_C, (is_a(_C, _) ; is_a(_, _C) ; _C = pedestrian), _L0), sort(_L0, L)")["L"]}
    assert in_prolog == {c.value for c in VehicleClass}
