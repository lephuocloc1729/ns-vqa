"""Engine-only replay of the phase-4.5 dev run (owner, 2026-11-17; stage A step 6). No API call.

Re-runs the rule engine with the current code on the dev run's stored scenes and parses
(`eval/runs/e2e/dev_frozen_13ded0d75451.jsonl`), applies the fallback trigger, and reports
the rules-only figures: decided coverage, accuracy on decided, and overall with every
non-decided question counted wrong.

Grades:
- an answer whose decision (verdict and value) is the one the dev run stored keeps its
  stored grade (the judge's, or the Yes/No mapping);
- a changed or newly decided answer has no judge grade without a paid call. It gets a
  **provisional grade** from `eval/runs/e2e/dev_provisional_grades.json` (local; graded
  by the assistant against the dataset answer, keyed by question id and decision hash),
  else it is listed as ungraded and left out of accuracy (and counted wrong in overall).
  A paid dev run with the judge confirms them later.

    .venv/bin/python eval/dev_replay.py [--label step] [--changed] [--programs FILE] [--scenes FILE]

`--programs` (phase 4.5 stage B): a local JSON file {question id: QueryProgram} of hand-written
programs in the form parser v7 is meant to produce, used in place of the stored parse for those
ids. Indicative only (they are not parses); the stored-parse replay stays the guardrail.
`--scenes`: a local JSON file {question id: {"guide_boards": [...]}} merged into the stored
scenes (B6 board readings from the guide trial), also indicative.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_eval as ee  # noqa: E402
from eval import gold_signs as gs  # noqa: E402

DEV_RUN = ROOT / "eval" / "runs" / "e2e" / "dev_frozen_13ded0d75451.jsonl"
PROVISIONAL = ROOT / "eval" / "runs" / "e2e" / "dev_provisional_grades.json"
DECIDED = ("yes", "no", "value")


# Added fields that don't change what an answer decides (they only name things): ignored
# when comparing with the stored decision. `group_vi` (rank 1) names the art. 11 group.
ADDED_FIELDS = ("group_vi",)


def _strip(v):
    if isinstance(v, dict):
        return {k: _strip(x) for k, x in v.items() if k not in ADDED_FIELDS}
    if isinstance(v, list):
        return [_strip(x) for x in v]
    return v


def decision(ans) -> str:
    v = {"verdict": ans.verdict.value, "value": _strip(ans.value)} if ans is not None else None
    return hashlib.sha256(json.dumps(v, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()[:12]


def stored_decision(rec: dict) -> str:
    ea = rec.get("engine_answer")
    v = {"verdict": ea["verdict"], "value": _strip(ea.get("value"))} if ea else None
    return hashlib.sha256(json.dumps(v, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()[:12]


def replay(engine=None, dev_run: Path = DEV_RUN, provisional: Path = PROVISIONAL,
           programs: dict[str, Any] | None = None, scenes: dict[str, Any] | None = None) -> dict[str, Any]:
    from vqa.answer.fallback import trigger
    from vqa.reasoning.engine import Engine, EngineError
    from vqa.schemas import QueryProgram, SceneGraph

    engine = engine or Engine()
    _, rows = ee.load(dev_run)
    prov = json.loads(provisional.read_text(encoding="utf-8")) if provisional.exists() else {}
    gold = {q["id"]: q for q in json.loads(gs.TRAIN_QA.read_text(encoding="utf-8"))}
    out_rows, n_dec, right, graded, ungraded, changed = [], 0, 0.0, 0, [], []
    for r in rows:
        p = (r["trace"].get("parser") or {})
        if programs and r["id"] in programs:
            p = {"status": "ok", "program": programs[r["id"]]}
        prog = QueryProgram.model_validate(p["program"]) if p.get("program") else None
        sd = r.get("scene")
        if sd and scenes and r["id"] in scenes:
            sd = {**sd, **scenes[r["id"]]}
        scene = SceneGraph.model_validate(sd) if sd else None
        ans, err = None, False
        if scene is not None and p.get("status") == "ok":
            try:
                ans = engine.answer(scene, prog)
            except EngineError:
                err = True
        why = trigger(scene_ok=scene is not None, parse_status=p.get("status"), answer=ans, engine_error=err)
        decided = why is None and ans is not None and ans.verdict.value in DECIDED
        d = decision(ans)
        same = (not decided and not r["decided"]) or (decided and r["decided"] and d == stored_decision(r))
        grade = None
        if decided:
            n_dec += 1
            if (g := prov.get(r["id"])) and g.get("decision") == d:
                grade = g["grade"]
            elif same and r["correct"] is not None:
                grade = r["correct"]
            if grade is None:
                ungraded.append(r["id"])
            else:
                graded += 1
                right += grade
        if not same:
            changed.append({"id": r["id"], "was": {"decided": r["decided"], "trigger": r["trigger"],
                                                   "verdict": r["engine_verdict"], "grade": r["correct"]},
                            "now": {"decided": decided, "trigger": why,
                                    "verdict": ans.verdict.value if ans else None,
                                    "value": ans.value if ans else None, "note": ans.note if ans else None,
                                    "decision": d, "grade": grade},
                            "question": gold[r["id"]]["question"], "answer": gold[r["id"]]["answer"]})
        out_rows.append({"id": r["id"], "decided": decided, "trigger": why, "grade": grade})
    n = len(rows)
    from collections import Counter
    return {"questions": n, "decided": n_dec, "coverage": n_dec / n,
            "accuracy_on_decided": right / graded if graded else None, "graded": graded,
            "ungraded_decided": ungraded,
            "overall_non_decided_wrong": right / n,
            "not_decided_by_cause": dict(Counter(x["trigger"] for x in out_rows if not x["decided"])),
            "changed": changed}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="")
    ap.add_argument("--changed", action="store_true")
    ap.add_argument("--programs", type=Path)
    ap.add_argument("--scenes", type=Path)
    a = ap.parse_args()
    load = lambda f: json.loads(f.read_text(encoding="utf-8")) if f else None  # noqa: E731
    rep = replay(programs=load(a.programs), scenes=load(a.scenes))
    head = {k: v for k, v in rep.items() if k != "changed"}
    print(json.dumps({"label": a.label, **head, "changed_count": len(rep["changed"])}, ensure_ascii=False, default=str))
    if a.changed:
        for c in rep["changed"]:
            print(json.dumps(c, ensure_ascii=False, default=str)[:1200])


if __name__ == "__main__":
    main()
