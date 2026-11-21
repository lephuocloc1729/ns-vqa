"""The RAG answer fallback (vqa/answer/rag_fallback.py, plan F3) and its wiring in the API.
The RAG service is faked with an in-memory httpx transport: no network, no GPU."""

from __future__ import annotations

import json

import httpx
import pytest

import vqa.pipeline as pl
from vqa.answer.rag_fallback import RagFallback, verdict_of

from tests.test_pipeline import RoutedSDK, warm

OOS = {"program": None, "out_of_scope": True, "out_of_scope_reason": "guide sign"}
REPLY = {"answer": "Biển chỉ đường đến Hà Nội.", "config_version": "rag-c@ac78ebff0dcf", "gate": "high",
         "citations": [{"law_id": "QCVN 41:2024/BGTVT", "article_id": "I.414", "rank": 1, "score": 0.81,
                        "text": "Biển chỉ hướng đường..."}],
         "timings": {"total": 7.2}, "usage": {"completion_tokens": 60}}


def transport(reply=REPLY, status=200, stream_tokens=("Biển chỉ ", "đường đến Hà Nội.")):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"detail": "down"})
        if request.url.path == "/answer/stream":
            body = "".join(f"event: token\ndata: {json.dumps({'text': t}, ensure_ascii=False)}\n\n" for t in stream_tokens)
            body += f"event: answer\ndata: {json.dumps(reply, ensure_ascii=False)}\n\nevent: done\ndata: {{}}\n\n"
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json=reply)
    t = httpx.MockTransport(handler)
    t.seen = seen
    return t


@pytest.fixture
def photo(tmp_path, monkeypatch):
    from tests.test_api import jpeg
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    p = tmp_path / "photo.jpg"
    p.write_bytes(jpeg())
    return p


# ---------------------------------------------------------------------- the client
def test_an_answer_comes_back_as_a_fallback_answer(photo):
    t = transport()
    fa = RagFallback("http://rag", transport=t).answer(photo, "Biển chỉ đường đi đâu?", scene=None)
    assert (fa.status, fa.text, fa.verdict, fa.prompt_id, fa.cost_usd) == \
        ("ok", REPLY["answer"], "value", "rag-c@ac78ebff0dcf", 0.0)
    assert json.loads(fa.raw[0])["retrieved"][0]["article_id"] == "I.414"
    sent = t.seen[0]
    assert sent.url.path == "/answer" and b"scene" not in sent.content         # image and question only (G4)


@pytest.mark.parametrize("status,reply,error", [
    (503, REPLY, "HTTPStatusError"),
    (200, {**REPLY, "answer": "  "}, "empty answer"),
])
def test_a_failed_service_gives_a_failed_fallback(photo, status, reply, error):
    fa = RagFallback("http://rag", transport=transport(reply, status)).answer(photo, "q?", None)
    assert fa.status == "failed" and error in fa.errors[0][0]


def test_an_unreachable_service_gives_a_failed_fallback(photo):
    def refuse(request):
        raise httpx.ConnectError("refused")
    fa = RagFallback("http://rag", transport=httpx.MockTransport(refuse)).answer(photo, "q?", None)
    assert fa.status == "failed" and "ConnectError" in fa.errors[0][0]


def test_streaming_passes_the_answer_text_on(photo):
    f = RagFallback("http://rag", transport=transport())
    events = []
    f.on_event = lambda k, p: events.append((k, p))
    fa = f.answer(photo, "Biển chỉ đường đi đâu?", None)
    assert fa.status == "ok" and "".join(p["text"] for _, p in events) == REPLY["answer"]
    assert {k for k, _ in events} == {"delta"}


@pytest.mark.parametrize("question,text,verdict", [
    ("Xe ô tô được đi vào, đúng hay sai?", "Đúng. Biển cho phép ô tô.", "yes"),
    ("Xe ô tô được đi vào, đúng hay sai?", "Sai, ô tô bị cấm.", "no"),
    ("Ô tô có được rẽ trái không?", "Không, biển cấm rẽ trái.", "no"),
    ("Ô tô có được rẽ trái không?", "Có, được rẽ trái.", "yes"),
    ("Đây là biển gì?", "Biển cấm đỗ xe.", "value"),
])
def test_the_verdict_follows_the_answer(question, text, verdict):
    assert verdict_of(question, text) == verdict


