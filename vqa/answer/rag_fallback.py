"""The answer fallback served by the RAG service (docs/plans/rag-fallback.md, F3).

`RagFallback.answer(image_path, question, scene)` has the interface of `AnswerFallback`
and returns a `FallbackAnswer`, so the pipeline treats it the same way:

- it sends only the image and the question (G4: never the scene graph);
- the service URL comes from the caller (the API reads it from VQA_RAG_URL);
- the RAG's answer is a fallback answer: the pipeline marks it `answered_by="fallback"`
  with no rule citations; the laws the RAG used travel in `raw` as JSON (`retrieved`),
  never as citations of the rule engine;
- failure (service down, timeout, bad reply, an error event, an empty answer) gives
  `status="failed"`, and the pipeline ships the engine's own answer through the writer (P3).

With `on_event` set, the call uses the streaming endpoint and the listener gets
("delta", {"attempt": 1, "text": ...}) for the answer text as it is generated, as the
writer's listener does. `cost_usd` is 0: the RAG runs on the project's own GPU.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any, Callable

import httpx

from vqa.answer.fallback import FallbackAnswer
from vqa.answer.faithfulness import is_true_false
from vqa.schemas import SceneGraph


def verdict_of(question: str, text: str) -> str:
    """The verdict a RAG answer states: Đúng/Sai for a true-false question, Có/Không for another
    yes/no question, otherwise a value."""
    t = unicodedata.normalize("NFC", text).strip().casefold()
    q = unicodedata.normalize("NFC", question).strip().casefold().rstrip("?.! ")
    if is_true_false(question):
        return "yes" if t.startswith("đúng") else "no" if t.startswith("sai") else "unknown"
    if q.endswith(("không", "chưa", "phải không", "đúng không")) or q.startswith(("có phải", "liệu")):
        if t.startswith(("có", "được", "đúng")):
            return "yes"
        if t.startswith(("không", "chưa", "sai")):
            return "no"
        return "unknown"
    return "value"


class RagFallback:
    def __init__(self, url: str, *, timeout: float = 180.0, transport: httpx.BaseTransport | None = None) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._transport = transport
        self.on_event: Callable[[str, dict[str, Any]], None] | None = None
        self.prompt_id = "rag"

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=httpx.Timeout(self.timeout, connect=10.0), transport=self._transport)

    def _emit(self, kind: str, payload: dict[str, Any]) -> None:
        if self.on_event is not None:
            try:
                self.on_event(kind, payload)
            except Exception:
                pass

    def answer(self, image_path: str | Path, question: str, scene: SceneGraph | None) -> FallbackAnswer:
        path = Path(image_path)
        files = {"image": (path.name, path.read_bytes(), "application/octet-stream")}
        data = {"question": question}
        try:
            with self._client() as client:
                if self.on_event is None:
                    r = client.post(self.url + "/answer", files=files, data=data)
                    r.raise_for_status()
                    reply = r.json()
                else:
                    reply = self._stream(client, files, data)
        except (httpx.HTTPError, ValueError, KeyError) as e:
            return FallbackAnswer(status="failed", attempts=1, errors=[[f"{type(e).__name__}: {e}"]],
                                  prompt_id=self.prompt_id)
        text = str(reply.get("answer") or "").strip()
        version = str(reply.get("config_version") or "rag")
        self.prompt_id = version
        if not text:
            return FallbackAnswer(status="failed", attempts=1, errors=[["empty answer"]], prompt_id=version)
        record = {"config_version": version, "retrieved": reply.get("citations", []),
                  "gate": reply.get("gate"), "timings": reply.get("timings"), "usage": reply.get("usage")}
        return FallbackAnswer(status="ok", verdict=verdict_of(question, text), text=text, attempts=1,
                              raw=[json.dumps(record, ensure_ascii=False)], prompt_id=version)

    def _stream(self, client: httpx.Client, files: dict, data: dict) -> dict[str, Any]:
        event = None
        with client.stream("POST", self.url + "/answer/stream", files=files, data=data) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: ") and event:
                    payload = json.loads(line[6:])
                    if event == "token":
                        self._emit("delta", {"attempt": 1, "text": payload.get("text", "")})
                    elif event == "answer":
                        return payload
                    elif event == "error":
                        raise ValueError(f"RAG service error: {payload.get('error')}")
                    event = None
        raise ValueError("the RAG stream ended without an answer")
