"""Builds the scene call's system prompt from a versioned prompt folder:

    prompts/scene/<version>/spec.md        task, output format, what counts as a sign
    prompts/scene/<version>/config.yaml    max_tokens, image prep, effort per model
    prompts/scene/<version>/examples.jsonl text-only output examples: {image, note, output}

and, when the config names one, a pictogram manifest (prompts/scene/<version>/
pictograms.yaml) with its local figure copies in pictograms/ (gitignored; built by
tools/build_scene_pictograms.py, CLAUDE.md exception). The copies are checked
against the manifest's sha256 and the version refuses to build if one is missing
or differs. The figures go in the user turn before the photo (the API takes only
text in the system prompt), with cache_control on the last figure.

The system prompt holds the sign catalog listing, generated in catalog order (code,
Vietnamese name, shape / border / background, whether it carries a number). The
prompt hash covers the spec, the examples, the config and the catalog listing, so
a catalog change is a new prompt: `prompt_id()` ("scene/v1@<sha12>") is what the
scene cache keys on. Examples are fixed per version, never chosen per image.
"""

from __future__ import annotations

import base64
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


class PictogramError(RuntimeError):
    pass


def manifest(version: str = DEFAULT_VERSION) -> dict[str, Any] | None:
    """The pictogram manifest named in the config, or None."""
    name = config(version).get("pictograms")
    if not name:
        return None
    return yaml.safe_load((_dir(version) / name).read_text(encoding="utf-8"))


def check_pictograms(version: str = DEFAULT_VERSION) -> list[Path]:
    """The local figure copies, each checked against the manifest's sha256."""
    m = manifest(version)
    if m is None:
        return []
    files, seen = [], set()
    for row in m["rows"]:
        for fig in row["figures"]:
            if fig["file"] in seen:
                continue
            seen.add(fig["file"])
            p = _dir(version) / "pictograms" / fig["file"]
            if not p.exists():
                raise PictogramError(f"{version}: pictogram {fig['file']} ({row['code']}) is missing; "
                                     f"run tools/build_scene_pictograms.py --version {version}")
            if hashlib.sha256(p.read_bytes()).hexdigest() != fig["sha256"]:
                raise PictogramError(f"{version}: pictogram {fig['file']} ({row['code']}) does not match "
                                     f"the manifest; run tools/build_scene_pictograms.py --version {version}")
            files.append(p)
    return files


def pictogram_blocks(version: str = DEFAULT_VERSION) -> list[dict[str, Any]]:
    """User-turn content blocks for the reference figures: a text label (every code
    the figure shows) then the image, figure by figure in manifest order; the last
    block carries cache_control so the figures are part of the cached prefix."""
    m = manifest(version)
    if m is None:
        return []
    check_pictograms(version)
    order, labels = [], {}
    for row in m["rows"]:
        for fig in row["figures"]:
            if fig["file"] not in labels:
                order.append(fig["file"])
                labels[fig["file"]] = []
            labels[fig["file"]].append(f"{row['code']} {row['name_vi']}")
    blocks: list[dict[str, Any]] = [{"type": "text", "text": "Reference figures:"}]
    for name in order:
        data = (_dir(version) / "pictograms" / name).read_bytes()
        blocks.append({"type": "text", "text": "; ".join(labels[name])})
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                   "data": base64.b64encode(data).decode("ascii")}})
    blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
    blocks.append({"type": "text", "text": "The photo:"})
    return blocks


def prompt_hash(version: str = DEFAULT_VERSION) -> str:
    """sha256 of the system prompt (spec, catalog listing, examples), the config and
    the pictogram manifest (whose sha256 values pin the figure copies)."""
    cfg = (_dir(version) / "config.yaml").read_text(encoding="utf-8")
    text = system_prompt(version) + "\n--config--\n" + cfg
    name = config(version).get("pictograms")
    if name:          # versions without pictograms keep the hash they had (v1, v2)
        text += "\n--pictograms--\n" + (_dir(version) / name).read_text(encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_id(version: str = DEFAULT_VERSION) -> str:
    """The prompt version the scene cache keys on: the folder plus the hash."""
    return f"scene/{version}@{prompt_hash(version)[:12]}"


def effort_for(model: str, version: str = DEFAULT_VERSION) -> str | None:
    return (config(version).get("effort") or {}).get(model)


def user_text(version: str | None = None) -> str:
    """The instruction after the photo. A version's config may set its own (`user_text`,
    the fallback's tile and crop prompts); v1-v4 set none and keep this one."""
    own = config(version).get("user_text") if version else None
    return own or "Read the road signs in this photo and reply with the JSON object."


def user_content(image_block: dict[str, Any], version: str = DEFAULT_VERSION) -> list[dict[str, Any]]:
    """The user turn: reference figures (if the version has them), the photo, the
    instruction. The photo is always the last image."""
    return [*pictogram_blocks(version), image_block, {"type": "text", "text": user_text(version)}]
