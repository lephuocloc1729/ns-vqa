"""The one public_holdout run (docs/plans/phase-4.md, procedure step 6). Aggregate only.

- Run once, after the freeze (step 5), with the frozen configuration. It refuses
  to start (owner, 2026-11-16) unless:
  - `--confirm-frozen` is given;
  - the git working tree is clean;
  - the live configuration and prompt ids equal `eval/frozen_phase4.json`
    (`eval/freeze.py`);
  - it has never run: no sentinel `eval/holdout_ran.json` (committed after the run)
    and no aggregate file in the runs folder.
  The sentinel is written before the first call, so a run that stops part way also
  counts as the one run.
- Fresh perception: a new, empty scene cache in a temporary directory that is
  deleted afterwards, so every call is independent and no holdout scene is kept.
- No per-question line is printed or written. Each answer's grade is kept in
  memory only long enough to sum it, and the per-question records are dropped;
  the only file written is the aggregate report (no question or image ids).

    .venv/bin/python eval/e2e_holdout.py --confirm-frozen --perception-model claude-haiku-5-5 --max-spend 2
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_eval as ee  # noqa: E402
from eval import freeze  # noqa: E402
from eval import gold_signs as gs  # noqa: E402
from eval import parser_eval as pev  # noqa: E402

HALF = "public_holdout"
OUT = ROOT / "eval" / "runs" / "e2e"
SENTINEL = ROOT / "eval" / "holdout_ran.json"
# Fields of a per-question record that the aggregate needs. Nothing that identifies
# a question (id, text, answer) is kept, except the image id until the
# duplicate split is computed.
_KEEP = ("image_id", "question_type", "correct", "strict", "trigger", "writer_status", "verdict",
         "engine_verdict", "fallback_status", "judge_label", "cost_usd", "judge_cost_usd", "seconds")


def load_questions(public_file: Path | None = None, split_file: Path | None = None) -> list[dict]:
    split = json.loads((split_file or pev.SPLIT_FILE).read_text(encoding="utf-8"))
    ids = set(split[HALF]["questions"])
    rows = json.loads((public_file or pev.PUBLIC_FILE).read_text(encoding="utf-8"))
    return [{k: q[k] for k in ("id", "question", "image_id", "question_type", "answer")}
            for q in rows if q["id"] in ids]


def aggregate(records: list[dict]) -> dict[str, Any]:
    """ee.summarize gives aggregates only (counts, means, the duplicate split with a CI)."""
    return ee.summarize(records)


def guards(perception_model: str, *, out_dir: Path = OUT, sentinel: Path = SENTINEL,
           frozen: Path = freeze.FROZEN, git=freeze.git_state) -> dict:
    """Refuses (SystemExit) unless the tree is clean, the configuration is the frozen
    one and the holdout has never run. Returns the git state."""
    g = git()
    if not g["clean"]:
        raise SystemExit("the git working tree is not clean: commit or remove these first:\n  "
                         + "\n  ".join(g["dirty"]))
    if d := freeze.check(frozen, perception_model):
        raise SystemExit("the live configuration differs from the freeze record:\n  " + "\n  ".join(d))
    if Path(sentinel).exists():
        raise SystemExit(f"the holdout has already run ({Path(sentinel).name}); it runs once")
    if Path(out_dir).exists() and any(Path(out_dir).glob("holdout_aggregate_*.json")):
        raise SystemExit(f"a holdout aggregate file already exists in {out_dir}; it runs once")
    return g


def run_holdout(max_spend: float, *, perception_model: str, confirm_frozen: bool = False, sdk=None,
                questions: list[dict] | None = None, out_dir: Path = OUT, image_path=None,
                sentinel: Path = SENTINEL, frozen: Path = freeze.FROZEN, git=freeze.git_state) -> Path:
    if not confirm_frozen:
        raise SystemExit("the holdout runs once, after the freeze: pass --confirm-frozen")
    g = guards(perception_model, out_dir=out_dir, sentinel=sentinel, frozen=frozen, git=git)
    config = freeze.live(perception_model)
    run_id = uuid.uuid4().hex[:12]
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    mark = {"what": "the one public_holdout run (procedure step 6); its existence blocks a second run",
            "run_id": run_id, "started": started, "git_commit": g["commit"], "status": "started",
            "frozen_record_sha256": hashlib.sha256(Path(frozen).read_bytes()).hexdigest()}
    Path(sentinel).write_text(json.dumps(mark, indent=2) + "\n", encoding="utf-8")
    from eval.judge import Judge
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.pipeline import Pipeline, PipelineConfig

    qs = questions if questions is not None else load_questions()
    image_path = image_path or (lambda i: gs.image_path(i, HALF))
    guard = SpendGuard(max_spend)
    records: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="vqa_holdout_cache_") as tmp:
        pipe = Pipeline(PipelineConfig(perception_model=perception_model, cache_dir=Path(tmp), cache_only=False),
                        sdk=sdk, guard=guard)
        judge = Judge(llm=LLMClient(model="claude-opus-5-5", guard=guard, sdk=sdk))
        for n, q in enumerate(qs, 1):
            a = pipe.answer(image_path(q["image_id"]), q["question"])
            t = a.trace
            rec = {"image_id": q["image_id"], "question_type": q["question_type"], "verdict": a.verdict,
                   "trigger": t["fallback"]["trigger"], "fallback_status": t["fallback"].get("status"),
                   "writer_status": (t.get("writer") or {}).get("status"),
                   "engine_verdict": (t.get("engine") or {}).get("verdict"),
                   "cost_usd": a.cost_usd, "seconds": a.seconds}
            rec.update(ee.grade(q, a.text, judge))
            records.append({k: rec.get(k) for k in _KEEP})
            del a, t, rec
            print(f"[{n}/{len(qs)}]  spent ${guard.spent:.4f}")        # a counter only
    report = {"what": "public_holdout, aggregate only (procedure step 6)", "run_id": run_id,
              "perception_model": perception_model, "questions": len(qs), "started": started,
              "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "git_commit": g["commit"], "frozen_config": config,
              "prompt_ids": {k: v["id"] for k, v in config["prompts"].items()},
              "spent_usd": round(guard.spent, 4), **aggregate(records)}
    records.clear()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"holdout_aggregate_{report['run_id']}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    mark.update(status="finished", finished=report["finished"], report=out.name, spent_usd=report["spent_usd"])
    Path(sentinel).write_text(json.dumps(mark, indent=2) + "\n", encoding="utf-8")
    print(f"aggregate report -> {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm-frozen", action="store_true")
    ap.add_argument("--perception-model", required=True, choices=["claude-haiku-5-5", "claude-sonnet-5-5"])
    ap.add_argument("--max-spend", type=float, required=True)
    a = ap.parse_args()
    run_holdout(a.max_spend, perception_model=a.perception_model, confirm_frozen=a.confirm_frozen)


if __name__ == "__main__":
    main()
