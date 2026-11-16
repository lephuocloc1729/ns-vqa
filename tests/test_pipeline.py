"""Phase-4 item 3: the pipeline, end to end with a fake SDK (no API call) and a
hand-made scene-cache record. Routes each call by its system prompt."""

from __future__ import annotations

import hashlib
import inspect
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

import vqa.pipeline as pl
from vqa.perception import prompt as sp
from vqa.perception.cache import CacheRecord, SceneCache

# A hand-made pass-1 reply modelled on train_181 (P.103a, 6:00-22:00), one sign, high
# confidence: no re-run, no tiles, no crops.
SCENE_REPLY = json.dumps({"signs": [{"code": "P.103a", "shape": "circle", "border": "red",
                                     "background": "white", "rank": 1, "side": "right", "confidence": "high",
                                     "plates": [{"kind": "time", "text": "6:00-22:00",
                                                 "time_windows": [{"start": "06:00", "end": "22:00"}]}]}],
                          "road": {"type": "urban"}, "vehicles": []})
Q_YES = "Đường này có cấm ô tô từ 6:00 đến 22:00 không?"
PROG_YES = {"program": {"intent": "forbidden", "action": "enter", "vehicle": {"vehicle_class": "car"},
                        "when": {"start": "06:00", "end": "22:00", "quantifier": "all"}}}
WRITER_YES = {"verdict": "yes", "answer": "Có. Biển P.103a (Cấm xe ô tô) có biển phụ 6:00-22:00.",
              "cited_signs": ["s1"], "cited_rules": ["r_prohibition"]}


class RoutedSDK:
    """Replies by role: parser, writer, fallback, perception (system prompt prefix)."""

    def __init__(self, **replies):
        self.replies = {k: list(v) for k, v in replies.items()}
        self.created: list[tuple[str, dict]] = []
        self.messages = self

    @staticmethod
    def role(kw) -> str:
        s = kw["system"][0]["text"]
        if s.startswith("You write the final answer"):
            return "writer"
        if s.startswith("You answer Vietnamese questions"):
            return "fallback"
        if s.startswith("# Task\n\nYou turn one Vietnamese question"):
            return "parser"
        return "perception"

    def count_tokens(self, **kw):
        return SimpleNamespace(input_tokens=3000)

    def create(self, **kw):
        role = self.role(kw)
        self.created.append((role, kw))
        text = self.replies[role].pop(0)
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
                               stop_details=None, _request_id="req_t",
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=80,
                                                     cache_read_input_tokens=2000, cache_creation_input_tokens=0))

    def roles(self):
        return [r for r, _ in self.created]


@pytest.fixture
def photo(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (90, 120, 200)).save(buf, format="JPEG")
    p = tmp_path / "photo.jpg"
    p.write_bytes(buf.getvalue())
    return p


def warm(tmp_path, photo, reply=SCENE_REPLY):
    d = tmp_path / "warm"
    sha = hashlib.sha256(photo.read_bytes()).hexdigest()
    m = "claude-haiku-5-5"
    SceneCache(d).put(CacheRecord(sha, m, sp.effort_for(m, "v4"), sp.prompt_id("v4"),
                                  replies=[{"pass": "first", "raw_text": reply, "stop_reason": "end_turn",
                                            "usage": {}, "cost_usd": 0.0, "request_id": "r1"}]))
    return d


def pipeline(tmp_path, sdk, cache_dir, cache_only=True):
    return pl.Pipeline(pl.PipelineConfig(cache_dir=cache_dir, cache_only=cache_only, max_spend=1.0), sdk=sdk)


def test_answer_takes_an_image_path_and_a_question_only():
    assert list(inspect.signature(pl.answer).parameters) == ["image_path", "question"]
    assert list(inspect.signature(pl.Pipeline.answer).parameters) == ["self", "image_path", "question"]


def test_rules_path_parser_engine_writer(tmp_path, photo):
    sdk = RoutedSDK(parser=[PROG_YES], writer=[WRITER_YES])
    a = pipeline(tmp_path, sdk, warm(tmp_path, photo)).answer(photo, Q_YES)
    assert sdk.roles() == ["parser", "writer"]                       # no perception call
    assert (a.answered_by, a.verdict, a.text) == ("rules", "yes", WRITER_YES["answer"])
    assert a.basis[0] == "rules" and "QCVN 41:2024/BGTVT B.3" in a.citations
    assert a.trace["perception"]["cache_hit"] and a.trace["fallback"]["trigger"] is None
    assert a.trace["writer"]["status"] == "first_try" and a.proof["verdict"] == "yes"
    assert a.cost_usd > 0 and a.seconds >= 0
    parser_user = sdk.created[0][1]["messages"][0]["content"]
    assert parser_user == f"Question: {Q_YES}"                        # D7: the question only


