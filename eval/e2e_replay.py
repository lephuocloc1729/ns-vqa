"""Replay a step-2 pipeline run with the current code (docs/plans/phase-4.md, tuning; owner 2026-11-16).

A tuning run re-checks the D5 gate pooled over H1-H3 without re-parsing: it reuses each
H run's stored scenes and parsed programs and runs everything after the parser again.

- **Scenes:** the H run's perception file is warmed into the warm cache (one run at a
  time, as in step 2) and the pipeline reads it cache-only, so perception code changes
  (T4) apply. A rebuilt scene that differs from the file is an error unless
  `--allow-scene-changes` is given; the changed images are then listed in the header.
- **Programs:** the stored parse (status, program, errors) of the same question in the
  stored run. The parser is never called.
- **The engine, the triggers and the writer** always run with the current code.
- **The fallback** is reused when its inputs are unchanged: same question, same scene
  (as the stored run saw it) and the same fallback prompt id. Otherwise it is called.
- **The judge** grade is reused when the answer text is unchanged; Yes/No needs no judge.

    .venv/bin/python eval/e2e_replay.py estimate <H1 file> <H2 file> <H3 file>
    .venv/bin/python eval/e2e_replay.py run --run <H pipeline file> --warm-run <its perception file> --label T1-H1 --max-spend 0.3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_eval as ee  # noqa: E402
from eval import gold_signs as gs  # noqa: E402
from eval import perception_eval as pe  # noqa: E402

RUNS = ee.RUNS
# Per-question costs for the estimate (step 2, measured: writer and judge per call, the
# fallback per question with its retries; logs/api_calls.jsonl and the H run traces).
COST = {"writer": 0.0004, "fallback": 0.006, "judge": 0.0055}


class StoredParser:
    """Returns the stored run's parse of the current question; never calls the model."""

    def __init__(self) -> None:
        self.rec: dict | None = None

    def parse(self, question: str):
        from vqa.parsing.claude_parser import ParseResult
        from vqa.schemas import QueryProgram

        p = (self.rec or {}).get("trace", {}).get("parser")
        if p is None:
            raise RuntimeError(f"{self.rec and self.rec['id']}: the stored run has no parse for this question")
        q = QueryProgram.model_validate(p["program"]) if p.get("program") else None
        return ParseResult(status=p["status"], query=q, errors=list(p.get("errors") or []),
                           attempts=0, cost_usd=0.0)


class StoredFallback:
    """The stored fallback outcome when its inputs are unchanged, else a real call."""

    def __init__(self, real, stored_scenes: dict[str, Any]) -> None:
        self.real, self.stored_scenes = real, stored_scenes
        self.prompt_id = real.prompt_id
        self.rec: dict | None = None
        self.reused: bool | None = None

    def answer(self, image_path, question, scene):
        from vqa.answer.fallback import FallbackAnswer

        fb = (self.rec or {}).get("trace", {}).get("fallback") or {}
        stored_scene = self.stored_scenes.get(self.rec["image_id"]) if self.rec else None
        same_scene = (scene is None and stored_scene is None) or (
            scene is not None and stored_scene is not None
            and ee_scene_json(scene) == ee_scene_json(stored_scene))
        if fb.get("status") and fb.get("prompt_id") == self.real.prompt_id and same_scene:
            self.reused = True
            ok = fb["status"] == "ok"
            return FallbackAnswer(status=fb["status"], verdict=self.rec["verdict"] if ok else None,
                                  text=self.rec["text"] if ok else "", attempts=fb.get("attempts", 0),
                                  errors=fb.get("errors", []), cost_usd=0.0, prompt_id=fb["prompt_id"],
                                  raw=list(fb.get("raw") or []))
        self.reused = False
        return self.real.answer(image_path, question, scene)


def ee_scene_json(scene) -> str:
    from vqa.schemas import SceneGraph

    if isinstance(scene, dict):
        scene = SceneGraph.model_validate(scene)
    return json.dumps(scene.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)


def _stored_scenes(warm_file: Path) -> dict[str, Any]:
    _, rows = pe.load_run(warm_file)
    return {r["image_id"]: r.get("scene") for r in rows}


