"""Builds the parser's system prompt from a versioned prompt folder:

    prompts/parser/<version>/spec.md        the DSL spec and conventions
    prompts/parser/<version>/fewshot.jsonl  examples: {id, split, question, output}

plus the sign catalog (code, key, tags, Vietnamese name), rendered in catalog
order so the prompt is byte-identical between runs (prompt caching is a prefix
match). Few-shot examples come only from train and public_dev (checked by
tests/test_parser.py); they are fixed per version, never chosen per question.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from vqa.kb import load_catalog

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "parser"


def examples(version: str = "v1") -> list[dict]:
    path = PROMPTS_DIR / version / "fewshot.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def catalog_table() -> str:
    lines = ["code | key | tags | name (vi)", "--- | --- | --- | ---"]
    for s in load_catalog().signs:
        lines.append(f"{s.code} | {s.key} | {', '.join(s.tags)} | {s.name_vi}")
    return "\n".join(lines)


@lru_cache(maxsize=8)
def system_prompt(version: str = "v1") -> str:
    spec = (PROMPTS_DIR / version / "spec.md").read_text(encoding="utf-8").strip()
    shots = []
    for ex in examples(version):
        shots.append(f"Question: {ex['question']}\nAnswer: "
                     + json.dumps(ex["output"], ensure_ascii=False, separators=(",", ":")))
    return (f"{spec}\n\n## Sign catalog\n\n{catalog_table()}\n\n## Examples\n\n"
            + "\n\n".join(shots) + "\n")
