"""Option C, step 3: compare the baseline and KB runs on public_dev.

Reads the two runs' predictions.jsonl, keeps the public_dev questions (the ids in the
knowledge-base export), and reports:
- how many answers changed, and how many questions actually got an extra article;
- Yes/No accuracy for both runs, graded by the answer's first word against the gold;
- the changed Natural QA answers, written to a CSV for judging (public_dev may be read
  question by question).
For the other public questions (public_holdout, aggregate only) it prints one count:
how many answers are identical across the runs, a check that the runs are repeatable.

    python experiments/option_c/compare_runs.py --base outputs/option_c/public_C_base \
        --kb outputs/option_c/public_C_kb1 --kb-file experiments/option_c/public_dev_phase4.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "data/raw/VLSP2025-MLQA-Natural/dataset/public_test data/vlsp_2025_public_test.json"
OUT = ROOT / "outputs/option_c"

YES = ("đúng", "có", "được")
NO = ("sai", "không")


def polarity(text: str | None) -> bool | None:
    """Đúng / Có / Được -> True; Sai / Không (được) -> False; anything else -> None."""
    t = unicodedata.normalize("NFC", (text or "").strip().lower())
    t = re.sub(r"^[\W_]+", "", t)
    if t.startswith(NO):
        return False
    if t.startswith(YES):
        return True
    return None


def predictions(folder: Path) -> dict[str, dict]:
    path = folder / "public_test" / "predictions.jsonl"
    return {r["id"]: r for r in (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--kb", type=Path, required=True)
    ap.add_argument("--kb-file", type=Path, required=True)
    a = ap.parse_args()
    dev = [json.loads(l)["id"] for l in a.kb_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    gold = {q["id"]: q for q in json.loads(PUBLIC.read_text(encoding="utf-8"))}
    base, kb = predictions(a.base), predictions(a.kb)
    other = [q for q in base if q not in set(dev)]
    rows, yn = [], {"n": 0, "base": 0, "kb": 0}
    for q in dev:
        b, k = base[q], kb[q]
        added = k.get("kb_added_citations") or []
        changed = b["answer"].strip() != k["answer"].strip()
        if gold[q]["question_type"] == "Yes/No":
            g = polarity(gold[q]["answer"])
            yn["n"] += 1
            yn["base"] += polarity(b["answer"]) == g
            yn["kb"] += polarity(k["answer"]) == g
        rows.append({"id": q, "type": gold[q]["question_type"], "kb_added": len(added),
                     "kb_kept_in_context": sum(1 for c in k.get("citations", []) if "kb" in (c.get("sources") or [])),
                     "changed": changed, "question": gold[q]["question"], "gold": gold[q]["answer"],
                     "base_answer": b["answer"], "kb_answer": k["answer"]})
    report = {
        "public_dev_questions": len(dev),
        "got_an_extra_article": sum(r["kb_added"] > 0 for r in rows),
        "extra_article_kept_in_context": sum(r["kb_kept_in_context"] > 0 for r in rows),
        "answers_changed": sum(r["changed"] for r in rows),
        "answers_changed_without_extra_article": sum(r["changed"] and not r["kb_added"] for r in rows),
        "yes_no": {"n": yn["n"], "base_right": yn["base"], "kb_right": yn["kb"]},
        "natural_qa_changed": sum(r["changed"] and r["type"] != "Yes/No" for r in rows),
        "other_public_identical": f"{sum(base[q]['answer'].strip() == kb[q]['answer'].strip() for q in other)}/{len(other)}",
        "seconds_per_question": {
            "base": round(sum(base[q].get("elapsed_seconds", 0) for q in dev) / len(dev), 2),
            "kb": round(sum(kb[q].get("elapsed_seconds", 0) for q in dev) / len(dev), 2)},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "compare_runs.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(OUT / "changed_natural_qa.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "question", "gold", "base_answer", "kb_answer", "base_label", "kb_label"])
        w.writeheader()
        for r in rows:
            if r["changed"] and r["type"] != "Yes/No":
                w.writerow({k: r.get(k, "") for k in ("id", "question", "gold", "base_answer", "kb_answer")}
                           | {"base_label": "", "kb_label": ""})
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
