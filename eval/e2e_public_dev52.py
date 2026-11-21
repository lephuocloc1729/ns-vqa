"""phase52 on public_dev (or public_holdout), rules only, then merged with the RAG's saved public
answers (owner, 2026-11-21). For the Chapter 4 error analysis: public_dev may be read question by
question, and since 2026-11-21 (owner, CLAUDE.md) public_holdout too, with `--split public_holdout`.

`run` answers the 51 public_dev questions with the frozen phase52 system (the private benchmark's
configuration: `eval/frozen_phase52.json`, answer fallback off), with fresh perception into a new
scene cache, and grades every answer (judge `judge/v1`, Opus 5.5; Yes/No by polarity). It writes
one record per question (model outputs, trace, grade) and the private runner's aggregate, into
the gitignored `eval/runs/public_dev52/<run_id>/`.

`merge` builds V2 (the rules where decided, the RAG where a trigger fired) and RAG alone from the
RAG's saved public_test predictions (configuration C, `answer_comparison/public_configs_C`),
restricted to public_dev's ids: the public_holdout half is neither read nor used. The rules'
grades are the run's own (not re-judged); only the RAG's Natural QA answers are judged. It writes
per-question merge records and the same aggregate as the private merge (`same_questions` included).

    .venv/bin/python eval/e2e_public_dev52.py run [--split public_holdout] --confirm-frozen --max-spend 1.2
    .venv/bin/python eval/e2e_public_dev52.py merge [--split public_holdout] --run-id <id> --max-spend 0.6 \\
        --rag-predictions <RAG repo>/artifacts/.../public_configs_C/public_test/predictions.jsonl
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_eval as ee  # noqa: E402
from eval import e2e_private as ep  # noqa: E402
from eval import e2e_private_rag as er  # noqa: E402
from eval import freeze  # noqa: E402
from eval import gold_signs as gs  # noqa: E402

OUT = ROOT / "eval" / "runs" / "public_dev52"
OUTS = {"public_dev": OUT, "public_holdout": ROOT / "eval" / "runs" / "public_holdout52"}
PROFILE = "phase52"


def load_public(split: str = "public_dev") -> list[dict]:
    """The questions of one half of the public test, with their answers, in id order."""
    if split == "public_dev":
        return ee.load_dev()
    if split != "public_holdout":
        raise SystemExit(f"--split must be public_dev or public_holdout, not {split!r}")
    from eval import parser_eval as pev
    ids = set(json.loads(pev.SPLIT_FILE.read_text())["public_holdout"]["questions"])
    rows = json.loads(pev.PUBLIC_FILE.read_text(encoding="utf-8"))
    out = [{k: q[k] for k in ("id", "question", "image_id", "question_type", "answer")} for q in rows if q["id"] in ids]
    if {q["id"] for q in out} != ids:
        raise SystemExit("public_holdout ids missing from the public test file")
    return sorted(out, key=lambda q: q["id"])


def guards(*, frozen: Path = freeze.FROZEN_PHASE52, git=freeze.git_state, ignored=ep.git_ignores,
           out_root: Path = OUT) -> dict:
    g = git()
    if not g["clean"]:
        raise SystemExit("the git working tree is not clean: commit or remove these first:\n  " + "\n  ".join(g["dirty"]))
    if (prof := freeze.profile_of(freeze.load(frozen))) != PROFILE:
        raise SystemExit(f"this run uses the phase52 freeze; {Path(frozen).name} is {prof}")
    if d := freeze.check(frozen, ep.frozen_perception_model(frozen)):
        raise SystemExit("the live configuration differs from the freeze record:\n  " + "\n  ".join(d))
    if not ignored(Path(out_root) / "probe"):
        raise SystemExit(f"git does not ignore {out_root}: the records must stay local")
    return g


def run(max_spend: float, *, split: str = "public_dev", confirm_frozen: bool = False, sdk=None,
        questions: list[dict] | None = None, image_path=None, out_root: Path | None = None, frozen: Path = freeze.FROZEN_PHASE52, git=freeze.git_state,
        ignored=ep.git_ignores) -> Path:
    if not confirm_frozen:
        raise SystemExit("this run uses the frozen phase52 system: pass --confirm-frozen")
    out_root = out_root or OUTS[split]
    g = guards(frozen=frozen, git=git, ignored=ignored, out_root=out_root)
    perception_model = ep.frozen_perception_model(frozen)
    qs = questions if questions is not None else load_public(split)
    image_path = image_path or (lambda i: gs.image_path(i, "public_dev"))
    run_id = uuid.uuid4().hex[:12]
    folder = Path(out_root) / run_id
    (folder / "scenes").mkdir(parents=True)
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    from eval.judge import Judge
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.pipeline import Pipeline

    guard = SpendGuard(max_spend)
    pipe = Pipeline(freeze.pipeline_config(PROFILE, perception_model, cache_dir=folder / "scenes", cache_only=False,
                                           answer_fallback=False), sdk=sdk, guard=guard)
    judge = Judge(llm=LLMClient(model="claude-opus-5-5", guard=guard, sdk=sdk))
    kept = []
    with open(folder / "records.jsonl", "w", encoding="utf-8") as f:
        for n, q in enumerate(qs, 1):
            a = pipe.answer(image_path(q["image_id"]), q["question"])
            t = a.trace
            rec = {"id": q["id"], "image_id": q["image_id"], "question_type": q["question_type"],
                   "question": q["question"], "gold_answer": q["answer"],
                   "text": a.text, "verdict": a.verdict, "answered_by": a.answered_by,
                   "trigger": t["fallback"]["trigger"], "fallback_status": t["fallback"].get("status"),
                   "writer_status": (t.get("writer") or {}).get("status"),
                   "engine_verdict": (t.get("engine") or {}).get("verdict"),
                   "parse_status": (t.get("parser") or {}).get("status"),
                   "cost_usd": a.cost_usd, "seconds": a.seconds, "trace": t}
            rec["features"] = ep.features(q["question"])
            rec["decided"] = rec["trigger"] is None and rec["engine_verdict"] in ep.DECIDED
            rec.update(ee.grade(q, a.text, judge))
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            f.flush()
            kept.append({k: rec.get(k) for k in ep._KEEP})
            print(f"[{n}/{len(qs)}]  spent ${guard.spent:.4f}")
    agg = ep.aggregate(kept)
    # the private aggregate's duplicate split is against train/public for private images: not
    # meaningful here, and no longer required (owner, 2026-11-20)
    agg.pop("by_images", None)
    agg["rules_only"].pop("by_images", None)
    report = {"what": f"phase52 on {split}, rules only (Chapter 4 error analysis)", "split": split, "run_id": run_id,
              "questions": len(qs), "images": len({q["image_id"] for q in qs}), "perception_model": perception_model,
              "answer_fallback": False, "started": started,
              "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "git_commit": g["commit"],
              "frozen_record_sha256": hashlib.sha256(Path(frozen).read_bytes()).hexdigest(),
              "spent_usd": round(guard.spent, 4), **agg}
    out = folder / "aggregate.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"aggregate report -> {out}")
    return out


def merge(max_spend: float, *, run_id: str, rag_predictions: Path, split: str = "public_dev", sdk=None,
          out_root: Path | None = None, questions: list[dict] | None = None) -> Path:
    folder = Path(out_root or OUTS[split]) / run_id
    recs = {r["id"]: r for r in (json.loads(x) for x in (folder / "records.jsonl").read_text(encoding="utf-8").splitlines()
                                  if x.strip())}
    qs = questions if questions is not None else load_public(split)
    ids = {q["id"] for q in qs}
    if set(recs) != ids:
        raise SystemExit(f"the run's records cover {len(recs)} questions, {split} has {len(ids)}")
    rows = {}
    for line in Path(rag_predictions).read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r["id"] in ids:                          # this half only; the other half's rows are skipped
                rows[r["id"]] = r
    if missing := ids - set(rows):
        raise SystemExit(f"the RAG predictions miss {len(missing)} {split} questions")
    if bad := sum(rows[i].get("status") != "COMPLETED" or not str(rows[i].get("answer") or "").strip() for i in ids):
        raise SystemExit(f"{bad} RAG predictions did not complete")

    from eval.judge import Judge
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard

    guard = SpendGuard(max_spend)
    judge = Judge(llm=LLMClient(model="claude-opus-5-5", guard=guard, sdk=sdk))
    v2, b2, out_rows = [], [], []
    for n, q in enumerate(qs, 1):
        r, rag = recs[q["id"]], rows[q["id"]]["answer"]
        g_rag = ee.grade(q, rag, judge)
        base = {"question_type": q["question_type"], "trigger": r["trigger"]}
        b2.append({**base, "correct": g_rag["correct"], "strict": g_rag["strict"], "judge_label": g_rag.get("judge_label")})
        if r["trigger"] is None:
            v2.append({**base, "source": "rules", "correct": r["correct"], "strict": r["strict"],
                       "judge_label": r.get("judge_label")})
        else:
            v2.append({**base, "source": "rag", "correct": g_rag["correct"], "strict": g_rag["strict"],
                       "judge_label": g_rag.get("judge_label")})
        out_rows.append({"id": q["id"], "question_type": q["question_type"], "trigger": r["trigger"],
                         "rules_text": r["text"], "rules_correct": r["correct"], "rules_judge_label": r.get("judge_label"),
                         "rag_text": rag, "rag_correct": g_rag["correct"], "rag_judge_label": g_rag.get("judge_label"),
                         "rag_judge_reason": g_rag.get("judge_reason"), "v2_source": v2[-1]["source"]})
        print(f"[{n}/{len(qs)}]  spent ${guard.spent:.4f}")
    with open(folder / "merge_records.jsonl", "w", encoding="utf-8") as f:
        for row in out_rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    report = {"what": f"phase52 on {split} merged with the RAG's saved public answers (config C)", "split": split,
              "run_id": run_id,
              "rag_predictions": {"file": str(rag_predictions),
                                  "sha256": hashlib.sha256(Path(rag_predictions).read_bytes()).hexdigest(),
                                  "config": er.rag_config(rag_predictions)},
              "spent_usd": round(guard.spent, 4), **er.aggregate(v2, b2)}
    out = folder / "merge_aggregate.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"merge report -> {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--split", choices=sorted(OUTS), default="public_dev")
    r.add_argument("--confirm-frozen", action="store_true")
    r.add_argument("--max-spend", type=float, required=True)
    m = sub.add_parser("merge")
    m.add_argument("--split", choices=sorted(OUTS), default="public_dev")
    m.add_argument("--run-id", required=True)
    m.add_argument("--max-spend", type=float, required=True)
    m.add_argument("--rag-predictions", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.max_spend, split=a.split, confirm_frozen=a.confirm_frozen)
    else:
        merge(a.max_spend, run_id=a.run_id, rag_predictions=a.rag_predictions, split=a.split)


if __name__ == "__main__":
    main()
