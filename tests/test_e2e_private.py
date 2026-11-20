"""Phase 5, item 1: the one private-test benchmark run (eval/e2e_private.py).
Guards as the holdout's, its own sentinel, aggregate only, the by-feature breakdown,
and the replay records (P4). Fake SDK, hand-made images and questions; no API call and
no dataset file."""

from __future__ import annotations

import json

import pytest

import eval.e2e_holdout as eh
import eval.e2e_private as ep
import eval.freeze as fz
from tests.freeze_at import phase47_record_file  # noqa: F401  (phase 4.7 record checked at 4ad9137)

from tests.test_e2e_eval import CLEAN, QS, SCENE_REPLY, _e2e_sdk, fake_set  # noqa: F401

SECRET_QS = [dict(q, id=f"private_secret_{i}", answer=f"{q['answer']} secret-gold-{i}")
             for i, q in enumerate(QS)]
# Yes/No grading maps the answer's first word, so the gold stays gradable.
TWO = {"questions": 2, "images": 2}


def _run(fake_set, **kw):
    sdk = kw.pop("sdk", None) or _e2e_sdk()
    sdk.replies["perception"] = [SCENE_REPLY, SCENE_REPLY]
    args = dict(confirm_frozen=True, sdk=sdk, questions=SECRET_QS, out_dir=fake_set / "agg",
                image_path=lambda i: fake_set / f"{i}.jpg", sentinel=fake_set / "private_ran.json",
                replay_root=fake_set / "private_run", git=CLEAN, ignored=lambda p: True, expected=TWO)
    args["frozen"] = fz.FROZEN_PHASE52
    args.update(kw)
    return ep.run_private(1.0, **args), sdk


# ---------------------------------------------------------------- guards

def test_it_refuses_without_the_freeze():
    with pytest.raises(SystemExit, match="confirm-frozen"):
        ep.run_private(1.0)


def test_a_dirty_tree_is_refused_before_the_sentinel(fake_set):
    dirty = lambda: {"commit": "c0ffee", "clean": False, "dirty": [" M vqa/pipeline.py"]}  # noqa: E731
    with pytest.raises(SystemExit, match="not clean"):
        _run(fake_set, git=dirty)
    assert not (fake_set / "private_ran.json").exists()


def test_a_configuration_that_differs_from_the_record_is_refused(fake_set):
    rec = fz.load(fz.FROZEN_PHASE52)   # phase 5.2 (owner, 2026-11-20): the private run's record
    rec["prompts"]["answer"]["id"] = "answer/v2@0000000000"
    p = fake_set / "frozen.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(SystemExit, match="differs from the freeze record"):
        _run(fake_set, frozen=p)
    assert not (fake_set / "private_ran.json").exists()


def test_the_perception_model_is_the_frozen_one():
    assert ep.frozen_perception_model() == fz.load()["pipeline_config"]["perception_model"] == "claude-haiku-5-5"


def test_it_runs_once(fake_set):
    out, _ = _run(fake_set)
    mark = json.loads((fake_set / "private_ran.json").read_text())
    assert mark["status"] == "finished" and mark["report"] == out.name and mark["git_commit"] == "c0ffee"
    with pytest.raises(SystemExit, match="already run"):
        _run(fake_set)
    (fake_set / "private_ran.json").unlink()                     # the aggregate file alone also blocks it
    with pytest.raises(SystemExit, match="aggregate file already exists"):
        _run(fake_set)


def test_the_holdout_files_do_not_block_it_and_it_does_not_block_the_holdout(fake_set):
    (fake_set / "agg").mkdir()
    (fake_set / "agg" / "holdout_aggregate_x.json").write_text("{}")
    _run(fake_set)
    assert ep.SENTINEL != eh.SENTINEL and ep.SENTINEL.name == "private_ran.json"


def test_the_sentinel_is_written_before_the_first_call(fake_set):
    class Boom(Exception):
        pass

    sdk = _e2e_sdk()

    def fail(**kw):
        assert json.loads((fake_set / "private_ran.json").read_text())["status"] == "started"
        raise Boom

    sdk.create = fail
    with pytest.raises(Boom):
        _run(fake_set, sdk=sdk)
    with pytest.raises(SystemExit, match="already run"):           # a stopped run still counts
        _run(fake_set)


def test_the_sentinel_is_a_committed_path_not_in_the_runs_folder():
    assert ep.SENTINEL.parent.name == "eval" and "runs" not in ep.SENTINEL.parts


def test_a_replay_folder_git_does_not_ignore_is_refused_before_the_sentinel(fake_set):
    with pytest.raises(SystemExit, match="does not ignore"):
        _run(fake_set, ignored=lambda p: False)
    assert not (fake_set / "private_ran.json").exists()


