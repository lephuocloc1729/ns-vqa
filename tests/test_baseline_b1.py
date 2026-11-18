"""Baseline B1, "Claude alone" (eval/baseline_b1.py; docs/plans/phase-5.md, item 2).
The prompt pin, the batch requests, the public_dev path, and the private path's guards,
sentinel and aggregate-only report. Fake SDK, hand-made images and questions; no API call
and no dataset file."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

import eval.baseline_b1 as b1

PROMPT_SHA = "e0914f00eb6eb6f85d513d22d3db9c2f6fa4b0793db025a1fcb750565ea47bfb"
CLEAN = lambda: {"clean": True, "commit": "c0ffee", "dirty": []}  # noqa: E731
DIRTY = lambda: {"clean": False, "commit": "c0ffee", "dirty": [" M x.py"]}  # noqa: E731
TWO = {"questions": 2, "images": 2}
NO_DUPS = {"groups": []}

QS = [{"id": "private_secret_0", "image_id": "private_img_secret_0", "question_type": "Yes/No",
       "question": "Xe máy có bị cấm đi vào đường này không?", "answer": "Có, secret-gold-0"},
      {"id": "private_secret_1", "image_id": "private_img_secret_1", "question_type": "Natural QA",
       "question": "Biển trong ảnh có ý nghĩa gì?", "answer": "Cấm xe máy secret-gold-1."}]


def _msg(text, stop="end_turn"):
    return SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking=""),
                                    SimpleNamespace(type="text", text=text)],
                           stop_reason=stop, stop_details=None, _request_id="req_t",
                           usage=SimpleNamespace(input_tokens=1800, output_tokens=300,
                                                 cache_read_input_tokens=0, cache_creation_input_tokens=0))


class FakeSDK:
    """messages.batches for the baseline; messages.create / count_tokens for the judge."""

    def __init__(self, answers, judge=None, status="ended", on_create=None):
        self.answers, self.judge = list(answers), list(judge or [])
        self.status, self.on_create = status, on_create
        self.requests: list[dict] = []
        self.judged = 0
        self.messages = self
        self.batches = self

    # batches
    def create(self, requests=None, **kw):
        if requests is None:                      # a judge call
            self.judged += 1
            reply = self.judge.pop(0) if self.judge else {"label": "correct", "reason": "same"}
            return _msg(json.dumps(reply))
        if self.on_create:
            self.on_create()
        self.requests = requests
        return SimpleNamespace(id="msgbatch_test")

    def retrieve(self, batch_id):
        return SimpleNamespace(processing_status=self.status)

    def results(self, batch_id):
        out = []
        for r, a in zip(self.requests, self.answers):
            if isinstance(a, tuple) and a[0] == "errored":
                out.append(SimpleNamespace(custom_id=r["custom_id"], result=SimpleNamespace(type="errored")))
            elif isinstance(a, tuple):
                out.append(SimpleNamespace(custom_id=r["custom_id"], result=SimpleNamespace(
                    type="succeeded", message=_msg(a[1], stop=a[0]))))
            else:
                out.append(SimpleNamespace(custom_id=r["custom_id"], result=SimpleNamespace(
                    type="succeeded", message=_msg(a))))
        return list(reversed(out))                # results come in any order

    def count_tokens(self, **kw):
        return SimpleNamespace(input_tokens=500)


@pytest.fixture
def imgs(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    for k, q in enumerate(QS):
        buf = io.BytesIO()
        Image.new("RGB", (320, 240), (k * 80, 50, 50)).save(buf, format="JPEG")
        (tmp_path / f"{q['image_id']}.jpg").write_bytes(buf.getvalue())
    return tmp_path


def _pin(tmp_path, version="v1"):
    return b1.pin(version, pinned=tmp_path / "baseline_pinned.json", git=CLEAN)


def _submit(tmp_path, sdk, **kw):
    args = dict(confirm_pinned=True, sdk=sdk, questions=[{k: v for k, v in q.items() if k != "answer"} for q in QS],
                image_path=lambda i: tmp_path / f"{i}.jpg", sentinel=tmp_path / "baseline_ran_b1_sonnet.json",
                out_dir=tmp_path / "agg", pinned=tmp_path / "baseline_pinned.json",
                answers_root=tmp_path / "private_run", git=CLEAN, ignored=lambda p: True, expected=TWO)
    args.update(kw)
    return b1.submit_private("sonnet", 5.0, **args)


def _collect(tmp_path, sdk, **kw):
    args = dict(sdk=sdk, questions=QS, sentinel=tmp_path / "baseline_ran_b1_sonnet.json", out_dir=tmp_path / "agg",
                answers_root=tmp_path / "private_run", duplicates=NO_DUPS)
    args.update(kw)
    return b1.collect_private("sonnet", 1.0, **args)


# ---------------------------------------------------------------- prompt and requests

def test_the_prompt_is_pinned_by_hash():
    assert b1.prompt_hash("v1") == PROMPT_SHA, "baseline prompt changed: make a new version"
    assert b1.config("v1")["effort"] == "medium"


def test_the_prompt_is_plain_no_rules_no_scene_no_dataset_text():
    text = b1.system_prompt("v1")
    for bad in ("scene graph", "P.1", "few-shot", "public_test", "private_test", "train_"):
        assert bad not in text


def test_the_models_are_the_three_planned():
    assert b1.MODELS == {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
    with pytest.raises(SystemExit):
        b1.model_id("gpt")


def test_a_request_is_image_then_question_with_an_index_id(imgs):
    r = b1.request(7, QS[0]["question"], (imgs / f"{QS[0]['image_id']}.jpg").read_bytes(), "claude-sonnet-5-5")
    assert r["custom_id"] == "q0007"
    p = r["params"]
    assert p["model"] == "claude-sonnet-5-5" and p["output_config"] == {"effort": "medium"}
    assert p["max_tokens"] == 4000 and p["system"] == b1.system_prompt("v1")
    content = p["messages"][0]["content"]
    assert [c["type"] for c in content] == ["image", "text"]
    assert content[1]["text"] == "Câu hỏi: " + QS[0]["question"]
    assert "private_secret" not in json.dumps(r) and "private_img" not in json.dumps(r)


def test_the_estimate_uses_counts_only_and_the_worst_case_bounds_it():
    e = b1.estimate("claude-sonnet-5-5", 146, 76)
    assert e["requests"] == 146 and e["natural_qa"] == 76
    assert 0 < e["batch_expected_usd"] < e["batch_worst_case_usd"]
    assert e["total_expected_usd"] == round(e["batch_expected_usd"] + e["judge_expected_usd"], 2)


# ---------------------------------------------------------------- public_dev

DEV = [dict(q, id=f"public_natural_{i}", image_id=f"public_test_{i}_{i}") for i, q in enumerate(QS, 1)]


@pytest.fixture
def dev_imgs(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    for q in DEV:
        buf = io.BytesIO()
        Image.new("RGB", (200, 150), (90, 50, 50)).save(buf, format="JPEG")
        (tmp_path / f"{q['image_id']}.jpg").write_bytes(buf.getvalue())
    return tmp_path


def test_dev_submit_then_collect_grades_per_question(dev_imgs):
    sdk = FakeSDK(["Có. Biển cấm xe máy.", "Cấm xe máy."], judge=[{"label": "partial", "reason": "x"}])
    state = b1.submit_dev("sonnet", 5.0, sdk=sdk, questions=DEV, image_path=lambda i: dev_imgs / f"{i}.jpg",
                          out_dir=dev_imgs / "runs")
    st = json.loads(state.read_text())
    assert st["batch_id"] == "msgbatch_test" and st["questions"] == [q["id"] for q in DEV]
    out = b1.collect_dev(state, 1.0, sdk=sdk, questions=DEV)
    lines = [json.loads(l) for l in out.read_text().splitlines()]
    head, rows = lines[0], lines[1:]
    assert head["kind"] == "header" and head["prompt_id"] == b1.prompt_id("v1")
    assert [r["id"] for r in rows] == [q["id"] for q in DEV]            # order kept, results reversed
    assert rows[0]["correct"] == 1.0 and rows[0]["yes_no_pred"] is True
    assert rows[1]["judge_label"] == "partial" and rows[1]["correct"] == 0.5
    assert head["summary"]["overall"] == 0.75 and sdk.judged == 1


def test_dev_submit_refuses_a_cap_below_the_worst_case_before_any_batch(dev_imgs):
    sdk = FakeSDK([])
    with pytest.raises(Exception, match="could cost up to"):
        b1.submit_dev("sonnet", 0.0001, sdk=sdk, questions=DEV, image_path=lambda i: dev_imgs / f"{i}.jpg",
                      out_dir=dev_imgs / "runs")
    assert sdk.requests == []


def test_refusals_truncations_and_errors_are_graded_wrong_without_a_judge_call(dev_imgs):
    sdk = FakeSDK([("refusal", ""), ("errored",)])
    state = b1.submit_dev("sonnet", 5.0, sdk=sdk, questions=DEV, image_path=lambda i: dev_imgs / f"{i}.jpg",
                          out_dir=dev_imgs / "runs")
    rows = [json.loads(l) for l in b1.collect_dev(state, 1.0, sdk=sdk, questions=DEV).read_text().splitlines()][1:]
    assert [r["status"] for r in rows] == ["refusal", "errored"]
    assert [r["correct"] for r in rows] == [0.0, 0.0] and sdk.judged == 0


def test_collect_waits_for_the_batch_to_end(dev_imgs, capsys):
    sdk = FakeSDK(["Có.", "Cấm xe máy."], status="in_progress")
    state = b1.submit_dev("sonnet", 5.0, sdk=sdk, questions=DEV, image_path=lambda i: dev_imgs / f"{i}.jpg",
                          out_dir=dev_imgs / "runs")
    assert b1.collect_dev(state, 1.0, sdk=sdk, questions=DEV) is None
    assert "in_progress" in capsys.readouterr().out


# ---------------------------------------------------------------- pin

def test_pin_is_write_once(tmp_path):
    p = _pin(tmp_path)
    rec = json.loads(p.read_text())
    assert rec["prompt_id"] == b1.prompt_id("v1") and rec["git_commit"] == "c0ffee"
    with pytest.raises(SystemExit, match="pinned once"):
        _pin(tmp_path)


# ---------------------------------------------------------------- private: guards

def test_it_refuses_without_confirm_pinned(imgs):
    _pin(imgs)
    with pytest.raises(SystemExit, match="--confirm-pinned"):
        _submit(imgs, FakeSDK([]), confirm_pinned=False)


@pytest.mark.parametrize("setup, kw, match", [
    (lambda t: _pin(t), {"git": DIRTY}, "not clean"),
    (lambda t: None, {}, "no pinned baseline prompt"),
    (lambda t: (t / "baseline_pinned.json").write_text(json.dumps({"version": "v1", "prompt_id": "baseline/v1@x"})),
     {}, "changed since it was pinned"),
    (lambda t: _pin(t), {"ignored": lambda p: False}, "does not ignore"),
    (lambda t: _pin(t), {"expected": {"questions": 3, "images": 2}}, "expected 3 questions"),
])
def test_a_failed_guard_stops_before_the_sentinel_and_the_batch(imgs, setup, kw, match):
    setup(imgs)
    sdk = FakeSDK([])
    with pytest.raises(SystemExit, match=match):
        _submit(imgs, sdk, **kw)
    assert not (imgs / "baseline_ran_b1_sonnet.json").exists() and sdk.requests == []


def test_the_sentinel_is_written_before_the_batch_is_created(imgs):
    _pin(imgs)
    seen = []
    sdk = FakeSDK([], on_create=lambda: seen.append((imgs / "baseline_ran_b1_sonnet.json").exists()))
    s = _submit(imgs, sdk)
    assert seen == [True]
    mark = json.loads(s.read_text())
    assert mark["status"] == "submitted" and mark["batch_id"] == "msgbatch_test"
    assert "private_secret" not in s.read_text() and "private_img" not in s.read_text()


def test_it_runs_once_per_model(imgs):
    _pin(imgs)
    _submit(imgs, FakeSDK([]))
    with pytest.raises(SystemExit, match="already run"):
        _submit(imgs, FakeSDK([]))
    _submit(imgs, FakeSDK([]), sentinel=imgs / "baseline_ran_b1_haiku.json")   # another model's sentinel


def test_an_existing_aggregate_blocks_a_new_start(imgs):
    _pin(imgs)
    (imgs / "agg").mkdir()
    (imgs / "agg" / "b1_private_aggregate_sonnet_abc.json").write_text("{}")
    with pytest.raises(SystemExit, match="aggregate already exists"):
        _submit(imgs, FakeSDK([]))


def test_the_private_sentinel_is_a_committed_path_outside_the_runs_folder():
    p = b1.sentinel_path("sonnet")
    assert p.parent.name == "eval" and p.name == "baseline_ran_b1_sonnet.json"
    assert b1.ANSWERS.parts[-2:] == ("cache", "private_run")


# ---------------------------------------------------------------- private: aggregate only

def _full_private(imgs, capsys, answers=("Có, bị cấm.", "Cấm xe máy."), judge=None):
    _pin(imgs)
    sdk = FakeSDK(list(answers), judge=judge)
    _submit(imgs, sdk)
    out = _collect(imgs, sdk)
    return out, sdk, capsys.readouterr().out


def test_collect_private_writes_only_an_aggregate_and_prints_no_question(imgs, capsys):
    out, sdk, printed = _full_private(imgs, capsys)
    assert [p.name for p in (imgs / "agg").iterdir()] == [out.name]
    text = out.read_text()
    for q in QS:
        for field in ("id", "question", "answer", "image_id"):
            assert q[field] not in text and q[field] not in printed
    rep = json.loads(text)
    assert rep["questions"] == 2 and rep["overall"] == 1.0
    assert rep["by_images"]["split"] == "private" and "ci95" in rep["by_images"]["non_duplicate_images"]
    assert rep["prompt_id"] == b1.prompt_id("v1") and rep["model"] == "claude-sonnet-5-5"
    assert rep["judge_prompt_id"].startswith("judge/v1@") and sdk.judged == 1
    assert set(rep["by_feature"]) >= {"meaning", "vehicle_class", "no_feature"}


def test_the_kept_answers_are_model_outputs_only(imgs, capsys):
    _full_private(imgs, capsys)
    files = list((imgs / "private_run").glob("b1_sonnet_*/answers.jsonl"))
    assert len(files) == 1
    rows = [json.loads(l) for l in files[0].read_text().splitlines()]
    assert all(set(r) == set(b1.ANSWER_FIELDS) for r in rows)
    assert "secret-gold" not in files[0].read_text()


def test_the_sentinel_is_finished_after_collect_and_collect_runs_once(imgs, capsys):
    out, sdk, _ = _full_private(imgs, capsys)
    mark = json.loads((imgs / "baseline_ran_b1_sonnet.json").read_text())
    assert mark["status"] == "finished" and mark["report"] == out.name
    with pytest.raises(SystemExit, match="finished, not submitted"):
        _collect(imgs, sdk)


def test_collect_private_refuses_another_question_order(imgs):
    _pin(imgs)
    sdk = FakeSDK(["Có.", "Cấm xe máy."])
    _submit(imgs, sdk)
    with pytest.raises(SystemExit, match="not in the order"):
        _collect(imgs, sdk, questions=list(reversed(QS)))


def test_a_wrong_yes_no_and_a_judged_wrong_answer_score_zero(imgs, capsys):
    out, _, _ = _full_private(imgs, capsys, answers=("Không.", "Cấm ô tô."),
                              judge=[{"label": "wrong", "reason": "x"}])
    rep = json.loads(out.read_text())
    assert rep["overall"] == 0.0 and rep["judge_labels"] == {"wrong": 1}


def test_the_baseline_module_never_names_the_private_question_file():
    src = (b1.ROOT / "eval" / "baseline_b1.py").read_text(encoding="utf-8")
    assert "vlsp_2025_private_test" not in src
