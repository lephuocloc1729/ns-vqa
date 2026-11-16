"""The answer writer's prompt, from prompts/answer/<version>/ (docs/plans/phase-4.md, item 1).

- `spec.md`: the instructions;
- `examples.jsonl`: text-only examples, train questions only, each with its engine
  digest and an answer in the dataset's style;
- `config.yaml`: model, effort, max_tokens.

The prompt is the same for every question (never chosen per image), and its
version id carries a hash of all three files, so a change is a new version.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from vqa.answer.digest import to_text

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "answer"
DEFAULT_VERSION = "v1"


def _dir(version: str) -> Path:
    d = PROMPTS_DIR / version
    if not d.is_dir():
        raise FileNotFoundError(f"no answer prompt {version!r} under {PROMPTS_DIR}")
    return d


@lru_cache(maxsize=8)
def config(version: str = DEFAULT_VERSION) -> dict[str, Any]:
    return yaml.safe_load((_dir(version) / "config.yaml").read_text(encoding="utf-8")) or {}


def examples(version: str = DEFAULT_VERSION) -> list[dict[str, Any]]:
    path = _dir(version) / "examples.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def user_text(question: str, digest: dict[str, Any], true_false: bool) -> str:
    return (f"Question: {question.strip()}\n"
            f"True/false question: {'yes' if true_false else 'no'}\n"
            f"Engine result: {to_text(digest)}")


@lru_cache(maxsize=8)
def system_prompt(version: str = DEFAULT_VERSION) -> str:
    spec = (_dir(version) / "spec.md").read_text(encoding="utf-8").strip()
    shots = []
    for ex in examples(version):
        shots.append(user_text(ex["question"], ex["engine"], ex["true_false"]) + "\nReply: "
                     + json.dumps(ex["reply"], ensure_ascii=False, separators=(",", ":")))
    return spec + "\n\n" + "\n\n".join(shots)


def prompt_hash(version: str = DEFAULT_VERSION) -> str:
    cfg = (_dir(version) / "config.yaml").read_text(encoding="utf-8")
    return hashlib.sha256((system_prompt(version) + "\n--config--\n" + cfg).encode("utf-8")).hexdigest()


def prompt_id(version: str = DEFAULT_VERSION) -> str:
    return f"answer/{version}@{prompt_hash(version)[:12]}"
