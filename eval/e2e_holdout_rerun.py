"""The paired re-run check on public_holdout (docs/plans/rerun-removal.md, R2). Aggregate only.

One run, owner-approved (2026-11-19, H0 lifted for this run alone). Two arms on the same
questions with the frozen phase49 system, answer fallback off (rules only):
- arm A: perception with the low-confidence re-run (the frozen behaviour);
- arm B: the same image without the re-run, rebuilt from the same temporary scene cache, so
  pass 1, tiles and the guide board are shared and only crops on boxes that exist in arm B
  alone are new calls.
The parser runs once per question and both arms use its program. A decided answer that both
arms give is written and judged once; a differing one is written and judged per arm.

It refuses to start unless:
- `--confirm` is given;
- the git working tree is clean;
- the live configuration equals `eval/frozen_phase49.json`, apart from `engine_code` (the code
  changed after the freeze: the parallel calls, `bd897a6`, and the `scene_rerun` switch; the
  hash is recorded in the report);
- it has never run: no sentinel `eval/holdout_rerun_ran.json` (written before the first call)
  and no `holdout_rerun_aggregate_*.json` in the runs folder.

Fresh perception: a new temporary scene cache, deleted afterwards. No question id, image id,
question text or per-question line is printed or written; the only file is the aggregate.

    .venv/bin/python eval/e2e_holdout_rerun.py estimate
    .venv/bin/python eval/e2e_holdout_rerun.py run --confirm --max-spend 1.0
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import math
import sys
import tempfile
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_eval as ee  # noqa: E402
from eval import e2e_holdout as eh  # noqa: E402
from eval import e2e_private as ep  # noqa: E402
from eval import freeze  # noqa: E402
from eval.report import duplicated_images  # noqa: E402

PROFILE = "phase49"
FROZEN = freeze.FROZEN_PHASE49
OUT = ROOT / "eval" / "runs" / "e2e"
SENTINEL = ROOT / "eval" / "holdout_rerun_ran.json"
DECIDED = ("yes", "no", "value")
ALLOWED_DIFFS = ("engine_code",)
# R4 estimate (docs/plans/rerun-removal.md): per item, from the usage log after 2026-11-17.
RATES = {"perception_per_image": 0.0031, "extra_crops_per_image": 0.0002, "parser_per_question": 0.0037,
         "parser_cold_write": 0.05, "writer_per_answer": 0.0003, "judge_per_natural_qa": 0.0067}


# ---------------------------------------------------------------- guards

def guards(*, out_dir: Path = OUT, sentinel: Path = SENTINEL, frozen: Path = FROZEN, git=freeze.git_state) -> dict:
    g = git()
    if not g["clean"]:
        raise SystemExit("the git working tree is not clean: commit or remove these first:\n  " + "\n  ".join(g["dirty"]))
    rec = freeze.load(frozen)
    if freeze.profile_of(rec) != PROFILE:
        raise SystemExit(f"{Path(frozen).name} is not the {PROFILE} record")
    if d := [x for x in freeze.check(frozen, rec["pipeline_config"]["perception_model"])
             if not x.startswith(ALLOWED_DIFFS)]:
        raise SystemExit("the live configuration differs from the freeze record:\n  " + "\n  ".join(d))
    if Path(sentinel).exists():
        raise SystemExit(f"the paired re-run check has already run ({Path(sentinel).name}); it runs once")
    if Path(out_dir).exists() and any(Path(out_dir).glob("holdout_rerun_aggregate_*.json")):
        raise SystemExit(f"a holdout_rerun aggregate file already exists in {out_dir}; it runs once")
    return g


# ---------------------------------------------------------------- one question, one arm

def engine_answer(pipe, scene, parse, question: str):
    """The rules' answer on one scene, as Pipeline.answer decides it (fallback off)."""
    from vqa.answer.asked import prune_unasked
    from vqa.answer.fallback import trigger
    from vqa.reasoning.engine import EngineError
    ans, err = None, False
    if scene is not None and parse.status == "ok":
        try:
            ans = prune_unasked(pipe.engine.answer(scene, parse.query), question)
        except EngineError:
            err = True
    why = trigger(scene_ok=scene is not None, parse_status=parse.status if scene is not None else None,
                  answer=ans, engine_error=err)
    decided = why is None and ans is not None and ans.verdict.value in DECIDED
    key = json.dumps([ans.verdict.value, ans.value], sort_keys=True, default=str) if ans is not None else None
    return {"answer": ans, "trigger": why, "decided": decided, "key": key}


