"""Phase 4.5 scope round (owner, 2026-11-17): the dev set and the per-question dev runs
(eval/e2e_dev.py). The split tests read ids only; the run test uses a fake SDK and
hand-made images; no API call."""

from __future__ import annotations

import json

import pytest

import eval.e2e_dev as ed
import eval.make_validation_split as mvs
from eval import coverage_analysis as ca
from tests.test_e2e_eval import CLEAN, QS, SCENE_REPLY, _e2e_sdk, fake_set  # noqa: F401

DEV = json.loads(mvs.DEV_OUT.read_text(encoding="utf-8"))
VAL = json.loads(mvs.OUT.read_text(encoding="utf-8"))


def test_the_dev_set_does_not_overlap_the_validation_set():
    assert not set(DEV["questions"]) & set(VAL["questions"])
    assert not set(DEV["images"]) & set(VAL["images"])
    ed.check_disjoint()


def test_dev_plus_validation_is_the_pool():
    images, questions, _ = ca.pool()
    assert set(DEV["images"]) | set(VAL["images"]) == set(images)
    assert set(DEV["questions"]) | set(VAL["questions"]) == {q["id"] for q in questions}
    assert mvs.build_dev() == DEV and DEV["counts"] == {"images": 60, "questions": 87,
                                                         "question_types": {"Natural QA": 87}}


def test_an_overlap_is_refused(tmp_path):
    p = tmp_path / "dev.json"
    p.write_text(json.dumps({"questions": VAL["questions"][:1], "images": []}), encoding="utf-8")
    with pytest.raises(SystemExit, match="overlaps"):
        ed.check_disjoint(p)


def test_a_dev_run_keeps_per_question_records_with_the_fallback_off(fake_set):
    sdk = _e2e_sdk()
    sdk.replies["perception"] = [SCENE_REPLY, SCENE_REPLY]
    out = ed.run_dev("t", 1.0, sdk=sdk, questions=QS, out_dir=fake_set / "dev",
                     image_path=lambda i: fake_set / f"{i}.jpg", git=CLEAN)
    head, rows = ed.ee.load(out)
    assert head["answer_fallback"] is False and head["kind"] == "dev"
    assert [r["id"] for r in rows] == ["q1", "q2"] and all(r["decided"] for r in rows)
    assert rows[0]["scene"]["signs"][0]["code"] == "P.104" and rows[0]["trace"]["parser"]["program"]
    assert rows[0]["correct"] == 1.0 and "fallback" not in sdk.created
    assert (fake_set / "dev" / head["cache_dir"]).is_dir()
    s = ed.summary(out)
    assert s["decided"] == 2 and s["coverage"] == 1.0


def test_a_dirty_tree_is_refused(fake_set):
    dirty = lambda: {"commit": "c", "clean": False, "dirty": [" M x"]}  # noqa: E731
    with pytest.raises(SystemExit, match="not clean"):
        ed.run_dev("t", 1.0, sdk=_e2e_sdk(), questions=QS, out_dir=fake_set / "dev", git=dirty)


def test_a_candidate_dev_run_uses_scene_v5_guide_reading_and_parser_v8(fake_set):
    """Phase 4.5 B4: `--candidate` runs the stage-B candidate; the header records it."""
    sdk = _e2e_sdk()
    sdk.replies["perception"] = [SCENE_REPLY, SCENE_REPLY]
    systems: dict[str, str] = {}
    create = sdk.create

    def spy(**kw):
        systems.setdefault(sdk.role(kw), "".join(b["text"] for b in kw["system"]))
        return create(**kw)
    sdk.create = spy
    out = ed.run_dev("c", 1.0, sdk=sdk, questions=QS, out_dir=fake_set / "dev",
                     image_path=lambda i: fake_set / f"{i}.jpg", git=CLEAN, candidate=ed.CANDIDATE)
    head, rows = ed.ee.load(out)
    assert head["candidate"] == {"scene_version": "v5", "parser_version": "v8", "guide_reading": True}
    ids = head["candidate_prompt_ids"]
    assert ids["scene"].startswith("scene/v5@") and ids["scene_tile"].startswith("scene/v5-tile@")
    assert ids["guide"].startswith("scene/v5-guide@") and ids["parser"].startswith("parser/v8@")
    assert "R.122 |" in systems["perception"] and '"intent":"guide"' in systems["parser"]
    assert all(r["decided"] for r in rows)


