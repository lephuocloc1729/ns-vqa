"""The RAG merge on the private test (docs/plans/rag-fallback.md, F4.3; owner, 2026-11-20). Aggregate only.

The private run (`eval/e2e_private.py`, phase52, answer fallback off) answered every question
with the rules and recorded, per question, whether a fallback trigger fired. Then (owner,
2026-11-21, plan F4.3) the RAG answers the triggered questions **live** on the GPU machine:

1. `ids` writes the triggered question ids (ids only) to `triggered_ids.json` in the replay folder;
2. the RAG repo's `experiments/private_live/run_private_live.sh <triggered_ids.json>` runs the
   pinned configuration live on those ids and writes `rag_live.jsonl` and `rag_live_meta.json`;
3. `run` grades, in memory:

- **V2:** the rules' answer where no trigger fired, the **live** RAG answer where one did;
- **B2:** the RAG's saved answer (`predictions.jsonl`, plan F1) for every question.

The report also counts the live answers that equal the saved ones (the determinism check) and
gives the live fallback's seconds per question.

**Runs 1–3 (owner, 2026-11-21).** The private test runs 3 times (`e2e_private.py --run N`); each run
is merged once with `--run N` (its own sentinel: `private_rag_ran.json` for run 1,
`private_rag_ran_N.json` for runs 2 and 3). The live file may cover more questions than the run's
triggered ones (the RAG ran live on all 146 private questions once; each answer depends on its own
question only): it must contain every triggered question, and only those are used.

It is scoring code, like `eval/e2e_private.py`, whose question loader it uses: the private
answers are read here in memory, graded and summed. No per-question line is printed; the report
holds no question or image id. **The owner's grading sheet** (owner, 2026-11-20; phase-5 P6):
`owner_grading_rag.csv` in the private run's gitignored replay folder, one row per question for
V2 and one for B2, with the question, gold answer, answer and the judge's grade, for the owner's
hand grading only. The assistant never reads it; nothing from it is printed.

It refuses to start unless:
- `--confirm` is given;
- the private run has finished (`eval/private_ran.json`, status `finished`) and the records
  are that run's (`cache/private_run/<run_id>/records.jsonl`);
- it has never run: no sentinel `eval/private_rag_ran.json`, written before the first judge call;
- the records, the RAG predictions and the private questions cover the same questions, the
  live answers cover exactly the triggered ones, and every RAG answer completed, non-empty.

    .venv/bin/python eval/e2e_private_rag.py ids [--run N]
    .venv/bin/python eval/e2e_private_rag.py run [--run N] --confirm --max-spend 1 \\
        --rag-predictions <RAG repo>/artifacts/.../private_test/predictions.jsonl \\
        --rag-live <RAG repo>/outputs/private_live/rag_live.jsonl

**Reproduction runs (owner, 2026-11-25).** `--reproduce <run id>` merges a reproduction run of
`eval/e2e_private.py reproduce` (its run id starts with `repro-`). It reads that run's marker
`reproduce.json` in its replay folder instead of the benchmark records, writes its own marker
`reproduce_rag.json` beside it (once per reproduction run), and its aggregate goes to
`eval/runs/reproduce/`. It never reads, writes or counts the benchmark merges' records.

    .venv/bin/python eval/e2e_private_rag.py ids --reproduce <run id>
    .venv/bin/python eval/e2e_private_rag.py run --reproduce <run id> --confirm --max-spend 1 \\
        --rag-predictions <RAG>/private_test/predictions.jsonl --rag-live <RAG>/rag_live.jsonl
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
TRIGGERED_IDS = "triggered_ids.json"
OWNER_SHEET = "owner_grading_rag.csv"
OUT = ep.OUT
# The RAG run flags kept in the report, from the predictions' run_config.json (plan F1).
REPRO_RAG_MARK = "reproduce_rag.json"
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


def merge_sentinel(run: int, base: Path = SENTINEL) -> Path:
    """Run 1's merge sentinel is `base` (eval/private_rag_ran.json); run N's is private_rag_ran_N.json."""
    return ep.sentinel_for(run, base)


def load_live(paths: list[Path], needed: set[str]) -> dict[str, dict]:
    """The live RAG answers for the `needed` (triggered) questions: id -> row. The files (one per
    live RAG run) may hold more questions; every needed one must be in exactly one of them and
    have completed."""
    rows = {}
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r["id"] in rows:
                    raise SystemExit("a question is in more than one live RAG file")
                rows[r["id"]] = {**r, "_meta": live_meta(path)}
    if missing := needed - set(rows):
        raise SystemExit(f"the live RAG answers miss {len(missing)} of the {len(needed)} triggered questions")
    bad = sum(rows[i].get("status") != "COMPLETED" or not str(rows[i].get("answer") or "").strip() for i in needed)
    if bad:
        raise SystemExit(f"{bad} live RAG answers did not complete")       # a count only
    return {i: rows[i] for i in needed}


def _live_files(rag_live) -> list[Path]:
    return [Path(rag_live)] if isinstance(rag_live, (str, Path)) else [Path(p) for p in rag_live]


def live_meta(live: Path) -> dict[str, Any]:
    m = Path(live).with_name("rag_live_meta.json")
    return json.loads(m.read_text(encoding="utf-8")) if m.exists() else {}


def _secs(xs: list[float]) -> dict[str, Any] | None:
    if not xs:
        return None
    s = sorted(xs)
    return {"mean": round(sum(s) / len(s), 2), "p50": round(s[len(s) // 2], 2),
            "p95": round(s[min(len(s) - 1, round(0.95 * (len(s) - 1)))], 2), "max": round(s[-1], 2), "n": len(s)}


def live_figures(live: dict[str, dict], saved: dict[str, str]) -> dict[str, Any]:
    """Each row carries its live run's meta (`_meta`): retrieval seconds per question and config."""
    def retrieval(r: dict) -> float:
        return r.get("_meta", {}).get("retrieval_seconds_per_question") or 0.0
    stage = {k: [r[k] for r in live.values() if isinstance(r.get(k), (int, float))]
             for k in ("caption_seconds", "embed_seconds", "answer_seconds")}
    total = [sum(r.get(k, 0.0) for k in stage) + retrieval(r) for r in live.values()]
    metas = {r["_meta"].get("run_config_sha256"): r["_meta"] for r in live.values() if r.get("_meta")}
    return {"answers": len(live),
            "identical_to_saved": sum(r["answer"].strip() == saved[i].strip() for i, r in live.items()),
            "incomplete_captions": sum(r.get("caption_status") != "COMPLETED" for r in live.values()),
            "seconds": {**{k.removesuffix("_seconds"): _secs(v) for k, v in stage.items()},
                        "retrieval": _secs([retrieval(r) for r in live.values()]), "total": _secs(total)},
            "live_runs": [{"run_config_sha256": k, "config": m.get("config", {})} for k, m in metas.items()]}


