"""End-to-end evaluation on public_dev (docs/plans/phase-4.md, item 4).

Development runs only: this module reads public_dev questions and answers and
nothing else (the aggregate-only holdout run is in eval/e2e_holdout.py).

    .venv/bin/python eval/e2e_eval.py oracle-a-yesno                 # free: engine only
    .venv/bin/python eval/e2e_eval.py estimate                       # step-2 cost, no call
    .venv/bin/python eval/e2e_eval.py run --warm-run <perception run file> --label H1 --max-spend 1
    .venv/bin/python eval/e2e_eval.py oracle --kind A --max-spend 0.5
    .venv/bin/python eval/e2e_eval.py oracle --kind B --warm-run <file> --label H1 --max-spend 0.5
    .venv/bin/python eval/e2e_eval.py score --h <3 files> [--s <file>] [--o <file>]
    .venv/bin/python eval/e2e_eval.py attribution <pipeline file> <oracle A file> <oracle B file>

Scene reuse (owner, 2026-11-16): a run's scenes reach the pipeline only through the
scene cache, warmed from its run file by `perception_eval.warm_run` into one
dedicated directory, one run at a time ("warm, run, next"). The pipeline then runs
in cache-only mode, through `answer(image_path, question)`.

Oracles call the engine, the writer and the fallback directly from here, never
through `answer()`. Oracle A uses gold scenes (gold signs v1) and gold programs
(gold intents v1); oracle B uses the warmed pipeline scenes and gold programs.

Every report gives scores on all images and on non-duplicate images (with a 95% CI),
rule coverage, the rules-only score, the fallback rate by trigger, faithfulness and
the template rate, and cost and time per question.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import gold_signs as gs  # noqa: E402
from eval import parser_eval as pev  # noqa: E402
from eval import perception_eval as pe  # noqa: E402
from eval.report import score_report  # noqa: E402
from vqa.answer.faithfulness import leading_polarity  # noqa: E402
from vqa.schemas import SceneGraph, Verdict  # noqa: E402

RUNS = ROOT / "eval" / "runs" / "e2e"
SPLIT = "public"                     # duplicates are counted against train
LOG = ROOT / "logs" / "api_calls.jsonl"


# ---------------------------------------------------------------- data (public_dev only)

def load_dev(public_file: Path | None = None, split_file: Path | None = None) -> list[dict]:
    """public_dev questions with their answers, in id order."""
    ids = pev.public_dev_ids(split_file)
    rows = json.loads((public_file or pev.PUBLIC_FILE).read_text(encoding="utf-8"))
    out = [{k: q[k] for k in ("id", "question", "image_id", "question_type", "answer")}
           for q in rows if q["id"] in ids]
    if {q["id"] for q in out} != ids:
        raise SystemExit("public_dev ids missing from the public test file")
    return sorted(out, key=lambda q: q["id"])


def yes_no(text: str | None) -> bool | None:
    """DESIGN section 9: Đúng / Có / Được -> true; Sai / Không (được) -> false."""
    return leading_polarity(text or "")


def gold_scene(row: dict) -> SceneGraph:
    """A gold-signs row as a scene graph. Unreadable gold signs stay as UNKNOWN signs;
    standalone local notices are left out (the engine does not model them)."""
    signs = []
    for s in row["signs"]:
        if s.get("local_notice"):
            continue
        readable = s.get("readable", True)
        s = {k: v for k, v in s.items() if k not in ("readable", "local_notice")}
        if not readable:
            s["code"] = "UNKNOWN"
        signs.append(s)
    return SceneGraph.model_validate({"scene_id": row["image_id"], "signs": signs,
                                      "vehicles": row.get("vehicles") or []})


def gold_scenes() -> dict[str, SceneGraph]:
    return {i: gold_scene(r) for i, r in pe.gold_rows().items() if r.get("split") == "public_dev"}


def gold_programs() -> dict[str, Any]:
    """{question id: QueryProgram} from gold intents v1, public_dev rows."""
    return {g["id"]: pev.gold_query(g["program"]) for g in pev.load_gold() if g["split"] == "public_dev"}


# ---------------------------------------------------------------- scoring one answer

def grade(q: dict, text: str, judge) -> dict[str, Any]:
    if q["question_type"] == "Yes/No":
        pred, gold = yes_no(text), yes_no(q["answer"])
        ok = float(pred is not None and pred == gold)
        return {"correct": ok, "strict": ok, "yes_no_pred": pred}
    if judge is None:
        return {"correct": None, "strict": None}
    v = judge.grade(q["question"], q["answer"], text)
    return {"correct": v.score, "strict": v.strict, "judge_label": v.label, "judge_reason": v.reason,
            "judge_cost_usd": v.cost_usd}


# ---------------------------------------------------------------- oracle A, Yes/No part (free)

def oracle_a_yesno() -> dict[str, Any]:
    """Gold scenes + gold programs -> engine verdicts on public_dev Yes/No questions.
    No writer, no API call: checks DESIGN's "engine with gold parts is close to 100%"."""
    from vqa.reasoning.engine import Engine, EngineError

    engine, scenes, programs = Engine(), gold_scenes(), gold_programs()
    rows, skipped = [], []
    for q in load_dev():
        if q["question_type"] != "Yes/No":
            continue
        prog = programs.get(q["id"])
        if prog is None:
            skipped.append(q["id"])
            continue
        if prog.out_of_scope:
            verdict = "out_of_scope"
        else:
            try:
                verdict = engine.answer(scenes[q["image_id"]], prog).verdict.value
            except EngineError as e:
                verdict = f"error: {e}"
        gold = yes_no(q["answer"])
        pred = {"yes": True, "no": False}.get(verdict)
        rows.append({"id": q["id"], "image_id": q["image_id"], "verdict": verdict, "gold": gold,
                     "correct": pred is not None and pred == gold})
    return {"what": "oracle A, Yes/No part: gold scenes + gold programs, engine verdicts only",
            "report": score_report(rows, SPLIT), "verdicts": dict(Counter(r["verdict"] for r in rows)),
            "skipped_no_gold_program": skipped,
            "wrong": [{k: r[k] for k in ("id", "verdict", "gold")} for r in rows if not r["correct"]]}


