"""The guide-board call (phase 4.5 B6; owner, 2026-11-17: approved, variant A).

One extra call per image whose scene lists a guide board: Haiku reads the photo alone with
`prompts/scene/v5-guide/` and transcribes the boards' destinations, distances, arrows, route
plates and the speed discs printed on or mounted with them. The result goes into the scene
as schema 1.3 `guide_boards`; the board speed discs also become P.127 / R.306 signs, so the
speed rules see them. Nothing here decides what is allowed.

- **When:** `needs_boards(scene)`: the scene lists an I / IE board, or a rectangular non-red
  board it could not read.
- **Cache:** a region record over the whole image (`region_key` with box (0, 0, w, h)) in the
  scene cache, keyed by image sha256 + model + effort + the guide prompt id. Model output
  only. One retry on a reply that isn't the JSON object, sending only the error.
- **Failure:** a refused, truncated or unusable reply leaves the scene as it was.

The prompt is the spec and examples alone (no catalog listing): it reads text, not codes.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from vqa.llm.client import LLMBadJSON, LLMRefusal, LLMTruncated, parse_json_reply
from vqa.perception.cache import RegionRecord, SceneCache
from vqa.perception.image import PreparedImage
from vqa.perception.wire import retry_messages
from vqa.schemas import (GUIDE_SCHEMA_VERSION, BoardSpeed, GuideBoard, GuideEntry, Position,
                         SceneGraph, Sign)

VERSION = "v5-guide"
PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts" / "scene" / VERSION
BOARD_CODES = ("I.", "IE.")
DIRECTIONS = ("straight", "left", "right", "slight_left", "slight_right", "u_turn", "none")


# ---------------------------------------------------------------- the prompt

@lru_cache(maxsize=1)
def config() -> dict[str, Any]:
    return yaml.safe_load((PROMPT_DIR / "config.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def system_prompt() -> str:
    spec = (PROMPT_DIR / "spec.md").read_text(encoding="utf-8").strip()
    ex = [json.loads(line) for line in (PROMPT_DIR / "examples.jsonl").read_text(encoding="utf-8").splitlines()
          if line.strip()]
    shots = "\n\n".join(f"Example ({e['note']}):\n" + json.dumps(e["output"], ensure_ascii=False, separators=(",", ":"))
                        for e in ex)
    return f"{spec}\n\n# Examples\n\n{shots}\n"


def prompt_hash() -> str:
    return hashlib.sha256((system_prompt() + "\n--config--\n" + (PROMPT_DIR / "config.yaml")
                           .read_text(encoding="utf-8")).encode("utf-8")).hexdigest()


def prompt_id() -> str:
    return f"scene/{VERSION}@{prompt_hash()[:12]}"


def effort_for(model: str) -> str | None:
    return (config().get("effort") or {}).get(model)


# ---------------------------------------------------------------- when to call

def is_guide_board(sign: Sign, catalog) -> bool:
    """An I / IE board, or an unread rectangular board that isn't red (a local ban notice)."""
    if sign.code.startswith(BOARD_CODES) and catalog.has(sign.code):
        return True
    if catalog.has(sign.code):
        return False
    shape = getattr(sign.shape, "value", sign.shape)
    colours = {getattr(sign.border, "value", sign.border), getattr(sign.background, "value", sign.background)}
    return shape in ("rectangle", "square") and "red" not in colours


def needs_boards(scene: SceneGraph, catalog) -> bool:
    return any(is_guide_board(s, catalog) for s in scene.signs)


# ---------------------------------------------------------------- the reply

def parse_distance_m(text: Any) -> float | None:
    """"61 KM" -> 61000, "150 M" -> 150, "5.8 km" -> 5800; None when no distance is printed."""
    if text is None:
        return None
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(km|m)\b", str(text), re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return v * 1000 if m.group(2).lower() == "km" else v


def to_boards(data: Any) -> tuple[list[GuideBoard], list[str]]:
    """The reply's boards as schema-1.3 GuideBoard rows, and the issues met. Lenient: a
    malformed entry or speed is dropped (and named), the rest is kept."""
    issues: list[str] = []
    if not isinstance(data, dict) or not isinstance(data.get("boards"), list):
        return [], ["the reply has no `boards` list"]
    out = []
    for n, b in enumerate(data["boards"], 1):
        if not isinstance(b, dict):
            issues.append(f"board {n} is not an object; dropped")
            continue
        entries = []
        for e in b.get("entries") or []:
            if not isinstance(e, dict) or not isinstance(e.get("text"), str) or not e["text"].strip():
                issues.append(f"board {n}: an entry without text; dropped")
                continue
            d = e.get("direction") or "none"
            if d not in DIRECTIONS:
                issues.append(f"board {n}: direction {d!r} is not one of {DIRECTIONS}; read as none")
                d = "none"
            entries.append(GuideEntry(text=e["text"].strip(), distance_m=parse_distance_m(e.get("distance")),
                                      direction=d))
        speeds = []
        for s in b.get("speeds") or []:
            v = s.get("value") if isinstance(s, dict) else None
            if isinstance(s, dict) and s.get("kind") in ("max", "min") and isinstance(v, (int, float)) \
                    and not isinstance(v, bool) and 5 <= v <= 150:
                speeds.append(BoardSpeed(kind=s["kind"], value=float(v)))
            else:
                issues.append(f"board {n}: speed {s!r} dropped")
        route = b.get("route") if isinstance(b.get("route"), str) and b["route"].strip() else None
        other = [x.strip() for x in b.get("other") or [] if isinstance(x, str) and x.strip()]
        if entries or speeds or route or other:
            out.append(GuideBoard(entries=entries, speeds=speeds, route=route, other=other))
    return out, issues


