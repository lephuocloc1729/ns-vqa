"""Procedure step 5 (owner, 2026-11-16): the freeze record and the holdout run's guards.
Fake SDK and hand-made images; no API call and no dataset file."""

from __future__ import annotations

import json

from pathlib import Path

import pytest

import eval.e2e_holdout as eh
import eval.freeze as fz
import vqa.pipeline as pl
from tests.test_e2e_eval import CLEAN, QS, SCENE_REPLY, _e2e_sdk, fake_set  # noqa: F401
from vqa.perception import fallback as sfb


# ---------------------------------------------------------------- the record

def test_the_current_defaults_and_prompt_pins_equal_the_freeze_record():
    assert fz.check() == [], "the live configuration differs from eval/frozen_phase4.json"


def test_the_record_is_the_approved_configuration():
    rec = fz.load()
    pc, p = rec["pipeline_config"], rec["prompts"]
    assert (pc["perception_model"], pc["scene_version"], pc["scene_fallback"]) == ("claude-haiku-5-5", "v4", True)
    assert (pc["parser_version"], pc["writer_version"], pc["answer_fallback_version"]) == ("v6", "v3", "v2")
    assert rec["scene_fallback"]["chosen_policy"] == sfb.CHOSEN_POLICY == "crop_always"
    assert rec["scene_fallback"]["drop_own_alt_on_agree"] is True
    assert p["answer"]["id"] == "answer/v3@7d0f2b8ddf1f" and p["answer_fallback"]["id"] == "answer_fallback/v2@8678a19681a9"
    assert p["judge"]["id"] == "judge/v1@7c500c35df27" and p["scene"]["id"] == "scene/v4@153536ec5975"
    assert {k for k in p} == {"scene", "scene_tile", "scene_crop", "parser", "answer", "answer_fallback", "judge"}
    assert all(len(v["sha256"]) == 64 and v["id"].endswith(v["sha256"][:12]) for v in p.values())


def test_the_pipeline_calls_the_models_the_record_names(tmp_path):
    rec = fz.load()["prompts"]
    pipe = pl.Pipeline(pl.PipelineConfig(cache_dir=tmp_path, cache_only=True), sdk=object())
    assert pipe.parser.llm.model == rec["parser"]["model"] and pipe.parser.effort == rec["parser"]["effort"]
    assert pipe.writer.llm.model == rec["answer"]["model"] and pipe.writer.effort == rec["answer"]["effort"]
    assert pipe.fallback.llm.model == rec["answer_fallback"]["model"]
    assert pipe.writer.prompt_id == rec["answer"]["id"] and pipe.fallback.prompt_id == rec["answer_fallback"]["id"]


def test_a_changed_setting_shows_in_the_check(tmp_path):
    rec = fz.load()
    rec["prompts"]["answer"]["sha256"] = "0" * 64
    rec["scene_fallback"]["drop_own_alt_on_agree"] = False
    p = tmp_path / "frozen.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    d = fz.check(p)
    assert any(x.startswith("prompts.answer.sha256") for x in d)
    assert any(x.startswith("scene_fallback.drop_own_alt_on_agree") for x in d)
    with pytest.raises(SystemExit, match="not frozen"):
        fz.check(tmp_path / "missing.json")


def test_the_run_specific_fields_are_left_out():
    assert set(fz.RUN_SPECIFIC) == {"cache_dir", "cache_only", "max_spend"}
    assert not set(fz.RUN_SPECIFIC) & set(fz.live()["pipeline_config"])


# ---------------------------------------------------------------- the holdout guards

def _run(fake_set, **kw):
    sdk = _e2e_sdk()
    sdk.replies["perception"] = [SCENE_REPLY, SCENE_REPLY]
    args = dict(confirm_frozen=True, sdk=sdk, questions=QS, out_dir=fake_set / "agg",
                image_path=lambda i: fake_set / f"{i}.jpg", sentinel=fake_set / "sentinel.json", git=CLEAN)
    args.update(kw)
    return eh.run_holdout(1.0, perception_model="claude-haiku-5-5", **args), sdk


def test_a_dirty_tree_is_refused(fake_set):
    dirty = lambda: {"commit": "c0ffee", "clean": False, "dirty": [" M vqa/pipeline.py"]}  # noqa: E731
    with pytest.raises(SystemExit, match="not clean"):
        _run(fake_set, git=dirty)
    assert not (fake_set / "sentinel.json").exists()


def test_a_configuration_that_differs_from_the_record_is_refused(fake_set):
    rec = fz.load()
    rec["prompts"]["answer_fallback"]["id"] = "answer_fallback/v1@dd75b41f09cd"
    p = fake_set / "frozen.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(SystemExit, match="differs from the freeze record"):
        _run(fake_set, frozen=p)
    with pytest.raises(SystemExit, match="differs from the freeze record"):
        eh.guards("claude-sonnet-5-5", out_dir=fake_set / "agg", sentinel=fake_set / "s.json", git=CLEAN)


