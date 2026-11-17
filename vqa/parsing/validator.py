"""Checks a parsed QueryProgram before it is used.

Beyond the Pydantic schemas (already applied by the converter):
- every_vehicle only inside claims (permitted, forbidden, speed_ok, required);
- is_sign and present targets exist in the catalog;
- phase 4.5: a speed_limit's vehicle list (which replaces its one vehicle) never holds
  every_vehicle; a guide direction / distance names its destination;
- a dry run on an empty scene must not raise (catches programs the engine cannot
  run, e.g. an unknown meaning or an intent/vehicle combination it rejects).
Returns a list of error messages; empty means valid.
"""

from __future__ import annotations

from pydantic import ValidationError

from vqa.reasoning.engine import Engine, EngineError
from vqa.schemas import (
    AllOf, AnyOf, BanTimes, ChoiceOption, Choose, Guide, IsSign, LanesFor, LanesWhere, Present,
    QueryProgram, SceneGraph, SpeedLimit, Verify,
)

_NO_EVERY = (LanesFor, LanesWhere, BanTimes, SpeedLimit)


def _walk(p):
    yield p
    if isinstance(p, Verify):
        yield from _walk(p.claim)
    elif isinstance(p, (AllOf, AnyOf)):
        for c in p.claims:
            yield from _walk(c)
    elif isinstance(p, Choose):
        for o in p.options:
            yield from _walk(o.claim)


def check(q: QueryProgram, engine: Engine) -> list[str]:
    if q.out_of_scope:
        return []
    errors: list[str] = []
    for node in _walk(q.program):
        v = getattr(node, "vehicle", None)
        if isinstance(node, _NO_EVERY) and v is not None and v.cls.value == "every_vehicle":
            errors.append(f"{node.intent}: every_vehicle is only for claims "
                          "(permitted, forbidden, speed_ok, required)")
        if isinstance(node, SpeedLimit) and node.vehicles:
            if any(x.cls.value == "every_vehicle" for x in node.vehicles):
                errors.append("speed_limit: every_vehicle is not a vehicle of a list")
        if isinstance(node, Guide) and node.ask in ("direction", "distance") and not (node.destination or "").strip():
            errors.append(f"guide: ask={node.ask} needs the destination named in the question")
        if isinstance(node, (IsSign, Present)):
            try:
                if node.code:
                    engine.catalog.codes_matching(node.code)
                if node.meaning:
                    engine.catalog.codes_for_meaning(node.meaning)
            except KeyError as e:
                errors.append(f"{node.intent}: {e}")
    if errors:
        return errors
    try:
        engine.answer(SceneGraph(scene_id="dry-run"), q)
    except (EngineError, ValueError, ValidationError) as e:
        errors.append(f"the engine cannot run this program: {e}")
    return errors