def test_git_ignores_the_real_replay_folder():
    assert ep.git_ignores(ep.REPLAY / "abc123" / "records.jsonl")
    assert not ep.git_ignores(ep.ROOT / "eval" / "e2e_private.py")


def test_wrong_counts_are_refused_before_the_sentinel(fake_set):
    with pytest.raises(SystemExit, match="expected 146 questions on 104 images"):
        _run(fake_set, expected=ep.EXPECTED)
    assert not (fake_set / "private_ran.json").exists()


def test_a_missing_image_is_refused_before_the_sentinel_without_naming_it(fake_set):
    def resolve(i):
        if i == "public_test_1_2":
            raise FileNotFoundError("no image file for a private question")
        return fake_set / f"{i}.jpg"

    with pytest.raises(SystemExit) as e:
        _run(fake_set, image_path=resolve)
    assert "1 of 2" in str(e.value) and "public_test_1_2" not in str(e.value)
    assert not (fake_set / "private_ran.json").exists()


def test_the_default_image_resolver_reads_the_private_image_folder(tmp_path):
    (tmp_path / "private_test_9_9.jpg").write_bytes(b"x")
    assert ep.image_file("private_test_9_9", tmp_path) == tmp_path / "private_test_9_9.jpg"
    with pytest.raises(FileNotFoundError) as e:
        ep.image_file("private_test_0_0", tmp_path)
    assert "private_test_0_0" not in str(e.value)


# ---------------------------------------------------------------- aggregate only

def test_it_writes_only_an_aggregate_file_and_prints_no_question(fake_set, capsys):
    out, sdk = _run(fake_set)
    assert [p.name for p in (fake_set / "agg").iterdir()] == [out.name]
    text, printed = out.read_text(), capsys.readouterr().out
    for q in SECRET_QS:
        for field in ("id", "question", "answer", "image_id"):
            assert q[field] not in text and q[field] not in printed
    rep = json.loads(text)
    assert rep["questions"] == 2 and rep["overall"] == 1.0
    assert rep["by_images"]["split"] == "private" and rep["by_images"]["against"] == ["public", "train"]
    assert "ci95" in rep["by_images"]["non_duplicate_images"]
    assert "perception" in sdk.created                                    # fresh perception


def test_the_report_records_the_commit_config_prompts_and_catalog_review(fake_set):
    out, _ = _run(fake_set)
    rep = json.loads(out.read_text())
    live52 = fz.live(profile="phase52")       # phase 5.2 (owner, 2026-11-20)
    assert rep["git_commit"] == "c0ffee" and rep["frozen_config"] == json.loads(json.dumps(live52, default=str))
    assert rep["prompt_ids"]["answer"] == "answer/v3@7d0f2b8ddf1f" and set(rep["prompt_ids"]) == set(live52["prompts"])
    assert rep["prompt_ids"]["parser"].startswith("parser/v18@") and "guide" in rep["prompt_ids"]
    cat = rep["catalog_review"]
    assert cat["sign_catalog.yaml"]["rows"] == sum(cat["sign_catalog.yaml"]["reviewed_by"].values())
    assert "assistant-reviewed" in cat["note"]
    assert set(rep["feature_rules"]) == set(ep.FEATURES)
    for k in ("rule_coverage", "rules_only_score", "fallback_score", "fallback_by_trigger", "faithfulness",
              "template_rate", "cost_per_question_usd", "seconds_per_question", "by_trigger", "by_feature"):
        assert k in rep, k


def test_the_by_feature_breakdown_is_counts_and_scores_only(fake_set):
    rep = json.loads(_run(fake_set)[0].read_text())
    bf = rep["by_feature"]
    assert set(bf) == set(ep.FEATURES) | {"no_feature"}
    assert bf["vehicle_class"] == {"n": 1, "score": 1.0, "strict": 1.0, "yes_no_n": 1, "rule_coverage": 1.0}
    assert bf["meaning"]["n"] == 1 and bf["meaning"]["yes_no_n"] == 0
    assert bf["speed"] == {"n": 0, "score": None, "strict": None, "yes_no_n": 0, "rule_coverage": None}


# ---------------------------------------------------------------- the replay records (P4)

