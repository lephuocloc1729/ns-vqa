"""Phase 4.8 proof replay (owner, 2026-11-18). Free: no API call.

Every question of dev (the judged phase-4.7 candidate, `dev_rejudge_f1f0ba0d2f8c`: parser v14
programs on scene v5) and of dev2 (the baseline, `dev2_baseline_9a403f66bb06`) runs through
today's engine (reading policy A, the KB's field switch and phase-4.8 switches) on its stored
scene and program. `baseline` stores the answers once, at the commit before the phase-4.8 engine
changes; `check` compares: a decided answer must be identical (verdict, value, citations) unless
listed as an intended change.

    .venv/bin/python eval/phase48_replay.py baseline   # at the commit before the changes
    .venv/bin/python eval/phase48_replay.py check

Records are local (`eval/runs/phase48/`, gitignored).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.phase47_replay import _record, compare  # noqa: E402

E2E = ROOT / "eval" / "runs" / "e2e"
RUNS = {"dev": E2E / "dev_rejudge_f1f0ba0d2f8c.jsonl", "dev2": E2E / "dev2_baseline_9a403f66bb06.jsonl"}
OUT = ROOT / "eval" / "runs" / "phase48"
BASELINE = OUT / "baseline.json"
# Decided answers the phase-4.8 fixes change on purpose (docs/status.md). `check` fails on any other.
INTENDED = {"dev2:train_121", "dev2:train_466", "dev2:train_502", "dev2:train_516"}
# A1, the confusable table (switch confusable_pairs): decided -> unknown where the partner reading differs.
INTENDED |= {"dev:train_222", "dev2:train_119", "dev2:train_131", "dev2:train_135", "dev2:train_347",
             "dev2:train_410", "dev2:train_448", "dev2:train_495", "dev2:train_527"}


def _rows(p: Path) -> list[dict]:
    return [json.loads(line) for line in Path(p).read_text(encoding="utf-8").splitlines()[1:] if line.strip()]


def replay(runs: dict[str, Path] | None = None, **engine_kw) -> dict[str, dict]:
    from vqa.answer.fallback import trigger
    from vqa.reasoning.engine import Engine, EngineError
    from vqa.schemas import QueryProgram, SceneGraph
    eng = Engine(reading_policy="higher_confidence", **engine_kw)
    out = {}
    for name, path in (runs or RUNS).items():
        for r in _rows(path):
            key = f"{name}:{r['id']}"
            p = (r.get("trace") or {}).get("parser") or {}
            if not r.get("scene"):
                out[key] = _record(None, "perception_failed")
                continue
            if not p.get("program"):
                out[key] = _record(None, "parse_failed")
                continue
            q = QueryProgram.model_validate(p["program"])
            if q.out_of_scope:
                out[key] = _record(None, "out_of_scope")
                continue
            scene = SceneGraph.model_validate(r["scene"])
            try:
                ans, err = eng.answer(scene, q), False
            except EngineError:
                ans, err = None, True
            out[key] = _record(ans, trigger(scene_ok=True, parse_status="ok", answer=ans, engine_error=err))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["baseline", "check"])
    ap.add_argument("--several-signs", choices=["on", "off"], help="override kb/switches_48.yaml")
    ap.add_argument("--confusable-pairs", choices=["on", "off"], help="override kb/switches_48.yaml")
    a = ap.parse_args()
    kw = {} if a.several_signs is None else {"several_signs": a.several_signs == "on"}
    if a.confusable_pairs is not None:
        kw["confusable_pairs"] = a.confusable_pairs == "on"
    now = replay(**kw)
    OUT.mkdir(parents=True, exist_ok=True)
    if a.cmd == "baseline":
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                cwd=ROOT).stdout.strip()
        BASELINE.write_text(json.dumps({"commit": commit, "answers": now}, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        print(json.dumps({"commit": commit, "questions": len(now), "decided": sum(v["decided"] for v in now.values())}))
        return
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    r = compare(base["answers"], now)
    r["baseline_commit"] = base["commit"]
    r["unintended"] = [k for k in r["decided_changed"] if k not in INTENDED]
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(1 if r["unintended"] else 0)


if __name__ == "__main__":
    main()
