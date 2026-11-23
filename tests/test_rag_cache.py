"""The cache of the RAG fallback's own answers (app/api/rag_cache.py). No GPU, no RAG service."""

from __future__ import annotations

import json
import os
import time

import pytest

from app.api.rag_cache import CachedRagFallback, RagAnswerCache, main
from vqa.answer.fallback import FallbackAnswer

V1 = {"config_version": "rag-c@aaa", "llama_parallel": 1}


class FakeRag:
    """Answers from the photo and the question; counts its calls."""

    url = "http://rag.test"

    def __init__(self, status="ok"):
        self.on_event, self.prompt_id, self.calls, self.status = None, "rag", 0, status

    def answer(self, image_path, question, scene):
        self.calls += 1
        if self.status != "ok":
            return FallbackAnswer(status="failed", attempts=1, errors=[["down"]], prompt_id="rag")
        text = f"Trả lời {self.calls} cho {question.strip()}"
        record = {"config_version": "rag-c@aaa", "retrieved": [{"law_id": "QCVN 41:2024/BGTVT", "article_id": "B.3"}]}
        if self.on_event:
            self.on_event("delta", {"text": text})
        self.prompt_id = "rag-c@aaa"
        return FallbackAnswer(status="ok", verdict="no", text=text, attempts=1,
                              raw=[json.dumps(record, ensure_ascii=False)], prompt_id="rag-c@aaa")


@pytest.fixture
def photo(tmp_path):
    p = tmp_path / "a.jpg"
    p.write_bytes(b"photo-a")
    return p


def cached(tmp_path, inner=None, version=V1, **kw):
    inner = inner or FakeRag()
    box = {"v": version}

    def fetch():
        if isinstance(box["v"], Exception):
            raise box["v"]
        return box["v"]
    fb = CachedRagFallback(inner, RagAnswerCache(tmp_path / "cache", **kw), version_ttl_s=0, fetch_version=fetch)
    return fb, inner, box


def test_a_repeated_question_is_answered_from_the_first_answer(tmp_path, photo):
    fb, inner, _ = cached(tmp_path)
    first = fb.answer(photo, "Xe ô tô có được đi vào không?", None)
    events = []
    fb.on_event = lambda kind, payload: events.append((kind, payload))
    again = fb.answer(photo, "  Xe ô tô có được đi vào không?  ", None)      # trimmed: the same question
    assert inner.calls == 1                                                  # the RAG ran once
    assert (again.text, again.verdict, again.status) == (first.text, first.verdict, "ok")
    assert again.cost_usd == 0.0 and json.loads(again.raw[-1])["cache_hit"] is True
    assert json.loads(again.raw[-1])["retrieved"][0]["article_id"] == "B.3"   # the laws it used, kept
    assert events == [("delta", {"text": first.text})]                       # still streamed
    assert (fb.hits, fb.misses) == (1, 1)


def test_another_question_another_photo_or_another_rag_version_is_asked_fresh(tmp_path, photo):
    fb, inner, box = cached(tmp_path)
    fb.answer(photo, "Câu một?", None)
    fb.answer(photo, "Câu hai?", None)                                       # another question
    other = tmp_path / "b.jpg"
    other.write_bytes(b"photo-b")
    fb.answer(other, "Câu một?", None)                                       # another photo
    box["v"] = {"config_version": "rag-c@bbb", "llama_parallel": 1}
    fb.answer(photo, "Câu một?", None)                                       # another RAG version
    assert inner.calls == 4


def test_failed_answers_and_answers_made_with_several_slots_are_not_kept(tmp_path, photo):
    fb, inner, _ = cached(tmp_path, inner=FakeRag(status="failed"))
    fb.answer(photo, "Câu?", None)
    fb.answer(photo, "Câu?", None)
    assert inner.calls == 2
    fb, inner, _ = cached(tmp_path / "x", version={"config_version": "rag-c@aaa", "llama_parallel": 2})
    fb.answer(photo, "Câu?", None)
    fb.answer(photo, "Câu?", None)
    assert inner.calls == 2                                                  # batching changes answers


def test_cached_answers_still_serve_when_the_rag_cannot_be_reached(tmp_path, photo):
    fb, inner, box = cached(tmp_path)
    first = fb.answer(photo, "Câu?", None)
    box["v"] = ConnectionError("GPU not rented")                            # the last version seen is used
    assert fb.answer(photo, "Câu?", None).text == first.text and inner.calls == 1


def test_a_rag_never_reached_is_not_cached(tmp_path, photo):
    fb, inner, _ = cached(tmp_path, version=ConnectionError("no RAG"))
    fb.answer(photo, "Câu?", None)
    fb.answer(photo, "Câu?", None)
    assert inner.calls == 2


def test_the_cache_keeps_the_newest_entries_and_can_expire(tmp_path):
    c = RagAnswerCache(tmp_path / "c", max_entries=3)
    for i in range(5):
        c.put(f"k{i}", {"answer": {"status": "ok"}})
        os.utime(c._path(f"k{i}"), (time.time() + i, time.time() + i))
    assert c.trim() == 2 and sorted(p.stem for p in c.entries()) == ["k2", "k3", "k4"]
    old = RagAnswerCache(tmp_path / "c", max_days=1)
    os.utime(old._path("k2"), (time.time() - 2 * 86400, time.time() - 2 * 86400))
    assert old.get("k2") is None and old.get("k3") is not None