def test_it_runs_once(fake_set):
    out, _ = _run(fake_set)
    mark = json.loads((fake_set / "sentinel.json").read_text())
    assert mark["status"] == "finished" and mark["report"] == out.name and mark["git_commit"] == "c0ffee"
    with pytest.raises(SystemExit, match="already run"):
        _run(fake_set)
    (fake_set / "sentinel.json").unlink()                       # the aggregate file alone also blocks it
    with pytest.raises(SystemExit, match="aggregate file already exists"):
        _run(fake_set)


def test_the_sentinel_is_written_before_the_first_call(fake_set):
    class Boom(Exception):
        pass

    sdk = _e2e_sdk()

    def fail(**kw):
        assert json.loads((fake_set / "sentinel.json").read_text())["status"] == "started"
        raise Boom

    sdk.create = fail
    with pytest.raises(Boom):
        _run(fake_set, sdk=sdk)
    with pytest.raises(SystemExit, match="already run"):           # a stopped run still counts
        _run(fake_set)


def test_the_report_records_the_commit_the_frozen_config_and_the_prompt_ids(fake_set):
    out, _ = _run(fake_set)
    rep = json.loads(out.read_text())
    assert rep["git_commit"] == "c0ffee" and rep["frozen_config"] == json.loads(json.dumps(fz.live(), default=str))
    assert rep["prompt_ids"]["answer"] == "answer/v3@7d0f2b8ddf1f" and set(rep["prompt_ids"]) == set(fz.live()["prompts"])


def test_the_sentinel_is_a_committed_path_not_in_the_runs_folder():
    assert eh.SENTINEL.parent.name == "eval" and "runs" not in eh.SENTINEL.parts


def test_the_default_image_resolver_reads_the_public_test_image_folder(tmp_path, monkeypatch):
    """The first holdout start stopped here (owner, 2026-11-16): gold_signs.image_path
    knows only train and public_dev, so the default resolver raised before any call."""
    monkeypatch.setattr(eh.gs, "PUBLIC_IMAGES", tmp_path)
    (tmp_path / "public_test_9_9.jpg").write_bytes(b"x")
    assert eh.image_file("public_test_9_9") == tmp_path / "public_test_9_9.jpg"
    with pytest.raises(FileNotFoundError):
        eh.image_file("public_test_0_0")


def test_the_holdout_runs_with_the_default_resolver(fake_set, monkeypatch):
    monkeypatch.setattr(eh.gs, "PUBLIC_IMAGES", fake_set)
    out, sdk = _run(fake_set, image_path=None)
    assert json.loads(out.read_text())["questions"] == 2 and "perception" in sdk.created


def test_post_freeze_switches_default_to_the_frozen_behaviour():
    """Phase 4.5: `answer_fallback` is left out of the freeze comparison; its default
    (on) is the frozen phase-4 behaviour, and the private and holdout runs never set it."""
    assert fz.POST_FREEZE_SWITCHES == {"answer_fallback": True, "guide_reading": False, "reading_policy": "all"}
    assert pl.PipelineConfig().answer_fallback is True and pl.PipelineConfig().guide_reading is False
    # phase 4.6 D1: the reading policy defaults to the behaviour both records froze ("all": uncertain)
    assert pl.PipelineConfig().reading_policy == "all"
    assert "reading_policy" not in fz.live(profile="phase45")["pipeline_config"]
    assert fz.live(profile="phase45")["excluded_switches"] == ["answer_fallback"]
    assert "answer_fallback" not in fz.live()["pipeline_config"] and "answer_fallback" not in fz.RUN_SPECIFIC
    import eval.e2e_private as ep
    src = open(ep.__file__, encoding="utf-8").read()
    assert "answer_fallback" not in src                     # the private run keeps the default (on)



# ---------------------------------------------------------------- B5: the phase-4.5 record (owner, 2026-11-17)

def test_the_phase45_record_matches_and_names_its_parts():
    assert fz.check(fz.FROZEN_PHASE45) == []
    rec = fz.load(fz.FROZEN_PHASE45)
    pc = rec["pipeline_config"]
    assert rec["profile"] == "phase45" and (pc["scene_version"], pc["parser_version"], pc["guide_reading"]) == ("v5", "v9", True)
    assert (pc["writer_version"], pc["answer_fallback_version"]) == ("v3", "v2") and "answer_fallback" not in pc
    sf = rec["scene_fallback"]
    assert sf["chosen_policy"] == "crop_always" and sf["drop_own_alt_on_agree"] is True
    assert set(rec["prompts"]) == {"scene", "scene_tile", "scene_crop", "guide", "parser", "answer", "answer_fallback", "judge"}
    assert rec["prompts"]["scene_tile"]["id"].startswith("scene/v5-tile@") and rec["prompts"]["guide"]["on"] is True
    assert all(len(p["sha256"]) == 64 for p in rec["prompts"].values())


