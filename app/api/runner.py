"""Runs the pipeline for the API, several questions at a time, and reports each stage.

The pipeline's `answer(image_path, question)` takes nothing else (a fixed rule of the
design), so stage events come from wrapping the stage methods of this process's
Pipeline instance: perception, the parser, the engine, the answer fallback and the
writer. The answers are exactly the pipeline's; the wrappers only observe.

Several answers at once (`slots` worker threads, VQA_ANSWER_SLOTS) share the one Pipeline
of the process; docs/plans/concurrent-answers.md has the review behind this:
- janus keeps one Prolog per process, and a scene's facts are global in it, so every
  `engine.answer` (the pipeline's and the parser's dry run) runs under one lock. It takes
  milliseconds; the Claude calls, almost all of an answer's time, run in parallel.
- each answer has its own context (where its events go, its start time, its photo's scale).
  Its own thread finds it in a thread-local. Perception runs in a thread the pipeline starts
  itself, so it finds its answer by the image path: each answer gets its own path, a link to
  the upload in a folder of its own (same file name, same bytes, so caches are unaffected).

Live settings (app/api/live.py): `prepare(pipe)` runs at the start of each answer, in its worker
thread, and may swap the pipeline's fallback (`instrument_fallback` wraps a new one first).
"""

from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from dataclasses import dataclass
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


@dataclass
class _Turn:
    """One answer's context: where its events go, when it started, its photo's scale."""
    emit: Emit | None
    t0: float
    scale: float = 1.0


class PipelineRunner:
    def __init__(self, factory: Callable[[], Any], slots: int = 1,
                 prepare: Callable[[Any], None] | None = None) -> None:
        self._factory = factory
        self._prepare = prepare
        self._pipe: Any = None
        self._lock = threading.Lock()            # building the pipeline
        self._prolog = threading.Lock()          # every engine.answer: one Prolog per process
        self.slots = max(1, int(slots))
        self._exec = ThreadPoolExecutor(max_workers=self.slots, thread_name_prefix="pipeline")
        self._local = threading.local()          # .turn, .in_parse: the answer of this thread
        self._by_path: dict[str, _Turn] = {}     # an answer's own image path -> its context
        self._paths_lock = threading.Lock()

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
    def _own_path(self, image_path: Path) -> Path:
        """A path for this answer alone: the upload, linked into a folder of its own."""
        folder = image_path.parent / ".turns" / uuid.uuid4().hex
        folder.mkdir(parents=True)
        own = folder / image_path.name
        try:
            os.link(image_path, own)
        except OSError:
            shutil.copyfile(image_path, own)
        return own

    def _run(self, image_path: Path, question: str, emit: Emit | None) -> Any:
        pipe = self.pipeline
        if self._prepare is not None:
            self._prepare(pipe)                 # live settings, before this answer starts
        turn = _Turn(emit=emit, t0=time.monotonic())
        try:
            turn.scale, size = image_scale(image_path)
        except Exception:
            size = None
        own = self._own_path(Path(image_path))
        key = str(own)
        with self._paths_lock:
            self._by_path[key] = turn
        self._local.turn = turn
        self._send("started", {"image_size": size})
        try:
            return pipe.answer(own, question)
        finally:
            self._local.turn = None
            with self._paths_lock:
                self._by_path.pop(key, None)
            shutil.rmtree(own.parent, ignore_errors=True)

    def _turn_for(self, image_path: Any = None) -> _Turn | None:
        turn = getattr(self._local, "turn", None)
        if turn is None and image_path is not None:
            with self._paths_lock:
                turn = self._by_path.get(str(image_path))
        return turn

    def _send(self, name: str, payload: dict[str, Any], turn: _Turn | None = None) -> None:
        turn = turn or self._turn_for()
        if turn is not None and turn.emit is not None:
            try:
                turn.emit(name, {**payload, "t": round(time.monotonic() - turn.t0, 3)})
            except Exception:
                pass                           # a broken listener never breaks an answer

    def _instrument(self, pipe: Any) -> None:
        runner = self
        catalog = getattr(getattr(pipe, "engine", None), "catalog", None)

        if hasattr(pipe, "_perceive"):
            perceive = pipe._perceive

            def _perceive(image_path, *a, **kw):
                turn = runner._turn_for(image_path)   # perception may run in the pipeline's own thread
                res, info = perceive(image_path, *a, **kw)
                scene = res.scene if getattr(res, "ok", False) else None
                runner._send("perception", {
                    "ok": bool(getattr(res, "ok", False)), "cache_hit": info.get("cache_hit"),
                    "error": info.get("error"),
                    "signs": sign_payload(scene, catalog, turn.scale if turn else 1.0) if scene is not None else [],
                    "guide_boards": len(getattr(scene, "guide_boards", []) or []) if scene is not None else 0},
                    turn)
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
                with runner._prolog:                   # a scene's facts are global in Prolog
                    ans = eng_answer(scene, program, *a, **kw)
                if not getattr(runner._local, "in_parse", False):     # not the parser's dry run
                    runner._send("engine", {"verdict": getattr(getattr(ans, "verdict", None), "value", None)})
                return ans
            engine.answer = _engine_answer

        fallback = getattr(pipe, "fallback", None)
        if fallback is not None:
            self.instrument_fallback(fallback)

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

    def instrument_fallback(self, fallback: Any) -> Any:
        """Report a fallback's route and streamed text. Wraps each object once."""
        if not hasattr(fallback, "answer") or getattr(fallback, "_runner_wrapped", False):
            return fallback
        runner = self
        fb_answer = fallback.answer

        def _fallback(*a, **kw):
            runner._send("route", {"to": "fallback"})
            return fb_answer(*a, **kw)
        fallback.answer = _fallback

        if hasattr(fallback, "on_event"):          # the RAG fallback streams its answer text
            fallback.on_event = lambda kind, payload: runner._send(
                "token" if kind == "delta" else "token_reset", payload)
        try:
            fallback._runner_wrapped = True
        except AttributeError:
            pass
        return fallback
