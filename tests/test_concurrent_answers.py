"""Several answers at once in one API process (app/api/runner.py, docs/plans/concurrent-answers.md).

No API calls: a fake SDK whose replies depend on the request (the question, the verdict), so
the order in which threads call it never matters; scene caches are warmed by hand."""

from __future__ import annotations

import io
import json
import random
import re
import threading
import time
from types import SimpleNamespace

import pytest
from PIL import Image

import vqa.pipeline as pl
from app.api.runner import PipelineRunner
from vqa.reasoning.engine import Engine
from vqa.schemas import Permitted

from conftest import V, scene, sign
from test_pipeline import warm

Q_CAR = "Xe ô tô có được đi vào đường này không?"
Q_MOTO = "Xe máy có được đi vào đường này không?"
PROGRAMS = {
    Q_CAR: {"program": {"intent": "permitted", "action": "enter", "vehicle": {"vehicle_class": "car"}}},
    Q_MOTO: {"program": {"intent": "permitted", "action": "enter", "vehicle": {"vehicle_class": "motorbike"}}},
}


def scene_reply(code: str) -> str:
    return json.dumps({"signs": [{"code": code, "shape": "circle", "border": "red", "background": "white",
                                  "rank": 1, "side": "right", "confidence": "high", "plates": []}],
                       "road": {"type": "urban"}, "vehicles": []})


class KeyedSDK:
    """The parser's reply comes from the question; the writer's from the verdict it is given.
    A short random pause in every call makes concurrent answers interleave."""

    def __init__(self) -> None:
        self.messages = self
        self.lock = threading.Lock()
        self.calls = 0

    def count_tokens(self, **kw):
        return SimpleNamespace(input_tokens=3000)

    def create(self, **kw):
        with self.lock:
            self.calls += 1
        time.sleep(random.uniform(0.0, 0.03))
        system = kw["system"][0]["text"]
        user = json.dumps(kw["messages"], ensure_ascii=False)
        if system.startswith("# Task\n\nYou turn one Vietnamese question"):
            q = Q_CAR if Q_CAR in user else Q_MOTO
            reply = PROGRAMS[q]
        elif system.startswith("You write the final answer"):
            content = kw["messages"][0]["content"]
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            m = re.search(r'Engine result: \{"verdict":"(\w+)"', text)
            v = m.group(1) if m else "unknown"
            reply = {"verdict": v, "answer": {"yes": "Có.", "no": "Không."}.get(v, "Chưa xác định được."),
                     "cited_signs": [], "cited_rules": []}
        else:
            raise AssertionError(f"unexpected call: {system[:60]}")
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(reply, ensure_ascii=False))],
                               stop_reason="end_turn", stop_details=None, _request_id="req_t",
                               usage=SimpleNamespace(input_tokens=100, output_tokens=10,
                                                     cache_read_input_tokens=0, cache_creation_input_tokens=0))


@pytest.fixture
def photos(tmp_path, monkeypatch):
    """Two photos with different signs: P.103a (no cars) and P.104 (no motorbikes)."""
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    out = {}
    for code, colour in (("P.103a", (90, 120, 200)), ("P.104", (200, 120, 90))):
        buf = io.BytesIO()
        Image.new("RGB", (640, 480), colour).save(buf, format="JPEG")
        p = tmp_path / "up" / f"{code}.jpg"
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(buf.getvalue())
        out[code] = p
        cache = warm(tmp_path, p, reply=scene_reply(code))
    return out, cache


def run_all(runner: PipelineRunner, jobs):
    """Submit every job at once; return each one's answer and the events its stream got."""
    events = [[] for _ in jobs]
    futures = [runner.submit(path, q, (lambda n, p, i=i: events[i].append((n, p)))) for i, (path, q) in enumerate(jobs)]
    return [f.result(timeout=60) for f in futures], events


def key(a):
    return (a.verdict, a.text, a.answered_by, tuple(a.citations), json.dumps(a.proof, sort_keys=True))


# ---------------------------------------------------------------------------- the Prolog lock
def test_the_runner_locks_prolog_so_threads_get_the_sequential_answers():
    eng = Engine()
    runner = PipelineRunner(lambda: SimpleNamespace(engine=eng), slots=8)
    runner.pipeline                                            # wraps engine.answer (with the lock)
    cases = [(scene(sign("s1", "P.103a")), Permitted(action="enter", vehicle=V("car"))),
             (scene(sign("s1", "P.106a")), Permitted(action="enter", vehicle=V("truck"))),
             (scene(sign("s1", "P.102")), Permitted(action="enter", vehicle=V("car"))),
             (scene(sign("s1", "P.104")), Permitted(action="enter", vehicle=V("motorbike"))),
             (scene(), Permitted(action="enter", vehicle=V("car")))]
    dump = lambda a: json.dumps(a.model_dump(mode="json"), sort_keys=True)  # noqa: E731
    want = [dump(eng.answer(s, p)) for s, p in cases]
    assert [json.loads(w)["verdict"] for w in want] == ["no", "no", "no", "no", "yes"]
    bad: list = []

    def worker(seed):
        r = random.Random(seed)
        for _ in range(40):
            i = r.randrange(len(cases))
            if dump(eng.answer(*cases[i])) != want[i]:
                bad.append(i)
    threads = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert bad == []                                           # without the lock, about 1 in 4 differ


