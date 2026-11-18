"""Phase 4.8c B2 (owner, 2026-11-18; switch `asked_only` in kb/switches_48.yaml): the answer keeps
only what the question asked, before the writer and the template see it.

- Vehicle lists (which_vehicles, lane_vehicles, applies_to) drop pedestrians unless the question
  names them ("người đi bộ", "bộ hành"): "những loại xe nào" asks about vehicles.
- A speed limit asked with no lane drops its per-lane rows when the overall limit is decided and
  the question doesn't mention lanes.

Presentation only: the rules' conclusions are unchanged (every class is still checked); what is
dropped is detail the question did not ask for. Applied to `multi` parts one by one."""

from __future__ import annotations

import re
from typing import Any

from vqa.schemas import Answer

_PEDESTRIAN_WORDS = re.compile(r"người đi bộ|bộ hành|người đi đường", re.IGNORECASE)
_LANE_WORDS = re.compile(r"\blàn\b", re.IGNORECASE)
_VEHICLE_LIST_KEYS = ("banned", "allowed", "conditional", "applies_to")


def switch_on() -> bool:
    from vqa.reasoning.engine import switches_from_kb
    return bool(switches_from_kb().get("asked_only", False))


def _prune_value(v: Any, question: str) -> Any:
    if not isinstance(v, dict):
        return v
    out = dict(v)
    if isinstance(out.get("parts"), list):
        out["parts"] = [{**p, "value": _prune_value(p.get("value"), question)} if isinstance(p, dict) else p
                        for p in out["parts"]]
    if not _PEDESTRIAN_WORDS.search(question):
        for k in _VEHICLE_LIST_KEYS:
            if isinstance(out.get(k), list) and "pedestrian" in out[k]:
                out[k] = [c for c in out[k] if c != "pedestrian"]
        if isinstance(out.get("per_class"), dict) and "pedestrian" in out["per_class"]:
            out["per_class"] = {c: x for c, x in out["per_class"].items() if c != "pedestrian"}
    if (out.get("per_lane") and "kind" in out and out.get("limit") is not None and out.get("lane") is None
            and not _LANE_WORDS.search(question)):
        out.pop("per_lane")
    return out


def prune_unasked(answer: Answer | None, question: str, on: bool | None = None) -> Answer | None:
    """The answer with the unasked detail dropped (switch `asked_only`, unless `on` is given)."""
    if answer is None or not (switch_on() if on is None else on):
        return answer
    v = _prune_value(answer.value, question)
    return answer if v == answer.value else answer.model_copy(update={"value": v})
