"""Phase 4.6 D3 (owner, 2026-11-17): parse-only diagnosis of the train working set's Yes/No questions.

**A biased set: diagnosis only, never a score.** The working set is train minus the dev set and
minus the validation set (`eval/phase46_analysis.py`). Its images fed the parser few-shots
(v7-v9), the stage-A sign list and rule design, so its numbers say *where* Yes/No questions go
undecided, not how well the system does.

- **Parse only, no new perception.** Every Yes/No question is parsed with the frozen phase-4.5
  parser (v9, Sonnet medium). Where the image already has a scene v5 record in the scene cache,
  the scene is rebuilt cache-only (every call refused; a missing tile, crop or board record is a
  refused call and is counted) and the engine runs with reading policy A (phase 4.6 step 1).
  Those engine results are indicative. Other questions get the parse outcome only.
- **Refuses** any question whose id or image is in the dev set or the validation set (the two
  split files are read for their ids only), a dirty git tree, and a live configuration that
  differs from `eval/frozen_phase45.json`.
- Per-question records go to the gitignored `eval/runs/trainset/`; the header says `biased: true`.
- The report gives causes by question type, by intent and by out-of-scope group.

    .venv/bin/python eval/e2e_trainset.py estimate
    .venv/bin/python eval/e2e_trainset.py run --max-spend 0.50
    .venv/bin/python eval/e2e_trainset.py summary eval/runs/trainset/trainset_yesno_<run_id>.jsonl
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_eval as ee  # noqa: E402
from eval import freeze  # noqa: E402
from eval import gold_signs as gs  # noqa: E402
from eval.make_validation_split import DEV_OUT, OUT as VALIDATION  # noqa: E402

OUT = ROOT / "eval" / "runs" / "trainset"
DECIDED = ("yes", "no", "value")
PARSER_RATE = 0.00396          # parser v9 per question: v9 gate run + v9 dev re-parse (51 calls)
READING_POLICY = "higher_confidence"
BIASED_NOTE = ("train minus dev minus validation; its images fed parser few-shots (v7-v9), the stage-A "
               "sign list and rule design: diagnosis only, never a score")


def _ids(path: Path) -> tuple[set[str], set[str]]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return set(d["questions"]), set(d["images"])


def forbidden_ids(dev_file: Path = DEV_OUT, validation_file: Path = VALIDATION) -> tuple[set[str], set[str]]:
    """Question ids and image ids of the dev and validation sets (ids only)."""
    dq, di = _ids(dev_file)
    vq, vi = _ids(validation_file)
    return dq | vq, di | vi


def check_ids(qs: list[dict], forbidden: tuple[set[str], set[str]]) -> None:
    fq, fi = forbidden
    bad = sum(q["id"] in fq or q["image_id"] in fi for q in qs)
    if bad:
        raise SystemExit(f"{bad} question(s) belong to the dev or validation set (by question or image id); "
                         "the train working set must exclude them")


def load_questions(qa_file: Path | None = None, forbidden: tuple[set[str], set[str]] | None = None) -> list[dict]:
    """The working set's Yes/No questions: train, minus dev and validation questions and images."""
    fq, fi = forbidden if forbidden is not None else forbidden_ids()
    rows = json.loads(Path(qa_file or gs.TRAIN_QA).read_text(encoding="utf-8"))
    return [{k: q[k] for k in ("id", "image_id", "question_type", "question", "answer")} for q in rows
            if q["question_type"] == "Yes/No" and q["id"] not in fq and q["image_id"] not in fi]


def estimate(qs: list[dict] | None = None) -> dict[str, Any]:
    qs = qs if qs is not None else load_questions()
    n = len(qs)
    total = n * PARSER_RATE
    return {"biased": True, "questions": n, "images": len({q["image_id"] for q in qs}),
            "parser_rate_usd": PARSER_RATE, "total_usd": round(total, 3),
            "range_usd": [round(0.8 * total, 3), round(1.3 * total, 3)],
            # the range's top, rounded up to 5 cents (the spend guard also keeps one call's worst case free)
            "suggested_max_spend": max(0.10, math.ceil(1.3 * total * 20) / 20),
            "note": "parse only; no perception call (cached scenes are rebuilt with every call refused), "
                    "no writer, no judge (Yes/No is graded by the yes/no mapping)"}


def _scene(pipe, img: Path):
    """The cached scene, cache-only, or (None, why)."""
    from vqa.pipeline import CacheMissError
    try:
        res, info = pipe._perceive(img)
    except CacheMissError:
        return None, {"cached": False}
    return (res.scene if res.ok else None), {"cached": True, "ok": res.ok,
                                             "refused_calls": info.get("refused_calls", 0)}


