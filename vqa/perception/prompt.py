"""Builds the scene call's system prompt from a versioned prompt folder:

    prompts/scene/<version>/spec.md        task, output format, what counts as a sign
    prompts/scene/<version>/config.yaml    max_tokens, image prep, effort per model
    prompts/scene/<version>/examples.jsonl text-only output examples: {image, note, output}

plus the sign catalog listing, generated at build time in catalog order (code,
Vietnamese name, shape / border / background, whether it carries a number). The
prompt hash covers the spec, the examples, the config and the catalog listing, so
a catalog change is a new prompt: `prompt_id()` ("scene/v1@<sha12>") is what the
scene cache keys on. Examples are fixed per version, never chosen per image.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from vqa.kb import load_catalog

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "scene"
DEFAULT_VERSION = "v1"


def _dir(version: str) -> Path:
    d = PROMPTS_DIR / version
    if not d.is_dir():
        raise FileNotFoundError(f"no scene prompt version {version!r} in {PROMPTS_DIR}")
    return d


@lru_cache(maxsize=8)
def config(version: str = DEFAULT_VERSION) -> dict[str, Any]:
    return yaml.safe_load((_dir(version) / "config.yaml").read_text(encoding="utf-8"))


def examples(version: str = DEFAULT_VERSION) -> list[dict[str, Any]]:
    p = _dir(version) / "examples.jsonl"
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def carries_value(sign) -> bool:
    e = sign.effect
    return bool(e.value or e.max_speed or e.min_speed or e.lane_board)


def catalog_listing() -> str:
    lines = []
    for s in load_catalog().signs:
        v = s.visual
        lines.append(f"{s.code} | {s.name_vi} | {v.shape} / {v.border} / {v.background}"
                     + (" | value" if carries_value(s) else ""))
    return "\n".join(lines)


@lru_cache(maxsize=8)
def system_prompt(version: str = DEFAULT_VERSION) -> str:
    spec = (_dir(version) / "spec.md").read_text(encoding="utf-8").strip()
    shots = []
    for ex in examples(version):
        shots.append(f"Example ({ex['note']}):\n"
                     + json.dumps(ex["output"], ensure_ascii=False, separators=(",", ":")))
    return (f"{spec}\n\n{catalog_listing()}\n\n# Examples\n\n" + "\n\n".join(shots) + "\n")


def prompt_hash(version: str = DEFAULT_VERSION) -> str:
    """sha256 of the system prompt (spec, catalog listing, examples) and the config."""
    cfg = (_dir(version) / "config.yaml").read_text(encoding="utf-8")
    return hashlib.sha256((system_prompt(version) + "\n--config--\n" + cfg).encode("utf-8")).hexdigest()


def prompt_id(version: str = DEFAULT_VERSION) -> str:
    """The prompt version the scene cache keys on: the folder plus the hash."""
    return f"scene/{version}@{prompt_hash(version)[:12]}"


def effort_for(model: str, version: str = DEFAULT_VERSION) -> str | None:
    return (config(version).get("effort") or {}).get(model)


def user_text() -> str:
    return "Read the road signs in this photo and reply with the JSON object."
