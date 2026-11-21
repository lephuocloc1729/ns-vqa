"""The API runs exactly the frozen phase52 configuration (eval/frozen_phase52.json)."""

from __future__ import annotations

import json
from pathlib import Path

from app.api.profiles import PROFILES, pipeline_config
from app.api.settings import Settings

ROOT = Path(__file__).resolve().parent.parent


def test_phase52_profile_equals_the_freeze_record():
    record = json.loads((ROOT / "eval" / "frozen_phase52.json").read_text(encoding="utf-8"))
    assert PROFILES["phase52"] == record["pipeline_config"]
    assert record["excluded_switches"] == ["answer_fallback"]


def test_only_the_fallback_and_run_fields_come_from_settings():
    c = pipeline_config(Settings(answer_fallback="claude", max_spend=3.0))
    assert c.answer_fallback is True and c.max_spend == 3.0 and c.cache_only is False
    assert pipeline_config(Settings()).answer_fallback is False
    for k, v in PROFILES["phase52"].items():
        assert getattr(c, k) == v