def apply(scene: SceneGraph, boards: list[GuideBoard]) -> SceneGraph:
    """The scene with its guide boards (schema 1.3). Each board speed disc not already in the
    scene as a P.127 (max) or R.306 (min) of the same value is added as one, so the speed
    rules apply it like any posted limit. Added signs are ids g1, g2, ... with the disc's
    look; they carry no box."""
    if not boards:
        return scene
    have = {(s.code, s.value) for s in scene.signs}
    added, n = [], 0
    for b in boards:
        for sp in b.speeds:
            code = "P.127" if sp.kind == "max" else "R.306"
            if (code, sp.value) in have:
                continue
            have.add((code, sp.value))
            n += 1
            look = dict(shape="circle", border="red", background="white") if code == "P.127" else \
                dict(shape="circle", border="none", background="blue")
            added.append(Sign(id=f"g{n}", code=code, value=sp.value, unit="km/h", confidence="high",
                              position=Position(), **look))
    return scene.model_copy(update={"guide_boards": list(boards), "signs": list(scene.signs) + added,
                                    "schema_version": GUIDE_SCHEMA_VERSION})


# ---------------------------------------------------------------- the call

@dataclass
class GuideResult:
    boards: list[GuideBoard] = field(default_factory=list)
    called: bool = False
    cache_hit: bool = False
    ok: bool = False
    cost_usd: float = 0.0
    issues: list[str] = field(default_factory=list)
    raw: list[str] = field(default_factory=list)


def read_boards(img: PreparedImage, *, model: str, client, cache: SceneCache, use_cache: bool = True) -> GuideResult:
    """The boards in one photo: from the cache, else one call (plus one retry)."""
    res = GuideResult()
    pid, effort = prompt_id(), effort_for(model)
    w, h = img.original_size
    box = (0, 0, int(w), int(h))
    if use_cache and (rec := cache.get_region(img.sha256, model, effort, pid, box)) is not None:
        text = rec.replies[-1]["raw_text"]
        res.cache_hit, res.raw = True, [text]
        try:
            res.boards, res.issues = to_boards(parse_json_reply(text))
            res.ok = True
        except LLMBadJSON as e:
            res.issues.append(f"cached reply is not JSON: {e}")
        return res
    if client is None:
        res.issues.append("no client: the guide call was not made")
        return res
    cfg, system = config(), system_prompt()
    user = [img.content_block(), {"type": "text", "text": cfg["user_text"]}]
    stored: list[dict[str, Any]] = []

    def call(extra=None):
        return client.json_reply(system=system, user=user, max_tokens=cfg["max_tokens"], effort=effort,
                                 purpose="guide boards" + (" retry" if extra else ""), extra_messages=extra)

    res.called = True
    errors: list[str] = []
    for attempt in (1, 2):
        try:
            reply = call(retry_messages(errors) if attempt == 2 else None)
        except (LLMRefusal, LLMTruncated) as e:
            res.cost_usd += getattr(e, "cost_usd", 0.0)
            res.issues.append(f"guide call failed ({type(e).__name__})")
            return res
        except LLMBadJSON as e:
            res.cost_usd += getattr(e, "cost_usd", 0.0)
            res.raw.append(getattr(e, "raw_text", "") or "")
            errors = [str(e)]
            res.issues.append(f"guide reply not JSON ({e})" + ("; retried" if attempt == 1 else ""))
            continue
        res.cost_usd += reply.cost_usd
        res.raw.append(reply.raw_text)
        if not isinstance(reply.data, dict) or not isinstance(reply.data.get("boards"), list):
            errors = ["the reply must be a JSON object with a `boards` list"]
            res.issues.append(errors[0] + ("; retried" if attempt == 1 else ""))
            continue
        stored.append({"pass": "guide" if attempt == 1 else "guide retry", "raw_text": reply.raw_text,
                       "stop_reason": "end_turn", "usage": reply.usage, "cost_usd": reply.cost_usd,
                       "request_id": reply.request_id})
        cache.put_region(RegionRecord(img.sha256, model, effort, pid, box, replies=stored))
        res.boards, issues = to_boards(reply.data)
        res.issues += issues
        res.ok = True
        return res
    return res