def test_reparse_reparses_yes_no_wording_and_judges_only_changed_decided_answers(fake_set):
    """Phase 4.5 (owner, 2026-11-17): a new parser version on a stored dev run. Only the
    yes/no-worded question (q1) is re-parsed; its program changes, so the engine runs on the
    stored scene and the writer is called for it alone (a Yes/No question is graded by the
    verdict mapping; Natural QA would go to the judge). No perception call."""
    from tests.test_e2e_eval import RoutedSDK
    sdk = _e2e_sdk()
    sdk.replies["perception"] = [SCENE_REPLY, SCENE_REPLY]
    src = ed.run_dev("c", 1.0, sdk=sdk, questions=QS, out_dir=fake_set / "dev",
                     image_path=lambda i: fake_set / f"{i}.jpg", git=CLEAN, candidate=ed.CANDIDATE)
    sdk2 = RoutedSDK(parser=[{"program": {"intent": "forbidden", "action": "enter",
                                          "vehicle": {"vehicle_class": "every_vehicle"}}}],
                     writer=[{"verdict": "no", "answer": "Không. Biển P.104 chỉ cấm xe máy.", "cited_signs": ["s1"],
                              "cited_rules": []}],
                     judge=[{"label": "wrong", "reason": "x"}])
    out = ed.reparse(src, "v9", 0.5, sdk=sdk2, out_dir=fake_set / "dev", git=CLEAN, questions=QS)
    head, rows = ed.ee.load(out)
    assert head["kind"] == "dev_reparse" and head["parser_version"] == "v9" and head["from_run"]
    assert sdk2.created == ["parser", "writer"]                           # q1 only; no perception
    q1, q2 = rows
    assert q1["reparsed"] and q1["changed"] and q1["engine_verdict"] == "no" and q1["was"]["correct"] == 1.0
    assert q1["correct"] == 0.0 and not q2["reparsed"] and q2["correct"] == 1.0


def test_reparse_keeps_an_unchanged_parse(fake_set):
    from tests.test_e2e_eval import RoutedSDK
    sdk = _e2e_sdk()
    sdk.replies["perception"] = [SCENE_REPLY, SCENE_REPLY]
    src = ed.run_dev("c", 1.0, sdk=sdk, questions=QS, out_dir=fake_set / "dev",
                     image_path=lambda i: fake_set / f"{i}.jpg", git=CLEAN, candidate=ed.CANDIDATE)
    sdk2 = RoutedSDK(parser=[{"program": {"intent": "forbidden", "action": "enter",
                                          "vehicle": {"vehicle_class": "motorbike"}}}])
    out = ed.reparse(src, "v9", 0.5, sdk=sdk2, out_dir=fake_set / "dev", git=CLEAN, questions=QS)
    _, rows = ed.ee.load(out)
    assert sdk2.created == ["parser"] and rows[0]["changed"] is False and rows[0]["correct"] == 1.0
    assert ed.YESNO.search("Xe máy có bị cấm đi vào đường này không?") and not ed.YESNO.search("Biển trong ảnh có ý nghĩa gì?")


def test_reparse_with_a_reading_policy_reruns_the_engine_on_unchanged_parses(fake_set):
    """Phase 4.6 step 6: with `reading_policy`, an unchanged parse whose answer the engine now
    decides differently is written and judged again; one whose answer is the same is kept."""
    from tests.test_e2e_eval import RoutedSDK
    sdk = _e2e_sdk()
    sdk.replies["perception"] = [SCENE_REPLY, SCENE_REPLY]
    src = ed.run_dev("c", 1.0, sdk=sdk, questions=QS, out_dir=fake_set / "dev",
                     image_path=lambda i: fake_set / f"{i}.jpg", git=CLEAN, candidate=ed.CANDIDATE)
    head, rows = ed.ee.load(src)
    rows[1]["engine_answer"] = {"verdict": "uncertain", "value": None}     # as if readings had disagreed
    lines = [json.dumps(head)] + [json.dumps(r, ensure_ascii=False) for r in rows]
    src.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sdk2 = RoutedSDK(parser=[{"program": {"intent": "forbidden", "action": "enter",
                                          "vehicle": {"vehicle_class": "motorbike"}}},
                             {"program": {"intent": "meaning", "sign": {"only": True}}}],
                     writer=[{"verdict": "value", "answer": "Cấm xe máy.", "cited_signs": ["s1"], "cited_rules": []}],
                     judge=[{"label": "correct", "reason": "same"}])
    out = ed.reparse(src, "v11", 0.5, sdk=sdk2, out_dir=fake_set / "dev", git=CLEAN, questions=QS,
                     select="all", reading_policy="higher_confidence")
    h2, rows2 = ed.ee.load(out)
    assert h2["reading_policy"] == "higher_confidence"
    assert rows2[0]["changed"] is False and rows2[1]["changed"] is True and rows2[1]["correct"] == 1.0
    assert sdk2.created == ["parser", "parser", "writer", "judge"]


