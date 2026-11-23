"""eval/uat/turn_stats.py: aggregate answer numbers for a UAT window, read from the API's database."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.api.storage import Store
from eval.uat.turn_stats import collect, format_report


@pytest.fixture
def store(tmp_path):
    return Store(f"sqlite:///{tmp_path / 'app.db'}")


def _turn(store, sid, image="0" * 64, **fields):
    t = store.start_turn(sid, "câu hỏi", image)
    store.finish_turn(t.id, **fields)
    return t.id


def test_collect_window_routes_feedback(store, tmp_path):
    sid = store.new_session().id
    a = _turn(store, sid, status="done", verdict="no", answered_by="rules", seconds=10.0, cost_usd=0.01)
    b = _turn(store, sid, status="done", verdict="value", answered_by="fallback", seconds=30.0, cost_usd=0.02,
              stages={"fallback": {"cache_hit": True}})
    _turn(store, sid, status="done", verdict="unknown", answered_by="rules", seconds=20.0, cost_usd=0.01)
    _turn(store, store.new_session().id, status="error", error="boom")
    store.add_feedback(a, "down", None, None)
    store.add_feedback(a, "up", None, None)          # the latest feedback per answer counts
    store.add_feedback(b, "down", "Được đi", None)

    now = datetime.now(timezone.utc)
    s = collect(store.engine.url.render_as_string(hide_password=False),
                now - timedelta(hours=1), now + timedelta(hours=1))
    assert s["questions"] == 4 and s["conversations"] == 2
    assert s["status"] == {"done": 3, "error": 1}
    assert s["answered_by"] == {"rules": 2, "fallback": 1}
    assert s["rag_cache_hits"] == 1
    assert s["seconds"]["p50"] == 20.0 and s["seconds"]["max"] == 30.0
    assert s["seconds_p50_by_route"]["rules"] == 15.0
    assert s["cost_usd"]["total"] == pytest.approx(0.04)
    assert s["feedback"] == {"answers_rated": 2, "up": 1, "down": 1, "up_share": 0.5, "corrected": 1}
    text = format_report(s)
    assert "p50 20.0" in text and "50% up" in text
    assert "câu hỏi" not in text and "Được đi" not in text     # aggregates only


def test_collect_outside_window_is_empty(store):
    _turn(store, store.new_session().id, status="done", answered_by="rules", seconds=5.0)
    later = datetime.now(timezone.utc) + timedelta(days=1)
    s = collect(store.engine.url.render_as_string(hide_password=False), later, later + timedelta(hours=1))
    assert s["questions"] == 0 and s["seconds"]["p50"] is None
    assert "Questions: **0**" in format_report(s)


def test_first_question_on_a_photo_vs_seen_before(store):
    sid = store.new_session().id
    _turn(store, sid, image="a" * 64, status="done", answered_by="rules", seconds=4.0)   # before the window
    cut = datetime.now(timezone.utc)
    _turn(store, sid, image="a" * 64, status="done", answered_by="rules", seconds=6.0)   # cached photo
    _turn(store, sid, image="b" * 64, status="done", answered_by="rules", seconds=25.0)  # first on b
    _turn(store, sid, image="b" * 64, status="done", answered_by="rules", seconds=7.0)   # follow-up on b
    s = collect(store.engine.url.render_as_string(hide_password=False), cut, cut + timedelta(hours=1))
    assert s["questions"] == 3 and s["photos"] == 2
    assert s["seconds_by_photo"]["first_on_photo"] == {"n": 1, "p50": 25.0, "p90": 25.0}
    assert s["seconds_by_photo"]["photo_seen_before"]["n"] == 2
    assert s["seconds_by_photo"]["photo_seen_before"]["p50"] == 6.5
    assert "**first question on a photo** p50 25.0" in format_report(s)
