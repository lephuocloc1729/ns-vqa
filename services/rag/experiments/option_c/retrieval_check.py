"""Option C, step 2: does adding the knowledge base's articles improve retrieval?

Offline and CPU-only: no model, no embedding, no change to the runner. It compares the
citations each variant would give the answer model with the dataset's gold
`relevant_articles`, using the same per-query metric as `natural_qa_tuning.metric_report`
(F2 = 5*tp / (|predicted| + 4*|gold|), macro-averaged), at K = 5.

Inputs:
- the neuro-symbolic project's export (`eval/kb_articles.py`): per question, the articles
  the sign catalog names for the readable signs in that photo;
- RAG's tuning predictions on its train-dev split (`tuning_predictions.jsonl`), the only
  RAG retrieval with gold citations and no self-retrieval from the example bank.

Variants (each capped at K):
- rag:        RAG's final hybrid citations, unchanged;
- kb:         the catalog articles only;
- kb_then_rag: catalog articles first, RAG's citations fill the rest;
- kbN_then_rag: at most N catalog articles, then RAG's.

Two reports: all variants on the questions both sides cover, and the catalog articles
alone on every question of the export (recall and precision of the knowledge base).

    python experiments/option_c/retrieval_check.py \
        --kb ../NewNeuroSymbolic/eval/runs/kb_articles/dev_phase49.jsonl \
             ../NewNeuroSymbolic/eval/runs/kb_articles/dev2_phase49.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TUNING = ROOT / "artifacts/experiments/text_based_rag/natural_qa/tuning_train_dev_expanded/tuning_predictions.jsonl"
TRAIN = ROOT / "data/raw/VLSP2025-MLQA-Natural/dataset/train data/vlsp_2025_train.json"
OUT = ROOT / "outputs/option_c"
K = 5


def key(c: dict) -> tuple[str, str]:
    return (str(c["law_id"]), str(c["article_id"]))


def dedupe(items):
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def metrics(gold: set, predicted: list) -> dict:
    pred = set(predicted)
    tp = len(gold & pred)
    return {"precision": tp / len(pred) if pred else 0.0, "recall": tp / len(gold) if gold else 0.0,
            "f2": 5 * tp / (len(pred) + 4 * len(gold)) if pred or gold else 0.0, "hit": int(tp > 0),
            "predicted": len(pred)}


def macro(rows: list[dict]) -> dict:
    n = len(rows)
    return {k: round(sum(r[k] for r in rows) / n, 4) for k in ("precision", "recall", "f2", "hit", "predicted")} | {"n": n}


def variants(kb: list, rag: list) -> dict[str, list]:
    out = {"rag": rag[:K], "kb": kb[:K], "kb_then_rag": dedupe(kb + rag)[:K]}
    for n in (1, 2, 3):
        out[f"kb{n}_then_rag"] = dedupe(kb[:n] + rag)[:K]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", type=Path, nargs="+", required=True)
    ap.add_argument("--tuning", type=Path, default=TUNING)
    ap.add_argument("--train", type=Path, default=TRAIN)
    a = ap.parse_args()
    kb = {}
    for p in a.kb:
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            kb[r["id"]] = dedupe(key(c) for c in r["articles"])
    gold = {q["id"]: {key(c) for c in (q.get("relevant_articles") or [])}
            for q in json.loads(a.train.read_text(encoding="utf-8"))}
    rag = {}
    for line in a.tuning.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        rag[r["id"]] = [key(c) for c in r["predicted_citations"]]
    both = sorted(q for q in kb if q in rag and gold.get(q))
    by_variant: dict[str, list] = {}
    for q in both:
        for name, pred in variants(kb[q], rag[q]).items():
            by_variant.setdefault(name, []).append(metrics(gold[q], pred))
    kb_all = [metrics(gold[q], kb[q][:K]) for q in kb if gold.get(q)]
    report = {"k": K, "questions_both": len(both),
              "on_questions_both_cover": {n: macro(rs) for n, rs in by_variant.items()},
              "kb_only_on_every_export_question": macro(kb_all) if kb_all else None,
              "kb_questions_with_no_article": sum(not kb[q] for q in kb if gold.get(q))}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "retrieval_check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
