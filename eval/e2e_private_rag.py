"""The RAG merge on the private test (docs/plans/rag-fallback.md, F4.3; owner, 2026-11-20). Aggregate only.

The private run (`eval/e2e_private.py`, phase52, answer fallback off) answered every question
with the rules and recorded, per question, whether a fallback trigger fired. The owner's RAG
is deterministic, and its saved answers for the private questions (`predictions.jsonl`, the
configuration pinned in the plan's F1) stand in for a live fallback. This script grades, in
memory:

- **V2:** the rules' answer where no trigger fired, the RAG's answer where one did;
- **B2:** the RAG's answer for every question.

It is scoring code, like `eval/e2e_private.py`, whose question loader it uses: the private
answers are read here in memory, graded and summed, never printed or written. No per-question
line is printed; the report holds no question or image id.

It refuses to start unless:
- `--confirm` is given;
- the private run has finished (`eval/private_ran.json`, status `finished`) and the records
  are that run's (`cache/private_run/<run_id>/records.jsonl`);
- it has never run: no sentinel `eval/private_rag_ran.json`, written before the first judge call;
- the records, the RAG predictions and the private questions cover the same questions, and
  every RAG prediction completed with a non-empty answer.

    .venv/bin/python eval/e2e_private_rag.py run --confirm --max-spend 1 \\
        --rag-predictions <RAG repo>/artifacts/.../private_test/predictions.jsonl
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_eval as ee  # noqa: E402
from eval import e2e_private as ep  # noqa: E402
from eval.report import wilson_ci  # noqa: E402

SENTINEL = ROOT / "eval" / "private_rag_ran.json"
OUT = ep.OUT
# The RAG run flags kept in the report, from the predictions' run_config.json (plan F1).
RAG_CONFIG_KEYS = ("embedding_model", "answer_model", "fewshot_k", "answer_with_images", "retrieval")


# ---------------------------------------------------------------- inputs

def load_records(path: Path) -> dict[str, dict]:
    """The private run's replay records: id -> the fields the merge needs (no trace)."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        out[r["id"]] = {k: r[k] for k in ("image_id", "question_type", "text", "trigger", "answered_by")}
    return out


def load_rag(path: Path) -> dict[str, str]:
    """The RAG's saved answers: id -> answer. Every prediction must have completed."""
    out, bad = {}, 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("status") != "COMPLETED" or not str(r.get("answer") or "").strip():
            bad += 1
            continue
        out[r["id"]] = r["answer"]
    if bad:
        raise SystemExit(f"{bad} RAG predictions did not complete")      # a count only
    return out


def rag_config(predictions: Path) -> dict[str, Any]:
    cfg = Path(predictions).with_name("run_config.json")
    if not cfg.exists():
        return {}
    c = json.loads(cfg.read_text(encoding="utf-8"))
    return {k: c[k] for k in RAG_CONFIG_KEYS if k in c}


def guards(*, records: Path, private_sentinel: Path, sentinel: Path) -> dict:
    if not Path(private_sentinel).exists():
        raise SystemExit("the private run has not run yet (no private sentinel)")
    mark = json.loads(Path(private_sentinel).read_text(encoding="utf-8"))
    if mark.get("status") != "finished":
        raise SystemExit("the private run has not finished")
    if Path(records).parent.name != mark.get("run_id"):
        raise SystemExit("the records are not the finished private run's")
    if Path(sentinel).exists():
        raise SystemExit(f"the RAG merge has already run ({Path(sentinel).name}); it runs once")
    return mark


# ---------------------------------------------------------------- the report

def _figs(rs: list[dict]) -> dict[str, Any]:
    graded = [r for r in rs if r.get("correct") is not None]
    right = sum(r["correct"] for r in graded)
    yn = [r for r in graded if r["question_type"] == "Yes/No"]
    nq = [r for r in graded if r["question_type"] != "Yes/No"]
    return {"n": len(rs), "overall": right / len(graded) if graded else None,
            "overall_ci95": list(wilson_ci(right, len(graded))) if graded else None,
            "overall_strict": ee._mean([r["strict"] for r in graded]),
            "yes_no_accuracy": ee._mean([r["correct"] for r in yn]), "yes_no_n": len(yn),
            "natural_qa_score": ee._mean([r["correct"] for r in nq]),
            "natural_qa_strict": ee._mean([r["strict"] for r in nq]), "natural_qa_n": len(nq),
            "judge_labels": dict(Counter(r.get("judge_label") for r in nq))}


