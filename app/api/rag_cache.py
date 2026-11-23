"""A cache of the RAG fallback's own answers (owner exception, 2026-11-23; docs/deploy.md).

The RAG answers exactly the same text for the same photo and question when it runs one question
at a time (temperature 0, a fixed seed: 24 of 24 identical on a rerun, docs/results/
rag-concurrency-2026-11-23.md). So a repeated question can be served from its first answer:
instantly, without the GPU, and with exactly the words the RAG would write again.

- **What is stored:** only answers the live RAG gave to questions asked through this API.
  - Successful ones only, made while the RAG ran one question at a time (its /version reports
    `llama_parallel`).
  - Never gold answers, dataset files, or earlier evaluation outputs.
- **The key:** the photo's sha256, the question exactly as asked (trimmed only), and the RAG's
  version (`config_version` and its slot count). A changed RAG never matches old entries.
- **Storage:** one small JSON file per answer, at most `max_entries` (the oldest go first),
  optionally ignored after `max_days`.
- **Switch:** VQA_RAG_CACHE=on (default off). Clear it with
  `python -m app.api.rag_cache clear [DIR]`; `stats` counts it.

`CachedRagFallback` has the RagFallback interface (`answer`, `on_event`, `prompt_id`, `url`), so the
pipeline and the runner use it unchanged. A hit streams its text as one token and marks the
record `cache_hit: true`.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import httpx

from vqa.answer.fallback import FallbackAnswer


class RagAnswerCache:
    def __init__(self, folder: Path, *, max_entries: int = 20000, max_days: float = 0.0) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.max_entries, self.max_days = max_entries, max_days
        self._puts = 0
        self._lock = threading.Lock()

    @staticmethod
    def key(image_sha256: str, question: str, version: str) -> str:
        text = json.dumps([image_sha256, question.strip(), version], ensure_ascii=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.folder / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        p = self._path(key)
        try:
            if self.max_days and time.time() - p.stat().st_mtime > self.max_days * 86400:
                return None
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def put(self, key: str, entry: dict[str, Any]) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.folder, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False)
        os.replace(tmp, self._path(key))
        with self._lock:
            self._puts += 1
            check = self._puts % 100 == 1
        if check:
            self.trim()

    def entries(self) -> list[Path]:
        return list(self.folder.glob("*.json"))

    def trim(self) -> int:
        """Keep the newest `max_entries` answers; return how many were removed."""
        files = self.entries()
        extra = len(files) - self.max_entries
        if extra <= 0:
            return 0
        files.sort(key=lambda p: p.stat().st_mtime)
        for p in files[:extra]:
            p.unlink(missing_ok=True)
        return extra

    def clear(self) -> int:
        files = self.entries()
        for p in files:
            p.unlink(missing_ok=True)
        return len(files)


class CachedRagFallback:
    """The RAG fallback with a cache of its own answers in front of it."""

    def __init__(self, inner: Any, cache: RagAnswerCache, *, version_ttl_s: float = 60.0,
                 fetch_version: Callable[[], dict[str, Any]] | None = None) -> None:
        self.inner, self.cache, self.version_ttl_s = inner, cache, version_ttl_s
        self._fetch = fetch_version or self._fetch_version
        self._version: tuple[float, dict[str, Any]] | None = None
        self._lock = threading.Lock()
        self.hits = self.misses = 0

    # the RagFallback interface ------------------------------------------------------------
    @property
    def url(self) -> str:
        return self.inner.url

    @property
    def on_event(self):
        return self.inner.on_event

    @on_event.setter
    def on_event(self, fn) -> None:
        self.inner.on_event = fn

    @property
    def prompt_id(self) -> str:
        return self.inner.prompt_id

    @prompt_id.setter
    def prompt_id(self, value: str) -> None:
        self.inner.prompt_id = value

    # ---------------------------------------------------------------------------------------
    def _fetch_version(self) -> dict[str, Any]:
        with httpx.Client(timeout=3.0) as c:
            r = c.get(self.inner.url + "/version")
            r.raise_for_status()
            return r.json()

    def version(self) -> dict[str, Any] | None:
        """The RAG's /version, fetched at most once a minute. When the RAG cannot be reached, the
        last version seen (also kept on disk), so its cached answers still serve."""
        with self._lock:
            if self._version and time.monotonic() - self._version[0] < self.version_ttl_s:
                return self._version[1]
        known = self.cache.folder / "rag_version.last"
        try:
            v = self._fetch()
            known.write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
        except Exception:
            try:
                v = json.loads(known.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
        with self._lock:
            self._version = (time.monotonic(), v)
        return v

    @staticmethod
    def version_key(v: dict[str, Any]) -> str:
        return f"{v.get('config_version')}|slots={v.get('llama_parallel', 1)}"

    def answer(self, image_path: str | Path, question: str, scene: Any) -> FallbackAnswer:
        v = self.version()
        if v is None or not v.get("config_version"):
            return self.inner.answer(image_path, question, scene)          # unknown RAG: no cache
        sha = hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
        k = self.cache.key(sha, question, self.version_key(v))
        hit = self.cache.get(k)
        if hit is not None:
            self.hits += 1
            fa = FallbackAnswer(**hit["answer"])
            fa.cost_usd = 0.0
            fa.raw = [self._mark_hit(r) for r in fa.raw]
            if self.inner.on_event is not None:
                try:
                    self.inner.on_event("delta", {"text": fa.text})
                except Exception:
                    pass
            self.inner.prompt_id = fa.prompt_id
            return fa
        self.misses += 1
        fa = self.inner.answer(image_path, question, scene)
        if fa.status == "ok" and fa.text and int(v.get("llama_parallel", 1)) == 1:
            self.cache.put(k, {"answer": asdict(fa), "rag_version": v.get("config_version"),
                               "stored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        return fa

    @staticmethod
    def _mark_hit(raw: str) -> str:
        try:
            record = json.loads(raw)
        except ValueError:
            return raw
        if isinstance(record, dict):
            record["cache_hit"] = True
            return json.dumps(record, ensure_ascii=False)
        return raw


def main(argv: list[str]) -> None:
    from app.api.settings import Settings
    if not argv or argv[0] not in ("clear", "stats"):
        raise SystemExit("usage: python -m app.api.rag_cache clear|stats [DIR]")
    folder = Path(argv[1]) if len(argv) > 1 else Settings.from_env().rag_cache_dir
    cache = RagAnswerCache(folder)
    if argv[0] == "clear":
        print(f"removed {cache.clear()} cached RAG answers from {folder}")
    else:
        files = cache.entries()
        print(f"{len(files)} cached RAG answers in {folder}, {sum(p.stat().st_size for p in files) // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1:])