def triggered(records: dict[str, dict]) -> list[str]:
    return sorted(i for i, r in records.items() if r["trigger"] is not None)


def reproduction_marks(reproduce: str, replay_root: Path = ep.REPLAY) -> tuple[Path, Path]:
    """A reproduction run's private marker and its merge marker, both in its own replay folder."""
    if not str(reproduce).startswith(ep.REPRO_PREFIX) or "/" in str(reproduce) or ".." in str(reproduce):
        raise SystemExit(f"--reproduce takes a reproduction run id (it starts with {ep.REPRO_PREFIX!r})")
    folder = Path(replay_root) / str(reproduce)
    return folder / ep.REPRO_MARK, folder / REPRO_RAG_MARK


def write_ids(*, run: int = 1, private_sentinel: Path = ep.SENTINEL, replay_root: Path = ep.REPLAY,
              ignored=ep.git_ignores, reproduce: str | None = None) -> Path:
    """Write run N's triggered question ids (ids only, no question text or gold) for the live RAG run.
    `private_sentinel` is run 1's; run N's is `ep.sentinel_for(N, private_sentinel)`. With `reproduce`,
    the reproduction run's marker is read instead."""
    if reproduce:
        private_sentinel, _ = reproduction_marks(reproduce, replay_root)
    else:
        ep.check_run_number(run)
        private_sentinel = ep.sentinel_for(run, private_sentinel)
    if not Path(private_sentinel).exists():
        raise SystemExit("the private run has not run yet (no private sentinel)")
    mark = json.loads(Path(private_sentinel).read_text(encoding="utf-8"))
    if mark.get("status") != "finished":
        raise SystemExit("the private run has not finished")
    folder = Path(replay_root) / mark["run_id"]
    out = folder / TRIGGERED_IDS
    if not ignored(out):
        raise SystemExit("git does not ignore the replay folder: the ids file must stay local")
    ids = triggered(load_records(folder / "records.jsonl"))
    out.write_text(json.dumps(ids, indent=0) + "\n", encoding="utf-8")
    print(f"{len(ids)} triggered ids -> {out}")                              # a count only
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