def test_out_of_scope_goes_to_the_fallback(tmp_path, photo):
    sdk = RoutedSDK(parser=[{"program": None, "out_of_scope": True, "out_of_scope_reason": "guide sign"}],
                    fallback=[{"verdict": "value", "answer": "Hà Nội."}])
    a = pipeline(tmp_path, sdk, warm(tmp_path, photo)).answer(photo, "Biển chỉ đường đi đâu?")
    assert sdk.roles() == ["parser", "fallback"]
    assert (a.answered_by, a.basis, a.citations, a.text) == ("fallback", ["fallback"], [], "Hà Nội.")
    assert (a.trace["fallback"]["trigger"], a.trace["fallback"]["status"]) == ("out_of_scope", "ok")
    content = sdk.created[1][1]["messages"][0]["content"]
    assert content[0]["type"] == "image" and "P.103a" in content[1]["text"]


def test_an_unknown_verdict_goes_to_the_fallback(tmp_path, photo):
    prog = {"program": {"intent": "permitted", "action": "enter", "vehicle": {"vehicle_class": "car"}}}
    sdk = RoutedSDK(parser=[prog], fallback=[{"verdict": "no", "answer": "Không."}])
    a = pipeline(tmp_path, sdk, warm(tmp_path, photo)).answer(photo, "Ô tô có được đi vào không?")
    assert a.trace["engine"]["verdict"] == "unknown" and a.trace["fallback"]["trigger"] == "unknown"
    assert a.answered_by == "fallback"


def test_a_failed_fallback_ships_the_engine_answer_through_the_writer(tmp_path, photo):
    prog = {"program": {"intent": "permitted", "action": "enter", "vehicle": {"vehicle_class": "car"}}}
    unk = {"verdict": "unknown", "answer": "Chưa xác định được: còn tùy giờ.", "cited_signs": ["s1"],
           "cited_rules": []}
    sdk = RoutedSDK(parser=[prog], fallback=["prose", "prose"], writer=[unk])
    a = pipeline(tmp_path, sdk, warm(tmp_path, photo)).answer(photo, "Ô tô có được đi vào không?")
    assert sdk.roles() == ["parser", "fallback", "fallback", "writer"]
    assert (a.answered_by, a.verdict) == ("rules", "unknown")
    assert a.trace["fallback"]["status"] == "failed"                  # P3, counted as a failure


def test_a_failed_parse_and_failed_fallback_still_give_an_unknown_answer(tmp_path, photo):
    sdk = RoutedSDK(parser=["prose", "prose"], fallback=["prose", "prose"], writer=["prose", "prose"])
    a = pipeline(tmp_path, sdk, warm(tmp_path, photo)).answer(photo, "?")
    assert a.trace["fallback"]["trigger"] == "parse_failed"
    assert (a.verdict, a.trace["writer"]["status"]) == ("unknown", "template")
    assert a.text.startswith("Chưa xác định được")


def test_cache_only_refuses_an_image_with_no_pass1_record(tmp_path, photo):
    sdk = RoutedSDK()
    with pytest.raises(pl.CacheMissError):
        pipeline(tmp_path, sdk, tmp_path / "empty").answer(photo, Q_YES)
    assert sdk.created == []


def test_without_cache_only_perception_calls_the_model(tmp_path, photo):
    sdk = RoutedSDK(perception=[SCENE_REPLY], parser=[PROG_YES], writer=[WRITER_YES])
    a = pipeline(tmp_path, sdk, tmp_path / "fresh", cache_only=False).answer(photo, Q_YES)
    assert sdk.roles() == ["perception", "parser", "writer"] and a.verdict == "yes"
    assert not a.trace["perception"]["cache_hit"]


def test_the_spend_guard_is_shared_across_stages(tmp_path, photo):
    p = pipeline(tmp_path, RoutedSDK(), warm(tmp_path, photo))
    assert p.parser.llm.guard is p.writer.llm.guard is p.fallback.llm.guard is p.guard


