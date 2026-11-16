"""The scene cache (docs/plans/phase-3.md, item 3; CLAUDE.md, leakage guard).

The only cache in the pipeline. It holds model outputs only, keyed by:

    image sha256 (of the original bytes) + model id + effort + prompt version

(plan D5: effort is part of the key, since it changes the output). Nothing else
can enter the key: not a file name, scene id or split. A record holds the replies
of the scene call (and of its re-run, if any) with their usage and cost; the scene
graph is rebuilt from the cached reply by the current wire and verification code,
so a change there needs no new call.

The two-pass fallback's tile and crop records (plan item 7) are kept here too,
keyed by the same four parts plus the region's pixel box (`region_key`).

Records live in cache/scenes/ (gitignored), or $VQA_SCENE_CACHE_DIR.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).resolve().parents[2] / "cache" / "scenes"

# What a stored reply may hold: the model's output and what the API said about it.
REPLY_FIELDS = frozenset({"pass", "raw_text", "stop_reason", "usage", "cost_usd", "request_id"})
RECORD_FIELDS = frozenset({"key", "image_sha256", "model", "effort", "prompt_version",
                           "replies", "created"})


def cache_dir() -> Path:
    return Path(os.environ.get("VQA_SCENE_CACHE_DIR", CACHE_DIR))


def scene_key(image_sha256: str, model: str, effort: str | None, prompt_version: str) -> str:
    """The cache key. Effort None (the model's default) is written as "default"."""
    if len(image_sha256) != 64 or any(c not in "0123456789abcdef" for c in image_sha256):
        raise ValueError("image_sha256 must be the hex sha256 of the image bytes")
    if not model or not prompt_version:
        raise ValueError("model and prompt_version are required")
    parts = "\n".join([image_sha256, model, effort or "default", prompt_version])
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


@dataclass
class CacheRecord:
    image_sha256: str
    model: str
    effort: str | None
    prompt_version: str
    replies: list[dict[str, Any]] = field(default_factory=list)
    created: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc)
                         .isoformat(timespec="seconds"))

    @property
    def key(self) -> str:
        return scene_key(self.image_sha256, self.model, self.effort, self.prompt_version)

    def check(self) -> None:
        """Model outputs only: every reply holds REPLY_FIELDS keys and nothing else."""
        for r in self.replies:
            if not isinstance(r, dict):
                raise ValueError("a cached reply must be an object")
            if extra := set(r) - REPLY_FIELDS:
                raise ValueError(f"the scene cache holds model outputs only; not {sorted(extra)}")
            if "raw_text" not in r:
                raise ValueError("a cached reply keeps the model's raw text")

    def to_json(self) -> dict[str, Any]:
        self.check()
        return {"key": self.key, **asdict(self)}


# ---------------------------------------------------------------- tile and crop records (plan item 7)
#
# The two-pass fallback reads parts of an image: a tile of a dense scene or a crop
# around one sign. Its records are keyed by the scene key's four parts plus the
# region's pixel box on the original image (owner, 2026-11-16), so a crop of one
# sign never answers for another. The scene key above is unchanged.

REGION_RECORD_FIELDS = RECORD_FIELDS | {"box"}


def _box(box) -> tuple[int, int, int, int]:
    if (not isinstance(box, (list, tuple)) or len(box) != 4
            or not all(isinstance(v, int) and not isinstance(v, bool) for v in box)):
        raise ValueError("box must be four integer pixel coordinates (x0, y0, x1, y1)")
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0 or x0 < 0 or y0 < 0:
        raise ValueError(f"box {tuple(box)} is empty or negative")
    return (x0, y0, x1, y1)


def region_key(image_sha256: str, model: str, effort: str | None, prompt_version: str,
               box) -> str:
    """The key of a tile or crop record: the scene key's parts plus the region's box."""
    scene_key(image_sha256, model, effort, prompt_version)          # same checks
    b = _box(box)
    parts = "\n".join([image_sha256, model, effort or "default", prompt_version, "region",
                       ",".join(map(str, b))])
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


@dataclass
class RegionRecord:
    image_sha256: str
    model: str
    effort: str | None
    prompt_version: str
    box: tuple[int, int, int, int]
    replies: list[dict[str, Any]] = field(default_factory=list)
    created: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc)
                         .isoformat(timespec="seconds"))

    @property
    def key(self) -> str:
        return region_key(self.image_sha256, self.model, self.effort, self.prompt_version, self.box)

    check = CacheRecord.check

    def to_json(self) -> dict[str, Any]:
        self.check()
        data = asdict(self)
        data["box"] = list(_box(tuple(self.box)))
        return {"key": self.key, **data}


class SceneCache:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else cache_dir()

    def path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, image_sha256: str, model: str, effort: str | None,
            prompt_version: str) -> CacheRecord | None:
        p = self.path(scene_key(image_sha256, model, effort, prompt_version))
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        if extra := set(data) - RECORD_FIELDS:
            raise ValueError(f"cache record {p.name} has fields it may not hold: {sorted(extra)}")
        data.pop("key", None)
        rec = CacheRecord(**data)
        rec.check()
        return rec

    def put(self, record: "CacheRecord | RegionRecord") -> Path:
        data = record.to_json()
        p = self.path(data["key"])
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, p)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return p

    def get_region(self, image_sha256: str, model: str, effort: str | None, prompt_version: str,
                   box) -> RegionRecord | None:
        """A tile or crop record (plan item 7), or None."""
        p = self.path(region_key(image_sha256, model, effort, prompt_version, box))
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        if extra := set(data) - REGION_RECORD_FIELDS:
            raise ValueError(f"cache record {p.name} has fields it may not hold: {sorted(extra)}")
        data.pop("key", None)
        data["box"] = tuple(data["box"])
        rec = RegionRecord(**data)
        rec.check()
        return rec

    def put_region(self, record: RegionRecord) -> Path:
        return self.put(record)
