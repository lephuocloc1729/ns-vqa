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
  (with v5-tile / v5-crop), the guide-board call on, parser v7 (`CANDIDATE`). Everything else
  is the frozen configuration, and the freeze check still runs (it guards the frozen parts).
  The header records the candidate and its prompt ids; stored scenes include the boards.

    .venv/bin/python eval/e2e_dev.py estimate [--candidate]
    .venv/bin/python eval/e2e_dev.py run --label frozen --max-spend 1.0
    .venv/bin/python eval/e2e_dev.py run --label candidate --candidate --max-spend 1.3
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
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
CANDIDATE = {"scene_version": "v5", "parser_version": "v7", "guide_reading": True}
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
    r.add_argument("--candidate", action="store_true", help="scene v5 + guide reading + parser v7 (CANDIDATE)")
    s = sub.add_parser("summary")
    s.add_argument("file", type=Path)
    a = ap.parse_args()
    if a.cmd == "estimate":
        print(json.dumps(estimate(candidate=a.candidate), indent=2, ensure_ascii=False))
    elif a.cmd == "summary":
        print(json.dumps(summary(a.file), indent=2))
    else:
        run_dev(a.label, a.max_spend, candidate=CANDIDATE if a.candidate else None)


if __name__ == "__main__":
    main()
