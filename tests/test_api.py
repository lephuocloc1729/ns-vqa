"""The backend API (app/api): endpoints, streaming, storage and validation.

No API calls: a fake pipeline drives most tests, and one test runs the real Pipeline
with the fake SDK and a warmed scene cache from test_pipeline.py."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import vqa.pipeline as pl
from vqa.llm.spend import SpendLimitExceeded
from vqa.perception.image import native_size
from vqa.schemas import Answer, Position, SceneGraph, Sign, Verdict

from app.api.main import create_app
from app.api.settings import Settings
from tests.test_pipeline import PROG_YES, Q_YES, WRITER_YES, RoutedSDK, warm


def jpeg(w=640, h=480, colour=(90, 120, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(buf, format="JPEG")
    return buf.getvalue()


class FakePipeline:
    """The stage methods the API wraps, called in the pipeline's order."""

    def __init__(self, box=(10, 20, 110, 120), fail: BaseException | None = None):
        self.box, self.fail, self.calls = box, fail, []
        self.engine = SimpleNamespace(answer=self._engine_answer, catalog=None)
        self.parser = SimpleNamespace(parse=self._parse)
        self.writer = SimpleNamespace(write=self._write)
        self.fallback = SimpleNamespace(answer=lambda *a, **k: None)

    def _perceive(self, image_path):
        scene = SceneGraph(scene_id="s", signs=[Sign(id="s1", code="P.103a", position=Position(box=self.box))])
        return SimpleNamespace(ok=True, scene=scene), {"cache_hit": True, "error": None}

    def _parse(self, question):
        self.engine.answer(SceneGraph(scene_id="dry"), None)        # the parser's dry run
        return SimpleNamespace(status="ok", query=None)

    def _engine_answer(self, scene, program):
        return Answer(verdict=Verdict.yes)

    def _write(self, question, answer, scene):
        return SimpleNamespace(text="Có.")

    def answer(self, image_path, question):
        self.calls.append((str(image_path), question))
        if self.fail:
            raise self.fail
        res, _ = self._perceive(image_path)
        self.parser.parse(question)
        ans = self.engine.answer(res.scene, None)
        self.writer.write(question, ans, res.scene)
        return pl.PipelineAnswer(text="Có. Biển P.103a cấm ô tô.", verdict="yes", answered_by="rules",
                                 basis=["rules"], citations=["QCVN 41:2024/BGTVT B.3"],
                                 proof={"verdict": "yes"},
                                 trace={"perception": {"ok": True, "cache_hit": True, "raw": "x"},
                                        "writer": {"status": "first_try", "raw": ["secret"], "cost_usd": 0.001}},
                                 cost_usd=0.002, seconds=1.5)


@pytest.fixture
def make(tmp_path):
    def _make(pipe=None, **kw):
        s = Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "up",
                     heartbeat_s=0.2, **kw)
        pipe = pipe or FakePipeline()
        return TestClient(create_app(s, pipeline_factory=lambda: pipe)), pipe
    return _make


def ask(client, path="/v1/ask", image=None, question=Q_YES, **form):
    return client.post(path, files={"image": ("p.jpg", image if image is not None else jpeg(), "image/jpeg")},
                       data={"question": question, **form})


def sse_events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.split("\n\n"):
        lines = [ln for ln in block.splitlines() if not ln.startswith(":")]
        if not lines:
            continue
        name = next(ln[7:] for ln in lines if ln.startswith("event: "))
        data = json.loads(next(ln[6:] for ln in lines if ln.startswith("data: ")))
        out.append((name, data))
    return out


# ---------------------------------------------------------------------- basics
def test_health_and_version(make):
    c, _ = make()
    assert c.get("/health").json() == {"status": "ok", "database": True, "pipeline_loaded": False}
    v = c.get("/version").json()
    assert v["profile"] == "phase52" and v["answer_fallback"] == "off" and v["pipeline"]["parser_version"] == "v18"
    assert c.get("/openapi.json").status_code == 200 and c.get("/docs").status_code == 200


def test_ask_answers_stores_the_turn_and_serves_the_image(make):
    c, pipe = make()
    r = ask(c)
    assert r.status_code == 200, r.text
    t = r.json()
    assert (t["status"], t["answer"], t["verdict"], t["answered_by"]) == ("done", "Có. Biển P.103a cấm ô tô.", "yes", "rules")
    assert t["citations"] == ["QCVN 41:2024/BGTVT B.3"] and t["proof"] == {"verdict": "yes"}
    assert t["signs"][0]["code"] == "P.103a" and t["cost_usd"] == 0.002
    assert "raw" not in json.dumps(t["stages"])                      # no raw model replies stored
    hist = c.get(f"/v1/sessions/{t['session_id']}/turns").json()
    assert [h["turn_id"] for h in hist] == [t["turn_id"]]
    assert c.get(f"/v1/turns/{t['turn_id']}").json()["answer"] == t["answer"]
    img = c.get(f"/v1/images/{t['image_sha256']}")
    assert img.status_code == 200 and img.content == jpeg()
    assert pipe.calls[0][1] == Q_YES
    assert c.get("/health").json()["pipeline_loaded"] is True


def test_turns_in_one_session_build_its_history(make):
    c, _ = make()
    sid = c.post("/v1/sessions").json()["session_id"]
    for q in ("Câu một?", "Câu hai?"):
        assert ask(c, question=q, session_id=sid).status_code == 200
    assert [h["question"] for h in c.get(f"/v1/sessions/{sid}/turns").json()] == ["Câu một?", "Câu hai?"]


