"""Load and stress test for the SignCite API (plan item 3.2), with Locust.

Each simulated user opens the page and starts a session, then, with 5-15 s of reading time between
actions, asks questions about a photo (reading the whole answer stream), reloads its history, opens
an earlier answer and checks the health endpoint. Run it against the Docker Compose stack with the
fake pipeline (no Claude calls), so the numbers measure our own system:

    API_WORKERS=2 docker compose up -d --wait
    LOAD_PROFILE=capacity LOAD_OUT=out/w2-capacity locust -f eval/load/locustfile.py --headless \\
        --host http://localhost:8080

LOAD_PROFILE: `capacity` steps through 10, 25, 50, 100, 200, 300 and 500 users (LOAD_STEP_S seconds
each, default 60). `stress` holds 100, then 1000 users, then drops to 20 to check recovery.
LOAD_OUT: where the per-step summary goes (<LOAD_OUT>.json and .md). The answer stream is measured
three ways: until its first event ("ask: first event"), until the `answer` event ("ask: answer"),
and until the stream ends ("ask: stream").
"""

from __future__ import annotations

import json
import os
import random
import time
from collections import defaultdict
from pathlib import Path

from locust import HttpUser, LoadTestShape, between, events, task

PHOTO = (Path(__file__).resolve().parents[2] / "web/e2e/fixtures/road.jpg").read_bytes()
QUESTIONS = [
    "Xe ô tô có được đi vào đường này không?",
    "Đây là biển báo gì?",
    "Xe tải có được đi qua đoạn đường này không?",
]
STEP_S = int(os.environ.get("LOAD_STEP_S", "60"))
PROFILE = os.environ.get("LOAD_PROFILE", "capacity")


class SignCiteUser(HttpUser):
    wait_time = between(5, 15)   # reading the answer before the next action

    def on_start(self) -> None:
        self.client.get("/", name="page")
        r = self.client.post("/v1/sessions", name="new session")
        self.sid = r.json().get("session_id") if r.ok else None
        self.turns: list[str] = []

    @task(3)
    def ask(self) -> None:
        t0 = time.perf_counter()
        first = answer = None
        ok, err = False, None
        try:
            with self.client.post(
                "/v1/ask/stream", name="ask: request", stream=True, timeout=180, catch_response=True,
                files={"image": ("road.jpg", PHOTO, "image/jpeg")},
                data={"question": random.choice(QUESTIONS), **({"session_id": self.sid} if self.sid else {})},
            ) as r:
                if r.status_code != 200:
                    err = f"HTTP {r.status_code}"
                    r.failure(err)
                else:
                    event = None
                    for raw in r.iter_lines(decode_unicode=True):
                        if raw.startswith("event: "):
                            event = raw[7:]
                            if first is None:
                                first = time.perf_counter()
                            if event == "answer":
                                answer = time.perf_counter()
                            elif event == "error":
                                err = "error event"
                        elif raw.startswith("data: ") and event == "turn":
                            tid = json.loads(raw[6:]).get("turn_id")
                            if tid:
                                self.turns.append(tid)
                    ok = answer is not None and err is None
                    if ok:
                        r.success()
                    else:
                        err = err or "no answer event"
                        r.failure(err)
        except Exception as e:   # a dropped connection, a timeout
            err = type(e).__name__
        end = time.perf_counter()
        fire = self.environment.events.request.fire
        exc = None if ok else Exception(err)
        fire(request_type="SSE", name="ask: first event", response_time=((first or end) - t0) * 1000,
             response_length=0, exception=exc if first is None else None, context={})
        fire(request_type="SSE", name="ask: answer", response_time=((answer or end) - t0) * 1000,
             response_length=0, exception=exc, context={})
        fire(request_type="SSE", name="ask: stream", response_time=(end - t0) * 1000,
             response_length=0, exception=exc, context={})

    @task(2)
    def history(self) -> None:
        if self.sid:
            self.client.get(f"/v1/sessions/{self.sid}/turns", name="history")

    @task(1)
    def open_turn(self) -> None:
        if self.turns:
            self.client.get(f"/v1/turns/{random.choice(self.turns)}", name="open answer")

    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="health")


class Steps(LoadTestShape):
    """(users, seconds) steps; users start at up to 20 per second."""

    def __init__(self) -> None:
        super().__init__()
        if PROFILE == "stress":
            self.steps = [(100, STEP_S), (1000, 2 * STEP_S), (20, STEP_S)]
        else:
            self.steps = [(n, STEP_S) for n in (10, 25, 50, 100, 200, 300, 500)]

    def tick(self):
        t = self.get_run_time()
        for users, secs in self.steps:
            if t < secs:
                return users, 20
            t -= secs
        return None


# ---------------------------------------------------------------------------- per-step summary
# Every request is filed under the step (of the shape above) that was running when it ended.
_rows: dict[tuple[int, str], list[float]] = defaultdict(list)
_fails: dict[tuple[int, str], int] = defaultdict(int)
_span: dict[int, list[float]] = {}
_env = None


@events.init.add_listener
def _init(environment, **_kw):
    global _env
    _env = environment


def _step() -> int:
    shape = _env.shape_class if _env else None
    if shape is None:
        return 0
    t = shape.get_run_time()
    for i, (_, secs) in enumerate(shape.steps):
        if t < secs:
            return i
        t -= secs
    return len(shape.steps) - 1


@events.request.add_listener
def _record(request_type, name, response_time, exception, **_kw):
    step = _step()
    _rows[(step, name)].append(response_time)
    if exception:
        _fails[(step, name)] += 1
    now = time.time()
    s = _span.setdefault(step, [now, now])
    s[1] = now


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else 0.0


@events.quitting.add_listener
def _write(environment, **_kw):
    out = os.environ.get("LOAD_OUT")
    if not out:
        return
    names = sorted({n for _, n in _rows})
    shape = environment.shape_class
    table = []
    for s in sorted({s for s, _ in _rows}):
        users = shape.steps[s][0] if shape else 0
        secs = max(1.0, _span[s][1] - _span[s][0])
        total = sum(len(_rows[(s, n)]) for n in names if not n.startswith("ask: ") or n == "ask: request")
        for n in names:
            xs = _rows.get((s, n), [])
            if not xs:
                continue
            table.append({
                "step": s + 1, "users": users, "name": n, "count": len(xs), "fails": _fails[(s, n)],
                "fail_pct": round(100 * _fails[(s, n)] / len(xs), 2),
                "rps": round(len(xs) / secs, 2), "p50_ms": round(_pct(xs, 50)), "p95_ms": round(_pct(xs, 95)),
                "max_ms": round(max(xs)), "step_seconds": round(secs), "step_http_rps": round(total / secs, 2)})
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(f"{out}.json").write_text(json.dumps({"profile": PROFILE, "step_s": STEP_S, "rows": table}, indent=1))
    md = [f"Profile `{PROFILE}`, {STEP_S} s per step. Times in ms; RPS per endpoint; "
          "`all RPS` counts every HTTP request in the step.", "",
          "| step | users | endpoint | requests | fail % | RPS | p50 | p95 | max | all RPS |",
          "|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in table:
        md.append(f"| {r['step']} | {r['users']} | {r['name']} | {r['count']} | {r['fail_pct']} | {r['rps']} | "
                  f"{r['p50_ms']} | {r['p95_ms']} | {r['max_ms']} | {r['step_http_rps']} |")
    Path(f"{out}.md").write_text("\n".join(md) + "\n")
