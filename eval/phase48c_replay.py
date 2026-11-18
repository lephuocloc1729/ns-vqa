"""Phase 4.8c free replay (owner, 2026-11-18). No API call.

Every question of dev and dev2, from the latest judged runs (parser v16 programs on scene v5:
`dev_reparse_v16_248e38bd215e`, `dev2_reparse_v16_c95f3934da5c`), runs through today's engine
(reading policy A, the KB's field switch) on its stored scene and program, then through the
`asked_only` pruning with its question text. The answer is compared with the one the run stored
(verdict and value, as the re-parse decides "changed"); every changed answer is listed.

`check` runs each phase-4.8c switch on its own (the others off), then all of them as the KB sets
them. With every new switch off the replay must change nothing: the new intents are additive.

    .venv/bin/python eval/phase48c_replay.py check

The output names question ids and verdicts only (no question text). Records stay local
(`eval/runs/phase48c/`, gitignored).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

E2E = ROOT / "eval" / "runs" / "e2e"
RUNS = {"dev": E2E / "dev_reparse_v16_248e38bd215e.jsonl", "dev2": E2E / "dev2_reparse_v16_c95f3934da5c.jsonl"}
OUT = ROOT / "eval" / "runs" / "phase48c"
SWITCHES = ("sign_charts", "one_sign_g1", "asked_only", "stated_exceptions")
OFF = {"sign_charts": False, "one_sign_g1": False, "stated_exceptions": False}


def _rows(p: Path) -> list[dict]:
    return [json.loads(line) for line in Path(p).read_text(encoding="utf-8").splitlines()[1:] if line.strip()]


def _questions() -> dict[str, str]:
    """Question text by key, for the pruning only (dev2's loader checks disjointness first)."""
    from eval import e2e_dev as ed
    from eval import e2e_dev2 as d2
    out = {f"dev:{q['id']}": q["question"] for q in ed.load_questions(with_answers=False)}
    out.update({f"dev2:{q['id']}": q["question"] for q in d2.load_questions(with_answers=False)})
    return out


def _key(verdict, value) -> str:
    return json.dumps({"verdict": verdict, "value": value}, sort_keys=True, default=str, ensure_ascii=False)


def replay(engine_kw: dict, asked_only: bool, runs: dict[str, Path] | None = None,
           questions: dict[str, str] | None = None) -> dict[str, dict]:
    """key -> {stored, now, changed, decided_before} for every question with a stored program."""
    from vqa.answer.asked import prune_unasked
    from vqa.answer.fallback import trigger
    from vqa.reasoning.engine import Engine, EngineError
    from vqa.schemas import QueryProgram, SceneGraph
    eng = Engine(reading_policy="higher_confidence", **engine_kw)
    qs = questions if questions is not None else _questions()
    out = {}
    for name, path in (runs or RUNS).items():
        for r in _rows(path):
            key = f"{name}:{r['id']}"
            p = (r.get("trace") or {}).get("parser") or {}
            if not r.get("scene") or not p.get("program"):
                continue
            q = QueryProgram.model_validate(p["program"])
            if q.out_of_scope:
                continue
            try:
                ans = prune_unasked(eng.answer(SceneGraph.model_validate(r["scene"]), q), qs.get(key, ""),
                                    on=asked_only)
                err = False
            except EngineError:
                ans, err = None, True
            ea = r.get("engine_answer") or {}
            now_v = ans.verdict.value if ans else None
            now_val = json.loads(json.dumps(ans.value, default=str)) if ans else None
            why = trigger(scene_ok=True, parse_status="ok", answer=ans, engine_error=err)
            out[key] = {"was": ea.get("verdict"), "now": now_v, "decided_before": bool(r.get("decided")),
                        "decided_now": why is None and now_v in ("yes", "no", "value"),
                        "correct_before": r.get("correct"),
                        "changed": _key(now_v, now_val) != _key(ea.get("verdict"), ea.get("value"))}
    return out


def changed(rep: dict[str, dict]) -> list[dict]:
    return [{"q": k, "was": v["was"], "now": v["now"], "decided": [v["decided_before"], v["decided_now"]],
             "correct_before": v["correct_before"]} for k, v in sorted(rep.items()) if v["changed"]]


def check() -> dict:
    qs = _questions()
    report = {"all_off": changed(replay(OFF, False, questions=qs))}
    for sw in SWITCHES:
        kw = dict(OFF)
        if sw in kw:
            kw.pop(sw)                   # this one from the KB, the others off
        report[sw] = changed(replay(kw, sw == "asked_only", questions=qs))
    report["all_on"] = changed(replay({}, True, questions=qs))
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check"])
    ap.parse_args()
    r = check()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "check.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(1 if r["all_off"] else 0)


if __name__ == "__main__":
    main()
