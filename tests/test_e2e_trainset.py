"""Phase 4.6 D3: the parse-only train Yes/No runner (eval/e2e_trainset.py). Fake SDK, hand-made
questions and ids; no API call. One test reads the real split ids and train questions (skipped
when the dataset is absent) to check the working set holds no dev or validation id."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image

import eval.e2e_trainset as et
from tests.test_e2e_eval import CLEAN, RoutedSDK

QS = [{"id": "train_9001", "image_id": "train_90_1", "question_type": "Yes/No",
       "question": "Xe máy có được đi vào đường này không?", "answer": "Không"},
      {"id": "train_9002", "image_id": "train_90_2", "question_type": "Yes/No",
       "question": "Gặp đèn đỏ, xe có được đi tiếp không?", "answer": "Không"}]
NONE = (set(), set())


@pytest.fixture
def images(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    for k, q in enumerate(QS):
        buf = io.BytesIO()
        Image.new("RGB", (64, 48), (k * 90, 40, 40)).save(buf, format="JPEG")
        (tmp_path / f"{q['image_id']}.jpg").write_bytes(buf.getvalue())
    return tmp_path


def _sdk():
    return RoutedSDK(parser=[{"program": {"intent": "forbidden", "action": "enter",
                                          "vehicle": {"vehicle_class": "motorbike"}}},
                             {"program": None, "out_of_scope": True, "out_of_scope_reason": "traffic lights"}])


def _run(tmp, **kw):
    args = dict(sdk=_sdk(), questions=QS, out_dir=tmp / "runs", git=CLEAN, forbidden=NONE,
                image_path=lambda i: tmp / f"{i}.jpg", cache_dir=tmp / "cache")
    args.update(kw)
    return et.run(0.5, **args)


@pytest.mark.parametrize("forbidden", [({"train_9001"}, set()), (set(), {"train_90_2"})])
def test_dev_or_validation_ids_are_refused(images, forbidden):
    with pytest.raises(SystemExit, match="dev or validation"):
        _run(images, forbidden=forbidden)
    assert not (images / "runs").exists()


@pytest.mark.skipif(not et.gs.TRAIN_QA.exists(), reason="dataset not present")
def test_the_real_working_set_holds_no_dev_or_validation_id():
    fq, fi = et.forbidden_ids()
    qs = et.load_questions(forbidden=(fq, fi))
    assert qs and all(q["question_type"] == "Yes/No" for q in qs)
    assert not any(q["id"] in fq or q["image_id"] in fi for q in qs)


def test_a_dirty_tree_is_refused(images):
    with pytest.raises(SystemExit, match="not clean"):
        _run(images, git=lambda: {"commit": "x", "clean": False, "dirty": ["?? f"]})


def test_parse_only_records_are_marked_biased_and_make_no_perception_call(images):
    sdk = _sdk()
    out = _run(images, sdk=sdk)
    lines = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    head, rows = lines[0], lines[1:]
    assert head["biased"] is True and "diagnosis only" in head["why_biased"]
    assert head["parser"].startswith("parser/v9@") and head["reading_policy"] == "higher_confidence"
    assert "perception" not in sdk.created and "writer" not in sdk.created and "judge" not in sdk.created
    assert [r["parse_status"] for r in rows] == ["ok", "out_of_scope"]
    assert rows[0]["intent"] == "forbidden" and rows[0]["scene"] == {"cached": False}
    assert rows[1]["trigger"] == "out_of_scope" and rows[1]["wording_group"] == "traffic_light"
    assert all("answer" not in r and "question" not in r for r in rows)
    s = et.summary(out)
    assert s["biased"] is True and s["questions"] == 2
    assert s["by_question_type"]["Yes/No"]["parse_status"] == {"ok": 1, "out_of_scope": 1}
    assert s["out_of_scope_by_wording_group"] == {"traffic_light": 1}


def test_a_cached_scene_runs_the_engine_and_grades_by_the_yes_no_mapping(images, monkeypatch):
    from vqa.schemas import Position, SceneGraph, Sign
    sc = SceneGraph(scene_id="x", signs=[Sign(id="s1", code="P.104", shape="circle", border="red",
                                              background="white", position=Position(rank_top_down=1, side="right"))])
    monkeypatch.setattr(et, "_scene", lambda pipe, img: (sc, {"cached": True, "ok": True, "refused_calls": 0}))
    out = _run(images)
    r = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()][1]
    assert r["decided"] is True and r["engine_verdict"] == "yes" and r["correct"] == 0.0   # "is it banned?" yes vs "Không"
    s = et.summary(out)
    assert s["with_cached_scene"]["decided"] == 1


def test_the_estimate_is_parse_only():
    e = et.estimate(QS)
    assert e["biased"] is True and e["questions"] == 2 and e["total_usd"] == round(2 * et.PARSER_RATE, 3)


def test_no_key_is_refused_before_anything_is_written(images, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        _run(images, sdk=None)
    assert not (images / "runs").exists()
