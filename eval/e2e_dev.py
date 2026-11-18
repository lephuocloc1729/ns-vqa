"""The phase-4.5 dev runs (docs/plans/phase-4.5.md, section 9; owner, 2026-11-17).

The dev set (`data/splits/train_dev.json`: the validation pool minus the validation set) is
readable question by question. A dev run is the frozen system with the answer fallback
**off**, and it keeps per-question records in the gitignored runs folder:
`eval/runs/e2e/dev_<label>_<run_id>.jsonl` (a header, then one line per question with
the question id, image id, type, answer text, verdict, trigger, the parse, the engine's
answer, the scene, the trace and the grade). The run's scene cache is kept beside it
(`eval/runs/e2e/dev_cache_<run_id>/`), so replays rebuild scenes with no call.

- A question is decided when the rules answer yes, no or a value; the rest count as wrong
  and are not judged. Decided answers are graded as everywhere (Yes/No mapping; the same
  judge for Natural QA).
- Guards: the live configuration equals the given freeze record; the dev set shares no
  question or image with the validation set; the git tree is clean (the header records the
  commit).
- `replay` re-runs the engine on a dev run's stored scenes and parses with the current code
  (no call) and reports the decided figures; changed decided Natural QA answers are
  ungraded (it reports them), unchanged ones keep their grade.

- `--candidate` (phase 4.5 B4): the stage-B candidate instead of the frozen system: scene v5
  (with v5-tile / v5-crop), the guide-board call on, parser v8 (`CANDIDATE`; v7 failed the gate rule, run 1). Everything else
  is the frozen configuration, and the freeze check still runs (it guards the frozen parts).
  The header records the candidate and its prompt ids; stored scenes include the boards.

    .venv/bin/python eval/e2e_dev.py estimate [--candidate]
    .venv/bin/python eval/e2e_dev.py run --label frozen --max-spend 1.0
    .venv/bin/python eval/e2e_dev.py run --label candidate --candidate --max-spend 1.3
    .venv/bin/python eval/e2e_dev.py reparse --from eval/runs/e2e/dev_candidate_7caed6170de6.jsonl --version v9 --max-spend 0.20
    .venv/bin/python eval/e2e_dev.py reparse --from eval/runs/e2e/dev_reparse_v9_8bbb5eb01cff.jsonl --version v11 --select all --reading-policy higher_confidence --max-spend 0.45

`reparse` (phase 4.5, owner 2026-11-17): a new parser version on a stored dev run, with no
perception call. It re-parses the dev questions whose wording the new rule is about
(`--select yesno`, chosen by pattern, never by outcome; `--select all` re-parses every
question), runs the engine on the stored scenes, and only for a decided answer whose
program changed calls the writer and the judge. Unchanged parses keep their record and grade.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_eval as ee  # noqa: E402
from eval import e2e_validation as ev  # noqa: E402
from eval import freeze  # noqa: E402
from eval.make_validation_split import DEV_OUT, OUT as VALIDATION  # noqa: E402

OUT = ROOT / "eval" / "runs" / "e2e"
DECIDED = ev.DECIDED
# The stage-B candidate (owner, 2026-11-17): PipelineConfig fields that differ from the frozen run.
CANDIDATE = {"scene_version": "v5", "parser_version": "v8", "guide_reading": True}
FROZEN_DEV_RUN = OUT / "dev_frozen_13ded0d75451.jsonl"


def candidate_prompt_ids(candidate: dict = CANDIDATE) -> dict[str, str]:
    from vqa.parsing.prompt import system_prompt as parser_prompt
    from vqa.perception import guide, prompt as sp
    from vqa.perception.fallback import config_for
    import hashlib
    fc = config_for(candidate["scene_version"])
    pv = candidate["parser_version"]
    return {"scene": sp.prompt_id(candidate["scene_version"]), "scene_tile": sp.prompt_id(fc.tile_version),
            "scene_crop": sp.prompt_id(fc.crop_version), "guide": guide.prompt_id(),
            "parser": f"parser/{pv}@" + hashlib.sha256(parser_prompt(pv).encode("utf-8")).hexdigest()[:12]}


def load_questions(dev_file: Path = DEV_OUT, qa_file: Path | None = None, *, with_answers: bool = True) -> list[dict]:
    return ev.load_questions(dev_file, qa_file, with_answers=with_answers)


def check_disjoint(dev_file: Path = DEV_OUT, validation_file: Path = VALIDATION) -> None:
    d = json.loads(Path(dev_file).read_text(encoding="utf-8"))
    v = json.loads(Path(validation_file).read_text(encoding="utf-8"))
    if set(d["questions"]) & set(v["questions"]) or set(d["images"]) & set(v["images"]):
        raise SystemExit("the dev set overlaps the validation set")


def run_dev(label: str, max_spend: float, *, sdk=None, questions: list[dict] | None = None, out_dir: Path = OUT,
            image_path=None, frozen: Path = freeze.FROZEN, git=freeze.git_state, dev_file: Path = DEV_OUT,
            validation_file: Path = VALIDATION, candidate: dict | None = None) -> Path:
    from eval.judge import Judge
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.perception.scene import perceive
    from vqa.pipeline import Pipeline, PipelineConfig, _RefuseCalls

    check_disjoint(dev_file, validation_file)
    g = git()
    if not g["clean"]:
        raise SystemExit("the git working tree is not clean: commit or remove these first:\n  " + "\n  ".join(g["dirty"]))
    pm = freeze.load(frozen)["pipeline_config"]["perception_model"]
    if d := freeze.check(frozen, pm):
        raise SystemExit("the live configuration differs from the freeze record:\n  " + "\n  ".join(d))
    image_path = image_path or ev.image_file
    qs = questions if questions is not None else load_questions(dev_file)
    run_id = uuid.uuid4().hex[:12]
    cache_dir = out_dir / f"dev_cache_{run_id}"
    guard = SpendGuard(max_spend)
    pipe = Pipeline(PipelineConfig(perception_model=pm, cache_dir=cache_dir, cache_only=False, answer_fallback=False,
                                   **(candidate or {})), sdk=sdk, guard=guard)
    judge = Judge(llm=LLMClient(model="claude-opus-5-5", guard=guard, sdk=sdk))
    config = freeze.live(pm)
    head = {"kind": "dev", "label": label, "run_id": run_id, "git_commit": g["commit"],
            "frozen_record": Path(frozen).name, "prompt_ids": {k: v["id"] for k, v in config["prompts"].items()},
            "cache_dir": cache_dir.name, "answer_fallback": False,
            "candidate": candidate, "candidate_prompt_ids": candidate_prompt_ids(candidate) if candidate else None,
            "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"dev_{label}_{run_id}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(head, ensure_ascii=False) + "\n")
        for n, q in enumerate(qs, 1):
            img = image_path(q["image_id"])
            a = pipe.answer(img, q["question"])
            t = a.trace
            # the scene the pipeline just used, rebuilt from its cache with every call refused
            sc = perceive(img, model=pm, version=pipe.config.scene_version, client=_RefuseCalls(pm),
                          cache=pipe.cache, use_cache=True, fallback=_scene_fallback(pipe)).scene
            sc = _with_boards(pipe, img, sc)
            ev_verdict = (t.get("engine") or {}).get("verdict")
            decided = t["fallback"]["trigger"] is None and ev_verdict in DECIDED
            rec = {"id": q["id"], "image_id": q["image_id"], "question_type": q["question_type"],
                   "text": a.text, "verdict": a.verdict, "answered_by": a.answered_by, "decided": decided,
                   "trigger": t["fallback"]["trigger"], "engine_verdict": ev_verdict,
                   "parse_status": (t.get("parser") or {}).get("status"), "engine_answer": a.proof,
                   "scene": sc.model_dump(mode="json", by_alias=True) if sc is not None else None,
                   "cost_usd": a.cost_usd, "seconds": a.seconds, "trace": t, "correct": None, "strict": None}
            if decided:
                rec.update(ee.grade(q, a.text, judge))
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            f.flush()
            print(f"[{n}/{len(qs)}] {q['id']}: {'decided' if decided else rec['trigger']}  spent ${guard.spent:.4f}")
    print(f"dev run {run_id} -> {out}  (spent ${guard.spent:.4f})")
    return out


# The yes/no wordings of parser v9's rule (the same list as its spec line).
YESNO = re.compile(r"(đúng hay sai|đúng không|phải không|được không|có phải .*không|\bcó\b.*\bkhông\s*\??\s*$)", re.I)


def _decision_key(verdict: str | None, value) -> str:
    return json.dumps({"verdict": verdict, "value": value}, sort_keys=True, default=str, ensure_ascii=False)


def reparse(src: Path, version: str, max_spend: float, *, select: str = "yesno", sdk=None, out_dir: Path = OUT,
            git=freeze.git_state, questions: list[dict] | None = None, reading_policy: str | None = None) -> Path:
    """`reading_policy` (phase 4.6 step 6): run the engine with this reading policy, and re-run it
    on unchanged parses too; an answer whose decision changes is written and judged as a changed
    one (policy A, F1, F2 change answers without a new parse)."""
    import dataclasses
    import tempfile
    from eval.judge import Judge
    from eval.parser_eval import canonical
    from vqa.answer.digest import build as build_digest
    from vqa.answer.fallback import trigger
    from vqa.answer.template import template_answer
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard, SpendLimitExceeded
    from vqa.pipeline import Pipeline, PipelineConfig
    from vqa.reasoning.engine import EngineError
    from vqa.schemas import Answer, QueryProgram, SceneGraph, Verdict

    g = git()
    if not g["clean"]:
        raise SystemExit("the git working tree is not clean: commit or remove these first:\n  " + "\n  ".join(g["dirty"]))
    head, rows = ee.load(src)
    qs = {q["id"]: q for q in (questions if questions is not None else load_questions())}
    guard = SpendGuard(max_spend)
    base = PipelineConfig(**{k: v for k, v in (head.get("candidate") or {}).items()})
    if reading_policy:
        base = dataclasses.replace(base, reading_policy=reading_policy)
    with tempfile.TemporaryDirectory() as tmp:
        pipe = Pipeline(dataclasses.replace(base, parser_version=version, cache_only=True, cache_dir=Path(tmp),
                                            answer_fallback=False), sdk=sdk, guard=guard)
        judge = Judge(llm=LLMClient(model="claude-opus-5-5", guard=guard, sdk=sdk))
        run_id = uuid.uuid4().hex[:12]
        out = out_dir / f"dev_reparse_{version}_{run_id}.jsonl"
        new_head = {**head, "kind": "dev_reparse", "label": f"reparse_{version}", "run_id": run_id,
                    "from_run": head["run_id"], "parser_version": version, "select": select,
                    "reading_policy": reading_policy or base.reading_policy,
                    "git_commit": g["commit"], "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        changed = []
        stopped = None
        with open(out, "w", encoding="utf-8") as f:
            f.write(json.dumps(new_head, ensure_ascii=False) + "\n")
            for r in rows:
              try:
                  q = qs[r["id"]]
                  if select != "all" and not YESNO.search(q["question"]):
                      f.write(json.dumps({**r, "reparsed": False}, ensure_ascii=False, default=str) + "\n")
                      continue
                  pr = pipe.parser.parse(q["question"])
                  old = (r["trace"].get("parser") or {})
                  old_c = canonical(QueryProgram.model_validate(old["program"])) if old.get("program") else None
                  new_c = canonical(pr.query) if pr.query is not None else None
                  scene = SceneGraph.model_validate(r["scene"]) if r.get("scene") else None
                  if old.get("status") == pr.status and old_c == new_c:
                      same = True
                      if reading_policy and scene is not None and pr.status == "ok":
                          try:
                              a0 = pipe.engine.answer(scene, pr.query)
                              ea = r.get("engine_answer") or {}
                              same = _decision_key(a0.verdict.value, json.loads(json.dumps(a0.value, default=str))) \
                                  == _decision_key(ea.get("verdict"), ea.get("value"))
                          except EngineError:
                              same = r.get("engine_verdict") is None
                      if same:
                          f.write(json.dumps({**r, "reparsed": True, "changed": False}, ensure_ascii=False, default=str) + "\n")
                          continue
                  ans, err = None, None
                  if scene is not None and pr.status == "ok":
                      try:
                          ans = pipe.engine.answer(scene, pr.query)
                      except EngineError as e:
                          err = str(e)
                  why = trigger(scene_ok=scene is not None, parse_status=pr.status, answer=ans, engine_error=err is not None)
                  decided = why is None and ans is not None and ans.verdict.value in DECIDED
                  rec = {**r, "reparsed": True, "changed": True, "decided": decided, "trigger": why,
                         "engine_verdict": ans.verdict.value if ans else None, "parse_status": pr.status,
                         "engine_answer": ans.model_dump(mode="json") if ans else None,
                         "correct": None, "strict": None, "judge_label": None, "judge_reason": None,
                         "was": {"decided": r["decided"], "correct": r["correct"], "trigger": r["trigger"]}}
                  rec["trace"] = {**r["trace"], "parser": {"status": pr.status, "attempts": pr.attempts, "errors": pr.errors,
                                                          "cost_usd": pr.cost_usd,
                                                          "program": pr.query.model_dump(mode="json", by_alias=True, exclude_none=True)
                                                          if pr.query else None}}
                  if decided:
                      w = pipe.writer.write(q["question"], ans, scene)
                      rec["text"] = w.text
                      rec.update(ee.grade(q, w.text, judge))
                  else:
                      a = ans or Answer(verdict=Verdict.unknown)
                      rec["text"] = template_answer(build_digest(a, scene, pipe.engine.catalog), q["question"])
                  changed.append(r["id"])
                  f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                  f.flush()
                  print(f"{r['id']}: changed; {'decided' if decided else why}  spent ${guard.spent:.4f}")
              except SpendLimitExceeded as e:       # phase 4.6: a stopped re-parse is kept as partial
                stopped = e
                break
    if stopped is not None:
        partial = out.with_suffix(".partial.jsonl")
        out.rename(partial)
        print(f"stopped by the spend guard ({stopped}); partial file -> {partial}  (spent ${guard.spent:.4f})")
        return partial
    print(f"reparse {run_id} -> {out}  changed: {changed}  (spent ${guard.spent:.4f})")
    return out


# Phase 4.7 (owner, 2026-11-18): scene v5 + parser v14, judged where the answer changed. Each
# question takes its program from a dev run (`programs`) and its stored scene from earlier runs
# (`scenes`, the first that has it). An engine answer identical to that scene run's keeps its row
# and judged grade; a changed decided answer is written and judged (writer + judge only, no
# perception or parser call). --dry-run makes no call and lists what would be judged.
REJUDGE_WRITER_USD, REJUDGE_JUDGE_USD = 0.0015, 0.0067   # per answer: Haiku writer; Opus judge (frozen-run means)


def rejudge(programs: Path, scenes: list[Path], max_spend: float, *, dry_run: bool = False, sdk=None,
            out_dir: Path = OUT, git=freeze.git_state, questions: list[dict] | None = None) -> dict[str, Any]:
    import dataclasses
    import tempfile
    from eval.judge import Judge
    from vqa.answer.fallback import trigger
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard, SpendLimitExceeded
    from vqa.pipeline import Pipeline, PipelineConfig
    from vqa.reasoning.engine import EngineError
    from vqa.schemas import QueryProgram, SceneGraph

    g = git()
    if not dry_run and not g["clean"]:
        raise SystemExit("the git working tree is not clean: commit or remove these first:\n  " + "\n  ".join(g["dirty"]))
    phead, prows = ee.load(programs)
    srcs = [ee.load(p) for p in scenes]
    qs = {q["id"]: q for q in (questions if questions is not None else load_questions())}
    base = PipelineConfig(**{k: v for k, v in (srcs[0][0].get("candidate") or {}).items()})
    base = dataclasses.replace(base, reading_policy="higher_confidence")
    guard = SpendGuard(max_spend if not dry_run else 0.0)
    plan, rows_out, stopped = [], [], None
    with tempfile.TemporaryDirectory() as tmp:
        pipe = Pipeline(dataclasses.replace(base, cache_only=True, cache_dir=Path(tmp), answer_fallback=False),
                        sdk=sdk, guard=guard)
        judge = Judge(llm=LLMClient(model="claude-opus-5-5", guard=guard, sdk=sdk))
        for pr in prows:
            old = next((r for _, rs in srcs for r in rs if r["id"] == pr["id"]), None)
            if old is None or not old.get("scene"):
                rows_out.append({**pr, "rejudge": "no stored scene"})
                continue
            scene = SceneGraph.model_validate(old["scene"])
            pt = pr["trace"].get("parser") or {}
            q = QueryProgram.model_validate(pt["program"]) if pt.get("program") else None
            ans, err = None, False
            if q is not None and not q.out_of_scope:
                try:
                    ans = pipe.engine.answer(scene, q)
                except EngineError:
                    err = True
            status = "out_of_scope" if q is not None and q.out_of_scope else (pt.get("status") or "failed")
            why = trigger(scene_ok=True, parse_status=status if q is not None else "failed", answer=ans,
                          engine_error=err)
            decided = why is None and ans is not None and ans.verdict.value in DECIDED
            ea = old.get("engine_answer") or {}
            same = ans is not None and _decision_key(ans.verdict.value, json.loads(json.dumps(ans.value, default=str))) \
                == _decision_key(ea.get("verdict"), ea.get("value")) and decided == bool(old.get("decided"))
            if same or (not decided and not old.get("decided")):
                rows_out.append({**old, "rejudge": "kept", "program_from": phead["run_id"]})
                continue
            rec = {**old, "rejudge": "changed", "decided": decided, "trigger": why,
                   "engine_verdict": ans.verdict.value if ans else None,
                   "engine_answer": ans.model_dump(mode="json") if ans else None, "correct": None, "strict": None,
                   "was": {"decided": old.get("decided"), "correct": old.get("correct")}}
            rec["trace"] = {**old["trace"], "parser": pt}
            if decided:
                plan.append(pr["id"])
                if not dry_run:
                    try:
                        w = pipe.writer.write(qs[pr["id"]]["question"], ans, scene)
                        rec["text"] = w.text
                        rec.update(ee.grade(qs[pr["id"]], w.text, judge))
                    except SpendLimitExceeded as e:
                        stopped = e
                        break
            rows_out.append(rec)
    est = round(len(plan) * (REJUDGE_WRITER_USD + REJUDGE_JUDGE_USD), 4)
    report = {"judge_ids": plan, "estimate_usd": est, "changed_undecided": [r["id"] for r in rows_out
              if r.get("rejudge") == "changed" and not r["decided"]]}
    if dry_run:
        return report
    run_id = uuid.uuid4().hex[:12]
    out = out_dir / f"dev_rejudge_{run_id}{'.partial' if stopped else ''}.jsonl"
    head = {**srcs[0][0], "kind": "dev_rejudge", "label": "rejudge", "run_id": run_id, "programs_from": phead["run_id"],
            "scenes_from": [h["run_id"] for h, _ in srcs], "git_commit": g["commit"],
            "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(head, ensure_ascii=False) + "\n")
        for r in rows_out:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    print(f"rejudge {run_id} -> {out}  judged: {plan}  (spent ${guard.spent:.4f})")
    return {**report, "file": str(out), "spent_usd": round(guard.spent, 4)}


def _with_boards(pipe, img, scene):
    """The scene with the boards the guide call read, from the run's cache (no call)."""
    if scene is None or not pipe.config.guide_reading:
        return scene
    from vqa.perception import guide
    from vqa.perception.image import prepare_file
    if not guide.needs_boards(scene, pipe.engine.catalog):
        return scene
    g = guide.read_boards(prepare_file(img), model=pipe.config.perception_model, client=None, cache=pipe.cache)
    return guide.apply(scene, g.boards) if g.ok else scene