def test_a_reparse_stopped_by_the_spend_guard_is_kept_as_partial(fake_set):
    from tests.test_e2e_eval import RoutedSDK
    sdk = _e2e_sdk()
    sdk.replies["perception"] = [SCENE_REPLY, SCENE_REPLY]
    src = ed.run_dev("c", 1.0, sdk=sdk, questions=QS, out_dir=fake_set / "dev",
                     image_path=lambda i: fake_set / f"{i}.jpg", git=CLEAN, candidate=ed.CANDIDATE)
    sdk2 = RoutedSDK(parser=[{"program": {"intent": "forbidden", "action": "enter",
                                          "vehicle": {"vehicle_class": "motorbike"}}}])
    out = ed.reparse(src, "v11", 0.0001, sdk=sdk2, out_dir=fake_set / "dev", git=CLEAN, questions=QS, select="all")
    assert out.name.endswith(".partial.jsonl") and out.exists()
    assert not out.with_name(out.name.replace(".partial", "")).exists()


def test_a_partial_reparse_resumes_with_only_the_missing_questions(fake_set):
    """Phase 4.8c: `resume` copies the partial file's rows and re-parses only the rest; a partial
    from another source, version or switch set is refused."""
    from tests.test_e2e_eval import RoutedSDK
    sdk = _e2e_sdk()
    sdk.replies["perception"] = [SCENE_REPLY, SCENE_REPLY]
    src = ed.run_dev("c", 1.0, sdk=sdk, questions=QS, out_dir=fake_set / "dev",
                     image_path=lambda i: fake_set / f"{i}.jpg", git=CLEAN, candidate=ed.CANDIDATE)
    unchanged = {"program": {"intent": "forbidden", "action": "enter", "vehicle": {"vehicle_class": "motorbike"}}}
    w = {"verdict": "no", "answer": "Không.", "cited_signs": ["s1"], "cited_rules": []}
    j = {"label": "correct", "reason": "x"}
    full = ed.reparse(src, "v11", 0.5, sdk=RoutedSDK(default={"writer": w, "judge": j}, parser=[unchanged, unchanged]),
                      out_dir=fake_set / "dev",
                      git=CLEAN, questions=QS, select="all")
    head, rows = ed.ee.load(full)
    partial = fake_set / "dev" / "p.partial.jsonl"
    partial.write_text(json.dumps(head) + "\n" + json.dumps(rows[0], ensure_ascii=False) + "\n", encoding="utf-8")
    sdk3 = RoutedSDK(default={"writer": w, "judge": j}, parser=[unchanged])
    out = ed.reparse(src, "v11", 0.5, sdk=sdk3, out_dir=fake_set / "dev", git=CLEAN, questions=QS, select="all",
                     resume=partial)
    h2, rows2 = ed.ee.load(out)
    assert sdk3.created[0] == "parser" and sdk3.created.count("parser") == 1 and h2["resumed_from"] == head["run_id"]
    assert [r["id"] for r in rows2] == [r["id"] for r in rows] and rows2[0] == rows[0]
    with pytest.raises(SystemExit, match="not this source"):
        ed.reparse(src, "v9", 0.5, sdk=RoutedSDK(), out_dir=fake_set / "dev", git=CLEAN, questions=QS,
                   select="all", resume=partial)