# ---------------------------------------------------------------------- streaming
def test_stream_sends_each_stage_then_the_answer(make):
    c, _ = make()
    r = ask(c, path="/v1/ask/stream")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = sse_events(r.text)
    names = [n for n, _ in ev]
    assert names == ["turn", "started", "perception", "parsed", "engine", "route", "answer", "done"]
    d = dict(ev)
    assert d["perception"]["signs"][0]["code"] == "P.103a" and d["engine"]["verdict"] == "yes"
    assert d["route"] == {"to": "writer", "t": d["route"]["t"]} and d["answer"]["answer"].startswith("Có.")
    assert d["started"]["image_size"] == [640, 480]
    assert c.get(f"/v1/turns/{d['turn']['turn_id']}").json()["status"] == "done"


def test_the_parsers_dry_run_is_not_reported_as_the_engine_answer(make):
    c, _ = make()
    names = [n for n, _ in sse_events(ask(c, path="/v1/ask/stream").text)]
    assert names.count("engine") == 1


def test_boxes_are_scaled_to_the_original_photo(make):
    c, _ = make(pipe=FakePipeline(box=(100, 200, 300, 400)))
    w, h = 4000, 3000
    nw, _ = native_size(w, h)
    s = nw / w
    t = ask(c, image=jpeg(w, h)).json()
    assert t["signs"][0]["box"] == [round(v / s) for v in (100, 200, 300, 400)]


def test_a_pipeline_error_streams_an_error_and_stores_it(make):
    c, _ = make(pipe=FakePipeline(fail=RuntimeError("boom")))
    ev = sse_events(ask(c, path="/v1/ask/stream").text)
    assert ev[-1][0] == "error" and "boom" in ev[-1][1]["error"]
    tid = ev[0][1]["turn_id"]
    assert c.get(f"/v1/turns/{tid}").json()["status"] == "error"
    r = ask(c)
    assert r.status_code == 500 and "boom" in r.json()["detail"]


def test_the_spend_limit_gives_503(make):
    c, _ = make(pipe=FakePipeline(fail=SpendLimitExceeded("over")))
    r = ask(c)
    assert r.status_code == 503 and "spend limit" in r.json()["detail"]


# ---------------------------------------------------------------------- feedback
def test_feedback_is_stored_with_the_turn(make):
    c, _ = make()
    tid = ask(c).json()["turn_id"]
    r = c.post(f"/v1/turns/{tid}/feedback", json={"thumb": "down", "corrected_answer": "Không.", "note": "sai biển"})
    assert r.status_code == 200 and r.json()["thumb"] == "down"
    fb = c.get(f"/v1/turns/{tid}").json()["feedback"]
    assert fb[0]["corrected_answer"] == "Không."
    assert c.post(f"/v1/turns/{tid}/feedback", json={}).status_code == 400
    assert c.post(f"/v1/turns/{tid}/feedback", json={"thumb": "maybe"}).status_code == 422
    assert c.post("/v1/turns/nope/feedback", json={"thumb": "up"}).status_code == 404


# ---------------------------------------------------------------------- validation
def test_bad_inputs_are_refused_before_the_pipeline(make):
    c, pipe = make(max_image_bytes=50_000)
    assert ask(c, image=b"not an image").status_code == 415
    assert ask(c, image=jpeg(3000, 3000, (1, 2, 3)) + b"\0" * 60_000).status_code == 413
    assert ask(c, question="   ").status_code == 400
    assert ask(c, question="x" * 501).status_code == 400
    assert ask(c, session_id="nope").status_code == 404
    gif = io.BytesIO()
    Image.new("RGB", (8, 8)).save(gif, format="GIF")
    assert ask(c, image=gif.getvalue()).status_code == 415
    assert c.get("/v1/images/../../etc").status_code == 404 or c.get("/v1/images/xyz").status_code == 400
    assert pipe.calls == []


def test_metrics_count_answers(make):
    c, _ = make()
    ask(c)
    body = c.get("/metrics").text
    assert 'vqa_answers_total{answered_by="rules"} 1.0' in body and "vqa_answer_seconds_bucket" in body


# ---------------------------------------------------------------------- the real pipeline
def test_the_api_answer_is_the_pipelines_answer(make, tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(jpeg())
    cache = warm(tmp_path, photo)

    def real():
        return pl.Pipeline(pl.PipelineConfig(cache_dir=cache, cache_only=True, max_spend=1.0),
                           sdk=RoutedSDK(parser=[PROG_YES], writer=[WRITER_YES]))

    direct = real().answer(photo, Q_YES)
    c, _ = make(pipe=real())
    ev = sse_events(ask(c, path="/v1/ask/stream", image=photo.read_bytes()).text)
    d = dict(ev)
    names = [n for n, _ in ev if n != "token"]
    # perception and the parser run in parallel inside the pipeline, so either may finish first
    assert sorted(names[2:4]) == ["parsed", "perception"]
    assert names[:2] + names[4:] == ["turn", "started", "engine", "route", "answer", "done"]
    # a non-streaming SDK hands the writer's whole reply over at once: one token, the full text
    assert "".join(e["text"] for n, e in ev if n == "token") == direct.text
    a = d["answer"]
    assert (a["answer"], a["verdict"], a["answered_by"], a["citations"]) == \
        (direct.text, direct.verdict, direct.answered_by, direct.citations)
    assert d["parsed"]["status"] == "ok" and d["parsed"]["program"] == direct.trace["parser"]["program"]
    assert d["perception"]["signs"][0]["code"] == "P.103a" and d["perception"]["signs"][0]["known"]