def run(max_spend: float, *, sdk=None, questions: list[dict] | None = None, out_dir: Path = OUT,
        frozen: Path = freeze.FROZEN_PHASE45, git=freeze.git_state, image_path=None, cache_dir: Path | None = None,
        forbidden: tuple[set[str], set[str]] | None = None) -> Path:
    from vqa.answer.fallback import trigger
    from vqa.llm.spend import SpendGuard
    from vqa.pipeline import Pipeline
    from vqa.reasoning.engine import EngineError

    from eval.phase46_analysis import group_of

    if sdk is None and not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set: no call can be made (nothing written)")
    forbidden = forbidden if forbidden is not None else forbidden_ids()
    qs = questions if questions is not None else load_questions(forbidden=forbidden)
    check_ids(qs, forbidden)
    g = git()
    if not g["clean"]:
        raise SystemExit("the git working tree is not clean: commit or remove these first:\n  " + "\n  ".join(g["dirty"]))
    pm = freeze.load(frozen)["pipeline_config"]["perception_model"]
    if d := freeze.check(frozen, pm):
        raise SystemExit("the live configuration differs from the freeze record:\n  " + "\n  ".join(d))
    image_path = image_path or (lambda i: gs.image_path(i, "train"))
    guard = SpendGuard(max_spend)
    cfg = freeze.pipeline_config(freeze.profile_of(freeze.load(frozen)), pm, cache_only=True, cache_dir=cache_dir,
                                 answer_fallback=False, reading_policy=READING_POLICY)
    pipe = Pipeline(cfg, sdk=sdk, guard=guard)
    run_id = uuid.uuid4().hex[:12]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"trainset_yesno_{run_id}.jsonl"
    head = {"kind": "trainset_yesno", "biased": True, "why_biased": BIASED_NOTE, "run_id": run_id,
            "git_commit": g["commit"], "frozen_record": Path(frozen).name,
            "parser": freeze.live(pm, freeze.profile_of(freeze.load(frozen)))["prompts"]["parser"]["id"],
            "reading_policy": READING_POLICY, "questions": len(qs),
            "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(head, ensure_ascii=False) + "\n")
        for n, q in enumerate(qs, 1):
            pr = pipe.parser.parse(q["question"])
            prog = pr.query.model_dump(mode="json", by_alias=True, exclude_none=True) if pr.query else None
            rec = {"id": q["id"], "image_id": q["image_id"], "question_type": q["question_type"],
                   "parse_status": pr.status, "attempts": pr.attempts, "errors": pr.errors, "cost_usd": pr.cost_usd,
                   "program": prog, "intent": ((prog or {}).get("program") or {}).get("intent"),
                   "out_of_scope_reason": (prog or {}).get("out_of_scope_reason"),
                   "wording_group": group_of(q["question"]),
                   "scene": None, "trigger": None, "engine_verdict": None, "decided": None, "correct": None}
            scene, rec["scene"] = _scene(pipe, image_path(q["image_id"]))
            if scene is not None:
                ans, err = None, False
                if pr.status == "ok":
                    try:
                        ans = pipe.engine.answer(scene, pr.query)
                    except EngineError:
                        err = True
                why = trigger(scene_ok=True, parse_status=pr.status, answer=ans, engine_error=err)
                decided = why is None and ans is not None and ans.verdict.value in DECIDED
                rec.update(trigger=why, engine_verdict=ans.verdict.value if ans else None, decided=decided,
                           basis=ans.basis if ans else [])
                if decided and ans.verdict.value in ("yes", "no"):
                    rec["correct"] = float((ans.verdict.value == "yes") == ee.yes_no(q["answer"]))
            elif pr.status != "ok":
                rec["trigger"] = "out_of_scope" if pr.status == "out_of_scope" else "parse_failed"
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            f.flush()
            print(f"[{n}/{len(qs)}] {pr.status}  spent ${guard.spent:.4f}")
    print(f"train Yes/No parse run {run_id} -> {out}  (spent ${guard.spent:.4f}; biased set, diagnosis only)")
    return out


def summary(path: Path) -> dict[str, Any]:
    lines = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    head, rows = lines[0], lines[1:]
    with_scene = [r for r in rows if (r.get("scene") or {}).get("cached") and r.get("decided") is not None]
    dec = [r for r in with_scene if r["decided"]]
    graded = [r for r in dec if r.get("correct") is not None]
    by_type: dict[str, Any] = {}
    for t in sorted({r["question_type"] for r in rows}):
        rs = [r for r in rows if r["question_type"] == t]
        by_type[t] = {"questions": len(rs), "parse_status": dict(Counter(r["parse_status"] for r in rs)),
                      "intents": dict(Counter(r["intent"] or "none" for r in rs if r["parse_status"] == "ok"))}
    return {"biased": head.get("biased"), "why_biased": head.get("why_biased"), "run_id": head.get("run_id"),
            "questions": len(rows), "spent_usd": round(sum(r.get("cost_usd") or 0 for r in rows), 4),
            "by_question_type": by_type,
            "out_of_scope_by_wording_group": dict(Counter(r["wording_group"] for r in rows
                                                          if r["parse_status"] == "out_of_scope")),
            "with_cached_scene": {"questions": len(with_scene), "decided": len(dec),
                                  "accuracy_on_decided": (sum(r["correct"] for r in graded) / len(graded)) if graded else None,
                                  "not_decided_by_cause": dict(Counter(r["trigger"] for r in with_scene if not r["decided"])),
                                  "refused_calls": sum((r.get("scene") or {}).get("refused_calls", 0) for r in with_scene),
                                  "note": "indicative: cached scenes rebuilt cache-only; a biased set"}}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estimate")
    r = sub.add_parser("run")
    r.add_argument("--max-spend", type=float, required=True)
    s = sub.add_parser("summary")
    s.add_argument("file", type=Path)
    a = ap.parse_args()
    if a.cmd == "estimate":
        print(json.dumps(estimate(), indent=2, ensure_ascii=False))
    elif a.cmd == "summary":
        print(json.dumps(summary(a.file), indent=2, ensure_ascii=False))
    else:
        run(a.max_spend)


if __name__ == "__main__":
    main()