def mcnemar_exact(b: int, c: int) -> float | None:
    """Two-sided exact McNemar p on the discordant pairs (b: only A right, c: only B right)."""
    n = b + c
    if n == 0:
        return None
    k = min(b, c)
    p = 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, p)


def paired(rows: list[dict]) -> dict[str, Any]:
    ra = sum(r["A"]["correct"] or 0 for r in rows if r["A"]["decided"])
    rb = sum(r["B"]["correct"] or 0 for r in rows if r["B"]["decided"])
    only_a = sum((r["A"]["correct"] == 1.0) and not (r["B"]["correct"] == 1.0) for r in rows)
    only_b = sum((r["B"]["correct"] == 1.0) and not (r["A"]["correct"] == 1.0) for r in rows)
    return {"answers_changed": sum(r["changed"] for r in rows),
            "decided_A": sum(r["A"]["decided"] for r in rows), "decided_B": sum(r["B"]["decided"] for r in rows),
            "correct_A": ra, "correct_B": rb, "net_correct_B_minus_A": rb - ra,
            "fully_right_only_A": only_a, "fully_right_only_B": only_b,
            "mcnemar_exact_p": mcnemar_exact(only_a, only_b)}


def decision(p: dict[str, Any]) -> dict[str, Any]:
    """R3, fixed before the run (owner, 2026-11-19)."""
    net_ok = p["net_correct_B_minus_A"] >= -1
    dec_ok = p["decided_B"] >= p["decided_A"] - 1
    return {"rule": "adopt B if net correct (B - A) >= -1 and decided(B) >= decided(A) - 1",
            "net_ok": net_ok, "decided_ok": dec_ok, "adopt_no_rerun": net_ok and dec_ok}


def arm_report(records: list[dict]) -> dict[str, Any]:
    dup = duplicated_images("public")
    nd = [r for r in records if r["image_id"] not in dup]
    return {**ep._rules_figs(records),
            "by_question_type": {t: ep._rules_figs([r for r in records if r["question_type"] == t])
                                 for t in sorted({r["question_type"] for r in records})},
            "by_images": {"split": "public_holdout", "against": ["train"],
                          "non_duplicate_images": ep._rules_figs(nd),
                          "duplicate_images": ep._rules_figs([r for r in records if r["image_id"] in dup])}}


# ---------------------------------------------------------------- the run

class _Timed:
    """Times the perception client's calls by purpose (the re-run's own seconds and cost)."""

    def __init__(self, client):
        self.client, self.by = client, defaultdict(lambda: {"calls": 0, "seconds": 0.0, "cost_usd": 0.0})

    def __getattr__(self, name):
        return getattr(self.client, name)

    def json_reply(self, **kw):
        t0 = time.monotonic()
        res = None
        try:
            res = self.client.json_reply(**kw)
            return res
        finally:
            b = self.by[kw.get("purpose", "")]
            b["calls"] += 1
            b["seconds"] += time.monotonic() - t0
            b["cost_usd"] += getattr(res, "cost_usd", 0.0) if res is not None else 0.0