def test_the_replay_records_hold_model_outputs_only(fake_set):
    out, _ = _run(fake_set)
    run_id = json.loads(out.read_text())["run_id"]
    folder = fake_set / "private_run" / run_id
    assert json.loads((fake_set / "private_ran.json").read_text())["replay_dir"] == f"private_run/{run_id}"
    rows = [json.loads(l) for l in (folder / "records.jsonl").read_text().splitlines()]
    assert [r["id"] for r in rows] == [q["id"] for q in SECRET_QS]
    raw = (folder / "records.jsonl").read_text()
    for r, q in zip(rows, SECRET_QS):
        assert tuple(r) == ep.RECORD_FIELDS
        assert "secret-gold" not in raw and q["question"] not in raw     # no gold, no question text
        assert not {"correct", "strict", "judge_label", "judge_reason", "answer"} & set(r)
    assert any((folder / "scenes").rglob("*.json"))                      # the run's own scene cache


def test_record_fields_carry_no_gold_or_grade():
    assert not {"answer", "question", "correct", "strict", "judge_label", "judge_reason"} & set(ep.RECORD_FIELDS)


# ---------------------------------------------------------------- the question file

def test_load_questions_can_drop_the_answers(tmp_path):
    p = tmp_path / "qs.json"
    p.write_text(json.dumps([dict(QS[0], relevant_articles=None)]), encoding="utf-8")
    assert "answer" not in ep.load_questions(p, with_answers=False)[0]
    assert ep.load_questions(p)[0]["answer"] == QS[0]["answer"]
    assert "relevant_articles" not in ep.load_questions(p)[0]