# ---------------------------------------------------------------- runs

def _header(kind: str, label: str, **kw) -> dict[str, Any]:
    from eval.judge import prompt_id as judge_pid
    from vqa.answer import fallback as afb
    from vqa.answer import prompt as wp
    return {"run_id": uuid.uuid4().hex[:12], "kind": kind, "label": label, "set": "public_dev",
            "writer": wp.prompt_id(), "answer_fallback": afb.prompt_id(), "parser": pev.PROMPT_VERSION,
            "judge": judge_pid(), "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            **kw}


def _out(kind: str, label: str, run_id: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"public_dev_{kind}_{label}_{run_id}.jsonl"


def _warm(warm_file: Path, warm_dir: Path | None) -> tuple[dict, dict]:
    rep = pe.warm_run(warm_file, warm_dir)
    if not rep["ok"]:
        raise SystemExit(f"warming {warm_file.name} failed: rebuilt scenes differ for {rep['mismatches']}")
    head, _ = pe.load_run(warm_file)
    return rep, head


def _check_still_warm(rep: dict) -> None:
    marker = json.loads((Path(rep["cache_dir"]) / pe.WARM_MARKER).read_text(encoding="utf-8"))
    if marker["run_id"] != rep["run_id"]:
        raise SystemExit(f"the warm cache now holds run {marker['run_id']}, not {rep['run_id']}: "
                         "runs must go one at a time")


def run_pipeline(warm_file: Path, label: str, max_spend: float, *, sdk=None, warm_dir: Path | None = None,
                 out_dir: Path = RUNS, questions: list[dict] | None = None, judge: bool = True) -> Path:
    """Warm the cache from one perception run, then run the pipeline on every
    public_dev question through answer(), cache-only, and grade it."""
    from eval.judge import Judge
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.pipeline import Pipeline, PipelineConfig

    rep, phead = _warm(Path(warm_file), warm_dir)
    guard = SpendGuard(max_spend)
    pipe = Pipeline(PipelineConfig(perception_model=phead["model"], cache_dir=Path(rep["cache_dir"]),
                                   cache_only=True), sdk=sdk, guard=guard)
    jd = Judge(llm=LLMClient(model="claude-opus-5-5", guard=guard, sdk=sdk)) if judge else None
    head = _header("pipeline", label, scenes_from=phead["run_id"], perception_model=phead["model"],
                   perception_prompt=phead["prompt_id"], scene_fallback=phead.get("fallback"))
    out = _out("pipeline", label, head["run_id"], out_dir)
    qs = questions if questions is not None else load_dev()
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(head, ensure_ascii=False) + "\n")
        for n, q in enumerate(qs, 1):
            a = pipe.answer(gs.image_path(q["image_id"], "public_dev"), q["question"])
            t = a.trace
            rec = {"id": q["id"], "image_id": q["image_id"], "question_type": q["question_type"],
                   "text": a.text, "verdict": a.verdict, "answered_by": a.answered_by,
                   "trigger": t["fallback"]["trigger"], "fallback_status": t["fallback"].get("status"),
                   "writer_status": (t.get("writer") or {}).get("status"),
                   "engine_verdict": (t.get("engine") or {}).get("verdict"),
                   "parse_status": (t.get("parser") or {}).get("status"),
                   "cost_usd": a.cost_usd, "seconds": a.seconds, "trace": t}
            rec.update(grade(q, a.text, jd))
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            f.flush()
            print(f"[{n}/{len(qs)}] {q['id']}: {a.answered_by} {a.verdict}  spent ${guard.spent:.4f}")
    _check_still_warm(rep)
    print(f"{label} -> {out}  (spent ${guard.spent:.4f})")
    return out


def run_oracle(kind: str, label: str, max_spend: float, *, warm_file: Path | None = None, sdk=None,
               warm_dir: Path | None = None, out_dir: Path = RUNS, questions: list[dict] | None = None,
               judge: bool = True) -> Path:
    """Oracle A (gold scenes) or B (warmed pipeline scenes), with gold programs, the
    engine, the writer and the answer-level fallback, called directly (not answer())."""
    from eval.judge import Judge
    from vqa.answer.fallback import AnswerFallback, trigger
    from vqa.answer.writer import AnswerWriter
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.perception.cache import SceneCache
    from vqa.perception.fallback import FallbackConfig
    from vqa.perception.scene import perceive
    from vqa.reasoning.engine import Engine, EngineError

    if kind not in ("A", "B"):
        raise SystemExit("--kind must be A or B")
    guard = SpendGuard(max_spend)
    engine = Engine()
    writer = AnswerWriter(llm=LLMClient(model="claude-haiku-5-5", guard=guard, sdk=sdk), catalog=engine.catalog)
    fallback = AnswerFallback(llm=LLMClient(model="claude-sonnet-5-5", guard=guard, sdk=sdk))
    jd = Judge(llm=LLMClient(model="claude-opus-5-5", guard=guard, sdk=sdk)) if judge else None
    programs = gold_programs()
    extra: dict[str, Any] = {}
    if kind == "A":
        scenes = gold_scenes()
        scene_of = lambda q: scenes[q["image_id"]]  # noqa: E731
    else:
        if warm_file is None:
            raise SystemExit("oracle B needs --warm-run")
        rep, phead = _warm(Path(warm_file), warm_dir)
        cache = SceneCache(Path(rep["cache_dir"]))
        extra = {"scenes_from": phead["run_id"], "perception_model": phead["model"]}

        def scene_of(q):
            res = perceive(gs.image_path(q["image_id"], "public_dev"), model=phead["model"], version="v4",
                           client=pe._NoCalls(phead["model"]), cache=cache, use_cache=True,
                           fallback=FallbackConfig() if phead.get("fallback") else None)
            return res.scene if res.ok else None
    head = _header("oracle" + kind, label, **extra)
    out = _out("oracle" + kind, label, head["run_id"], out_dir)
    qs = questions if questions is not None else load_dev()
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(head, ensure_ascii=False) + "\n")
        for n, q in enumerate(qs, 1):
            prog = programs.get(q["id"])
            rec: dict[str, Any] = {"id": q["id"], "image_id": q["image_id"], "question_type": q["question_type"]}
            if prog is None:
                rec.update(skipped="no_gold_program")
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                continue
            t0, cost = time.monotonic(), 0.0
            scene = scene_of(q)
            ans, err = None, None
            if scene is not None and not prog.out_of_scope:
                try:
                    ans = engine.answer(scene, prog)
                except EngineError as e:
                    err = str(e)
            why = trigger(scene_ok=scene is not None,
                          parse_status="out_of_scope" if prog.out_of_scope else "ok",
                          answer=ans, engine_error=err is not None)
            text, verdict, fstatus, wstatus = "", None, None, None
            if why is not None:
                fa = fallback.answer(gs.image_path(q["image_id"], "public_dev"), q["question"], scene)
                cost += fa.cost_usd
                fstatus = fa.status
                if fa.status == "ok":
                    text, verdict = fa.text, fa.verdict
            if not text:
                from vqa.schemas import Answer
                w = writer.write(q["question"], ans or Answer(verdict=Verdict.unknown), scene)
                cost += w.cost_usd
                text, verdict, wstatus = w.text, w.verdict, w.status
            rec.update(text=text, verdict=verdict, answered_by="fallback" if fstatus == "ok" else "rules",
                       trigger=why, fallback_status=fstatus, writer_status=wstatus,
                       engine_verdict=ans.verdict.value if ans else None, cost_usd=cost,
                       seconds=time.monotonic() - t0)
            rec.update(grade(q, text, jd))
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            f.flush()
            print(f"[{n}/{len(qs)}] {q['id']}: {rec['answered_by']} {verdict}  spent ${guard.spent:.4f}")
    print(f"oracle {kind} {label} -> {out}  (spent ${guard.spent:.4f})")
    return out


