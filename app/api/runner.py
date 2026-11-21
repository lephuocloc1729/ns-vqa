"""Runs the pipeline for the API, one question at a time per process, and reports each stage.

The pipeline's `answer(image_path, question)` takes nothing else (a fixed rule of the
design), so stage events come from wrapping the stage methods of this process's
Pipeline instance: perception, the parser, the engine, the answer fallback and the
writer. The answers are exactly the pipeline's; the wrappers only observe.

All calls run on one worker thread: janus keeps one Prolog engine per process, and the
pipeline already overlaps perception with the parser internally. More throughput comes
from more API worker processes, not threads.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps

from vqa.perception.image import native_size

Emit = Callable[[str, dict[str, Any]], None]


def image_scale(image_path: Path) -> tuple[float, tuple[int, int]]:
    """(scale, (width, height)): the model saw the photo resized by `scale`; boxes divide by it."""
    with Image.open(image_path) as im:
        w, h = ImageOps.exif_transpose(im).size
    nw, _ = native_size(w, h)
    return nw / w, (w, h)


def sign_payload(scene: Any, catalog: Any, scale: float) -> list[dict[str, Any]]:
    out = []
    for s in getattr(scene, "signs", []) or []:
        name = None
        known = False
        if catalog is not None and s.code and s.code != "UNKNOWN":
            try:
                row = catalog.get(s.code)
                name, known = getattr(row, "name_vi", None), True
            except KeyError:
                pass
        box = s.position.box
        out.append({
            "id": s.id, "code": s.code, "name": name, "known": known,
            "confidence": getattr(s.confidence, "value", s.confidence),
            "value": s.value, "unit": s.unit,
            "box": [round(v / scale) for v in box] if box else None,
            "plates": [p.text or p.code for p in s.plates if (p.text or p.code)],
            "alternatives": [a.code for a in getattr(s, "alternatives", [])],
        })
    return out


class PipelineRunner:
    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory
        self._pipe: Any = None
        self._lock = threading.Lock()
        self._exec = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")
        self._emit: Emit | None = None
        self._t0 = 0.0
        self._scale = 1.0
        self._local = threading.local()

    @property
    def loaded(self) -> bool:
        return self._pipe is not None

    @property
    def pipeline(self) -> Any:
        with self._lock:
            if self._pipe is None:
                self._pipe = self._factory()
                self._instrument(self._pipe)
            return self._pipe

    def submit(self, image_path: Path, question: str, emit: Emit | None = None) -> Future:
        return self._exec.submit(self._run, image_path, question, emit)

    def shutdown(self) -> None:
        self._exec.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ internals
    def _run(self, image_path: Path, question: str, emit: Emit | None) -> Any:
        pipe = self.pipeline
        self._emit, self._t0 = emit, time.monotonic()
        try:
            self._scale, size = image_scale(image_path)
        except Exception:
            self._scale, size = 1.0, None
        self._send("started", {"image_size": size})
        try:
            return pipe.answer(image_path, question)
        finally:
            self._emit = None

    def _send(self, name: str, payload: dict[str, Any]) -> None:
        emit = self._emit
        if emit is not None:
            try:
                emit(name, {**payload, "t": round(time.monotonic() - self._t0, 3)})
            except Exception:
                pass                           # a broken listener never breaks an answer

    def _instrument(self, pipe: Any) -> None:
        runner = self
        catalog = getattr(getattr(pipe, "engine", None), "catalog", None)

        if hasattr(pipe, "_perceive"):
            perceive = pipe._perceive

            def _perceive(image_path, *a, **kw):
                res, info = perceive(image_path, *a, **kw)
                scene = res.scene if getattr(res, "ok", False) else None
                runner._send("perception", {
                    "ok": bool(getattr(res, "ok", False)), "cache_hit": info.get("cache_hit"),
                    "error": info.get("error"),
                    "signs": sign_payload(scene, catalog, runner._scale) if scene is not None else [],
                    "guide_boards": len(getattr(scene, "guide_boards", []) or []) if scene is not None else 0})
                return res, info
            pipe._perceive = _perceive

        parser = getattr(pipe, "parser", None)
        if parser is not None and hasattr(parser, "parse"):
            parse = parser.parse

            def _parse(question, *a, **kw):
                runner._local.in_parse = True
                try:
                    pr = parse(question, *a, **kw)
                finally:
                    runner._local.in_parse = False
                query = getattr(pr, "query", None)
                program = query.model_dump(mode="json", by_alias=True, exclude_none=True) if query is not None else None
                runner._send("parsed", {"status": getattr(pr, "status", None), "program": program})
                return pr
            parser.parse = _parse

        engine = getattr(pipe, "engine", None)
        if engine is not None and hasattr(engine, "answer"):
            eng_answer = engine.answer

            def _engine_answer(scene, program, *a, **kw):
                ans = eng_answer(scene, program, *a, **kw)
                if not getattr(runner._local, "in_parse", False):     # not the parser's dry run
                    runner._send("engine", {"verdict": getattr(getattr(ans, "verdict", None), "value", None)})
                return ans
            engine.answer = _engine_answer

        fallback = getattr(pipe, "fallback", None)
        if fallback is not None and hasattr(fallback, "answer"):
            fb_answer = fallback.answer

            def _fallback(*a, **kw):
                runner._send("route", {"to": "fallback"})
                return fb_answer(*a, **kw)
            fallback.answer = _fallback

        writer = getattr(pipe, "writer", None)
        if writer is not None and hasattr(writer, "write"):
            write = writer.write

            def _write(*a, **kw):
                runner._send("route", {"to": "writer"})
                return write(*a, **kw)
            writer.write = _write

            # the writer's answer text as it streams ("token"), and its withdrawal before a
            # retry or the template answer ("token_reset"); the final `answer` event is authoritative
            def _writer_event(kind: str, payload: dict[str, Any]) -> None:
                runner._send("token" if kind == "delta" else "token_reset", payload)
            writer.on_event = _writer_event
