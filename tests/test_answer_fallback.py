"""Phase-4 item 2: the answer-level fallback (triggers, prompt, reply check, the call
with a fake SDK; no API call)."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from vqa.answer import fallback as fb
from vqa.llm.client import LLMClient
from vqa.llm.spend import SpendGuard
from vqa.perception.wire import PLACEHOLDER
from vqa.schemas import Answer, SceneGraph, Verdict

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural"))
TRAIN_FILE = DATASET_DIR / "dataset" / "train data" / "vlsp_2025_train.json"
V1_SHA = "dd75b41f09cde7e42178e90a6b9d5b6249b52fba195f3d1e1f9fa5bc5350b0da"


# ---------------------------------------------------------------- triggers (D3)

def ans(verdict, **kw):
    return Answer(verdict=verdict, **kw)


@pytest.mark.parametrize("kw, want", [
    (dict(scene_ok=False, parse_status="ok", answer=ans(Verdict.yes)), "perception_failed"),
    (dict(scene_ok=True, parse_status="out_of_scope", answer=None), "out_of_scope"),
    (dict(scene_ok=True, parse_status="invalid", answer=None), "parse_failed"),
    (dict(scene_ok=True, parse_status="error", answer=None), "parse_failed"),
    (dict(scene_ok=True, parse_status="ok", answer=None, engine_error=True), "program_cannot_run"),
    (dict(scene_ok=True, parse_status="ok",
          answer=ans(Verdict.unknown, note="no sign in the scene matches the selector")), "program_cannot_run"),
    (dict(scene_ok=True, parse_status="ok",
          answer=ans(Verdict.unknown, note="expected exactly one sign in the scene")), "program_cannot_run"),
    (dict(scene_ok=True, parse_status="ok", answer=ans(Verdict.unknown, uncertain_signs=["s2"])), "unreadable_sign"),
    (dict(scene_ok=True, parse_status="ok", answer=ans(Verdict.uncertain, uncertain_signs=["s1"])), "uncertain"),
    (dict(scene_ok=True, parse_status="ok", answer=ans(Verdict.unknown)), "unknown"),
    (dict(scene_ok=True, parse_status="ok", answer=ans(Verdict.yes)), None),
    (dict(scene_ok=True, parse_status="ok", answer=ans(Verdict.no)), None),
    (dict(scene_ok=True, parse_status="ok", answer=ans(Verdict.value, value=[1])), None),
])
def test_triggers(kw, want):
    assert fb.trigger(**kw) == want


def test_every_unknown_and_uncertain_verdict_triggers():
    for v in (Verdict.unknown, Verdict.uncertain):
        assert fb.trigger(scene_ok=True, parse_status="ok", answer=ans(v)) in fb.TRIGGERS


# ---------------------------------------------------------------- prompt

def test_prompt_is_pinned_sonnet_and_train_only():
    assert fb.prompt_id("v1") == "answer_fallback/v1@" + V1_SHA[:12], "prompt changed: make a new version"
    assert fb.config("v1")["model"] == "claude-sonnet-5-5"                  # D3
    exs = fb.examples("v1")
    assert exs and all(e["question_id"].startswith("train_") for e in exs)
    for e in exs:
        assert fb.check_reply(e["reply"], e["question"]) == [], e


def test_prompt_never_mentions_law_articles_retrieval():
    text = fb.system_prompt("v1").lower()
    assert "law_db" not in text and "retriev" not in text


def test_examples_use_the_datasets_exact_text_and_answers():
    if not TRAIN_FILE.exists():
        pytest.skip("dataset not available")
    train = {x["id"]: x for x in json.loads(TRAIN_FILE.read_text(encoding="utf-8"))}
    for e in fb.examples("v1"):
        assert e["question"] == train[e["question_id"]]["question"]
        assert e["reply"]["answer"] == train[e["question_id"]]["answer"]


# ---------------------------------------------------------------- reply check

@pytest.mark.parametrize("reply, q, ok", [
    ({"verdict": "yes", "answer": "Có."}, "Có cấm không?", True),
    ({"verdict": "no", "answer": "Có."}, "Có cấm không?", False),
    ({"verdict": "yes", "answer": "Có."}, "Cấm ô tô, đúng hay sai?", False),
    ({"verdict": "yes", "answer": "Đúng."}, "Cấm ô tô, đúng hay sai?", True),
    ({"verdict": "value", "answer": "Cấm đỗ xe."}, "Biển gì?", True),
    ({"verdict": "unknown", "answer": "Không rõ."}, "Biển gì?", False),
    ({"verdict": "maybe", "answer": "x"}, "?", False),
    ({"verdict": "value", "answer": "x", "cited_rules": []}, "?", False),
])
def test_reply_check(reply, q, ok):
    assert (fb.check_reply(reply, q) == []) is ok


# ---------------------------------------------------------------- the call (fake SDK)

class FakeSDK:
    def __init__(self, replies):
        self.replies, self.created = list(replies), []
        self.messages = self

    def count_tokens(self, **kw):
        return SimpleNamespace(input_tokens=3000)

    def create(self, **kw):
        self.created.append(kw)
        text, stop = self.replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop,
                               stop_details=SimpleNamespace(category="test"), _request_id="req_t",
                               usage=SimpleNamespace(input_tokens=1500, output_tokens=60,
                                                     cache_read_input_tokens=1500,
                                                     cache_creation_input_tokens=0))


@pytest.fixture
def photo(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (90, 120, 200)).save(buf, format="JPEG")
    p = tmp_path / "photo.jpg"
    p.write_bytes(buf.getvalue())
    return p


SCENE = SceneGraph.model_validate({"scene_id": "t", "signs": [
    {"id": "s1", "code": "P.131a", "shape": "circle", "border": "red", "background": "blue",
     "position": {"rank_top_down": 1, "side": "right"}}]})


def run(photo, replies, scene=SCENE):
    sdk = FakeSDK(replies)
    f = fb.AnswerFallback(llm=LLMClient(model="claude-sonnet-5-5", sdk=sdk, guard=SpendGuard(1.0)))
    return f.answer(photo, "Biển trong ảnh có ý nghĩa gì?", scene), sdk


def test_one_call_with_image_question_and_scene_graph_only(photo):
    r, sdk = run(photo, [(json.dumps({"verdict": "value", "answer": "Cấm đỗ xe."}, ensure_ascii=False), "end_turn")])
    assert (r.status, r.verdict, r.text, r.attempts) == ("ok", "value", "Cấm đỗ xe.", 1)
    content = sdk.created[0]["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "text"]
    assert "Scene graph:" in content[1]["text"] and "P.131a" in content[1]["text"]


def test_no_scene_is_sent_as_null(photo):
    r, sdk = run(photo, [('{"verdict": "value", "answer": "x"}', "end_turn")], scene=None)
    assert "Scene graph: null" in sdk.created[0]["messages"][0]["content"][1]["text"]


def test_a_bad_reply_gets_one_error_only_retry(photo):
    r, sdk = run(photo, [("Đây là biển cấm đỗ xe.", "end_turn"),
                         ('{"verdict": "value", "answer": "Cấm đỗ xe."}', "end_turn")])
    assert (r.status, r.attempts) == ("ok", 2)
    assert sdk.created[1]["messages"][1] == {"role": "assistant", "content": PLACEHOLDER}


def test_two_failures_or_a_refusal_fail(photo):
    r, _ = run(photo, [("prose", "end_turn"), ("prose", "end_turn")])
    assert (r.status, r.attempts) == ("failed", 2)
    r, sdk = run(photo, [("", "refusal")])
    assert (r.status, r.attempts, len(sdk.created)) == ("failed", 1, 1)