# ---------------------------------------------------------------- scoring runs

def load(path: Path) -> tuple[dict, list[dict]]:
    lines = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    return lines[0], [r for r in lines[1:] if not r.get("skipped")]


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def summarize(records: list[dict]) -> dict[str, Any]:
    """The phase-4 report for one run (or pooled runs)."""
    graded = [r for r in records if r.get("correct") is not None]
    yn = [r for r in graded if r["question_type"] == "Yes/No"]
    nq = [r for r in graded if r["question_type"] != "Yes/No"]
    rules = [r for r in graded if r.get("trigger") is None]
    writer = [r for r in records if r.get("writer_status")]
    faithful = [r for r in writer if r["verdict"] == (r.get("engine_verdict") or "unknown")]
    templates = [r for r in writer if r["writer_status"] == "template"]
    triggers = Counter(r.get("trigger") for r in records if r.get("trigger"))
    return {
        "questions": len(records),
        "overall": _mean([r["correct"] for r in graded]),
        "overall_strict": _mean([r["strict"] for r in graded]),
        "yes_no_accuracy": _mean([r["correct"] for r in yn]), "yes_no_n": len(yn),
        "natural_qa_score": _mean([r["correct"] for r in nq]),
        "natural_qa_strict": _mean([r["strict"] for r in nq]), "natural_qa_n": len(nq),
        "judge_labels": dict(Counter(r.get("judge_label") for r in nq)),
        "by_images": score_report([{"image_id": r["image_id"], "correct": r["correct"]} for r in graded], SPLIT),
        "rule_coverage": len([r for r in records if r.get("trigger") is None]) / len(records) if records else None,
        "rules_only_score": _mean([r["correct"] for r in rules]), "rules_only_n": len(rules),
        "fallback_by_trigger": dict(triggers),
        "fallback_rate": sum(triggers.values()) / len(records) if records else None,
        "fallback_failed": sum(r.get("fallback_status") == "failed" for r in records),
        "writer_answers": len(writer),
        "writer_status": dict(Counter(r["writer_status"] for r in writer)),
        "faithfulness": len(faithful) / len(writer) if writer else None,
        "template_rate": len(templates) / len(writer) if writer else None,
        "cost_per_question_usd": _mean([(r.get("cost_usd") or 0.0) + (r.get("judge_cost_usd") or 0.0) for r in records]),
        "seconds_per_question": _mean([r.get("seconds") or 0.0 for r in records]),
    }


