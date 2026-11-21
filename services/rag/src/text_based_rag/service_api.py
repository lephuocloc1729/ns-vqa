"""HTTP API of the RAG service (ns-vqa plan F2).

    uvicorn --factory text_based_rag.service_api:create_app --host 0.0.0.0 --port 8100

- POST /answer          image + question -> answer, analysis, cited laws (with text), retrieval,
                        timings per stage, token usage, config_version
- POST /answer/stream   the same as server-sent events: `caption`, `retrieval`, `token` (the
                        final_answer text as it is generated), then `answer` and `done` (or `error`)
- GET  /health, GET /version

One question at a time (one GPU): requests queue on a single worker thread.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from text_based_rag.service import CONFIG_C, CONFIG_VERSION, RagEngine

MAX_IMAGE_BYTES = 10 * 1024 * 1024


def create_app(engine_factory: Callable[[], RagEngine] | None = None, start: bool = True) -> FastAPI:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag")
    state: dict[str, Any] = {"engine": None, "error": None}
    uploads = Path(tempfile.mkdtemp(prefix="rag_uploads_"))

    def build() -> None:
        try:
            engine = (engine_factory or RagEngine)()
            if start:
                engine.start()
            state["engine"] = engine
        except Exception as e:                 # reported by /health; requests get 503
            state["error"] = f"{type(e).__name__}: {e}"

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await asyncio.get_running_loop().run_in_executor(executor, build)
        yield
        if state["engine"] is not None:
            state["engine"].close()
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Traffic-law RAG service", version="1.0", lifespan=lifespan,
                  description="Configuration C of the multimodal RAG, one question at a time.")

    def engine() -> RagEngine:
        if state["engine"] is None:
            raise HTTPException(503, f"engine not ready: {state['error'] or 'starting'}")
        return state["engine"]

    async def save(image: UploadFile) -> Path:
        data = await image.read(MAX_IMAGE_BYTES + 1)
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413 if data else 400, "image missing or larger than 10 MB")
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
        except (UnidentifiedImageError, OSError, SyntaxError):
            raise HTTPException(415, "not a readable image")
        path = uploads / (hashlib.sha256(data).hexdigest() + ".img")
        if not path.exists():
            path.write_bytes(data)
        return path

    def check(question: str) -> str:
        q = question.strip()
        if not q or len(q) > 1000:
            raise HTTPException(400, "question empty or longer than 1000 characters")
        return q

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok" if state["engine"] is not None else ("error" if state["error"] else "starting"),
                "error": state["error"]}

    @app.get("/version")
    def version() -> dict[str, Any]:
        return {"config_version": CONFIG_VERSION, "config": CONFIG_C}

    @app.post("/answer")
    async def answer(image: UploadFile = File(...), question: str = Form(...)) -> dict[str, Any]:
        eng, q, path = engine(), check(question), await save(image)
        try:
            result = await asyncio.get_running_loop().run_in_executor(executor, lambda: eng.ask(path, q))
        except Exception as e:
            raise HTTPException(500, f"{type(e).__name__}: {e}")
        return result.to_json()

    @app.post("/answer/stream")
    async def answer_stream(image: UploadFile = File(...), question: str = Form(...)) -> StreamingResponse:
        eng, q, path = engine(), check(question), await save(image)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=8192)

        def put(item):
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                pass

        def emit(name: str, payload: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(put, (name, payload))

        def work():
            try:
                res = eng.ask(path, q, emit=emit, stream=True)
                loop.call_soon_threadsafe(put, ("answer", res.to_json()))
            except Exception as e:
                loop.call_soon_threadsafe(put, ("error", {"error": f"{type(e).__name__}: {e}"}))

        loop.run_in_executor(executor, work)

        async def events() -> AsyncIterator[str]:
            while True:
                try:
                    name, payload = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if name == "answer":
                    yield "event: done\ndata: {}\n\n"
                    return
                if name == "error":
                    return

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app
