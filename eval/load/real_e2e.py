"""A small real end-to-end load run (checklist 3.2, part 3; owner's go-ahead 2026-11-25, cap $0.80).

The Locust runs (docs/results/load-test-*.md) used a fake pipeline, to measure our own system without Claude
calls. This run uses the real one: users ask at the same time, each with their own photo, a first question and
two follow-ups in one session, through the streaming endpoint. It reports time to the first event and to the
answer, the routes, errors and the cost.

Runs inside the API container on the server, which has the key and the code; it talks to the API directly
(http://127.0.0.1:8000), behind nginx's login:

    docker compose exec -T api python - --steps 5,10 --max-spend 0.80 < eval/load/real_e2e.py

Each user's photo is one of the server's uploaded photos with one corner pixel changed, so its hash is new and the
first question really reads it with the vision model (no scene cache). The run stops starting new questions once
the answers' own cost reaches the cap.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import statistics
import time
from pathlib import Path

import httpx
from PIL import Image

QUESTIONS = [
    "Biển báo trong ảnh có ý nghĩa gì?",
    "Xe ô tô có được đi vào đường này không?",
    "Còn xe máy thì sao?",
]


def variant(src: Path, n: int) -> bytes:
    """The photo with one corner pixel set from n: the same picture, a new hash (so no scene cache)."""
    im = Image.open(src).convert("RGB")
    im.putpixel((0, 0), (n % 256, (n // 256) % 256, 17))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


class Spend:
    def __init__(self, cap: float) -> None:
        self.cap, self.spent = cap, 0.0

    def ok(self) -> bool:
        return self.spent < self.cap


async def ask(client: httpx.AsyncClient, base: str, img: bytes, q: str, sid: str | None) -> dict:
    t0 = time.monotonic()
    rec: dict = {"question": q, "first_event_s": None, "answer_s": None, "ok": False}
    data = {"question": q, **({"session_id": sid} if sid else {})}
    try:
        async with client.stream("POST", f"{base}/v1/ask/stream", data=data,
                                 files={"image": ("p.png", img, "image/png")}, timeout=300) as r:
            r.raise_for_status()
            event = None
            async for line in r.aiter_lines():
                if line.startswith("event: "):
                    event = line[7:].strip()
                    if rec["first_event_s"] is None:
                        rec["first_event_s"] = time.monotonic() - t0
                elif line.startswith("data: ") and event in ("answer", "error", "turn"):
                    d = json.loads(line[6:])
                    if event == "turn":
                        rec["session_id"] = d.get("session_id")
                    elif event == "answer":
                        rec.update(ok=True, answer_s=time.monotonic() - t0, answered_by=d.get("answered_by"),
                                   cost_usd=d.get("cost_usd") or 0.0, understood=bool(d.get("understood_as")),
                                   cache_hit=(d.get("stages") or {}).get("perception", {}).get("cache_hit"))
                    else:
                        rec["error"] = str(d.get("error"))[:200]
    except Exception as e:                       # noqa: BLE001 — every failure is a result here
        rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return rec


async def user(i: int, photos: list[Path], base: str, spend: Spend, out: list[dict], step: int) -> None:
    img = variant(photos[i % len(photos)], step * 100 + i)
    sid = None
    async with httpx.AsyncClient() as client:
        for n, q in enumerate(QUESTIONS):
            if not spend.ok():
                return
            rec = await ask(client, base, img, q, sid)
            rec.update(step=step, user=i, n=n)
            sid = rec.get("session_id", sid)
            spend.spent += rec.get("cost_usd", 0.0) or 0.0
            out.append(rec)


def pct(xs: list[float], p: float) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return round(xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))], 2)


def summary(recs: list[dict], seconds: float) -> dict:
    ok = [r for r in recs if r["ok"]]
    first = [r for r in ok if r["n"] == 0]
    follow = [r for r in ok if r["n"] > 0]
    routes: dict[str, int] = {}
    for r in ok:
        routes[r.get("answered_by") or "?"] = routes.get(r.get("answered_by") or "?", 0) + 1
    return {
        "questions": len(recs), "answered": len(ok), "errors": len(recs) - len(ok),
        "wall_s": round(seconds, 1), "answers_per_min": round(60 * len(ok) / seconds, 1) if seconds else None,
        "first_event_p95_s": pct([r["first_event_s"] for r in recs], 0.95),
        "answer_s_first_question": {"p50": pct([r["answer_s"] for r in first], .5),
                                    "p95": pct([r["answer_s"] for r in first], .95),
                                    "mean": round(statistics.mean(r["answer_s"] for r in first), 2) if first else None},
        "answer_s_follow_ups": {"p50": pct([r["answer_s"] for r in follow], .5),
                                "p95": pct([r["answer_s"] for r in follow], .95),
                                "mean": round(statistics.mean(r["answer_s"] for r in follow), 2) if follow else None},
        "routes": routes, "follow_ups_rewritten": sum(1 for r in follow if r.get("understood")),
        "first_questions_read_fresh": sum(1 for r in first if r.get("cache_hit") is False),
        "cost_usd": round(sum(r.get("cost_usd", 0.0) or 0.0 for r in ok), 4),
        "error_samples": [r.get("error") for r in recs if not r["ok"]][:3],
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--photos", default="/app/var/uploads")
    ap.add_argument("--steps", default="5,10", help="users at once, one step after the other")
    ap.add_argument("--max-spend", type=float, required=True)
    a = ap.parse_args()
    photos = sorted(p for p in Path(a.photos).iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    if not photos:
        raise SystemExit("no photos")
    spend = Spend(a.max_spend)
    report = {"photos": len(photos), "questions_per_user": len(QUESTIONS), "max_spend": a.max_spend, "steps": []}
    for step in (int(x) for x in a.steps.split(",")):
        if not spend.ok():
            break
        recs: list[dict] = []
        t0 = time.monotonic()
        await asyncio.gather(*(user(i, photos, a.base_url, spend, recs, step) for i in range(step)))
        s = {"users": step, **summary(recs, time.monotonic() - t0)}
        report["steps"].append(s)
        print(json.dumps(s, ensure_ascii=False), flush=True)
    report["total_cost_usd"] = round(spend.spent, 4)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