FAITHFULNESS_MIN = 0.99            # D5, pooled over the 3 H runs
TEMPLATE_RATE_MAX = 0.05           # D5 (owner, 2026-11-16)
SONNET_MARGIN = 0.05               # D2: S must beat H's mean by >= 5 points and its best run


def gate(h_records: list[dict]) -> dict[str, Any]:
    s = summarize(h_records)
    ok = (s["faithfulness"] is not None and s["faithfulness"] >= FAITHFULNESS_MIN
          and s["template_rate"] is not None and s["template_rate"] <= TEMPLATE_RATE_MAX)
    return {"rule": f"faithfulness >= {FAITHFULNESS_MIN} and template rate <= {TEMPLATE_RATE_MAX}, "
                    "pooled over the 3 H runs (D5; P2: writer-path answers only)",
            "writer_answers": s["writer_answers"], "faithfulness": s["faithfulness"],
            "template_rate": s["template_rate"], "pass": ok}


def perception_rule(h_overall: list[float], s_overall: float) -> dict[str, Any]:
    mean_h, best_h = statistics.mean(h_overall), max(h_overall)
    sonnet = s_overall >= mean_h + SONNET_MARGIN and s_overall > best_h
    return {"rule": "D2: Sonnet + fallback only if S >= mean(H) + 5 points and S > best H",
            "h_mean": mean_h, "h_best": best_h, "s": s_overall,
            "step6_perception": "claude-sonnet-5-5" if sonnet else "claude-haiku-5-5"}