def _scene_fallback(pipe):
    return pipe.fallback_config()


def summary(path: Path) -> dict[str, Any]:
    _, rows = ee.load(path)
    rs = [{"image_id": r["image_id"], "decided": r["decided"], "correct": r["correct"]} for r in rows]
    from eval.coverage_analysis import decided_summary
    s = decided_summary(rs, "train")
    s["not_decided_by_cause"] = dict(Counter(r["trigger"] for r in rows if not r["decided"]))
    s.pop("non_duplicate", None)
    return s


# ---------------------------------------------------------------- estimate (no call)

def estimate(dev_file: Path = DEV_OUT, candidate: bool = False) -> dict[str, Any]:
    e = ev.estimate(dev_file)
    e["note"] = ("validation baseline measured $0.0060 per question all-in; the dev set is all Natural QA, so the "
                 "judge share is higher")
    e["measured_rate_usd"] = round(0.0060 * e["questions"], 2)
    if candidate:
        e["candidate"] = candidate_estimate()
    return e


def candidate_estimate(dev_run: Path = FROZEN_DEV_RUN, decided_expected: int = 59,
                       guide_per_image: float = 0.00039, parser_scale: float = 1.18,
                       perception_scale: float = 1.05) -> dict[str, Any]:
    """The candidate run, calibrated on the frozen dev run's measured per-stage costs:
    perception x1.05 (v5's longer listing), the guide call on images whose stored scene lists a
    board ($0.00039 each, the B6 trial's variant A), the parser x1.18 (v7's prompt is 18% longer),
    the writer and the judge per decided answer, at the hand-program replay's 59 decided."""
    from vqa.kb import load_catalog
    from vqa.perception import guide
    from vqa.schemas import SceneGraph
    head, rows = ee.load(dev_run)
    cat = load_catalog()
    stage = Counter()
    boards, seen = 0, set()
    for r in rows:
        t = r["trace"]
        if r["image_id"] not in seen:
            seen.add(r["image_id"])
            stage["perception"] += (t.get("perception") or {}).get("cost_usd") or 0
            if r.get("scene") and guide.needs_boards(SceneGraph.model_validate(r["scene"]), cat):
                boards += 1
        stage["parser"] += (t.get("parser") or {}).get("cost_usd") or 0
        stage["writer"] += (t.get("writer") or {}).get("cost_usd") or 0
        stage["judge"] += r.get("judge_cost_usd") or 0
    dec = sum(r["decided"] for r in rows)
    lines = {"perception v5 + fallback": stage["perception"] * perception_scale,
             f"guide call ({boards} images with a board)": boards * guide_per_image,
             "parser v7, Sonnet medium": stage["parser"] * parser_scale,
             "writer, per decided": stage["writer"] / dec * decided_expected,
             "judge, Opus, per decided": stage["judge"] / dec * decided_expected}
    total = sum(lines.values())
    return {"measured_frozen_run_usd": {k: round(v, 4) for k, v in stage.items()}, "frozen_decided": dec,
            "decided_expected": decided_expected, "lines_usd": {k: round(v, 3) for k, v in lines.items()},
            "total_usd": round(total, 2), "range_usd": [round(0.8 * total, 2), round(1.3 * total, 2)]}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estimate")
    e.add_argument("--candidate", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--max-spend", type=float, required=True)
    r.add_argument("--candidate", action="store_true", help="scene v5 + guide reading + parser v8 (CANDIDATE)")
    r.add_argument("--scene-version", help="scene prompt override for a candidate run")
    r.add_argument("--parser-version", help="parser prompt override for a candidate run")
    r.add_argument("--reading-policy", choices=["all", "higher_confidence"],
                   help="alternative sign-reading policy for a candidate run")
    rp = sub.add_parser("reparse")
    rp.add_argument("--from", dest="src", type=Path, required=True)
    rp.add_argument("--version", required=True)
    rp.add_argument("--max-spend", type=float, required=True)
    rp.add_argument("--select", choices=["yesno", "all"], default="yesno")
    rp.add_argument("--reading-policy", choices=["all", "higher_confidence"], default=None,
                    help="phase 4.6: the engine's reading policy; also re-runs the engine on unchanged parses")
    rj = sub.add_parser("rejudge", help="phase 4.7: programs from one run on stored scenes; judge changed answers only")
    rj.add_argument("--programs", type=Path, required=True)
    rj.add_argument("--scenes", type=Path, nargs="+", required=True)
    rj.add_argument("--max-spend", type=float, default=0.0)
    rj.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("summary")
    s.add_argument("file", type=Path)
    a = ap.parse_args()
    if a.cmd == "estimate":
        print(json.dumps(estimate(candidate=a.candidate), indent=2, ensure_ascii=False))
    elif a.cmd == "reparse":
        reparse(a.src, a.version, a.max_spend, select=a.select, reading_policy=a.reading_policy)
    elif a.cmd == "rejudge":
        print(json.dumps(rejudge(a.programs, a.scenes, a.max_spend, dry_run=a.dry_run), indent=2, ensure_ascii=False))
    elif a.cmd == "summary":
        print(json.dumps(summary(a.file), indent=2))
    else:
        overrides = {k: getattr(a, k) for k in ("scene_version", "parser_version", "reading_policy")
                     if getattr(a, k) is not None}
        candidate = {**CANDIDATE, **overrides} if a.candidate or overrides else None
        run_dev(a.label, a.max_spend, candidate=candidate)


if __name__ == "__main__":
    main()