def test_the_phase4_record_is_unchanged_by_the_profiles():
    assert fz.check(fz.FROZEN) == [] and "profile" not in fz.load(fz.FROZEN)
    assert fz.pipeline_config("phase4") == pl.PipelineConfig()


def test_a_freeze_record_is_written_once(tmp_path):
    p = tmp_path / "x.json"
    fz.write(p, "phase45")
    with pytest.raises(SystemExit, match="written once"):
        fz.write(p, "phase45")


# ---------------------------------------------------------------- phase 4.7 record (owner, 2026-11-18)

def test_the_phase47_record_matches_and_names_its_parts(tmp_path):
    # phase 4.8 (owner, option 1): engine hash checked at the freeze commit 4ad9137 (tests/freeze_at.py)
    from tests.freeze_at import phase47_record_file
    assert fz.check(phase47_record_file(tmp_path)) == []
    rec = fz.load(fz.FROZEN_PHASE47)
    pc = rec["pipeline_config"]
    assert rec["profile"] == "phase47" and "answer_fallback" not in pc
    assert (pc["scene_version"], pc["parser_version"], pc["guide_reading"], pc["reading_policy"]) == \
        ("v5", "v14", True, "higher_confidence")
    assert (pc["writer_version"], pc["answer_fallback_version"]) == ("v3", "v2")
    assert rec["v6_fields_off"] == ["signals"] and rec["engine_code"]["sha256"]
    assert rec["prompts"]["scene_tile"]["id"].startswith("scene/v5-tile@")
    assert rec["prompts"]["scene_crop"]["id"].startswith("scene/v5-crop@")
    assert rec["prompts"]["parser"]["id"].startswith("parser/v14@") and rec["prompts"]["guide"]["on"] is True


def test_the_phase47_record_is_written_once(tmp_path):
    p = tmp_path / "frozen.json"
    fz.write(p, "phase47")
    with pytest.raises(SystemExit, match="written once"):
        fz.write(p, "phase47")


def test_the_phase48_record_matches_and_names_its_parts():
    """Phase 4.8 (owner, 2026-11-18): scene v5 + guide reading, parser v16, policy A, signals off, the
    engine switches (several_signs on, confusable_pairs off), and the engine-code hash. Phase 4.8c: the
    hash is checked at freeze commit f8bcb67 (tests/freeze_at.py)."""
    from tests.freeze_at import phase48_record_file
    import tempfile
    assert fz.check(phase48_record_file(Path(tempfile.mkdtemp()))) == []
    rec = fz.load(fz.FROZEN_PHASE48)
    pc = rec["pipeline_config"]
    assert rec["profile"] == "phase48" and "answer_fallback" not in pc
    assert (pc["scene_version"], pc["parser_version"], pc["guide_reading"], pc["reading_policy"]) == \
        ("v5", "v16", True, "higher_confidence")
    assert rec["prompts"]["parser"]["id"] == "parser/v16@b296b65cb7cb"
    assert rec["v6_fields_off"] == ["signals"] and rec["engine_code"]["sha256"]
    assert rec["engine_switches"] == {"confusable_pairs": False, "several_signs": True}


def test_the_phase48_record_is_written_once(tmp_path):
    p = tmp_path / "frozen.json"
    fz.write(p, "phase48")
    with pytest.raises(SystemExit, match="written once"):
        fz.write(p, "phase48")


def test_phase49_pins_the_owner_approved_v17_configuration():
    assert fz.check(fz.FROZEN_PHASE49) == []
    rec = fz.load(fz.FROZEN_PHASE49)
    assert rec["pipeline_config"]["parser_version"] == "v17"
    assert rec["pipeline_config"]["reading_policy"] == "higher_confidence"
    assert rec["v6_fields_off"] == ["signals"]
    assert rec["engine_switches"] == {
        "several_signs": True, "confusable_pairs": False,
        "sign_charts": True, "sign_chart_signs": 20,
        "one_sign_g1": True, "asked_only": True, "stated_exceptions": False,
    }
    assert rec["engine_code"] == fz.code_hash()


def test_phase50_is_phase49_without_the_scene_rerun():
    assert fz.check(fz.FROZEN_PHASE50) == []
    rec, old = fz.load(fz.FROZEN_PHASE50), fz.load(fz.FROZEN_PHASE49)
    assert rec["pipeline_config"] == {**old["pipeline_config"], "scene_rerun": False}
    assert rec["prompts"] == old["prompts"] and rec["engine_switches"] == old["engine_switches"]
    assert rec["engine_code"] == fz.code_hash()
    assert fz.pipeline_config("phase50").scene_rerun is False and fz.pipeline_config("phase49").scene_rerun is True
