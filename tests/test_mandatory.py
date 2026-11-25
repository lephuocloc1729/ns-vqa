"""Rule family: mandatory directions by placement (QCVN 41:2024 D.1a, art. 32),
and the similar_rudimentary class (interpretation of Law 36 art. 34(2)(e))."""

from vqa.kb import load_catalog
from vqa.reasoning import explain
from vqa.schemas import LanesFor, Permitted, Required, Verdict

from conftest import V, articles, only_for, scene, sign, spec


def required(engine, sc, action, placement=None, vehicle=None):
    return engine.answer(sc, Required(action=action, placement=placement, vehicle=vehicle))


def test_turn_right_only_after_intersection(engine):
    # "Nếu biển đặt sau nơi đường giao nhau, có bắt buộc rẽ phải ngay không?"
    sc = scene(sign("s1", "R.301b"))
    a = required(engine, sc, "turn_right", "after_intersection")
    assert a.verdict == Verdict.yes
    [d] = a.value["signs"]
    assert d["scope"] == "intersection_ahead" and d["standard"] == "after_intersection"
    assert {"32", "D.1a"} <= articles(a)
    # no placement given: the sign's standard placement (after) is used
    assert required(engine, sc, "turn_right").verdict == Verdict.yes


def test_placement_the_article_does_not_describe_is_unknown(engine):
    # D.1a only describes R.301d placed before the intersection
    sc = scene(sign("s1", "R.301d"))
    assert required(engine, sc, "turn_right", "before_intersection").verdict == Verdict.yes
    a = required(engine, sc, "turn_right", "after_intersection")
    assert a.verdict == Verdict.unknown
    assert a.value["signs"][0]["scope"] == "not_described"


def test_straight_only_scope_depends_on_placement(engine):
    sc = scene(sign("s1", "R.301a"))
    before = required(engine, sc, "go_straight", "before_intersection")
    assert before.verdict == Verdict.yes
    assert before.value["signs"][0]["scope"] == "intersection_behind"
    after = required(engine, sc, "go_straight", "after_intersection")
    assert after.value["signs"][0]["scope"] == "until_next_intersection"
    # placement unknown: both placements D.1a describes agree
    assert required(engine, sc, "go_straight").verdict == Verdict.yes


def test_placement_from_the_scene(engine):
    sc = scene(sign("s1", "R.301e", position={"placement": "before_intersection"}))
    a = required(engine, sc, "turn_left")
    assert a.verdict == Verdict.yes
    assert a.value["signs"][0]["placement"] == "before_intersection"


def test_not_required_when_other_directions_are_allowed(engine):
    sc = scene(sign("s1", "R.301f"))  # straight or right
    a = required(engine, sc, "go_straight")
    assert a.verdict == Verdict.no
    assert {r.sign_id: r.detail for r in a.reasons} == {"s1": "not_the_only_direction"}
    assert "D.1a" in articles(a)
    # R.301g also allows a U-turn (D.1a): left is not the only direction
    g = required(engine, scene(sign("s1", "R.301g")), "turn_left")
    assert g.verdict == Verdict.no
    assert g.value["signs"][0]["directions"] == ["go_straight", "turn_left", "u_turn"]


def test_vehicle_plate_limits_the_requirement(engine):
    sc = scene(sign("s1", "R.301b", plates=[only_for(spec("truck"))]))
    assert required(engine, sc, "turn_right", vehicle=V("truck")).verdict == Verdict.yes
    a = required(engine, sc, "turn_right", vehicle=V("passenger_car"))
    assert a.verdict == Verdict.no and a.reasons[0].detail == "plate_vehicle_not_covered"


def test_no_direction_sign(engine):
    a = required(engine, scene(sign("s1", "P.104")), "turn_right")
    assert a.verdict == Verdict.no
    assert a.reasons[0].detail == "not_a_direction_sign" and "B.4" in articles(a)


# ---------------------------------------------------------------- similar_rudimentary

def test_interpretation_recorded_in_catalog():
    [vi] = [v for v in load_catalog().vehicle_interpretations
            if v.cls is not None and v.cls.value == "similar_rudimentary"]
    assert (vi.source.law_id, vi.source.article_id) == ("36/2024/QH15", "34")
    assert "Interpretation" in vi.note


def test_similar_rudimentary_is_rudimentary_and_cited_as_interpretation(engine):
    # R.412g: lane for motorbikes and bicycles "kể cả các loại xe thô sơ khác"
    sc = scene(sign("s1", "R.412g", position={"lane": 2}), lanes=2)
    a = engine.answer(sc, LanesFor(vehicle=V("similar_rudimentary")))
    assert a.value["lanes"] == [1, 2]
    assert "34" in articles(a)
    goals = [n.goal for r in a.reasons if r.proof for n in explain.walk(r.proof)]
    assert any(g and g.startswith("class_interpretation(similar_rudimentary") for g in goals)


def test_similar_rudimentary_not_covered_by_cyclo_ban(engine):
    a = engine.answer(scene(sign("s1", "P.111d")),
                      Permitted(action="enter", vehicle=V("similar_rudimentary")))
    assert a.verdict == Verdict.yes and a.reasons[0].detail == "vehicle_not_covered"
    assert "34" in articles(a)
