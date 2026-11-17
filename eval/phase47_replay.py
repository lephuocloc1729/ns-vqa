"""Phase 4.7 proof replay (owner, 2026-11-17: additive only). Free: no API call.

After each step, every question of dev (stored v11 programs on the stored scenes of
`dev_reparse_v11_f52e160181ca`) and of D3's cached-scene questions (stored v9 programs plus the
phase-4.6 hand programs `d3_v10_handprograms.json`, the forms v11 parses; cache-only scenes) runs
through today's engine. An answer that was decided in the baseline must be identical: verdict,
value and citations. Only answers that were undecided may change.

    .venv/bin/python eval/phase47_replay.py baseline   # once, at the commit before any change
    .venv/bin/python eval/phase47_replay.py check      # after each step: identical / changed counts
    .venv/bin/python eval/phase47_replay.py check --programs dev=<json> d3=<json>   # step 3: v12 hand programs

Records are local (`eval/runs/phase47/`, gitignored).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

E2E = ROOT / "eval" / "runs" / "e2e"
DEV_RUN = E2E / "dev_reparse_v11_f52e160181ca.partial.jsonl"
D3_RUN = ROOT / "eval" / "runs" / "trainset" / "trainset_yesno_821164d62679.jsonl"
D3_HAND = ROOT / "eval" / "runs" / "trainset" / "d3_v10_handprograms.json"
OUT = ROOT / "eval" / "runs" / "phase47"
BASELINE = OUT / "baseline.json"
DECIDED = ("yes", "no", "value")


def _rows(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()[1:] if line.strip()]


def _hand(path: Path | None) -> dict:
    if path is None or not Path(path).exists():
        return {}
    from vqa.parsing.wire import from_wire, to_query
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: to_query(from_wire(v), 2025) for k, v in d.items() if not k.startswith("_")}


def _record(ans, why) -> dict:
    if ans is None:
        return {"decided": False, "trigger": why}
    cites = sorted({(c.law_id, c.article_id) for c in ans.citations})
    return {"decided": why is None and ans.verdict.value in DECIDED, "trigger": why,
            "verdict": ans.verdict.value,
            "value": json.loads(json.dumps(ans.value, default=str, ensure_ascii=False, sort_keys=True)),
            "citations": [list(c) for c in cites]}


def _items(dev_programs: Path | None = None, d3_programs: Path | None = None):
    """(key, scene, program) for every replayed question."""
    from vqa.schemas import QueryProgram, SceneGraph
    hand = _hand(dev_programs)
    for r in _rows(DEV_RUN):
        p = (r.get("trace") or {}).get("parser") or {}
        q = hand.get(r["id"])
        if q is None and p.get("status") == "ok" and p.get("program"):
            q = QueryProgram.model_validate(p["program"])
        if q is None and p.get("status") == "out_of_scope" and p.get("program"):
            q = QueryProgram.model_validate(p["program"])
        yield "dev:" + r["id"], SceneGraph.model_validate(r["scene"]) if r.get("scene") else None, q
    from eval import e2e_trainset as et
    from eval import freeze
    from eval import gold_signs as gs
    from vqa.pipeline import Pipeline
    pipe = Pipeline(freeze.pipeline_config("phase45", "claude-haiku-5-5", cache_only=True, answer_fallback=False,
                                           reading_policy="higher_confidence"))
    hand3 = {**_hand(D3_HAND), **_hand(d3_programs)}
    for r in _rows(D3_RUN):
        if not (r.get("scene") or {}).get("cached"):
            continue
        scene, _ = et._scene(pipe, gs.image_path(r["image_id"], "train"))
        q = hand3.get(r["id"]) or (QueryProgram.model_validate(r["program"]) if r.get("program") else None)
        yield "d3:" + r["id"], scene, q


def replay(dev_programs: Path | None = None, d3_programs: Path | None = None) -> dict[str, dict]:
    from vqa.answer.fallback import trigger
    from vqa.reasoning.engine import Engine, EngineError
    eng = Engine(reading_policy="higher_confidence")
    out = {}
    for key, scene, q in _items(dev_programs, d3_programs):
        if scene is None:
            out[key] = _record(None, "perception_failed")
            continue
        if q is None:
            out[key] = _record(None, "parse_failed")
            continue
        if q.out_of_scope:
            out[key] = _record(None, "out_of_scope")
            continue
        try:
            ans, err = eng.answer(scene, q), False
        except EngineError:
            ans, err = None, True
        out[key] = _record(ans, trigger(scene_ok=True, parse_status="ok", answer=ans, engine_error=err))
    return out


def compare(base: dict, now: dict) -> dict:
    keys = ("verdict", "value", "citations")
    identical, broken, changed_undecided, same_undecided = [], [], [], []
    for k, b in base.items():
        n = now.get(k)
        if b["decided"]:
            if n is not None and n["decided"] and all(n.get(x) == b.get(x) for x in keys):
                identical.append(k)
            else:
                broken.append(k)
        elif n is not None and (n["decided"] or n.get("verdict") != b.get("verdict") or n.get("value") != b.get("value")):
            changed_undecided.append({"q": k, "was": b.get("trigger"), "now": n.get("trigger") or n.get("verdict")})
        else:
            same_undecided.append(k)
    return {"baseline_decided": sum(b["decided"] for b in base.values()), "identical": len(identical),
            "decided_changed": broken, "undecided_changed": changed_undecided,
            "undecided_same": len(same_undecided),
            "now_decided": sum(n["decided"] for n in now.values()), "questions": len(base)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["baseline", "check"])
    ap.add_argument("--programs", nargs="*", default=[], help="dev=<json> d3=<json> (hand programs)")
    a = ap.parse_args()
    progs = dict(x.split("=", 1) for x in a.programs)
    OUT.mkdir(parents=True, exist_ok=True)
    now = replay(Path(progs["dev"]) if "dev" in progs else None, Path(progs["d3"]) if "d3" in progs else None)
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
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(1 if r["decided_changed"] else 0)


if __name__ == "__main__":
    main()
