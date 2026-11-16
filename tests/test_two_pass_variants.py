"""The two free variants of the two-pass trial (eval/two_pass_variants.py): trial minus
UNKNOWN, the hybrid, and the engine-only answer comparison. Hand-made scenes; no API call."""

from __future__ import annotations

from types import SimpleNamespace

import eval.two_pass_variants as tv
from vqa.kb import load_catalog
from vqa.schemas import Position, SceneGraph, Sign

CAT = load_catalog()


def S(sid, code, box=None, rank=None, side="right", conf="high"):
    return Sign(id=sid, code=code, confidence=conf, shape="circle", border="red", background="white",
                position=Position(rank_top_down=rank, side=side, box=box))


def test_minus_unknown_drops_only_unknown_signs():
    sc = SceneGraph(scene_id="x", signs=[S("s1", "P.104"), S("s2", "UNKNOWN"), S("s3", "P.123a")])
    out, dropped = tv.minus_unknown(sc)
    assert [s.code for s in out.signs] == ["P.104", "P.123a"] and dropped == [1]


def test_hybrid_adds_only_new_regions_with_a_real_code_and_keeps_frozen_codes():
    frozen = SceneGraph(scene_id="x", signs=[S("s1", "P.104", (100, 100, 150, 150), 1),
                                             S("s2", "P.130", (400, 300, 450, 350), 2)])
    trial = SceneGraph(scene_id="x", signs=[S("s1", "P.106a", (102, 101, 151, 149), 1),   # same region: frozen code kept
                                            S("s2", "UNKNOWN", (600, 50, 640, 90), 2),    # no real code
                                            S("s3", "P.123a", (200, 10, 240, 50), 3, side="left")])
    out, st = tv.hybrid(frozen, trial, 800, CAT)
    assert [s.code for s in out.signs] == ["P.104", "P.130", "P.123a"]
    assert st == {"skipped_overlap": 1, "skipped_unknown": 1, "added": 1}
    added = out.signs[2]
    assert added.position.rank_top_down == 1 and added.position.side.value == "left"   # top-most; trial's side
    assert [s.position.rank_top_down for s in out.signs[:2]] == [2, 3]                   # frozen shifted down
    assert added.id == "s3" and len({s.id for s in out.signs}) == 3


def test_hybrid_does_not_add_a_second_copy_of_an_unboxed_frozen_sign():
    frozen = SceneGraph(scene_id="x", signs=[S("s1", "P.104", None, 1)])
    trial = SceneGraph(scene_id="x", signs=[S("s1", "P.104", (0, 0, 9, 9), 1)])
    out, st = tv.hybrid(frozen, trial, 100, CAT)
    assert len(out.signs) == 1 and st["skipped_same_row_as_unboxed_frozen"] == 1


def test_hybrid_with_nothing_new_is_the_frozen_scene():
    frozen = SceneGraph(scene_id="x", signs=[S("s1", "P.104", (0, 0, 50, 50), 1)])
    trial = SceneGraph(scene_id="x", signs=[S("s1", "P.104", (1, 1, 49, 49), 1)])
    assert tv.hybrid(frozen, trial, 100, CAT)[0] == frozen


class FakeEngine:
    """Answers by the first sign's code: P.104 -> no, P.123a -> yes, UNKNOWN -> unknown with an
    uncertain sign, none -> unknown."""

    def answer(self, scene, program):
        from vqa.schemas import Answer, Verdict
        code = scene.signs[0].code if scene.signs else None
        if code == "P.104":
            return Answer(verdict=Verdict.no)
        if code == "P.123a":
            return Answer(verdict=Verdict.yes)
        if code == "UNKNOWN":
            return Answer(verdict=Verdict.unknown, uncertain_signs=["s1"])
        return Answer(verdict=Verdict.unknown)


def Q(i, qtype="Yes/No", answer="Sai", stored=None):
    return {"id": f"q{i}", "image_id": f"i{i}", "question_type": qtype, "answer": answer,
            "parse_status": "ok", "program": SimpleNamespace(), "stored": stored}


def scenes(**codes):
    return {k: SceneGraph(scene_id=k, signs=[S("s1", c)] if c else []) for k, c in codes.items()}


def test_compare_answers_grades_yes_no_and_counts_moves():
    qs = [Q(1, answer="Sai", stored={"correct": 1.0}),       # no -> yes: Yes/No, graded: -1
          Q(2, answer="Đúng", stored={"correct": 0.0}),      # no -> unreadable: to fallback, ungraded
          Q(3, "Natural QA", "x", {"correct": 1.0}),         # unchanged: keeps its grade
          Q(4, "Natural QA", "x", {"correct": 0.5})]         # no -> yes: Natural QA, ungraded
    base = scenes(i1="P.104", i2="P.104", i3="P.104", i4="P.104")
    var = scenes(i1="P.123a", i2="UNKNOWN", i3="P.104", i4="P.123a")
    r = tv.compare_answers(qs, base, var, FakeEngine())
    assert r["questions"] == 4 and r["unchanged"] == 1 and r["changed"] == 3
    assert r["to_fallback"] == 1 and r["to_fallback_by_trigger"] == {"unreadable_sign": 1}
    assert r["rules_decision_changed"] == 2 and r["graded"] == 1 and r["net_correct_graded"] == -1.0
    assert r["ungraded"] == 2
    assert r["net_correct_bounds"] == [-1.0 - 0.0 - 0.5, -1.0 + 1.0 + 0.5]
    assert abs(r["net_correct_estimate"] - (-1.0 + (tv.FALLBACK_ACC - 0.0) + (tv.RULES_ACC - 0.5))) < 1e-9


def test_without_a_stored_grade_a_yes_no_baseline_is_graded_from_its_verdict():
    qs = [Q(1, answer="Đúng")]
    r = tv.compare_answers(qs, scenes(i1="P.104"), scenes(i1="P.123a"), FakeEngine())
    assert r["net_correct_graded"] == 1.0 and r["ungraded"] == 0


def test_lost_real_signs_splits_the_dropped_unknowns():
    gold = {"i": {"signs": [
        {"readable": True, "code": "P.104", "shape": "circle", "border": "red", "background": "white",
         "position": {"rank_top_down": 1, "side": "right"}},
        {"readable": False, "code": "P.123a", "shape": "circle", "border": "red", "background": "white",
         "position": {"rank_top_down": 2, "side": "left"}}]}}
    trial = {"i": SceneGraph(scene_id="i", signs=[S("s1", "UNKNOWN", rank=1, side="right"),
                                                  S("s2", "UNKNOWN", rank=2, side="left"),
                                                  S("s3", "UNKNOWN", rank=3, side="center")])}
    trial["i"].signs[2].shape = None
    r = tv.lost_real_signs(trial, gold, CAT)
    assert r["dropped"] == 3 and r["matched_real_gold_sign"] == 1 and r["matched_excluded_gold"] == 1
