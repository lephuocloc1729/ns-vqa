"""The one public_holdout run (docs/plans/phase-4.md, procedure step 6). Aggregate only.

- Run once, after the freeze (step 5), with the frozen configuration. It refuses
  to start without `--confirm-frozen`.
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
from eval import gold_signs as gs  # noqa: E402
from eval import parser_eval as pev  # noqa: E402

HALF = "public_holdout"
OUT = ROOT / "eval" / "runs" / "e2e"
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


def run_holdout(max_spend: float, *, perception_model: str, confirm_frozen: bool = False, sdk=None,
                questions: list[dict] | None = None, out_dir: Path = OUT, image_path=None) -> Path:
    if not confirm_frozen:
        raise SystemExit("the holdout runs once, after the freeze: pass --confirm-frozen")
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
    report = {"what": "public_holdout, aggregate only (procedure step 6)", "run_id": uuid.uuid4().hex[:12],
              "perception_model": perception_model, "questions": len(qs),
              "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "spent_usd": round(guard.spent, 4), **aggregate(records)}
    records.clear()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"holdout_aggregate_{report['run_id']}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
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