def score(h: list[Path], s: Path | None = None, o: list[Path] | None = None) -> dict[str, Any]:
    runs = {}
    h_records = []
    for p in h:
        head, recs = load(p)
        runs[p.name] = {"label": head["label"], "kind": head["kind"], **summarize(recs)}
        h_records += recs
    out: dict[str, Any] = {"runs": runs}
    if h:
        out["h_pooled"] = summarize(h_records)
        out["gate"] = gate(h_records)
    for p in (o or []):
        head, recs = load(p)
        runs[p.name] = {"label": head["label"], "kind": head["kind"], **summarize(recs)}
    if s is not None:
        head, recs = load(s)
        runs[s.name] = {"label": head["label"], "kind": head["kind"], **summarize(recs)}
        if len(h) == 3:
            out["perception_rule"] = perception_rule([runs[p.name]["overall"] for p in h], runs[s.name]["overall"])
    return out


def attribution(pipeline_file: Path, oracle_a: Path, oracle_b: Path) -> dict[str, Any]:
    """Each wrong (not fully correct) pipeline answer, assigned to a stage."""
    _, pipe = load(pipeline_file)
    a = {r["id"]: r for r in load(oracle_a)[1]}
    b = {r["id"]: r for r in load(oracle_b)[1]}
    stages = {}
    for r in pipe:
        if r.get("correct") is None or r["correct"] >= 1:
            continue
        if r["id"] not in a or r["id"] not in b:
            stages[r["id"]] = "no_gold_program"
        elif b[r["id"]].get("correct", 0) >= 1:
            stages[r["id"]] = "parser"
        elif a[r["id"]].get("correct", 0) >= 1:
            stages[r["id"]] = "perception"
        else:
            stages[r["id"]] = "rules_writer_or_fallback"
    return {"wrong": len(stages), "by_stage": dict(Counter(stages.values())), "per_question": stages}


# ---------------------------------------------------------------- estimate (no call)

COST = {"writer": 0.0003, "fallback": 0.008, "judge": 0.007, "parser": 0.0028,
        "perception_haiku_fb": 0.0028, "perception_sonnet_fb": 0.023}


