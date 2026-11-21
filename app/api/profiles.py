"""The pipeline configuration the API runs.

PROFILES holds the frozen settings of each profile, copied from its freeze record.
tests/test_api_profile.py checks that they stay equal to the record, so the API runs
exactly the benchmarked system. Only the answer fallback (excluded from the freeze,
which was run with it off) and the run-specific fields (cache, spend) are set here.
"""

from __future__ import annotations

from typing import Any

from vqa.pipeline import PipelineConfig

from app.api.settings import Settings

PROFILES: dict[str, dict[str, Any]] = {
    # phase52: the system benchmarked on the private test (tag v1.0-benchmark).
    "phase52": {
        "perception_model": "claude-haiku-5-5",
        "scene_version": "v5",
        "scene_fallback": True,
        "parser_model": "claude-sonnet-5-5",
        "parser_effort": "medium",
        "parser_version": "v18",
        "context_year": 2025,
        "writer_version": "v3",
        "answer_fallback_version": "v2",
        "guide_reading": True,
        "reading_policy": "higher_confidence",
        "scene_rerun": False,
    },
}


def pipeline_config(settings: Settings) -> PipelineConfig:
    if settings.profile not in PROFILES:
        raise ValueError(f"unknown profile {settings.profile!r}; one of {sorted(PROFILES)}")
    return PipelineConfig(**PROFILES[settings.profile],
                          answer_fallback=settings.answer_fallback != "off",
                          cache_dir=settings.scene_cache, cache_only=False, max_spend=settings.max_spend)
