"""Phase 4.8 (owner, 2026-11-18): the dev2 split (eval/make_dev2_split.py) and its runner
(eval/e2e_dev2.py). The split tests read ids, image ids and question types only; the run tests
use a fake SDK and hand-made images; no API call."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import eval.e2e_dev2 as e2
import eval.freeze as fz
import eval.make_dev2_split as m2
import eval.make_validation_split as mvs
from tests.test_e2e_eval import CLEAN, QS, SCENE_REPLY, _e2e_sdk, fake_set  # noqa: F401

DEV2 = json.loads(m2.OUT.read_text(encoding="utf-8"))
DEV = json.loads(mvs.DEV_OUT.read_text(encoding="utf-8"))
VAL = json.loads(mvs.OUT.read_text(encoding="utf-8"))
ROWS = m2.train_rows()


def test_the_committed_split_is_what_the_builder_makes():
    assert m2.build() == DEV2
    assert DEV2["seed"] == m2.SEED == 20261118 and DEV2["biased"] is True and DEV2["biased_note"]


def test_it_has_100_questions_stratified_by_the_working_sets_types():
    ws = m2.working_set(ROWS)
    assert DEV2["working_set"]["questions"] == len(ws) == 333
    assert DEV2["counts"]["questions"] == 100 and len(set(DEV2["questions"])) == 100
    assert DEV2["counts"]["question_types"] == m2.quotas(ws) == {"Natural QA": 70, "Yes/No": 30}
    types = {q["id"]: q["question_type"] for q in ROWS}
    assert sum(types[i] == "Yes/No" for i in DEV2["questions"]) == 30
    img = {q["id"]: q["image_id"] for q in ROWS}
    assert DEV2["images"] == sorted({img[i] for i in DEV2["questions"]})


def test_it_is_inside_the_working_set_and_shares_nothing_with_dev_or_validation():
    assert set(DEV2["questions"]) <= {q["id"] for q in m2.working_set(ROWS)}
    for other in (DEV, VAL):
        assert not set(DEV2["questions"]) & set(other["questions"])
        assert not set(DEV2["images"]) & set(other["images"])
    e2.check_disjoint()


def test_it_excludes_every_parser_few_shot_v7_to_v14_and_the_gold_v12_new_train_rows():
    fs = m2.fewshot_ids()
    assert fs and not set(DEV2["questions"]) & fs
    gold = m2.gold_train_ids()
    assert len(gold) == 6 and not set(DEV2["questions"]) & gold
    for v in m2.FEWSHOT_VERSIONS:
        rows = [json.loads(x) for x in (m2.ROOT / "prompts" / "parser" / v / "fewshot.jsonl")
                .read_text(encoding="utf-8").splitlines() if x.strip()]
        assert not {r["id"] for r in rows} & set(DEV2["questions"])


def test_selection_is_by_id_only_and_never_reads_duplicates():
    src = inspect.getsource(m2)
    assert "duplicates" not in src.replace("duplicates.json` is not read", "")
    assert "imagehash" not in src and "phash" not in src


def test_quotas_round_by_largest_remainder():
    ws = [{"question_type": "a"}] * 2 + [{"question_type": "b"}] * 1
    assert m2.quotas(ws, 100) == {"a": 67, "b": 33} and m2.quotas(ws, 10) == {"a": 7, "b": 3}


def test_the_seed_decides_the_draw():
    other = m2.build(seed=1)
    assert other["counts"]["question_types"] == DEV2["counts"]["question_types"]
    assert other["questions"] != DEV2["questions"]


def test_an_overlap_with_dev_or_validation_is_refused(tmp_path):
    for name, src in (("dev", DEV), ("validation", VAL)):
        p = tmp_path / f"dev2_{name}.json"
        p.write_text(json.dumps({"questions": [], "images": src["images"][:1]}), encoding="utf-8")
        with pytest.raises(SystemExit, match=f"overlaps the {name} set"):
            e2.check_disjoint(p)
        with pytest.raises(SystemExit, match="overlaps"):
            e2.load_questions(p)


# ---------------------------------------------------------------- the runner

def _split(tmp_path) -> Path:
    p = tmp_path / "train_dev2.json"
    p.write_text(json.dumps({"questions": [q["id"] for q in QS], "images": [q["image_id"] for q in QS],
                             "biased": True, "biased_note": "test"}), encoding="utf-8")
    return p


def test_the_runner_defaults_to_the_phase47_record():
    assert e2.FROZEN == fz.FROZEN_PHASE47 and e2.PROFILE == "phase47"
    # phase 4.8: `frozen` defaults to None, which means this record for a non-candidate run
    assert inspect.signature(e2.run).parameters["frozen"].default is None


def test_a_dev2_run_uses_the_phase47_profile_with_the_fallback_off(fake_set):
    sdk = _e2e_sdk()
    sdk.replies["perception"] = [SCENE_REPLY] * 6
    systems: dict[str, str] = {}
    create = sdk.create

    def spy(**kw):
        systems.setdefault(sdk.role(kw), "".join(b["text"] for b in kw["system"]))
        return create(**kw)
    sdk.create = spy
    from tests.freeze_at import phase47_record_file
    out = e2.run("t", 1.0, sdk=sdk, questions=QS, out_dir=fake_set / "dev2", dev2_file=_split(fake_set),
                 image_path=lambda i: fake_set / f"{i}.jpg", git=CLEAN, frozen=phase47_record_file(fake_set / "rec47"))
    head, rows = e2.ed.ee.load(out)
    assert out.name.startswith("dev2_t_") and head["kind"] == "dev2" and head["profile"] == "phase47"
    assert head["frozen_record"] == "frozen_phase47.json" and head["answer_fallback"] is False
    assert head["biased"] is True and head["split_file"] == "train_dev2.json" and head["candidate"] is None
    rec = fz.load(fz.FROZEN_PHASE47)
    assert head["prompt_ids"]["parser"] == rec["prompts"]["parser"]["id"]
    assert head["prompt_ids"]["parser"].startswith("parser/v14@")
    assert (fake_set / "dev2" / head["cache_dir"]).is_dir() and head["cache_dir"].startswith("dev2_cache_")
    assert [r["id"] for r in rows] == ["q1", "q2"] and "fallback" not in sdk.created
    assert all(r["decided"] for r in rows) and rows[0]["correct"] == 1.0
    s = e2.summary(out)
    assert s["biased"] is True and s["decided"] == 2 and set(s["by_type"]) == {"Yes/No", "Natural QA"}


def test_a_record_of_another_profile_is_refused(fake_set):
    with pytest.raises(SystemExit, match="profile 'phase46', not 'phase47'"):
        e2.run("t", 1.0, sdk=_e2e_sdk(), questions=QS, out_dir=fake_set / "dev2", dev2_file=_split(fake_set),
               frozen=fz.FROZEN_PHASE46, git=CLEAN)


def test_a_phase47_mismatch_is_refused(fake_set):
    rec = fz.load(fz.FROZEN_PHASE47)
    rec["pipeline_config"]["parser_version"] = "v13"
    p = fake_set / "frozen47.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(SystemExit, match="differs from the freeze record"):
        e2.run("t", 1.0, sdk=_e2e_sdk(), questions=QS, out_dir=fake_set / "dev2", dev2_file=_split(fake_set),
               frozen=p, git=CLEAN)


def test_a_dirty_tree_is_refused(fake_set):
    dirty = lambda: {"commit": "c", "clean": False, "dirty": [" M x"]}  # noqa: E731
    with pytest.raises(SystemExit, match="not clean"):
        e2.run("t", 1.0, sdk=_e2e_sdk(), questions=QS, out_dir=fake_set / "dev2", dev2_file=_split(fake_set),
               git=dirty)


def test_the_estimate_uses_counts_only():
    e = e2.estimate()
    assert e["questions"] == 100 and e["images"] == DEV2["counts"]["images"]
    assert e["question_types"] == {"Natural QA": 70, "Yes/No": 30}
    lo, hi = e["estimates"]["dev_phase47"]["total_usd"], e["estimates"]["all_decided"]["total_usd"]
    assert 0 < lo <= hi and e["suggested_max_spend"] >= e["estimates"]["all_decided"]["range_usd"][1]


def test_a_candidate_run_is_phase47_with_its_changes_and_records_the_switches(fake_set):
    """Phase 4.8 step 4: scene and parser versions changed; the KB switches are recorded."""
    assert e2.candidate(parser_version="v15") == {**e2.PHASE47_FIELDS, "parser_version": "v15"}
    assert e2.candidate("v7")["scene_version"] == "v7"
    sdk = _e2e_sdk()
    sdk.replies["perception"] = [SCENE_REPLY] * 6
    out = e2.run("c", 1.0, sdk=sdk, questions=QS, out_dir=fake_set / "dev2", dev2_file=_split(fake_set),
                 image_path=lambda i: fake_set / f"{i}.jpg", git=CLEAN, cand=e2.candidate(parser_version="v15"))
    head, rows = e2.ed.ee.load(out)
    assert head["candidate"]["parser_version"] == "v15" and head["frozen_record"] == "frozen_phase4.json"
    assert head["candidate_prompt_ids"]["parser"].startswith("parser/v15@")
    assert head["switches_48"]["several_signs"] is True and head["kind"] == "dev2"
