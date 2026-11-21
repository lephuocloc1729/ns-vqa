"""Streaming the writer's answer text: the field decoder, the client's stream path, the
writer's events, and the API's token events. Streaming must never change an answer."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import vqa.pipeline as pl
from vqa.answer.stream import FieldStream
from vqa.answer.writer import AnswerWriter
from vqa.llm.client import LLMClient
from vqa.llm.spend import SpendGuard
from vqa.schemas import Answer, Verdict

from tests.test_pipeline import PROG_YES, Q_YES, WRITER_YES, RoutedSDK, warm


def chunks(text: str, n: int) -> list[str]:
    return [text[i:i + n] for i in range(0, len(text), n)]


# ---------------------------------------------------------------------- the field decoder
@pytest.mark.parametrize("n", [1, 2, 3, 5, 7, 1000])
def test_the_answer_field_decodes_the_same_in_any_chunking(n):
    reply = json.dumps({"verdict": "yes", "answer": 'Có. Biển "P.103a"\nCấm ô tô \\ 6:00–22:00 😀',
                        "cited_signs": ["s1"]}, ensure_ascii=True)       # \uXXXX escapes, a surrogate pair
    fs = FieldStream()
    got = "".join(fs.feed(c) for c in chunks(reply, n))
    assert got == json.loads(reply)["answer"] and fs.done


def test_the_field_may_come_after_others_and_inside_a_fence():
    reply = '```json\n{"cited_rules": ["r"], "answer": "Không.", "verdict": "no"}\n```'
    fs = FieldStream()
    assert "".join(fs.feed(c) for c in chunks(reply, 4)) == "Không."


def test_nothing_is_decoded_without_the_field_or_after_its_end():
    fs = FieldStream()
    assert fs.feed('{"verdict": "yes", "cited_signs": []}') == "" and not fs.done
    fs = FieldStream()
    assert fs.feed('{"answer": "A", "x": "B"}') == "A" and fs.feed('"more"') == ""


# ---------------------------------------------------------------------- a streaming fake SDK
class StreamingSDK(RoutedSDK):
    """RoutedSDK with messages.stream: the same reply, delivered in small text chunks."""

    def __init__(self, chunk=5, **replies):
        super().__init__(**replies)
        self.chunk, self.streamed = chunk, []

    def stream(self, **kw):
        resp = self.create(**kw)
        self.streamed.append(self.created[-1][0])
        text = resp.content[0].text
        sdk = self

        class _Stream:
            text_stream = iter(chunks(text, sdk.chunk))
            request_id = "req_stream"

            def get_final_message(self):
                return resp

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False
        return _Stream()


def writer_with(sdk):
    return AnswerWriter(llm=LLMClient(model="claude-haiku-5-5", guard=SpendGuard(1.0), sdk=sdk), version="v3")


ANSWER_YES = Answer(verdict=Verdict.yes)
# a reply the faithfulness guard accepts for a scene-less "yes" answer (WRITER_YES cites a scene sign)
GOOD = {"verdict": "yes", "answer": "Có, ô tô bị cấm \"6:00–22:00\".", "cited_signs": [], "cited_rules": []}


# ---------------------------------------------------------------------- the client
def test_the_client_streams_and_returns_the_same_result(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    kw = dict(system="You write the final answer x", user="q", max_tokens=100, purpose="answer")
    plain = LLMClient(model="claude-haiku-5-5", guard=SpendGuard(1.0), sdk=RoutedSDK(writer=[WRITER_YES]))
    a = plain.json_reply(**kw)
    sdk = StreamingSDK(writer=[WRITER_YES])
    got: list[str] = []
    b = LLMClient(model="claude-haiku-5-5", guard=SpendGuard(1.0), sdk=sdk).json_reply(on_text=got.append, **kw)
    assert sdk.streamed == ["writer"] and len(got) > 3 and "".join(got) == b.raw_text
    assert (a.data, a.cost_usd, a.usage, a.raw_text) == (b.data, b.cost_usd, b.usage, b.raw_text)
    log = [json.loads(ln) for ln in (tmp_path / "logs" / "api_calls.jsonl").read_text().splitlines()]
    assert [r["status"] for r in log] == ["ok", "ok"]


def test_without_a_listener_the_client_never_streams(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    sdk = StreamingSDK(writer=[WRITER_YES])
    LLMClient(model="claude-haiku-5-5", guard=SpendGuard(1.0), sdk=sdk).json_reply(
        system="You write the final answer x", user="q", purpose="answer")
    assert sdk.streamed == [] and sdk.roles() == ["writer"]


def test_a_failing_listener_does_not_fail_the_call(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))

    def bad(_):
        raise RuntimeError("display broke")
    r = LLMClient(model="claude-haiku-5-5", guard=SpendGuard(1.0), sdk=StreamingSDK(writer=[WRITER_YES])).json_reply(
        system="You write the final answer x", user="q", purpose="answer", on_text=bad)
    assert r.data == WRITER_YES


# ---------------------------------------------------------------------- the writer
def test_the_writer_streams_its_answer_text_and_ships_the_same_result(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    base = writer_with(RoutedSDK(writer=[GOOD])).write(Q_YES, ANSWER_YES, None)
    assert base.status == "first_try"
    w = writer_with(StreamingSDK(writer=[GOOD]))
    events: list[tuple[str, dict]] = []
    w.on_event = lambda k, p: events.append((k, p))
    res = w.write(Q_YES, ANSWER_YES, None)
    assert (res.status, res.text, res.cited_signs, res.verdict) == (base.status, base.text, base.cited_signs, base.verdict)
    assert {k for k, _ in events} == {"delta"} and "".join(p["text"] for _, p in events) == res.text


def test_a_rejected_first_reply_is_withdrawn_before_the_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    wrong = {**WRITER_YES, "verdict": "no", "answer": "Không. Ô tô được đi."}      # fails the guard
    w = writer_with(StreamingSDK(writer=[wrong, GOOD]))
    events: list[tuple[str, dict]] = []
    w.on_event = lambda k, p: events.append((k, p))
    res = w.write(Q_YES, ANSWER_YES, None)
    assert res.status == "regenerated"
    reset = events.index(("reset", {"attempt": 1, "reason": "retry"}))
    assert all(p["attempt"] == 1 for k, p in events[:reset]) and "".join(p["text"] for _, p in events[:reset]) == wrong["answer"]
    assert "".join(p["text"] for k, p in events[reset + 1:]) == res.text


def test_the_template_answer_withdraws_the_streamed_text(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    wrong = {**WRITER_YES, "verdict": "no", "answer": "Không."}
    w = writer_with(StreamingSDK(writer=[wrong, wrong]))
    events: list[tuple[str, dict]] = []
    w.on_event = lambda k, p: events.append((k, p))
    res = w.write(Q_YES, ANSWER_YES, None)
    assert res.status == "template" and events[-1] == ("reset", {"attempt": 2, "reason": "template"})


# ---------------------------------------------------------------------- the API
def test_the_api_streams_tokens_and_the_answer_is_unchanged(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.main import create_app
    from app.api.settings import Settings
    from tests.test_api import ask, jpeg, sse_events

    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(jpeg())
    cache = warm(tmp_path, photo)
    cfg = pl.PipelineConfig(cache_dir=cache, cache_only=True, max_spend=1.0)
    direct = pl.Pipeline(cfg, sdk=RoutedSDK(parser=[PROG_YES], writer=[WRITER_YES])).answer(photo, Q_YES)
    pipe = pl.Pipeline(cfg, sdk=StreamingSDK(parser=[PROG_YES], writer=[WRITER_YES]))
    s = Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "up", heartbeat_s=0.2)
    c = TestClient(create_app(s, pipeline_factory=lambda: pipe))
    ev = sse_events(ask(c, path="/v1/ask/stream", image=photo.read_bytes()).text)
    names = [n for n, _ in ev]
    tokens = [d["text"] for n, d in ev if n == "token"]
    assert len(tokens) > 3 and "".join(tokens) == direct.text
    assert names.index("route") < names.index("token") and names[-2:] == ["answer", "done"]
    answer = dict(ev)["answer"]
    assert (answer["answer"], answer["verdict"], answer["citations"]) == (direct.text, direct.verdict, direct.citations)