# ---------------------------------------------------------------------- in the pipeline
def pipe_with_rag(tmp_path, photo, rag_transport, **replies):
    p = pl.Pipeline(pl.PipelineConfig(cache_dir=warm(tmp_path, photo), cache_only=True, max_spend=1.0),
                    sdk=RoutedSDK(**replies))
    p.fallback = RagFallback("http://rag", transport=rag_transport)
    return p


def test_the_pipeline_ships_the_rag_answer_as_a_fallback_answer(tmp_path, photo):
    a = pipe_with_rag(tmp_path, photo, transport(), parser=[OOS]).answer(photo, "Biển chỉ đường đi đâu?")
    assert (a.answered_by, a.text, a.citations) == ("fallback", REPLY["answer"], [])   # no rule citations
    assert a.trace["fallback"]["status"] == "ok" and a.trace["fallback"]["prompt_id"].startswith("rag-c@")


def test_a_failed_rag_ships_the_engines_answer_through_the_writer(tmp_path, photo):
    prog = {"program": {"intent": "permitted", "action": "enter", "vehicle": {"vehicle_class": "car"}}}
    unk = {"verdict": "unknown", "answer": "Chưa xác định được: còn tùy giờ.", "cited_signs": ["s1"],
           "cited_rules": []}
    a = pipe_with_rag(tmp_path, photo, transport(status=503), parser=[prog], writer=[unk]).answer(
        photo, "Ô tô có được đi vào không?")
    assert (a.answered_by, a.verdict, a.trace["fallback"]["status"]) == ("rules", "unknown", "failed")


# ---------------------------------------------------------------------- in the API
def test_the_api_streams_the_rag_answer_and_keeps_its_laws_apart(tmp_path, photo):
    from fastapi.testclient import TestClient

    from app.api.main import create_app
    from app.api.settings import Settings
    from tests.test_api import ask, sse_events

    pipe = pipe_with_rag(tmp_path, photo, transport(), parser=[OOS])
    s = Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "up", heartbeat_s=0.2,
                 answer_fallback="rag")
    c = TestClient(create_app(s, pipeline_factory=lambda: pipe))
    ev = sse_events(ask(c, path="/v1/ask/stream", image=photo.read_bytes(), question="Biển chỉ đường đi đâu?").text)
    names = [n for n, _ in ev]
    assert ("route", "fallback") in [(n, d.get("to")) for n, d in ev]
    assert "".join(d["text"] for n, d in ev if n == "token") == REPLY["answer"]
    a = dict(ev)["answer"]
    assert (a["answered_by"], a["basis"], a["citations"]) == ("fallback", ["fallback", "rag"], [])
    assert a["retrieved"][0]["article_id"] == "I.414" and names[-2:] == ["answer", "done"]


def test_rag_settings():
    from app.api.profiles import pipeline_config
    from app.api.settings import Settings
    s = Settings(answer_fallback="rag", rag_url="http://gpu:8100")
    assert pipeline_config(s).answer_fallback is True and s.rag_url == "http://gpu:8100"
    with pytest.raises(ValueError):
        Settings(answer_fallback="gpt")


def test_an_older_database_gets_the_new_column(tmp_path):
    import sqlite3

    from app.api.storage import Store
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE chat_session (id VARCHAR(32) PRIMARY KEY, created_at DATETIME)")
    con.execute("CREATE TABLE turn (id VARCHAR(32) PRIMARY KEY, session_id VARCHAR(32), created_at DATETIME, "
                "question TEXT, image_sha256 VARCHAR(64), status VARCHAR(16))")
    con.commit()
    con.close()
    store = Store(f"sqlite:///{db}")
    sid = store.new_session().id
    t = store.start_turn(sid, "q", "0" * 64)
    assert store.finish_turn(t.id, status="done", retrieved=[{"article_id": "B.1"}]).retrieved == [{"article_id": "B.1"}]