def test_a_row_without_a_field_is_named_by_field_only(tmp_path):
    p = tmp_path / "qs.json"
    p.write_text(json.dumps([{"id": "private_secret", "question": "x"}]), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        ep.load_questions(p)
    assert "image_id" in str(e.value) and "private_secret" not in str(e.value)


def test_the_estimate_uses_counts_only():
    qs = [{"id": f"q{i}", "image_id": f"i{i // 2}", "question_type": "Yes/No" if i % 2 else "Natural QA",
           "question": "x"} for i in range(10)]
    e = ep.estimate(qs)
    assert (e["questions"], e["images"], e["natural_qa"]) == (10, 5, 5)
    # phase 4.6: the stage lines times the calibration to the final validation's measured total
    assert abs(e["total_usd"] - sum(e["lines_usd"].values()) * ep.CALIBRATION) <= 0.01 and e["total_usd"] > 0


# ---------------------------------------------------------------- features (hand-written questions)

@pytest.mark.parametrize("question, expected", [
    ("Xe tải có được rẽ trái ở đây không, đúng hay sai?", {"claim", "vehicle_class", "turn_stop_park_overtake"}),
    ("Tốc độ tối đa cho ô tô trên làn 2 là bao nhiêu km/h?", {"speed", "vehicle_class", "lanes"}),
    ("Từ 6 giờ đến 22 giờ, xe khách trên 29 chỗ có bị cấm không?", {"time", "vehicle_class", "weight_or_seats"}),
    ("Xe có trọng tải 2 tấn có được vào lúc 7:30 không?", {"weight_or_seats", "time"}),
    ("Đây là biển báo gì?", {"meaning"}),
    ("Biển trong ảnh báo hiệu điều gì?", {"meaning"}),
    ("Trong hình có phương tiện nào vi phạm không?", {"vehicle_class", "violation"}),
    ("Đường này có cho dừng xe không?", {"turn_stop_park_overtake"}),
    ("Hướng đi tiếp theo là gì?", set()),
])
def test_features(question, expected):
    assert set(ep.features(question)) == expected


def test_speed_words_are_not_times():
    assert ep.features("Tốc độ tối đa là 60 km/giờ phải không?") == ["claim", "speed"]
    assert "time" in ep.features("Buổi tối có được đỗ xe không?")



# ---------------------------------------------------------------- B5: the phase-4.5 record (owner, 2026-11-17)

def test_the_private_run_checks_the_phase52_record_by_default():
    """Phase 5.2 (owner, 2026-11-20): the private runner requires the v18 record with the lane fixes."""
    import inspect
    for fn in (ep.run_private, ep.guards, ep.frozen_perception_model):
        assert inspect.signature(fn).parameters["frozen"].default == fz.FROZEN_PHASE52
    assert ep.PRIVATE_PROFILES == ("phase52",)


@pytest.mark.parametrize("record", [fz.FROZEN_PHASE45, fz.FROZEN_PHASE46, fz.FROZEN_PHASE47, fz.FROZEN_PHASE48,
                                    fz.FROZEN_PHASE49, fz.FROZEN_PHASE50, fz.FROZEN_PHASE51])
def test_an_older_record_is_refused_before_the_sentinel(fake_set, record):
    """An unchanged older record (phase 4.5 to 5.1) is refused by its profile, before any other check."""
    with pytest.raises(SystemExit, match="phase-5.2 freeze only"):
        _run(fake_set, frozen=record)
    assert not (fake_set / "private_ran.json").exists()


@pytest.mark.parametrize("field, value", [
    (("pipeline_config", "parser_version"), "v13"), (("pipeline_config", "guide_reading"), False),
    (("pipeline_config", "reading_policy"), "all"), (("v6_fields_off",), []), (("engine_code", "sha256"), "0" * 64),
    (("pipeline_config", "scene_version"), "v4"), (("prompts", "guide", "sha256"), "0" * 64),
    (("scene_fallback", "chosen_policy"), "rules"), (("engine_switches", "several_signs"), False),
    (("engine_switches", "confusable_pairs"), True), (("pipeline_config", "parser_version"), "v17"),
    (("pipeline_config", "scene_rerun"), True)])
def test_a_phase52_mismatch_is_refused_before_the_sentinel(fake_set, field, value):
    rec = fz.load(fz.FROZEN_PHASE52)
    node = rec
    for k in field[:-1]:
        node = node[k]
    node[field[-1]] = value
    p = fake_set / "frozen47.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(SystemExit, match="differs from the freeze record"):
        _run(fake_set, frozen=p)
    assert not (fake_set / "private_ran.json").exists()


# ---------------------------------------------------------------- phase 4.6 step 2: rules-only figures, re-based estimate

def _rec(img, qt, decided, correct, trigger=None):
    return {"image_id": img, "question_type": qt, "decided": decided, "correct": correct, "strict": correct,
            "trigger": trigger}


DUPS = {"groups": [{"images": [{"split": "private", "image_id": "p1"}, {"split": "train", "image_id": "t9"}]},
                   {"images": [{"split": "private", "image_id": "p2"}, {"split": "private", "image_id": "p3"}]}]}


def test_rules_only_figures_count_non_decided_as_wrong_and_split_duplicates():
    rs = [_rec("p1", "Yes/No", True, 1.0), _rec("p1", "Natural QA", True, 0.5),
          _rec("p2", "Yes/No", False, 1.0, "out_of_scope"),           # the fallback's grade does not count
          _rec("p3", "Natural QA", True, 0.0), _rec("p3", "Natural QA", False, None, "uncertain")]
    ro = ep.rules_only(rs, DUPS)
    assert (ro["questions"], ro["decided"]) == (5, 3)
    assert ro["decided_coverage"] == 0.6 and ro["accuracy_on_decided"] == 0.5 and ro["overall_non_decided_wrong"] == 0.3
    assert ro["not_decided_by_cause"] == {"out_of_scope": 1, "uncertain": 1}
    assert ro["by_question_type"]["Yes/No"]["decided"] == 1 and ro["by_question_type"]["Natural QA"]["questions"] == 3
    bi = ro["by_images"]
    assert bi["against"] == ["public", "train"]
    assert bi["duplicate_images"]["questions"] == 2                 # p1 is also in train; p2/p3 only private
    nd = bi["non_duplicate_images"]
    assert (nd["questions"], nd["decided"], nd["overall_non_decided_wrong"]) == (3, 1, 0.0)
    for k in ("decided_coverage_ci95", "accuracy_on_decided_ci95", "overall_non_decided_wrong_ci95"):
        assert len(nd[k]) == 2


def test_the_run_report_carries_the_rules_only_figures(fake_set):
    rep = json.loads(_run(fake_set)[0].read_text())
    ro = rep["rules_only"]
    assert ro["questions"] == 2 and "non_duplicate_images" in ro["by_images"]
    assert ro["decided"] + sum(ro["not_decided_by_cause"].values()) == 2


def test_the_estimate_reads_no_private_file_by_default(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the estimate must not read the private file")
    monkeypatch.setattr(ep, "load_questions", refuse)
    e = ep.estimate()
    assert (e["questions"], e["images"], e["natural_qa"]) == (146, 104, 76)
    assert e["total_fallback_off_usd"] < e["total_usd"]
    assert ep.estimate(decided_share=0.9)["total_usd"] < e["total_usd"]    # fewer fallback answers
    assert e["decided_share_assumed"] == ep.DECIDED_SHARE_48 and e["rates_usd"] == ep.RATES_48   # phase 4.8


def test_the_estimate_is_calibrated_to_the_final_validation():
    """The stage rates times CALIBRATION give the final validation's measured $0.83 (fallback off)."""
    qs = [{"id": f"q{i}", "image_id": f"i{i % 54}", "question_type": "Natural QA" if i < 57 else "Yes/No"}
          for i in range(110)]
    e = ep.estimate(qs, decided_share=52 / 110, rates=ep.RATES)            # the phase-4.5 rates it was fitted on
    assert abs(e["total_fallback_off_usd"] - 0.83) <= 0.06