def aggregate(v2: list[dict], b2: list[dict]) -> dict[str, Any]:
    rag_part = [r for r in v2 if r["source"] == "rag"]
    keys = sorted({r["trigger"] for r in rag_part})
    return {"v2_rules_plus_rag_fallback": {**_figs(v2),
                                            "rules_answered": sum(r["source"] == "rules" for r in v2),
                                            "rag_answered": len(rag_part),
                                            "rules_part": _figs([r for r in v2 if r["source"] == "rules"]),
                                            "rag_part": _figs(rag_part),
                                            "rag_part_by_trigger": {k: _figs([r for r in rag_part if r["trigger"] == k])
                                                                    for k in keys}},
            "b2_rag_alone": _figs(b2)}


# ---------------------------------------------------------------- the run

def run_merge(max_spend: float, *, confirm: bool = False, records: Path | None = None, rag_predictions: Path,
              questions: list[dict] | None = None, sdk=None, out_dir: Path = OUT, sentinel: Path = SENTINEL,
              private_sentinel: Path = ep.SENTINEL, replay_root: Path = ep.REPLAY) -> Path:
    if not confirm:
        raise SystemExit("the RAG merge runs once: pass --confirm")
    if records is None:
        if not Path(private_sentinel).exists():
            raise SystemExit("the private run has not run yet (no private sentinel)")
        run_id = json.loads(Path(private_sentinel).read_text(encoding="utf-8")).get("run_id", "")
        records = Path(replay_root) / run_id / "records.jsonl"
    mark = guards(records=records, private_sentinel=private_sentinel, sentinel=sentinel)
    recs, rag = load_records(records), load_rag(rag_predictions)
    qs = questions if questions is not None else ep.load_questions()
    ids = {q["id"] for q in qs}
    if set(recs) != ids or set(rag) != ids:
        raise SystemExit(f"the inputs cover different questions: {len(ids)} private, {len(recs)} records, "
                         f"{len(rag)} RAG answers")                              # counts only
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    pred_sha = hashlib.sha256(Path(rag_predictions).read_bytes()).hexdigest()
    me = {"what": "the one RAG merge on the private test (docs/plans/rag-fallback.md F4.3); blocks a second run",
          "private_run_id": mark["run_id"], "started": started, "status": "started",
          "rag_predictions_sha256": pred_sha}
    Path(sentinel).write_text(json.dumps(me, indent=2) + "\n", encoding="utf-8")

    from eval.judge import Judge
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard

    guard = SpendGuard(max_spend)
    judge = Judge(llm=LLMClient(model="claude-opus-5-5", guard=guard, sdk=sdk))
    graded: dict[tuple[str, str], dict] = {}

    def grade(q: dict, text: str) -> dict:
        key = (q["id"], text)
        if key not in graded:
            graded[key] = ee.grade(q, text, judge)
        return graded[key]

    v2, b2 = [], []
    for n, q in enumerate(qs, 1):
        r = recs[q["id"]]
        base = {"question_type": q["question_type"], "trigger": r["trigger"]}
        g_rag = grade(q, rag[q["id"]])
        b2.append({**base, "correct": g_rag["correct"], "strict": g_rag["strict"],
                   "judge_label": g_rag.get("judge_label")})
        if r["trigger"] is None:
            g = grade(q, r["text"])
            v2.append({**base, "source": "rules", "correct": g["correct"], "strict": g["strict"],
                       "judge_label": g.get("judge_label")})
        else:
            v2.append({**base, "source": "rag", "correct": g_rag["correct"], "strict": g_rag["strict"],
                       "judge_label": g_rag.get("judge_label")})
        print(f"[{n}/{len(qs)}]  spent ${guard.spent:.4f}")                 # a counter only
    graded.clear()
    report = {"what": "private test, RAG merge, aggregate only (docs/plans/rag-fallback.md F4.3)",
              "private_run_id": mark["run_id"], "private_run_commit": mark.get("git_commit"),
              "questions": len(qs), "started": started,
              "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "rag_predictions": {"file": Path(rag_predictions).name, "sha256": pred_sha,
                                  "config": rag_config(rag_predictions)},
              "spent_usd": round(guard.spent, 4), **aggregate(v2, b2)}
    v2.clear(), b2.clear()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = Path(out_dir) / f"private_rag_aggregate_{mark['run_id']}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    me.update(status="finished", finished=report["finished"], report=out.name, spent_usd=report["spent_usd"])
    Path(sentinel).write_text(json.dumps(me, indent=2) + "\n", encoding="utf-8")
    print(f"aggregate report -> {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--confirm", action="store_true")
    r.add_argument("--max-spend", type=float, required=True)
    r.add_argument("--rag-predictions", type=Path, required=True)
    r.add_argument("--records", type=Path, default=None, help="default: the finished private run's records")
    a = ap.parse_args()
    run_merge(a.max_spend, confirm=a.confirm, records=a.records, rag_predictions=a.rag_predictions)


if __name__ == "__main__":
    main()
