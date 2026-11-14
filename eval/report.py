"""Score reports that separate duplicated images from the rest.

Many test images also appear in train (data/splits/duplicates.json), so every
evaluation reports its score twice: on all questions, and on questions whose
image has no near-duplicate in the data used for development. The second
figure gets a 95% Wilson confidence interval, since the subset is small.

    from eval.report import score_report, format_report
    rep = score_report(results, split="public")   # results: [{question_id, image_id, correct}]
    print(format_report(rep))
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
DUPLICATES = ROOT / "data" / "splits" / "duplicates.json"

# Which other splits count as "seen" when a test image is a duplicate.
DEFAULT_AGAINST = {
    "public": {"train"},
    "private": {"train", "public"},
    "train": set(),
}


def wilson_ci(correct: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion (correct may be fractional)."""
    if n == 0:
        return (0.0, 0.0)
    p = correct / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def duplicated_images(split: str, duplicates: dict[str, Any] | None = None,
                      against: set[str] | None = None) -> set[str]:
    """Image ids of `split` that share a duplicate group with any split in `against`."""
    dup = duplicates if duplicates is not None else json.loads(DUPLICATES.read_text("utf-8"))
    against = DEFAULT_AGAINST.get(split, set()) if against is None else against
    out: set[str] = set()
    for g in dup["groups"]:
        splits = {im["split"] for im in g["images"]}
        if split in splits and splits & against:
            out |= {im["image_id"] for im in g["images"] if im["split"] == split}
    return out


def _summary(rows: list[dict[str, Any]], with_ci: bool) -> dict[str, Any]:
    n = len(rows)
    correct = float(sum(float(r["correct"]) for r in rows))
    out: dict[str, Any] = {"n": n, "correct": correct, "accuracy": correct / n if n else None}
    if with_ci:
        out["ci95"] = list(wilson_ci(correct, n))
    return out


def score_report(results: Iterable[dict[str, Any]], split: str,
                 duplicates: dict[str, Any] | None = None,
                 against: set[str] | None = None) -> dict[str, Any]:
    """results: one dict per question with image_id and correct (bool or 0..1)."""
    rows = list(results)
    dup = duplicated_images(split, duplicates, against)
    non_dup = [r for r in rows if r["image_id"] not in dup]
    return {
        "split": split,
        "against": sorted(DEFAULT_AGAINST.get(split, set()) if against is None else against),
        "all_images": _summary(rows, with_ci=False),
        "non_duplicate_images": _summary(non_dup, with_ci=True),
        "duplicate_images": _summary([r for r in rows if r["image_id"] in dup], with_ci=False),
    }


def format_report(rep: dict[str, Any]) -> str:
    def pct(x: float | None) -> str:
        return "n/a" if x is None else f"{100 * x:.1f}%"

    a, nd, d = rep["all_images"], rep["non_duplicate_images"], rep["duplicate_images"]
    lo, hi = nd["ci95"]
    return (f"{rep['split']}: all images {pct(a['accuracy'])} (n={a['n']}) | "
            f"non-duplicate {pct(nd['accuracy'])} (n={nd['n']}, 95% CI {pct(lo)}-{pct(hi)}) | "
            f"duplicate {pct(d['accuracy'])} (n={d['n']}; duplicates of "
            f"{', '.join(rep['against']) or 'none'})")
