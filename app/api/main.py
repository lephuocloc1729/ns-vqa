"""The VQA backend API (FastAPI). Swagger UI at /docs, OpenAPI at /openapi.json.

    uvicorn --factory app.api.main:create_app --port 8000      # settings from VQA_* environment variables

Endpoints:
- POST /v1/sessions                      start a conversation
- POST /v1/ask                           image + question -> answer (JSON)
- POST /v1/ask/stream                    the same, as server-sent events: one event per pipeline stage,
                                         the writer's text as it is written (`token`; `token_reset`
                                         withdraws it before a retry or the template answer), then
                                         `answer` (authoritative, guard-checked) and `done` (or `error`)
- GET  /v1/sessions/{id}/turns           the conversation's history
- GET  /v1/turns/{id}                    one turn (also how a client that lost the stream gets its answer)
- POST /v1/turns/{id}/feedback           thumbs up/down, a corrected answer, a note
- GET  /v1/images/{sha256}               an uploaded image
- GET  /health, GET /version, GET /metrics (Prometheus)
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from PIL import Image, UnidentifiedImageError
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from vqa.llm.spend import SpendLimitExceeded

from app.api.profiles import PROFILES, pipeline_config
from app.api.runner import PipelineRunner
from app.api.settings import Settings
from app.api.storage import Store, Turn

IMAGE_TYPES = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------- response models
class SessionOut(BaseModel):
    session_id: str


class FeedbackIn(BaseModel):
    thumb: Literal["up", "down"] | None = None
    corrected_answer: str | None = Field(default=None, max_length=4000)
    note: str | None = Field(default=None, max_length=2000)


class FeedbackOut(BaseModel):
    id: str
    thumb: str | None
    corrected_answer: str | None
    note: str | None


class TurnOut(BaseModel):
    turn_id: str
    session_id: str
    status: str
    question: str
    image_sha256: str
    answer: str | None = None
    verdict: str | None = None
    answered_by: str | None = None
    basis: list[str] = []
    citations: list[str] = []
    signs: list[dict[str, Any]] = []
    retrieved: list[dict[str, Any]] = []      # laws the RAG fallback used (never rule citations)
    proof: dict[str, Any] | None = None
    stages: dict[str, Any] = {}
    cost_usd: float | None = None
    seconds: float | None = None
    error: str | None = None
    feedback: list[FeedbackOut] = []


def turn_out(t: Turn) -> TurnOut:
    return TurnOut(turn_id=t.id, session_id=t.session_id, status=t.status, question=t.question,
                   image_sha256=t.image_sha256, answer=t.answer_text, verdict=t.verdict,
                   answered_by=t.answered_by, basis=t.basis or [], citations=t.citations or [],
                   signs=t.signs or [], retrieved=t.retrieved or [], proof=t.proof, stages=t.stages or {}, cost_usd=t.cost_usd,
                   seconds=t.seconds, error=t.error,
                   feedback=[FeedbackOut(id=f.id, thumb=f.thumb, corrected_answer=f.corrected_answer, note=f.note)
                             for f in getattr(t, "feedback", []) or []])


def stage_summary(trace: dict[str, Any]) -> dict[str, Any]:
    """The trace without raw model replies: what each stage did and cost."""
    keep = {
        "perception": ("ok", "cache_hit", "error", "prompt_id", "cost_usd", "scene_fallback", "guide"),
        "parser": ("status", "attempts", "errors", "cost_usd", "used", "program"),
        "engine": ("verdict", "error"),
        "fallback": ("trigger", "status", "attempts", "cost_usd", "prompt_id"),
        "writer": ("status", "attempts", "cost_usd", "prompt_id", "cited_signs", "cited_rules"),
    }
    return {stage: {k: trace[stage][k] for k in fields if k in trace[stage]}
            for stage, fields in keep.items() if isinstance(trace.get(stage), dict)}


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter("vqa_requests", "API requests", ["endpoint", "status"], registry=self.registry)
        self.answers = Counter("vqa_answers", "Answers by route", ["answered_by"], registry=self.registry)
        self.cost = Counter("vqa_cost_usd", "Claude API spend in USD", ["answered_by"], registry=self.registry)
        self.seconds = Histogram("vqa_answer_seconds", "Seconds per answer", registry=self.registry,
                                 buckets=(1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120))
        self.feedback = Counter("vqa_feedback", "Feedback received, by kind", ["kind"], registry=self.registry)
        self.stage = Histogram("vqa_stage_seconds", "Seconds from start to each stage event", ["stage"],
                               registry=self.registry, buckets=(0.5, 1, 2, 5, 10, 15, 20, 30, 60))


# ---------------------------------------------------------------------- the app
def create_app(settings: Settings | None = None, pipeline_factory: Callable[[], Any] | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = Store(settings.database_url)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    metrics = Metrics()

    def default_factory() -> Any:
        from vqa.pipeline import Pipeline
        pipe = Pipeline(pipeline_config(settings))
        if settings.answer_fallback == "rag":
            from vqa.answer.rag_fallback import RagFallback
            pipe.fallback = RagFallback(settings.rag_url, timeout=settings.rag_timeout_s)
        return pipe

    runner = PipelineRunner(pipeline_factory or default_factory, slots=settings.answer_slots)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        runner.shutdown()

    app = FastAPI(title="Traffic-sign VQA API", version="1.0",
                  description="Neuro-symbolic answers about Vietnamese traffic signs, with proofs and citations.",
                  lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"],
                       allow_headers=["*"])
    app.state.settings, app.state.store, app.state.runner, app.state.metrics = settings, store, runner, metrics

    # ------------------------------------------------------------------ helpers
    async def save_upload(image: UploadFile) -> tuple[str, Path]:
        data = await image.read(settings.max_image_bytes + 1)
        if len(data) > settings.max_image_bytes:
            raise HTTPException(413, f"image larger than {settings.max_image_bytes // (1024 * 1024)} MB")
        if not data:
            raise HTTPException(400, "empty image")
        try:
            with Image.open(io.BytesIO(data)) as im:
                fmt = im.format
                im.verify()
        except (UnidentifiedImageError, OSError, SyntaxError):
            raise HTTPException(415, "not a readable image")
        if fmt not in IMAGE_TYPES:
            raise HTTPException(415, f"image type {fmt} not accepted (JPEG, PNG or WEBP)")
        sha = hashlib.sha256(data).hexdigest()
        path = settings.upload_dir / f"{sha}{IMAGE_TYPES[fmt]}"
        if not path.exists():
            path.write_bytes(data)
        return sha, path

    def check_question(question: str) -> str:
        q = question.strip()
        if not q:
            raise HTTPException(400, "empty question")
        if len(q) > settings.max_question_chars:
            raise HTTPException(400, f"question longer than {settings.max_question_chars} characters")
        return q

    def session_for(session_id: str | None) -> str:
        if session_id:
            if store.get_session(session_id) is None:
                raise HTTPException(404, "unknown session")
            return session_id
        return store.new_session().id

    def rag_part(result: Any) -> tuple[list[str], list[dict[str, Any]]]:
        """For a RAG fallback answer: the basis gains "rag", and its laws go to `retrieved`."""
        fb = (result.trace or {}).get("fallback") or {}
        if result.answered_by != "fallback" or not str(fb.get("prompt_id", "")).startswith("rag"):
            return list(result.basis), []
        try:
            record = json.loads((fb.get("raw") or ["{}"])[-1])
        except (TypeError, ValueError):
            record = {}
        return [*result.basis, "rag"], list(record.get("retrieved") or [])

    def finish(turn_id: str, result: Any, signs: list[dict[str, Any]]) -> Turn:
        basis, retrieved = rag_part(result)
        metrics.answers.labels(result.answered_by).inc()
        metrics.cost.labels(result.answered_by).inc(result.cost_usd or 0.0)
        metrics.seconds.observe(result.seconds or 0.0)
        return store.finish_turn(turn_id, status="done", answer_text=result.text, verdict=result.verdict,
                                 answered_by=result.answered_by, basis=basis, retrieved=retrieved,
                                 citations=list(result.citations), proof=result.proof, signs=signs,
                                 stages=stage_summary(result.trace or {}), cost_usd=result.cost_usd,
                                 seconds=result.seconds)

    def fail(turn_id: str, exc: BaseException) -> Turn:
        msg = ("the spend limit for this server was reached" if isinstance(exc, SpendLimitExceeded)
               else f"{type(exc).__name__}: {exc}")
        return store.finish_turn(turn_id, status="error", error=msg)

    # ------------------------------------------------------------------ endpoints
    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "database": store.ping(), "pipeline_loaded": runner.loaded}

    @app.get("/version")
    def version() -> dict[str, Any]:
        return {"profile": settings.profile, "pipeline": PROFILES.get(settings.profile),
                "answer_fallback": settings.answer_fallback, "answer_slots": runner.slots}

    @app.get("/metrics")
    def prom() -> Response:
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/sessions", response_model=SessionOut)
    def new_session() -> SessionOut:
        return SessionOut(session_id=store.new_session().id)

    @app.get("/v1/sessions/{session_id}/turns", response_model=list[TurnOut])
    def history(session_id: str) -> list[TurnOut]:
        if store.get_session(session_id) is None:
            raise HTTPException(404, "unknown session")
        return [turn_out(t) for t in store.turns(session_id)]

    @app.get("/v1/turns/{turn_id}", response_model=TurnOut)
    def get_turn(turn_id: str) -> TurnOut:
        t = store.get_turn(turn_id)
        if t is None:
            raise HTTPException(404, "unknown turn")
        return turn_out(t)

    @app.post("/v1/turns/{turn_id}/feedback", response_model=FeedbackOut)
    def feedback(turn_id: str, body: FeedbackIn) -> FeedbackOut:
        if store.get_turn(turn_id) is None:
            raise HTTPException(404, "unknown turn")
        if body.thumb is None and not body.corrected_answer and not body.note:
            raise HTTPException(400, "empty feedback")
        f = store.add_feedback(turn_id, body.thumb, body.corrected_answer, body.note)
        metrics.requests.labels("feedback", "ok").inc()
        if body.thumb:
            metrics.feedback.labels(body.thumb).inc()
        if body.corrected_answer:
            metrics.feedback.labels("corrected").inc()
        return FeedbackOut(id=f.id, thumb=f.thumb, corrected_answer=f.corrected_answer, note=f.note)

    @app.get("/v1/images/{sha256}")
    def get_image(sha256: str) -> FileResponse:
        if not SHA_RE.match(sha256):
            raise HTTPException(400, "bad image id")
        for ext in IMAGE_TYPES.values():
            p = settings.upload_dir / f"{sha256}{ext}"
            if p.exists():
                return FileResponse(p)
        raise HTTPException(404, "unknown image")

    @app.post("/v1/ask", response_model=TurnOut)
    async def ask(image: UploadFile = File(...), question: str = Form(...),
                  session_id: str | None = Form(None)) -> TurnOut:
        q = check_question(question)
        sid = session_for(session_id)
        sha, path = await save_upload(image)
        turn = store.start_turn(sid, q, sha)
        signs: list[dict[str, Any]] = []

        def emit(name: str, payload: dict[str, Any]) -> None:
            if name == "perception":
                signs[:] = payload.get("signs", [])

        try:
            result = await asyncio.wrap_future(runner.submit(path, q, emit))
        except Exception as e:
            t = fail(turn.id, e)
            metrics.requests.labels("ask", "error").inc()
            raise HTTPException(503 if isinstance(e, SpendLimitExceeded) else 500, t.error)
        metrics.requests.labels("ask", "ok").inc()
        return turn_out(finish(turn.id, result, signs))

    @app.post("/v1/ask/stream")
    async def ask_stream(request: Request, image: UploadFile = File(...), question: str = Form(...),
                         session_id: str | None = Form(None)) -> StreamingResponse:
        q = check_question(question)
        sid = session_for(session_id)
        sha, path = await save_upload(image)
        turn = store.start_turn(sid, q, sha)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(maxsize=8192)
        signs: list[dict[str, Any]] = []

        def put(name: str, payload: dict[str, Any]) -> None:
            try:
                queue.put_nowait((name, payload))
            except asyncio.QueueFull:
                pass                            # a stalled client; the final `answer` event still has the text

        def emit(name: str, payload: dict[str, Any]) -> None:   # pipeline thread
            if name == "perception":
                signs[:] = payload.get("signs", [])
            metrics.stage.labels(name).observe(payload.get("t", 0.0))
            loop.call_soon_threadsafe(put, name, payload)

        future = runner.submit(path, q, emit)

        def store_result(f: Any) -> None:       # runs even if the client has gone away
            try:
                finish(turn.id, f.result(), signs)
                metrics.requests.labels("ask_stream", "ok").inc()
            except Exception as e:
                fail(turn.id, e)
                metrics.requests.labels("ask_stream", "error").inc()
            loop.call_soon_threadsafe(put, "_finished", {})

        future.add_done_callback(store_result)

        def sse(event: str, data: dict[str, Any]) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        async def events() -> AsyncIterator[str]:
            yield sse("turn", {"turn_id": turn.id, "session_id": sid, "image_sha256": sha})
            while True:
                if await request.is_disconnected():
                    return                      # the answer is still stored; GET /v1/turns/{id} has it
                try:
                    name, payload = await asyncio.wait_for(queue.get(), timeout=settings.heartbeat_s)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if name == "_finished":
                    t = store.get_turn(turn.id)
                    if t is not None and t.status == "done":
                        yield sse("answer", turn_out(t).model_dump())
                        yield sse("done", {"turn_id": turn.id})
                    else:
                        yield sse("error", {"turn_id": turn.id, "error": t.error if t else "unknown error"})
                    return
                yield sse(name, payload)

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app