def test_clear_and_stats(tmp_path, capsys):
    c = RagAnswerCache(tmp_path / "c")
    c.put("k", {"answer": {"status": "ok"}})
    main(["stats", str(tmp_path / "c")])
    main(["clear", str(tmp_path / "c")])
    out = capsys.readouterr().out
    assert "1 cached RAG answers" in out and "removed 1" in out and c.entries() == []


def test_the_api_caches_the_rag_by_default_and_can_turn_it_off(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.main import create_app
    from app.api.settings import Settings

    def version(**kw):
        s = Settings(database_url=f"sqlite:///{tmp_path / 'a.db'}", upload_dir=tmp_path / "up", **kw)
        return TestClient(create_app(s)).get("/version").json()["rag_cache"]
    assert version() is False                                                # no RAG fallback, no cache
    assert version(answer_fallback="rag") is True                            # on by default for the RAG
    assert version(answer_fallback="rag", rag_cache=False) is False          # VQA_RAG_CACHE=off
    assert version(answer_fallback="claude") is False                        # the Sonnet fallback: never


def test_the_runner_streams_a_hit_and_the_pipeline_sees_a_rag_answer(tmp_path, photo):
    """The wrapper keeps the RagFallback interface the runner instruments (on_event, answer)."""
    from app.api.runner import PipelineRunner

    fb, inner, _ = cached(tmp_path)

    class Pipe:
        def __init__(self):
            self.fallback = fb

        def answer(self, image_path, question):
            return self.fallback.answer(image_path, question, None)

    runner = PipelineRunner(lambda: Pipe())
    out = []
    for _ in range(2):
        ev = []
        a = runner.submit(photo, "Câu?", lambda n, p: ev.append((n, p))).result(timeout=10)
        out.append((a, ev))
    (a1, ev1), (a2, ev2) = out
    assert inner.calls == 1 and a1.text == a2.text
    assert [n for n, _ in ev2 if n != "started"] == ["route", "token"]
    assert "".join(p["text"] for n, p in ev2 if n == "token") == a2.text


def test_the_setting_reads_on_by_default_and_off_when_asked(monkeypatch):
    from app.api.settings import Settings
    monkeypatch.delenv("VQA_RAG_CACHE", raising=False)
    assert Settings.from_env().rag_cache is True
    for off in ("off", "0", "false", "OFF"):
        monkeypatch.setenv("VQA_RAG_CACHE", off)
        assert Settings.from_env().rag_cache is False


def test_the_stored_turn_and_the_metrics_show_a_cache_hit(tmp_path, monkeypatch):
    """Through the API and the real pipeline: the repeat is answered from the cache, and the stored
    turn (raw replies are not stored) and /metrics say so."""
    import io
    from types import SimpleNamespace

    from fastapi.testclient import TestClient
    from PIL import Image

    import vqa.pipeline as pl
    from app.api.main import create_app
    from app.api.settings import Settings
    from test_api import sse_events
    from test_pipeline import warm

    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (90, 120, 200)).save(buf, format="JPEG")
    photo = tmp_path / "p.jpg"
    photo.write_bytes(buf.getvalue())
    scenes = warm(tmp_path, photo)

    class SDK:                                    # the parser sends every question to the fallback
        messages = property(lambda self: self)

        def count_tokens(self, **kw):
            return SimpleNamespace(input_tokens=100)

        def create(self, **kw):
            r = {"program": None, "out_of_scope": True, "out_of_scope_reason": "law text"}
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(r))], stop_reason="end_turn",
                                   stop_details=None, _request_id="r",
                                   usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0,
                                                         cache_creation_input_tokens=0))

    fb, inner, _ = cached(tmp_path)

    def make():
        pipe = pl.Pipeline(pl.PipelineConfig(cache_dir=scenes, cache_only=True, max_spend=1.0), sdk=SDK())
        pipe.fallback = fb
        return pipe

    s = Settings(database_url=f"sqlite:///{tmp_path / 'a.db'}", upload_dir=tmp_path / "up", answer_fallback="rag")
    c = TestClient(create_app(s, pipeline_factory=make))
    hits = []
    for _ in range(2):
        ev = dict(sse_events(c.post("/v1/ask/stream", data={"question": "Biển này nghĩa là gì?"},
                                    files={"image": ("p.jpg", photo.read_bytes(), "image/jpeg")}).text))
        assert ev["answer"]["answered_by"] == "fallback" and "rag" in ev["answer"]["basis"]
        turn = c.get(f"/v1/turns/{ev['turn']['turn_id']}").json()
        hits.append(turn["stages"]["fallback"]["cache_hit"])
    assert hits == [False, True] and inner.calls == 1
    body = c.get("/metrics").text
    assert 'vqa_rag_cache_total{result="miss"} 1.0' in body and 'vqa_rag_cache_total{result="hit"} 1.0' in body
