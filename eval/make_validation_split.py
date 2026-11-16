"""The phase-4.5 validation set (docs/plans/phase-4.5.md, section 5; owner, 2026-11-16).

Untouched train questions: the pool is `eval/coverage_analysis.pool()`. It leaves out
set T, gold signs, gold intents, any image or question named in prompts, eval/prompts,
tests, kb, eval/audits, docs or tools, any image in a duplicate group with public or
private, and any image in a duplicate group with an excluded train image.

Drawn by image with seed 20261116: every question of a drawn image comes along. Images
with a Yes/No question are drawn first (so the Yes/No share comes close to the private
test's 48%), then the rest, until the set reaches TARGET questions. Reads ids and
question types only, never question text or answers.

Writes `data/splits/train_validation.json` (ids only). The set is aggregate only, like
public_holdout: no question, answer or per-question result is read in phase 4.5.

    .venv/bin/python eval/make_validation_split.py
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import coverage_analysis as ca  # noqa: E402

SEED = 20261116
TARGET = 110
OUT = ROOT / "data" / "splits" / "train_validation.json"


def draw(images: list[str], questions: list[dict], seed: int = SEED, target: int = TARGET) -> list[str]:
    """Image ids in draw order until the set holds at least `target` questions."""
    by_img: dict[str, list[dict]] = {}
    for q in questions:
        by_img.setdefault(q["image_id"], []).append(q)
    rng = random.Random(seed)
    yn = sorted(i for i in images if any(q["question_type"] == "Yes/No" for q in by_img.get(i, [])))
    rest = sorted(i for i in images if i not in set(yn) and by_img.get(i))
    rng.shuffle(yn)
    rng.shuffle(rest)
    out, n = [], 0
    for i in yn + rest:
        if n >= target:
            break
        out.append(i)
        n += len(by_img[i])
    return out


def build(seed: int = SEED, target: int = TARGET) -> dict:
    images, questions, excluded = ca.pool()
    drawn = draw(images, questions, seed, target)
    chosen = set(drawn)
    qs = sorted((q for q in questions if q["image_id"] in chosen), key=lambda q: q["id"])
    return {
        "what": "phase-4.5 validation set: untouched train questions, aggregate only (docs/plans/phase-4.5.md)",
        "seed": seed, "target_questions": target,
        "pool": {"images": len(images), "questions": len(questions),
                 "excluded_images": {k: len(v) for k, v in excluded.items()}},
        "images": sorted(drawn), "questions": [q["id"] for q in qs],
        "counts": {"images": len(drawn), "questions": len(qs),
                   "question_types": dict(Counter(q["question_type"] for q in qs))},
    }


def split_sha256(path: Path = OUT) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> None:
    rec = build()
    OUT.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {rec['counts']}")


if __name__ == "__main__":
    main()
