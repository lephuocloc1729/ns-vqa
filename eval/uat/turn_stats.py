"""Aggregate numbers on the answers given during the UAT, read from the API's database.

Prints aggregates only: no question text, photo or answer. Run it on the server inside the API
container, for one session window (UTC; the stored times are UTC):

    docker compose exec -T api python - --since 2026-11-26T01:00 --until 2026-11-26T11:00 \\
        < eval/uat/turn_stats.py

or locally against any database URL with --db.

Answers are also split by photo: the **first question ever asked on a photo** (its scene is read
fresh: the real wait) and **a photo seen before** (the fixed tasks' photos after the dry run, and
follow-ups; the scene comes from the cache). "Ever" looks at the whole database, not just the window. It imports only SQLAlchemy and the standard library,
so it runs in the API image, which has no eval/ folder.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from collections import Counter
from datetime import datetime

from sqlalchemy import DateTime, bindparam, create_engine, text


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _cache_hit(stages: object) -> bool:
    if isinstance(stages, str):
        try:
            stages = json.loads(stages)
        except ValueError:
            return False
    fb = stages.get("fallback") if isinstance(stages, dict) else None
    return bool(isinstance(fb, dict) and fb.get("cache_hit"))


def _window(sql: str):
    return text(sql).bindparams(bindparam("a", type_=DateTime()), bindparam("b", type_=DateTime()))


def collect(db_url: str, since: datetime, until: datetime) -> dict:
    since, until = (d.replace(tzinfo=None) for d in (since, until))   # stored as UTC without a zone
    eng = create_engine(db_url)
    with eng.connect() as c:
        turns = c.execute(_window(
            "SELECT id, session_id, status, verdict, answered_by, seconds, cost_usd, stages, image_sha256 "
            "FROM turn WHERE created_at >= :a AND created_at < :b"), {"a": since, "b": until}).all()
        # the first turn ever on each photo in the window (ties broken by id)
        first_ids = set(c.execute(_window(
            "SELECT t.id FROM turn t WHERE t.created_at >= :a AND t.created_at < :b AND NOT EXISTS ("
            "SELECT 1 FROM turn e WHERE e.image_sha256 = t.image_sha256 AND "
            "(e.created_at < t.created_at OR (e.created_at = t.created_at AND e.id < t.id)))"),
            {"a": since, "b": until}).scalars())
        fb = c.execute(_window(
            "SELECT f.turn_id, f.thumb, f.corrected_answer FROM feedback f JOIN turn t ON t.id = f.turn_id "
            "WHERE t.created_at >= :a AND t.created_at < :b ORDER BY f.created_at"),
            {"a": since, "b": until}).all()
    done = [t for t in turns if t.status == "done"]
    secs = [t.seconds for t in done if t.seconds is not None]
    by_route = Counter(t.answered_by or "none" for t in done)
    route_secs = {r: [t.seconds for t in done if (t.answered_by or "none") == r and t.seconds is not None]
                  for r in by_route}
    def _secs(ts):
        xs = [t.seconds for t in ts if t.seconds is not None]
        return {"n": len(xs), "p50": _pct(xs, 0.5), "p90": _pct(xs, 0.9)}
    by_photo = {"first_on_photo": _secs([t for t in done if t.id in first_ids]),
                "photo_seen_before": _secs([t for t in done if t.id not in first_ids])}
    last_fb: dict[str, tuple] = {}
    for f in fb:                     # the latest feedback per answer counts
        last_fb[f.turn_id] = (f.thumb, bool(f.corrected_answer))
    thumbs = Counter(v[0] or "none" for v in last_fb.values())
    up, down = thumbs.get("up", 0), thumbs.get("down", 0)
    return {
        "window_utc": [since.isoformat(), until.isoformat()],
        "conversations": len({t.session_id for t in turns}),
        "photos": len({t.image_sha256 for t in turns}),
        "questions": len(turns),
        "status": dict(Counter(t.status for t in turns)),
        "answered_by": dict(by_route),
        "verdict": dict(Counter(t.verdict or "none" for t in done)),
        "rag_cache_hits": sum(_cache_hit(t.stages) for t in done),
        "seconds": {"n": len(secs), "mean": statistics.fmean(secs) if secs else None,
                    "p50": _pct(secs, 0.5), "p90": _pct(secs, 0.9), "p95": _pct(secs, 0.95),
                    "max": max(secs) if secs else None},
        "seconds_by_photo": by_photo,
        "seconds_p50_by_route": {r: _pct(v, 0.5) for r, v in route_secs.items()},
        "cost_usd": {"total": sum(t.cost_usd or 0.0 for t in done),
                     "per_answer": statistics.fmean([t.cost_usd for t in done if t.cost_usd is not None])
                     if any(t.cost_usd is not None for t in done) else None},
        "feedback": {"answers_rated": len(last_fb), "up": up, "down": down,
                     "up_share": up / (up + down) if up + down else None,
                     "corrected": sum(v[1] for v in last_fb.values())},
    }


def format_report(s: dict) -> str:
    def f(x, unit="", nd=1):
        return "–" if x is None else f"{x:.{nd}f}{unit}"
    sec, cost, fb = s["seconds"], s["cost_usd"], s["feedback"]
    out = [f"# Answers during the UAT ({s['window_utc'][0]} – {s['window_utc'][1]} UTC)", "",
           f"- Questions: **{s['questions']}** in {s['conversations']} conversations on {s['photos']} photos; "
           f"status {s['status']}.",
           f"- Answered by: {s['answered_by']}; RAG cache hits: {s['rag_cache_hits']}.",
           f"- Verdicts: {s['verdict']}.",
           f"- Seconds per answer: mean {f(sec['mean'])}, **p50 {f(sec['p50'])}**, p90 {f(sec['p90'])}, "
           f"p95 {f(sec['p95'])}, max {f(sec['max'])} (n = {sec['n']}).",
           "- Seconds by photo: " + "; ".join(
               f"{label} p50 {f(s['seconds_by_photo'][k]['p50'])}, p90 {f(s['seconds_by_photo'][k]['p90'])} "
               f"(n = {s['seconds_by_photo'][k]['n']})"
               for k, label in (("first_on_photo", "**first question on a photo**"),
                                ("photo_seen_before", "photo seen before"))),
           "- Median seconds by route: " + ", ".join(f"{r} {f(v)}" for r, v in s["seconds_p50_by_route"].items()),
           f"- Claude API cost: ${f(cost['total'], nd=2)} in all, ${f(cost['per_answer'], nd=4)} per answer.",
           f"- In-app feedback: {fb['answers_rated']} answers rated, {fb['up']} up / {fb['down']} down"
           + (f" (**{100 * fb['up_share']:.0f}% up**)" if fb["up_share"] is not None else "")
           + f", {fb['corrected']} with a corrected answer.", ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", required=True, type=datetime.fromisoformat, help="UTC, e.g. 2026-11-26T01:00")
    ap.add_argument("--until", required=True, type=datetime.fromisoformat, help="UTC, exclusive")
    ap.add_argument("--db", default=os.environ.get("VQA_DATABASE_URL"),
                    help="SQLAlchemy URL (default: $VQA_DATABASE_URL, as in the API container)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    a = ap.parse_args(argv)
    if not a.db:
        raise SystemExit("no database: pass --db or set VQA_DATABASE_URL")
    s = collect(a.db, a.since, a.until)
    print(json.dumps(s, indent=2) if a.json else format_report(s))


if __name__ == "__main__":
    sys.exit(main())