def _measured_parser_cost() -> float | None:
    if not LOG.exists():
        return None
    xs = [c["cost_usd"] for c in (json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip())
          if c.get("purpose") == "parse" and c.get("model") == "claude-sonnet-5-5" and c.get("status") == "ok"]
    return statistics.mean(xs) if xs else None


def estimate(fallback_rate: float = 0.45, oracle_fallback_rate: float = 0.15) -> dict[str, Any]:
    qs = load_dev()
    n = len(qs)
    nqa = sum(q["question_type"] != "Yes/No" for q in qs) / n
    n_gold = len(set(gold_programs()) & {q["id"] for q in qs})
    parser = _measured_parser_cost() or COST["parser"]
    per_q = parser + COST["writer"] + fallback_rate * COST["fallback"] + nqa * COST["judge"]
    per_oracle_q = COST["writer"] + oracle_fallback_rate * COST["fallback"] + nqa * COST["judge"]
    images = len(pe.set_images("public_dev"))
    lines = {
        "owner: 2 fresh Haiku v4 pass-1 runs + fallback (perception only)": 2 * images * COST["perception_haiku_fb"],
        "step 2: H x 3 pipeline runs": 3 * n * per_q,
        "step 2: S x 1 pipeline run": n * per_q,
        "step 2: oracle A x 1": n_gold * per_oracle_q,
        "step 2: oracle B x 3 (H)": 3 * n_gold * per_oracle_q,
    }
    return {"assumptions": {"questions": n, "natural_qa_share": round(nqa, 3), "gold_programs": n_gold,
                            "parser_per_call": round(parser, 5), "fallback_rate": fallback_rate,
                            "oracle_fallback_rate": oracle_fallback_rate, **COST},
            "per_question_usd": round(per_q, 5),
            "lines_usd": {k: round(v, 3) for k, v in lines.items()},
            "total_usd": round(sum(lines.values()), 3),
            "range_usd_pm50": [round(0.5 * sum(lines.values()), 3), round(1.5 * sum(lines.values()), 3)]}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("oracle-a-yesno", help="gold scenes + gold programs, engine verdicts only (no call)")
    e = sub.add_parser("estimate", help="step-2 cost estimate (no call)")
    e.add_argument("--fallback-rate", type=float, default=0.45)
    r = sub.add_parser("run", help="warm one perception run, then the pipeline on public_dev")
    r.add_argument("--warm-run", type=Path, required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--max-spend", type=float, required=True)
    r.add_argument("--warm-dir", type=Path)
    o = sub.add_parser("oracle", help="oracle A (gold scenes) or B (warmed scenes), gold programs")
    o.add_argument("--kind", choices=["A", "B"], required=True)
    o.add_argument("--label", default="O")
    o.add_argument("--warm-run", type=Path)
    o.add_argument("--max-spend", type=float, required=True)
    o.add_argument("--warm-dir", type=Path)
    s = sub.add_parser("score")
    s.add_argument("--h", type=Path, nargs="*", default=[])
    s.add_argument("--s", type=Path)
    s.add_argument("--o", type=Path, nargs="*", default=[])
    at = sub.add_parser("attribution")
    at.add_argument("pipeline", type=Path)
    at.add_argument("oracle_a", type=Path)
    at.add_argument("oracle_b", type=Path)
    a = ap.parse_args()
    if a.cmd == "oracle-a-yesno":
        print(json.dumps(oracle_a_yesno(), indent=2, ensure_ascii=False))
    elif a.cmd == "estimate":
        print(json.dumps(estimate(a.fallback_rate), indent=2, ensure_ascii=False))
    elif a.cmd == "run":
        run_pipeline(a.warm_run, a.label, a.max_spend, warm_dir=a.warm_dir)
    elif a.cmd == "oracle":
        run_oracle(a.kind, a.label, a.max_spend, warm_file=a.warm_run, warm_dir=a.warm_dir)
    elif a.cmd == "score":
        print(json.dumps(score(a.h, a.s, a.o), indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps(attribution(a.pipeline, a.oracle_a, a.oracle_b), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