# ---------------------------------------------------------------------------- the whole pipeline
def test_concurrent_answers_equal_sequential_ones_and_streams_never_mix(photos):
    paths, cache = photos
    # "xe máy" means a two-wheeler since 2026-11-25 (owner), so P.103a allows it
    expected_verdict = {("P.103a", Q_CAR): "no", ("P.103a", Q_MOTO): "yes",
                        ("P.104", Q_CAR): "yes", ("P.104", Q_MOTO): "no"}
    combos = list(expected_verdict)
    jobs_named = [combos[i % 4] for i in range(24)]
    jobs = [(paths[code], q) for code, q in jobs_named]

    def make():
        return pl.Pipeline(pl.PipelineConfig(cache_dir=cache, cache_only=True, max_spend=5.0,
                                           answer_fallback=False), sdk=KeyedSDK())

    one = PipelineRunner(make, slots=1)
    seq = {c: key(one.submit(paths[c[0]], c[1]).result(timeout=60)) for c in combos}
    assert {c: seq[c][0] for c in combos} == expected_verdict

    many = PipelineRunner(make, slots=6)
    answers, events = run_all(many, jobs)
    for (code, q), a, ev in zip(jobs_named, answers, events):
        assert key(a) == seq[(code, q)]                        # the same answer as when run alone
        got = dict(ev)
        assert [n for n, _ in ev][0] == "started"
        assert [s["code"] for s in got["perception"]["signs"]] == [code]      # its own photo
        assert got["parsed"]["program"]["program"]["vehicle"]["class"] == ("car" if q == Q_CAR else "motorbike")
        assert got["engine"]["verdict"] == expected_verdict[(code, q)]
        if a.answered_by == "rules":                                         # the writer streamed it
            assert "".join(p["text"] for n, p in ev if n == "token") == a.text   # its own words only
        else:
            assert not any(n == "token" for n, _ in ev)
    assert {"Có.", "Không."} <= {a.text for a in answers}                 # the writer's own answers ran
    # the answers' own copies of the photo are cleaned up
    assert not any((paths["P.103a"].parent / ".turns").glob("*/*"))


def test_answers_overlap_in_time(photos):
    """Six slots finish six slow answers in about the time of one."""
    paths, cache = photos

    class SlowSDK(KeyedSDK):
        def create(self, **kw):
            time.sleep(0.3)
            return super().create(**kw)

    def make():
        return pl.Pipeline(pl.PipelineConfig(cache_dir=cache, cache_only=True, max_spend=5.0,
                                           answer_fallback=False), sdk=SlowSDK())

    def timed(slots):
        r = PipelineRunner(make, slots=slots)
        r.pipeline
        t0 = time.monotonic()
        run_all(r, [(paths["P.103a"], Q_CAR)] * 6)
        return time.monotonic() - t0

    one, six = timed(1), timed(6)
    assert six < one / 3, (one, six)                           # about 6 x 0.6 s vs 0.6 s


def test_slots_are_bounded():
    from app.api.settings import Settings
    with pytest.raises(ValueError):
        Settings(answer_slots=0)
    assert PipelineRunner(lambda: None, slots=3).slots == 3


# ---------------------------------------------------------------------------- the API
def test_two_streams_at_once_each_get_their_own_answer(photos, tmp_path):
    from fastapi.testclient import TestClient

    from app.api.main import create_app
    from app.api.settings import Settings
    from test_api import sse_events

    paths, cache = photos

    def make():
        return pl.Pipeline(pl.PipelineConfig(cache_dir=cache, cache_only=True, max_spend=5.0,
                                             answer_fallback=False), sdk=KeyedSDK())

    s = Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "uploads",
                 heartbeat_s=0.2, answer_slots=2)
    client = TestClient(create_app(s, pipeline_factory=make))
    assert client.get("/version").json()["answer_slots"] == 2
    asks = [("P.103a", Q_CAR, "Không."), ("P.104", Q_CAR, "Có."), ("P.104", Q_MOTO, "Không.")] * 2
    results: list = [None] * len(asks)

    def ask(i, code, q):
        r = client.post("/v1/ask/stream", data={"question": q},
                        files={"image": ("p.jpg", paths[code].read_bytes(), "image/jpeg")})
        results[i] = sse_events(r.text)
    threads = [threading.Thread(target=ask, args=(i, c, q)) for i, (c, q, _) in enumerate(asks)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    for (code, q, text), ev in zip(asks, results):
        d = dict(ev)
        assert d["answer"]["answer"] == text
        assert [s["code"] for s in d["perception"]["signs"]] == [code]
        assert "".join(p["text"] for n, p in ev if n == "token") == text
