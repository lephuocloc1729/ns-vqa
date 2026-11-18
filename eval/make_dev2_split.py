"""The phase-4.8 dev2 set (owner, 2026-11-18): a second development set, since dev is saturated.

**Biased.** dev2 comes from the train working set (train minus dev and validation questions and
validation images: 333 questions, `eval/phase46_analysis.working_set()`). Those images are shared
with the public and private test splits, and train is the rules' source, so dev2 is for finding
and fixing coverage gaps, never for reporting scores.

Selection (ids only):
- the pool is the working set minus
  - every dev and validation question **and image** (`data/splits/train_dev.json`,
    `train_validation.json`, read for their ids only),
  - every train question used as a parser few-shot in v7-v14 (`prompts/parser/v*/fewshot.jsonl`,
    read for `split` and `id` only),
  - the train rows of the new-types gold (`gold_v12_new.yaml`, read for `source` and `id` only);
- stratified by question type: each type gets its share of the **working set** (not the pool),
  rounded, so 100 questions are 70 Natural QA and 30 Yes/No;
- inside each type, a seeded sample of question ids (seed 20261118). Never by image similarity:
  `data/splits/duplicates.json` is not read. Questions on one image may fall on either side.

Reads the train QA file for `id`, `image_id` and `question_type` only (never question text or
answers). Writes `data/splits/train_dev2.json` (ids only).

    .venv/bin/python eval/make_dev2_split.py
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import gold_signs as gs  # noqa: E402
from eval.make_validation_split import DEV_OUT, OUT as VALIDATION  # noqa: E402

SEED = 20261118
TARGET = 100
OUT = ROOT / "data" / "splits" / "train_dev2.json"
FEWSHOT_VERSIONS = tuple(f"v{n}" for n in range(7, 15))
GOLD_V12_NEW = ROOT / "data" / "annotations" / "gold_v12_new" / "gold_v12_new.yaml"
BIASED_NOTE = ("train working-set questions: their images are shared with public and private, and train is "
               "the rules' source; for finding and fixing coverage gaps, never for reporting scores")


def _ids(path: Path) -> tuple[set[str], set[str]]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return set(d["questions"]), set(d["images"])


def train_rows(qa_file: Path | None = None) -> list[dict]:
    """Train questions as id, image id and type only."""
    rows = json.loads(Path(qa_file or gs.TRAIN_QA).read_text(encoding="utf-8"))
    return [{"id": q["id"], "image_id": q["image_id"], "question_type": q["question_type"]} for q in rows]


def working_set(rows: list[dict], dev_file: Path = DEV_OUT, validation_file: Path = VALIDATION) -> list[dict]:
    """Train minus dev and validation questions and validation images (phase46_analysis.working_set)."""
    dq, _ = _ids(dev_file)
    vq, vi = _ids(validation_file)
    return [q for q in rows if q["id"] not in dq and q["id"] not in vq and q["image_id"] not in vi]


def fewshot_ids(root: Path = ROOT, versions: tuple[str, ...] = FEWSHOT_VERSIONS) -> set[str]:
    """Train question ids used as parser few-shots in the given versions (split and id fields only)."""
    out: set[str] = set()
    for v in versions:
        f = root / "prompts" / "parser" / v / "fewshot.jsonl"
        if not f.exists():
            raise SystemExit(f"no few-shot file for parser {v}: {f}")
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("split") == "train":
                    out.add(r["id"])
    return out


def gold_train_ids(path: Path = GOLD_V12_NEW) -> set[str]:
    import yaml
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return {r["id"] for r in d["rows"] if r.get("source") == "train"}


def quotas(ws: list[dict], target: int = TARGET) -> dict[str, int]:
    """Each type's share of the working set, rounded (largest remainder), summing to `target`."""
    c = Counter(q["question_type"] for q in ws)
    n = sum(c.values())
    raw = {t: target * k / n for t, k in c.items()}
    out = {t: int(v) for t, v in raw.items()}
    for t in sorted(raw, key=lambda t: (-(raw[t] - out[t]), t))[: target - sum(out.values())]:
        out[t] += 1
    return dict(sorted(out.items()))


def build(seed: int = SEED, target: int = TARGET, *, rows: list[dict] | None = None,
          dev_file: Path = DEV_OUT, validation_file: Path = VALIDATION, root: Path = ROOT,
          gold_file: Path = GOLD_V12_NEW) -> dict:
    rows = rows if rows is not None else train_rows()
    ws = working_set(rows, dev_file, validation_file)
    dq, di = _ids(dev_file)
    vq, vi = _ids(validation_file)
    fs, gold = fewshot_ids(root), gold_train_ids(gold_file)
    excluded = {"dev_or_validation_image": {q["id"] for q in ws if q["image_id"] in di | vi},
                "parser_fewshot_v7_v14": {q["id"] for q in ws if q["id"] in fs},
                "gold_v12_new_train_rows": {q["id"] for q in ws if q["id"] in gold}}
    drop = set().union(*excluded.values())
    pool = [q for q in ws if q["id"] not in drop and q["id"] not in dq | vq]
    want = quotas(ws, target)
    rng = random.Random(seed)
    chosen: list[dict] = []
    for t, k in want.items():
        ids = sorted(q["id"] for q in pool if q["question_type"] == t)
        if len(ids) < k:
            raise SystemExit(f"the pool has {len(ids)} {t} questions; {k} are needed")
        pick = set(rng.sample(ids, k))
        chosen += [q for q in pool if q["id"] in pick]
    chosen.sort(key=lambda q: q["id"])
    return {"what": "phase-4.8 dev2 set: train working-set questions, readable per question (owner, 2026-11-18)",
            "biased": True, "biased_note": BIASED_NOTE,
            "seed": seed, "target_questions": target,
            "stratified_by": "question_type, in the working set's proportions",
            "working_set": {"questions": len(ws), "question_types": dict(sorted(Counter(
                q["question_type"] for q in ws).items()))},
            "excluded_questions": {k: len(v) for k, v in excluded.items()},
            "pool": {"questions": len(pool), "question_types": dict(sorted(Counter(
                q["question_type"] for q in pool).items()))},
            "images": sorted({q["image_id"] for q in chosen}), "questions": [q["id"] for q in chosen],
            "counts": {"images": len({q["image_id"] for q in chosen}), "questions": len(chosen),
                       "question_types": dict(sorted(Counter(q["question_type"] for q in chosen).items()))}}


def main() -> None:
    rec = build()
    OUT.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {rec['counts']}  pool {rec['pool']}  excluded {rec['excluded_questions']}")


if __name__ == "__main__":
    main()