def run(max_spend: float, *, confirm: bool = False, sdk=None, questions: list[dict] | None = None,
        out_dir: Path = OUT, image_path=None, sentinel: Path = SENTINEL, frozen: Path = FROZEN,
        git=freeze.git_state) -> Path:
    if not confirm:
        raise SystemExit("the paired re-run check runs once (owner, 2026-11-19): pass --confirm")
    g = guards(out_dir=out_dir, sentinel=sentinel, frozen=frozen, git=git)
    rec = freeze.load(frozen)
    perception_model = rec["pipeline_config"]["perception_model"]
    run_id = uuid.uuid4().hex[:12]
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    mark = {"what": "the one paired re-run check on public_holdout (docs/plans/rerun-removal.md); blocks a second run",
            "run_id": run_id, "started": started, "git_commit": g["commit"], "status": "started",
            "frozen_record_sha256": hashlib.sha256(Path(frozen).read_bytes()).hexdigest()}
    Path(sentinel).write_text(json.dumps(mark, indent=2) + "\n", encoding="utf-8")

    from eval.judge import Judge
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.pipeline import Pipeline

    qs = questions if questions is not None else eh.load_questions()
    image_path = image_path or eh.image_file
    by_image: dict[str, list[dict]] = defaultdict(list)
    for q in qs:
        by_image[q["image_id"]].append(q)
    guard = SpendGuard(max_spend)
    rows: list[dict] = []
    seconds_a = 0.0
    with tempfile.TemporaryDirectory(prefix="vqa_holdout_rerun_") as tmp:
        cfg = freeze.pipeline_config(PROFILE, perception_model, cache_dir=Path(tmp), cache_only=False,
                                     answer_fallback=False)
        pipe = Pipeline(cfg, sdk=sdk, guard=guard)
        timed = _Timed(pipe._perception_client)
        pipe._perception_client = timed
        judge = Judge(llm=LLMClient(model="claude-opus-5-5", guard=guard, sdk=sdk))
        n = 0
        for image_id, group in by_image.items():
            img = image_path(image_id)
            t0 = time.monotonic()
            res_a, _ = pipe._perceive(img, rerun=True)
            seconds_a += time.monotonic() - t0
            res_b, _ = pipe._perceive(img, rerun=False)
            scene_a = res_a.scene if res_a.ok else None
            scene_b = res_b.scene if res_b.ok else None
            for q in group:
                n += 1
                parse = pipe.parser.parse(q["question"])
                arms = {"A": engine_answer(pipe, scene_a, parse, q["question"]),
                        "B": engine_answer(pipe, scene_b, parse, q["question"])}
                same = arms["A"]["decided"] == arms["B"]["decided"] and arms["A"]["key"] == arms["B"]["key"]
                graded: dict[str, dict] = {}
                for k, scene in (("A", scene_a), ("B", scene_b)):
                    if not arms[k]["decided"]:
                        graded[k] = {"correct": None, "strict": None}
                    elif k == "B" and same:
                        graded[k] = graded["A"]
                    else:
                        w = pipe.writer.write(q["question"], arms[k]["answer"], scene)
                        graded[k] = ee.grade(q, w.text, judge)
                row = {"changed": not same}
                for k in ("A", "B"):
                    row[k] = {"image_id": image_id, "question_type": q["question_type"],
                              "decided": arms[k]["decided"], "trigger": arms[k]["trigger"],
                              "correct": graded[k]["correct"], "strict": graded[k]["strict"]}
                rows.append(row)
                del arms, graded, parse
                print(f"[{n}/{len(qs)}]  spent ${guard.spent:.4f}")        # a counter only
    pr = paired(rows)
    rerun = dict(timed.by.get("scene rerun", {"calls": 0, "seconds": 0.0, "cost_usd": 0.0}))
    report = {"what": "public_holdout paired re-run check, aggregate only (docs/plans/rerun-removal.md)",
              "run_id": run_id, "profile": PROFILE, "perception_model": perception_model,
              "questions": len(qs), "images": len(by_image), "started": started,
              "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "git_commit": g["commit"], "frozen_record": Path(frozen).name,
              "engine_code_live": freeze.code_hash(), "answer_fallback": False,
              "spent_usd": round(guard.spent, 4),
              "arm_A_with_rerun": arm_report([r["A"] for r in rows]),
              "arm_B_without_rerun": arm_report([r["B"] for r in rows]),
              "paired": pr, "decision_R3": decision(pr),
              "rerun_calls": {**rerun, "per_image_seconds": rerun["seconds"] / len(by_image) if by_image else None,
                              "share_of_arm_A_perception_seconds": rerun["seconds"] / seconds_a if seconds_a else None},
              "perception_calls_by_purpose": {k: dict(v) for k, v in timed.by.items()}}
    rows.clear()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"holdout_rerun_aggregate_{run_id}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    mark.update(status="finished", finished=report["finished"], report=out.name, spent_usd=report["spent_usd"])
    Path(sentinel).write_text(json.dumps(mark, indent=2) + "\n", encoding="utf-8")
    print(f"aggregate report -> {out}")
    return out


def estimate(questions: list[dict] | None = None) -> dict[str, Any]:
    """R4: counts only (no text is read beyond question types and image ids)."""
    qs = questions if questions is not None else eh.load_questions()
    images = len({q["image_id"] for q in qs})
    nqa = sum(q["question_type"] != "Yes/No" for q in qs)
    r = RATES
    items = {"perception": images * r["perception_per_image"], "extra_crops": images * r["extra_crops_per_image"],
             "parser": len(qs) * r["parser_per_question"] + r["parser_cold_write"],
             "writer": len(qs) * 1.2 * r["writer_per_answer"], "judge": nqa * 1.2 * r["judge_per_natural_qa"]}
    return {"questions": len(qs), "images": images, "natural_qa": nqa,
            "items_usd": {k: round(v, 3) for k, v in items.items()}, "total_usd": round(sum(items.values()), 3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estimate")
    r = sub.add_parser("run")
    r.add_argument("--confirm", action="store_true")
    r.add_argument("--max-spend", type=float, required=True)
    a = ap.parse_args()
    if a.cmd == "estimate":
        print(json.dumps(estimate(), indent=2))
    else:
        run(a.max_spend, confirm=a.confirm)


if __name__ == "__main__":
    main()