def replay(run_file: Path, warm_file: Path, label: str, max_spend: float, *, sdk=None,
           warm_dir: Path | None = None, out_dir: Path = RUNS, judge: bool = True,
           allow_scene_changes: bool = False, questions: list[dict] | None = None) -> Path:
    from eval.judge import Judge
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.pipeline import Pipeline, PipelineConfig

    shead, stored = ee.load(Path(run_file))
    phead, _ = pe.load_run(Path(warm_file))
    if shead.get("scenes_from") != phead["run_id"]:
        raise SystemExit(f"{Path(run_file).name} used scenes {shead.get('scenes_from')}, "
                         f"not {phead['run_id']} ({Path(warm_file).name})")
    rep = pe.warm_run(Path(warm_file), warm_dir)
    if not rep["ok"] and not allow_scene_changes:
        raise SystemExit(f"rebuilt scenes differ for {rep['mismatches']}; pass --allow-scene-changes "
                         "for a perception change")
    guard = SpendGuard(max_spend)
    pipe = Pipeline(PipelineConfig(perception_model=phead["model"], cache_dir=Path(rep["cache_dir"]),
                                   cache_only=True), sdk=sdk, guard=guard)
    parser, fallback = StoredParser(), StoredFallback(pipe.fallback, _stored_scenes(Path(warm_file)))
    pipe.parser, pipe.fallback = parser, fallback
    jd = Judge(llm=LLMClient(model="claude-opus-5-5", guard=guard, sdk=sdk)) if judge else None
    head = ee._header("replay", label, replay_of=shead["run_id"], replay_of_label=shead["label"],
                      scenes_from=phead["run_id"], perception_model=phead["model"],
                      perception_prompt=phead["prompt_id"], scene_fallback=phead.get("fallback"),
                      scene_changes=sorted(rep["mismatches"]) if not rep["ok"] else [])
    out = ee._out("replay", label, head["run_id"], out_dir)
    questions = {q["id"]: q for q in (questions if questions is not None else ee.load_dev())}
    grade_keys = ("correct", "strict", "yes_no_pred", "judge_label", "judge_reason", "judge_cost_usd")
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(head, ensure_ascii=False) + "\n")
        for n, s in enumerate(stored, 1):
            q = questions[s["id"]]
            parser.rec = fallback.rec = s
            fallback.reused = None
            a = pipe.answer(gs.image_path(q["image_id"], "public_dev"), q["question"])
            t = a.trace
            rec = {"id": q["id"], "image_id": q["image_id"], "question_type": q["question_type"],
                   "text": a.text, "verdict": a.verdict, "answered_by": a.answered_by,
                   "trigger": t["fallback"]["trigger"], "fallback_status": t["fallback"].get("status"),
                   "writer_status": (t.get("writer") or {}).get("status"),
                   "engine_verdict": (t.get("engine") or {}).get("verdict"),
                   "parse_status": (t.get("parser") or {}).get("status"),
                   "fallback_reused": fallback.reused, "cost_usd": a.cost_usd, "seconds": a.seconds,
                   "trace": t}
            if a.text == s["text"] and s.get("correct") is not None:
                rec.update({k: s[k] for k in grade_keys if k in s}, judge_reused=True, judge_cost_usd=0.0)
            else:
                rec.update(ee.grade(q, a.text, jd), judge_reused=False)
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            f.flush()
            print(f"[{n}/{len(stored)}] {q['id']}: {a.answered_by} {a.verdict}  spent ${guard.spent:.4f}")
    ee._check_still_warm(rep)
    print(f"{label} -> {out}  (spent ${guard.spent:.4f})")
    return out


def estimate(run_files: list[Path], *, fallback_changed: bool = False) -> dict[str, Any]:
    """The paid part of a replay: every writer-path answer is rewritten (and judged
    again when Natural QA); the fallback is called again only if its prompt changed."""
    writer = nqa_writer = fb = nqa_fb = 0
    for p in run_files:
        _, recs = ee.load(Path(p))
        for r in recs:
            nqa = r["question_type"] != "Yes/No"
            if r.get("fallback_status"):
                fb += 1 if fallback_changed else 0
                nqa_fb += 1 if (fallback_changed and nqa) else 0
            if r.get("answered_by") == "rules":
                writer += 1
                nqa_writer += nqa
    lines = {"writer": writer * COST["writer"], "fallback": fb * COST["fallback"],
             "judge": (nqa_writer + nqa_fb) * COST["judge"]}
    total = sum(lines.values())
    return {"calls": {"writer": writer, "fallback": fb, "judge (Natural QA)": nqa_writer + nqa_fb},
            "per_call_usd": COST, "lines_usd": {k: round(v, 3) for k, v in lines.items()},
            "total_usd": round(total, 3), "range_usd_pm50": [round(0.5 * total, 3), round(1.5 * total, 3)]}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estimate")
    e.add_argument("runs", type=Path, nargs="+")
    e.add_argument("--fallback-changed", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--run", type=Path, required=True)
    r.add_argument("--warm-run", type=Path, required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--max-spend", type=float, required=True)
    r.add_argument("--warm-dir", type=Path)
    r.add_argument("--allow-scene-changes", action="store_true")
    a = ap.parse_args()
    if a.cmd == "estimate":
        print(json.dumps(estimate(a.runs, fallback_changed=a.fallback_changed), indent=2))
    else:
        replay(a.run, a.warm_run, a.label, a.max_spend, warm_dir=a.warm_dir,
               allow_scene_changes=a.allow_scene_changes)


if __name__ == "__main__":
    main()
