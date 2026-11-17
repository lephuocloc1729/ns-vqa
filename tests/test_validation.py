"""Phase 4.5 (owner, 2026-11-16): the validation set (eval/make_validation_split.py) and the
aggregate-only, fallback-off validation runs (eval/e2e_validation.py). The split tests read
ids only; the run tests use a fake SDK and hand-made images; no API call."""

from __future__ import annotations

import json

import pytest

import eval.coverage_analysis as ca
import eval.e2e_validation as ev
import eval.freeze as fz
import eval.make_validation_split as mvs
from eval import gold_signs as gs
from eval import parser_eval as pev
from eval import perception_eval as pe
from tests.test_e2e_eval import CLEAN, QS, SCENE_REPLY, RoutedSDK, _e2e_sdk, fake_set  # noqa: F401

SPLIT = json.loads(mvs.OUT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the split (ids only)

def test_the_committed_split_is_what_the_builder_makes():
    """The builder draws the same set. `named_in_repo` (how many train images the repo names)
    is a report count that grows when new train ids are named outside the pool (phase-4.5
    parser v7 few-shots); the pool itself and the draw must not move. Phase 4.6: so is
    `duplicate_of_an_excluded_train_image`, which drops when an image it counted becomes named
    (v10 few-shots): the two report counts overlap, the pool is the same."""
    built = mvs.build()
    report_counts = ("named_in_repo", "duplicate_of_an_excluded_train_image")
    strip = lambda d: {**d, "pool": {**d["pool"], "excluded_images": {  # noqa: E731
        k: v for k, v in d["pool"]["excluded_images"].items() if k not in report_counts}}}
    assert strip(built) == strip(SPLIT)
    assert built["pool"]["images"] == SPLIT["pool"]["images"] and built["pool"]["questions"] == SPLIT["pool"]["questions"]
    assert SPLIT["seed"] == 20261116 and 100 <= SPLIT["counts"]["questions"] <= 120


def test_the_split_is_whole_images_of_untouched_train_questions():
    rows = json.loads(gs.TRAIN_QA.read_text(encoding="utf-8"))
    img_of = {q["id"]: q["image_id"] for q in rows}
    imgs = set(SPLIT["images"])
    assert {img_of[q] for q in SPLIT["questions"]} == imgs
    assert set(SPLIT["questions"]) == {q["id"] for q in rows if q["image_id"] in imgs}     # every question of an image


def test_the_split_avoids_set_t_gold_and_anything_named_in_the_repo():
    imgs, qids = set(SPLIT["images"]), set(SPLIT["questions"])
    assert not imgs & set(gs.set_t_images())
    assert not imgs & {r["image_id"] for r in pe.gold_rows().values()}
    assert not qids & {g["id"] for g in pev.load_gold()}
    named_imgs, named_q = ca.mentioned()
    assert not imgs & named_imgs and not qids & named_q


def test_no_split_image_shares_a_duplicate_group_with_public_or_private():
    dup = json.loads((ca.ROOT / "data" / "splits" / "duplicates.json").read_text(encoding="utf-8"))
    for g in dup["groups"]:
        tr = {i["image_id"] for i in g["images"] if i["split"] == "train"}
        if tr & set(SPLIT["images"]):
            assert not {"public", "private"} & set(g["splits"]), g


def test_no_few_shot_or_prompt_example_names_a_split_question():
    for p in list((ca.ROOT / "prompts").rglob("*.jsonl")) + list((ca.ROOT / "eval" / "prompts").rglob("*")):
        if p.is_file():
            t = p.read_text(encoding="utf-8", errors="ignore")
            assert not any(f'"{q}"' in t for q in SPLIT["questions"]), p
            assert not any(i in t for i in SPLIT["images"]), p


def test_yes_no_images_are_drawn_first():
    qs = [{"id": f"q{k}", "image_id": f"i{k}", "question_type": "Yes/No" if k < 3 else "Natural QA"}
          for k in range(10)]
    drawn = mvs.draw([f"i{k}" for k in range(10)], qs, seed=1, target=4)
    assert set(drawn[:3]) == {"i0", "i1", "i2"} and len(drawn) == 4


def test_the_split_is_close_to_the_private_yes_no_share():
    t = SPLIT["counts"]["question_types"]
    assert 0.40 <= t["Yes/No"] / SPLIT["counts"]["questions"] <= 0.55


# ---------------------------------------------------------------- the runs

def _run(fake_set, **kw):
    sdk = kw.pop("sdk", None) or _e2e_sdk()
    sdk.replies.setdefault("perception", [SCENE_REPLY, SCENE_REPLY])
    args = dict(confirm_frozen=True, sdk=sdk, questions=[dict(q, id=f"train_secret_{i}") for i, q in enumerate(QS)],
                out_dir=fake_set / "agg", image_path=lambda i: fake_set / f"{i}.jpg",
                sentinel_path=fake_set / "validation_ran_baseline.json", git=CLEAN)
    args.update(kw)
    return ev.run_validation("baseline", 1.0, **args), sdk


def test_it_refuses_without_the_freeze_and_with_an_unknown_label():
    with pytest.raises(SystemExit, match="confirm-frozen"):
        ev.run_validation("baseline", 1.0)
    with pytest.raises(SystemExit, match="--label"):
        ev.run_validation("public_holdout", 1.0, confirm_frozen=True)


def test_the_labels_name_their_freeze_records():
    assert ev.LABELS["baseline"] == fz.FROZEN and ev.LABELS["final"].name == "frozen_phase45.json"


def test_a_dirty_tree_is_refused_before_the_sentinel(fake_set):
    dirty = lambda: {"commit": "c0ffee", "clean": False, "dirty": [" M vqa/pipeline.py"]}  # noqa: E731
    with pytest.raises(SystemExit, match="not clean"):
        _run(fake_set, git=dirty)
    assert not (fake_set / "validation_ran_baseline.json").exists()


def test_a_configuration_that_differs_from_the_record_is_refused(fake_set):
    rec = fz.load()
    rec["prompts"]["answer"]["id"] = "answer/v2@0000000000"
    p = fake_set / "frozen.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(SystemExit, match="differs from the freeze record"):
        _run(fake_set, frozen=p)


def test_a_missing_image_is_refused_before_the_sentinel(fake_set):
    with pytest.raises(SystemExit, match="1 validation images have no file"):
        _run(fake_set, image_path=lambda i: fake_set / ("missing.jpg" if i.endswith("_2") else f"{i}.jpg"))
    assert not (fake_set / "validation_ran_baseline.json").exists()


def test_it_runs_once(fake_set):
    out, _ = _run(fake_set)
    mark = json.loads((fake_set / "validation_ran_baseline.json").read_text())
    assert mark["status"] == "finished" and mark["report"] == out.name and mark["split_sha256"]
    with pytest.raises(SystemExit, match="already run"):
        _run(fake_set)
    (fake_set / "validation_ran_baseline.json").unlink()
    with pytest.raises(SystemExit, match="aggregate file already exists"):
        _run(fake_set)


def test_the_sentinel_is_written_before_the_first_call(fake_set):
    class Boom(Exception):
        pass

    sdk = _e2e_sdk()

    def fail(**kw):
        assert json.loads((fake_set / "validation_ran_baseline.json").read_text())["status"] == "started"
        raise Boom

    sdk.create = fail
    with pytest.raises(Boom):
        _run(fake_set, sdk=sdk)
    with pytest.raises(SystemExit, match="already run"):
        _run(fake_set)


def test_it_writes_only_an_aggregate_with_the_three_figures(fake_set, capsys):
    out, sdk = _run(fake_set)
    assert [p.name for p in (fake_set / "agg").iterdir()] == [out.name]
    text, printed = out.read_text(), capsys.readouterr().out
    for i, q in enumerate(QS):
        for v in (f"train_secret_{i}", q["question"], q["answer"], q["image_id"]):
            assert v not in text and v not in printed
    rep = json.loads(text)
    assert rep["questions"] == 2 and rep["decided"] == 2 and rep["decided_coverage"] == 1.0
    assert rep["accuracy_on_decided"] == 1.0 and rep["overall_non_decided_wrong"] == 1.0
    assert "decided_coverage_ci95" in rep and rep["targets"]["decided_coverage"]["floor"] == 0.70
    assert "fallback" not in sdk.created and "perception" in sdk.created


def test_a_non_decided_question_counts_wrong_with_no_fallback_or_judge_call(fake_set):
    sdk = RoutedSDK(parser=[{"program": None, "out_of_scope": True, "out_of_scope_reason": "guide sign"}] * 2)
    out, sdk = _run(fake_set, sdk=sdk)
    rep = json.loads(out.read_text())
    assert rep["decided"] == 0 and rep["overall_non_decided_wrong"] == 0.0
    assert rep["accuracy_on_decided"] is None and rep["not_decided_by_cause"] == {"out_of_scope": 2}
    assert "fallback" not in sdk.created and "judge" not in sdk.created and "writer" not in sdk.created


def test_the_targets_are_the_plans():
    assert ev.TARGETS == {"decided_coverage": {"target": 0.80, "floor": 0.70},
                          "accuracy_on_decided": {"target": 0.88, "floor": 0.85},
                          "overall_non_decided_wrong": {"target": 0.70, "floor": 0.60}}


def test_the_estimate_uses_counts_only():
    e = ev.estimate()
    assert e["questions"] == SPLIT["counts"]["questions"] and e["images"] == SPLIT["counts"]["images"]
    assert e["lines_usd"]["answer fallback"] == 0.0 and e["total_usd"] > 0



# ---------------------------------------------------------------- B5: the final label (owner, 2026-11-17)

def _run_final(fake_set, **kw):
    sdk = kw.pop("sdk", None) or _e2e_sdk()
    sdk.replies.setdefault("perception", [SCENE_REPLY, SCENE_REPLY])
    args = dict(confirm_frozen=True, sdk=sdk, questions=[dict(q, id=f"train_secret_{i}") for i, q in enumerate(QS)],
                out_dir=fake_set / "agg", image_path=lambda i: fake_set / f"{i}.jpg",
                sentinel_path=fake_set / "validation_ran_final.json", git=CLEAN)
    args.update(kw)
    return ev.run_validation("final", 1.0, **args), sdk


def test_the_final_run_uses_the_phase45_profile(fake_set):
    out, sdk = _run_final(fake_set)
    rep = json.loads(out.read_text())
    assert rep["frozen_record"] == "frozen_phase45.json" and rep["profile"] == "phase45"
    assert rep["prompt_ids"]["parser"].startswith("parser/v9@") and rep["prompt_ids"]["scene"].startswith("scene/v5@")
    assert rep["prompt_ids"]["guide"].startswith("scene/v5-guide@") and "fallback" not in sdk.created


@pytest.mark.parametrize("field, value", [
    (("pipeline_config", "parser_version"), "v8"), (("pipeline_config", "guide_reading"), False),
    (("prompts", "scene", "sha256"), "0" * 64), (("profile",), "phase4")])
def test_a_final_mismatch_is_refused_before_the_sentinel(fake_set, field, value):
    rec = fz.load(fz.FROZEN_PHASE45)
    node = rec
    for k in field[:-1]:
        node = node[k]
    node[field[-1]] = value
    p = fake_set / "frozen45.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(SystemExit, match="differs from the freeze record"):
        _run_final(fake_set, frozen=p)
    assert not (fake_set / "validation_ran_final.json").exists()


# ---------------------------------------------------------------- phase 4.6: final2 (owner, 2026-11-17, D4)

def _run_final2(fake_set, **kw):
    sdk = kw.pop("sdk", None) or _e2e_sdk()
    sdk.replies.setdefault("perception", [SCENE_REPLY, SCENE_REPLY])
    args = dict(confirm_frozen=True, sdk=sdk, questions=[dict(q, id=f"train_secret_{i}") for i, q in enumerate(QS)],
                out_dir=fake_set / "agg", image_path=lambda i: fake_set / f"{i}.jpg",
                sentinel_path=fake_set / "validation_ran_final2.json", git=CLEAN)
    args.update(kw)
    return ev.run_validation("final2", 1.0, **args), sdk


def test_final2_has_its_own_record_and_sentinel():
    assert ev.LABELS["final2"] == fz.FROZEN_PHASE46 and ev.sentinel("final2").name == "validation_ran_final2.json"
    assert ev.sentinel("final2") != ev.sentinel("final")
    rec = fz.load(fz.FROZEN_PHASE46)
    assert rec["profile"] == "phase46" and rec["pipeline_config"]["parser_version"] == "v11"
    assert rec["pipeline_config"]["reading_policy"] == "higher_confidence" and rec["engine_code"]["files"] > 0
    assert fz.check(fz.FROZEN_PHASE46) == [] and fz.check(fz.FROZEN_PHASE45) == [] and fz.check(fz.FROZEN) == []


def test_the_final2_run_uses_the_phase46_profile(fake_set):
    out, sdk = _run_final2(fake_set)
    rep = json.loads(out.read_text())
    assert rep["frozen_record"] == "frozen_phase46.json" and rep["profile"] == "phase46"
    assert rep["what"].startswith("phase 4.6 validation, final2")
    assert rep["prompt_ids"]["parser"].startswith("parser/v11@") and "fallback" not in sdk.created
    assert rep["frozen_config"]["pipeline_config"]["reading_policy"] == "higher_confidence"
    mark = json.loads((fake_set / "validation_ran_final2.json").read_text())
    assert mark["status"] == "finished" and mark["frozen_record"] == "frozen_phase46.json"


def test_an_engine_code_change_is_refused_before_the_final2_sentinel(fake_set):
    rec = fz.load(fz.FROZEN_PHASE46)
    rec["engine_code"]["sha256"] = "0" * 64
    p = fake_set / "frozen46.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(SystemExit, match="differs from the freeze record"):
        _run_final2(fake_set, frozen=p)
    assert not (fake_set / "validation_ran_final2.json").exists()