def test_the_trace_keeps_the_raw_writer_and_fallback_replies(tmp_path, photo):
    """T1 (owner, 2026-11-16): the writer's reply text of every attempt is kept."""
    sdk = RoutedSDK(parser=[PROG_YES], writer=[WRITER_YES])
    a = pipeline(tmp_path, sdk, warm(tmp_path, photo)).answer(photo, Q_YES)
    assert a.trace["writer"]["prompt_id"].startswith("answer/v3@")
    assert [json.loads(r) for r in a.trace["writer"]["raw"]] == [WRITER_YES]
    prog = {"program": {"intent": "permitted", "action": "enter", "vehicle": {"vehicle_class": "car"}}}
    sdk = RoutedSDK(parser=[prog], fallback=["prose", {"verdict": "no", "answer": "Không."}])
    a = pipeline(tmp_path, sdk, warm(tmp_path, photo)).answer(photo, "Ô tô có được đi vào không?")
    assert a.trace["fallback"]["raw"][0] == "prose" and len(a.trace["fallback"]["raw"]) == 2


def test_only_the_fallback_call_sends_a_json_schema(tmp_path, photo):
    """T2: the structured-output schema is on the fallback call only (not parser or writer)."""
    prog = {"program": {"intent": "permitted", "action": "enter", "vehicle": {"vehicle_class": "car"}}}
    sdk = RoutedSDK(parser=[prog], fallback=[{"verdict": "no", "answer": "Không."}])
    pipeline(tmp_path, sdk, warm(tmp_path, photo)).answer(photo, "Ô tô có được đi vào không?")
    sdk2 = RoutedSDK(parser=[PROG_YES], writer=[WRITER_YES])
    pipeline(tmp_path, sdk2, warm(tmp_path, photo)).answer(photo, Q_YES)
    calls = sdk.created + sdk2.created
    with_schema = [role for role, kw in calls if "format" in kw.get("output_config", {})]
    assert with_schema == ["fallback"]


# ---------------------------------------------------------------- phase 4.5: fallback off

def pipeline_off(tmp_path, sdk, cache_dir):
    return pl.Pipeline(pl.PipelineConfig(cache_dir=cache_dir, cache_only=True, max_spend=1.0,
                                         answer_fallback=False), sdk=sdk)


def test_the_fallback_is_on_by_default():
    assert pl.PipelineConfig().answer_fallback is True


def test_fallback_off_makes_no_call_for_a_non_decided_question(tmp_path, photo):
    prog = {"program": {"intent": "permitted", "action": "enter", "vehicle": {"vehicle_class": "car"}}}
    sdk = RoutedSDK(parser=[prog])
    a = pipeline_off(tmp_path, sdk, warm(tmp_path, photo)).answer(photo, "Ô tô có được đi vào không?")
    assert sdk.roles() == ["parser"]                                 # no fallback, no writer
    assert (a.answered_by, a.verdict, a.basis, a.citations) == ("not_decided", "unknown", ["not_decided"], [])
    assert a.trace["fallback"] == {"trigger": "unknown", "status": "off"} and a.text.startswith("Chưa xác định")


def test_fallback_off_out_of_scope_gets_an_unknown_that_says_why(tmp_path, photo):
    sdk = RoutedSDK(parser=[{"program": None, "out_of_scope": True, "out_of_scope_reason": "guide sign"}])
    a = pipeline_off(tmp_path, sdk, warm(tmp_path, photo)).answer(photo, "Biển chỉ đường đi đâu?")
    assert sdk.roles() == ["parser"] and a.answered_by == "not_decided" and a.verdict == "unknown"
    assert "outside what the rules model" in a.proof["note"]


def test_fallback_off_leaves_decided_answers_unchanged(tmp_path, photo):
    on = pipeline(tmp_path, RoutedSDK(parser=[PROG_YES], writer=[WRITER_YES]), warm(tmp_path, photo)).answer(photo, Q_YES)
    sdk = RoutedSDK(parser=[PROG_YES], writer=[WRITER_YES])
    off = pipeline_off(tmp_path, sdk, warm(tmp_path, photo)).answer(photo, Q_YES)
    assert sdk.roles() == ["parser", "writer"]
    assert (off.answered_by, off.verdict, off.text, off.citations) == (on.answered_by, on.verdict, on.text, on.citations)