def run_merge(max_spend: float, *, run: int = 1, confirm: bool = False, records: Path | None = None,
              rag_predictions: Path, rag_live: Path, questions: list[dict] | None = None, sdk=None, out_dir: Path = OUT,
              sentinel: Path = SENTINEL, private_sentinel: Path = ep.SENTINEL, replay_root: Path = ep.REPLAY,
              ignored=ep.git_ignores, reproduce: str | None = None) -> Path:
    """`sentinel` and `private_sentinel` are run 1's; run N uses merge_sentinel(N) and ep.sentinel_for(N).
    With `reproduce` (a reproduction run id), both markers sit in that run's replay folder and the
    aggregate goes to ep.REPRO_OUT (when `out_dir` is the default)."""
    if not confirm:
        raise SystemExit("the RAG merge runs once per private run: pass --confirm")
    if reproduce:
        private_sentinel, sentinel = reproduction_marks(reproduce, replay_root)
        out_dir = ep.REPRO_OUT if out_dir == OUT else Path(out_dir)
    else:
        ep.check_run_number(run)
        sentinel, private_sentinel = merge_sentinel(run, sentinel), ep.sentinel_for(run, private_sentinel)
    if records is None:
        if not Path(private_sentinel).exists():
            raise SystemExit("the private run has not run yet (no private sentinel)")
        run_id = json.loads(Path(private_sentinel).read_text(encoding="utf-8")).get("run_id", "")
        records = Path(replay_root) / run_id / "records.jsonl"
    mark = guards(records=records, private_sentinel=private_sentinel, sentinel=sentinel)
    sheet_path = Path(records).parent / OWNER_SHEET
    if not ignored(sheet_path):
        raise SystemExit("git does not ignore the replay folder: the grading sheet must stay local")
    recs, rag = load_records(records), load_rag(rag_predictions)
    qs = questions if questions is not None else ep.load_questions()
    ids = {q["id"] for q in qs}
    if set(recs) != ids or set(rag) != ids:
        raise SystemExit(f"the inputs cover different questions: {len(ids)} private, {len(recs)} records, "
                         f"{len(rag)} RAG answers")                              # counts only
    live_paths = _live_files(rag_live)
    live = load_live(live_paths, set(triggered(recs)))
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    pred_sha = hashlib.sha256(Path(rag_predictions).read_bytes()).hexdigest()
    live_sha = {p.name if len(live_paths) == 1 else str(p.parent.name) + "/" + p.name:
                hashlib.sha256(p.read_bytes()).hexdigest() for p in live_paths}
    me = {"what": ("the RAG merge of a reproduction run (owner, 2026-11-25); not a benchmark merge" if reproduce
                   else "the one RAG merge on the private test (docs/plans/rag-fallback.md F4.4); blocks a second run"),
          "run": "reproduce" if reproduce else run, "private_run_id": mark["run_id"], "started": started, "status": "started",
          "rag_predictions_sha256": pred_sha, "rag_live_sha256": live_sha}
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
    sheet_f, sheet = ep.open_owner_sheet(sheet_path)
    for n, q in enumerate(qs, 1):
        r = recs[q["id"]]
        base = {"question_type": q["question_type"], "trigger": r["trigger"]}
        g_rag = grade(q, rag[q["id"]])
        b2.append({**base, "correct": g_rag["correct"], "strict": g_rag["strict"],
                   "judge_label": g_rag.get("judge_label")})
        sheet.writerow(ep.owner_sheet_row(q, "b2_rag_alone", rag[q["id"]], "rag", r["trigger"], g_rag))
        if r["trigger"] is None:
            g = grade(q, r["text"])
            v2.append({**base, "source": "rules", "correct": g["correct"], "strict": g["strict"],
                       "judge_label": g.get("judge_label")})
            sheet.writerow(ep.owner_sheet_row(q, "v2_rules_plus_rag", r["text"], "rules", None, g))
        else:
            text = live[q["id"]]["answer"]
            g = grade(q, text)
            v2.append({**base, "source": "rag", "correct": g["correct"], "strict": g["strict"],
                       "judge_label": g.get("judge_label")})
            sheet.writerow(ep.owner_sheet_row(q, "v2_rules_plus_rag", text, "rag_live", r["trigger"], g))
        sheet_f.flush()
        print(f"[{n}/{len(qs)}]  spent ${guard.spent:.4f}")                 # a counter only
    graded.clear()
    sheet_f.close()
    report = {"what": ("private test, RAG merge of a reproduction run, aggregate only" if reproduce
                       else "private test, RAG merge, aggregate only (docs/plans/rag-fallback.md F4.3)"),
              "run": "reproduce" if reproduce else run, "private_run_id": mark["run_id"], "private_run_commit": mark.get("git_commit"),
              "questions": len(qs), "started": started,
              "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "rag_predictions": {"file": Path(rag_predictions).name, "sha256": pred_sha,
                                  "config": rag_config(rag_predictions)},
              "rag_live": {"files_sha256": live_sha, **live_figures(live, rag)},
              "spent_usd": round(guard.spent, 4), **aggregate(v2, b2)}
    v2.clear(), b2.clear()
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = Path(out_dir) / (f"private_rag_reproduce_{mark['run_id']}.json" if reproduce
                           else f"private_rag_aggregate_{mark['run_id']}.json")
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    me.update(status="finished", finished=report["finished"], report=out.name, spent_usd=report["spent_usd"])
    Path(sentinel).write_text(json.dumps(me, indent=2) + "\n", encoding="utf-8")
    print(f"aggregate report -> {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ids", help="write the triggered question ids for the live RAG run")
    i.add_argument("--run", type=int, default=1, help="the private run (1, 2 or 3)")
    i.add_argument("--reproduce", default=None, help="a reproduction run id (repro-...) instead of --run")
    r = sub.add_parser("run")
    r.add_argument("--confirm", action="store_true")
    r.add_argument("--run", type=int, default=1, help="the private run (1, 2 or 3)")
    r.add_argument("--max-spend", type=float, required=True)
    r.add_argument("--rag-predictions", type=Path, required=True, help="the RAG's saved answers (B2)")
    r.add_argument("--rag-live", type=Path, nargs="+", required=True,
                   help="the live RAG answer files (V2); together they must cover the triggered ids")
    r.add_argument("--records", type=Path, default=None, help="default: the finished private run's records")
    r.add_argument("--reproduce", default=None, help="a reproduction run id (repro-...) instead of --run")
    a = ap.parse_args()
    if a.cmd == "ids":
        write_ids(run=a.run, reproduce=a.reproduce)
        return
    run_merge(a.max_spend, run=a.run, confirm=a.confirm, records=a.records, rag_predictions=a.rag_predictions,
              rag_live=a.rag_live, reproduce=a.reproduce)


if __name__ == "__main__":
    main()
