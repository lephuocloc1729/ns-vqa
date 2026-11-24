"""The VQA backend API (FastAPI). Swagger UI at /docs, OpenAPI at /openapi.json.

    uvicorn --factory app.api.main:create_app --port 8000      # settings from VQA_* environment variables

Endpoints:
- POST /v1/sessions                      start a conversation
- POST /v1/ask                           image + question -> answer (JSON)
  (with a session_id, a follow-up such as "Còn xe khách thì sao?" is first rewritten into a complete
   question from the previous one about the same photo, app/api/followup.py; `understood_as` has it)
- POST /v1/ask/stream                    the same, as server-sent events: one event per pipeline stage,
                                         the writer's text as it is written (`token`; `token_reset`
                                         withdraws it before a retry or the template answer), then
                                         `answer` (authoritative, guard-checked) and `done` (or `error`)
- GET  /v1/sessions/{id}/turns           the conversation's history
- GET  /v1/turns/{id}                    one turn (also how a client that lost the stream gets its answer)
- POST /v1/turns/{id}/feedback           thumbs up/down, a corrected answer, a note
- GET  /v1/images/{sha256}               an uploaded image
- GET  /health, GET /version, GET /metrics (Prometheus)
- /v1/admin/...                          the admin site (app/api/admin.py): its own login, live settings,
                                         site accounts, stored answers and feedback
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import threading
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

from app.api import followup as followup_mod
from app.api import live as live_mod
from app.api.admin import admin_router, sync_users
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
    understood_as: str | None = None          # a follow-up, rewritten into the question that was answered
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
                   understood_as=getattr(t, "understood_as", None),
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
    out = {stage: {k: trace[stage][k] for k in fields if k in trace[stage]}
           for stage, fields in keep.items() if isinstance(trace.get(stage), dict)}
    hit = rag_cache_hit(trace)
    if hit is not None:
        out["fallback"]["cache_hit"] = hit                     # a RAG answer: cached or fresh
    return out


# The answer shown when the parser finds no road-sign question it can express and no fallback answers
# (no GPU connected). The pipeline's own not-decided template ("còn tùy điều kiện không thấy trong
# ảnh") reads as if the photo were the problem, which misleads for "write me a poem"
# (docs/results/redteam-2026-11-24.md). Only the text shown changes: the verdict, the route and the
# benchmark (vqa/) stay as they are.
SCOPE_TEXT = ("Hệ thống chỉ trả lời câu hỏi về biển báo giao thông trong ảnh, và câu hỏi này nằm ngoài "
              "những gì hệ luật trả lời được. Bạn có thể hỏi biển có ý nghĩa gì, hoặc một loại xe có được "
              "đi, đỗ, rẽ hay chạy bao nhiêu km/h ở đây.")


def shown_text(result: Any) -> str:
    """The answer text to store and show: SCOPE_TEXT for an out-of-scope question nobody answered."""
    parser = (result.trace or {}).get("parser") or {}
    if result.answered_by == "not_decided" and parser.get("status") == "out_of_scope":
        return SCOPE_TEXT
    return result.text


def rag_cache_hit(trace: dict[str, Any]) -> bool | None:
    """For a RAG fallback answer, whether it came from the RAG answer cache; else None."""
    fb = trace.get("fallback") if isinstance(trace, dict) else None
    if not isinstance(fb, dict) or fb.get("status") != "ok" or not str(fb.get("prompt_id", "")).startswith("rag"):
        return None
    try:
        record = json.loads((fb.get("raw") or ["{}"])[-1])
    except (TypeError, ValueError):
        return False
    return bool(isinstance(record, dict) and record.get("cache_hit"))


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter("vqa_requests", "API requests", ["endpoint", "status"], registry=self.registry)
        self.answers = Counter("vqa_answers", "Answers by route", ["answered_by"], registry=self.registry)
        self.cost = Counter("vqa_cost_usd", "Claude API spend in USD", ["answered_by"], registry=self.registry)
        self.seconds = Histogram("vqa_answer_seconds", "Seconds per answer", registry=self.registry,
                                 buckets=(1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120))
        self.feedback = Counter("vqa_feedback", "Feedback received, by kind", ["kind"], registry=self.registry)
        self.rag_cache = Counter("vqa_rag_cache", "RAG fallback answers, from the answer cache or fresh",
                                 ["result"], registry=self.registry)
        self.followup = Counter("vqa_followup", "Follow-up rewrites, by result", ["result"],
                                registry=self.registry)
        self.stage = Histogram("vqa_stage_seconds", "Seconds from start to each stage event", ["stage"],
                               registry=self.registry, buckets=(0.5, 1, 2, 5, 10, 15, 20, 30, 60))


# ---------------------------------------------------------------------- the app
def create_app(settings: Settings | None = None, pipeline_factory: Callable[[], Any] | None = None,
               followup_llm: Callable[[], Any] | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = Store(settings.database_url)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    metrics = Metrics()

    def default_factory() -> Any:
        from vqa.pipeline import Pipeline
        pipe = Pipeline(pipeline_config(settings))
        applier.claude_fallback = pipe.fallback     # the Sonnet answer fallback, for the "claude" mode
        return pipe

    def live_now() -> live_mod.Live:
        return live_mod.effective(settings, store.settings_overrides())

    class LiveApplier:
        """Brings the pipeline in line with the live settings before each answer (app/api/live.py).

        The fallback object is swapped only on the API's own pipeline (default_factory); a test's or
        demo's pipeline keeps its own, and gets only the switch and the spend limit."""

        def __init__(self) -> None:
            self.applied: live_mod.Live | None = None
            self.claude_fallback: Any = None
            self._lock = threading.Lock()
            self._rag_cache: Any = None

        def __call__(self, pipe: Any) -> None:
            want = live_now()
            with self._lock:
                if want == self.applied:
                    return
                self._apply(pipe, want)
                self.applied = want

        def _apply(self, pipe: Any, want: live_mod.Live) -> None:
            config = getattr(pipe, "config", None)
            if dataclasses.is_dataclass(config) and hasattr(config, "answer_fallback"):
                pipe.config = dataclasses.replace(config, answer_fallback=want.answer_fallback != "off")
            if self.claude_fallback is not None:
                if want.answer_fallback == "rag":
                    from vqa.answer.rag_fallback import RagFallback
                    fb: Any = RagFallback(want.rag_url, timeout=settings.rag_timeout_s)
                    if want.rag_cache:             # the RAG's own earlier answers, for repeats
                        from app.api.rag_cache import CachedRagFallback, RagAnswerCache
                        if self._rag_cache is None:
                            self._rag_cache = RagAnswerCache(settings.rag_cache_dir,
                                                             max_days=settings.rag_cache_max_days)
                        fb = CachedRagFallback(fb, self._rag_cache)
                    pipe.fallback = runner.instrument_fallback(fb)
                else:
                    pipe.fallback = self.claude_fallback
            guard = getattr(pipe, "guard", None)
            if guard is not None and hasattr(guard, "limit"):
                from vqa.llm.spend import default_limit
                guard.limit = want.spend_limit if want.spend_limit is not None else default_limit()

    applier = LiveApplier()
    runner = PipelineRunner(pipeline_factory or default_factory, slots=settings.answer_slots, prepare=applier)

    llm_box: dict[str, Any] = {}

    def default_followup_llm() -> Any:
        """One Haiku client, counted by the pipeline's own spend guard (one limit for everything)."""
        if "llm" not in llm_box:
            from vqa.llm.spend import SpendGuard
            guard = getattr(runner.pipeline, "guard", None) or SpendGuard(live_now().spend_limit)
            llm_box["llm"] = followup_mod.make_client(guard)
        return llm_box["llm"]

    followup = followup_mod.Followup(followup_llm or default_followup_llm, max_chars=settings.max_question_chars)
    sync_users(settings, store)                     # the web server's password file, from the database

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
    app.include_router(admin_router(settings, store, live_now, runner, lambda: settings.rag_cache_dir))

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

    def account_of(request: Request) -> str | None:
        """The site login that asked: set by the web server (it overwrites what a browser sends)."""
        name = (request.headers.get("x-remote-user") or "").strip()
        return name[:64] or None

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

    async def understand(given_session: str | None, sid: str, sha: str, q: str) -> tuple[str, followup_mod.Rewrite | None]:
        """The question to answer: a follow-up rewritten from the previous question on this photo."""
        if not given_session or not live_now().followup:
            return q, None
        previous = store.previous_question(sid, sha)
        if previous is None:
            return q, None
        rw = await asyncio.to_thread(followup.rewrite, q, previous)
        metrics.followup.labels(rw.status).inc()
        return rw.question, rw

    def followup_stage(rw: followup_mod.Rewrite | None) -> dict[str, Any] | None:
        if rw is None:
            return None
        return {"status": rw.status, "cost_usd": rw.cost_usd, "prompt_id": f"followup/{followup.version}",
                **({"error": rw.error} if rw.error else {})}

    def finish(turn_id: str, result: Any, signs: list[dict[str, Any]],
               rw: followup_mod.Rewrite | None = None) -> Turn:
        basis, retrieved = rag_part(result)
        metrics.answers.labels(result.answered_by).inc()
        metrics.cost.labels(result.answered_by).inc(result.cost_usd or 0.0)
        metrics.seconds.observe(result.seconds or 0.0)
        hit = rag_cache_hit(result.trace or {})
        if hit is not None:
            metrics.rag_cache.labels("hit" if hit else "miss").inc()
        return store.finish_turn(turn_id, status="done", answer_text=shown_text(result), verdict=result.verdict,
                                 answered_by=result.answered_by, basis=basis, retrieved=retrieved,
                                 citations=list(result.citations), proof=result.proof, signs=signs,
                                 stages={**stage_summary(result.trace or {}),
                                         **({"followup": followup_stage(rw)} if rw else {})},
                                 cost_usd=(result.cost_usd or 0.0) + (rw.cost_usd if rw else 0.0),
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
        now = live_now()
        return {"profile": settings.profile, "pipeline": PROFILES.get(settings.profile),
                "answer_fallback": now.answer_fallback, "answer_slots": runner.slots,
                "rag_cache": now.rag_cache and now.answer_fallback == "rag"}

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
    async def ask(request: Request, image: UploadFile = File(...), question: str = Form(...),
                  session_id: str | None = Form(None)) -> TurnOut:
        q = check_question(question)
        sid = session_for(session_id)
        sha, path = await save_upload(image)
        asked, rw = await understand(session_id, sid, sha, q)
        turn = store.start_turn(sid, q, sha, account_of(request), understood_as=asked if asked != q else None)
        signs: list[dict[str, Any]] = []

        def emit(name: str, payload: dict[str, Any]) -> None:
            if name == "perception":
                signs[:] = payload.get("signs", [])

        try:
            result = await asyncio.wrap_future(runner.submit(path, asked, emit))
        except Exception as e:
            t = fail(turn.id, e)
            metrics.requests.labels("ask", "error").inc()
            raise HTTPException(503 if isinstance(e, SpendLimitExceeded) else 500, t.error)
        metrics.requests.labels("ask", "ok").inc()
        return turn_out(finish(turn.id, result, signs, rw))

    @app.post("/v1/ask/stream")
    async def ask_stream(request: Request, image: UploadFile = File(...), question: str = Form(...),
                         session_id: str | None = Form(None)) -> StreamingResponse:
        q = check_question(question)
        sid = session_for(session_id)
        sha, path = await save_upload(image)
        asked, rw = await understand(session_id, sid, sha, q)
        understood = asked if asked != q else None
        turn = store.start_turn(sid, q, sha, account_of(request), understood_as=understood)
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

        future = runner.submit(path, asked, emit)

        def store_result(f: Any) -> None:       # runs even if the client has gone away
            try:
                finish(turn.id, f.result(), signs, rw)
                metrics.requests.labels("ask_stream", "ok").inc()
            except Exception as e:
                fail(turn.id, e)
                metrics.requests.labels("ask_stream", "error").inc()
            loop.call_soon_threadsafe(put, "_finished", {})

        future.add_done_callback(store_result)

        def sse(event: str, data: dict[str, Any]) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        async def events() -> AsyncIterator[str]:
            yield sse("turn", {"turn_id": turn.id, "session_id": sid, "image_sha256": sha,
                               "understood_as": understood})
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
