"""Phase 4.7 step 2 (owner, 2026-11-17): generated tests.

- Every prohibitory row of the 80 stage-A signs x every vehicle class x each banned action: a scene
  holding only that sign; the engine's `permitted` verdict is checked against an oracle written from
  the catalog row alone (its vehicles, exceptions, value conditions, days) and the ontology.
- Speed rows x every class: `speed_ok` above and below the number on the sign.
- Every mandatory row x every direction: the verdict against the row's directions.

Rows where the engine disagrees with the oracle and the oracle is right are fixed if the row is new
(phase 4.7) and listed in docs/plans/phase-4.7-review.md ("existing rows that look wrong") if not.
KNOWN_DIFFERENCES holds those cases with the reason; they are asserted to still differ, so a later
change shows up. No API call."""

from __future__ import annotations

import pytest

from eval.coverage_matrix import stage_a_codes
from vqa.kb import load_catalog
from vqa.reasoning.engine import Engine
from vqa.schemas import ONTOLOGY_CLASSES, Permitted, Position, SceneGraph, Sign, SpeedOk, Vehicle, Verdict

CAT = load_catalog()
CLASSES = [c.value for c in ONTOLOGY_CLASSES]
DIRECTIONS = ["go_straight", "turn_left", "turn_right", "u_turn"]


@pytest.fixture(scope="module")
def engine():
    return Engine()


def _sub(a: str, b: str) -> bool:
    import janus_swi as janus
    Engine()                                   # loads the knowledge base once
    return bool(janus.query_once(f"subclass_of({a}, {b})")["truth"])


_SUB: dict[tuple[str, str], bool] = {}


def sub(a: str, b: str) -> bool:
    if (a, b) not in _SUB:
        _SUB[(a, b)] = _sub(a, b)
    return _SUB[(a, b)]


def scene(code: str, value: float | None = None) -> SceneGraph:
    v = CAT.get(code).visual
    return SceneGraph(scene_id="gen", signs=[Sign(id="s1", code=code, value=value, confidence="high", shape=v.shape,
                                                  border=v.border, background=v.background,
                                                  position=Position(rank_top_down=1, side="right"))])


def oracle_ban(code: str, action: str, cls: str) -> str:
    """yes / no / unknown for "may `cls` do `action`" under this one row, from the row alone."""
    e = CAT.get(code).effect
    specs = [v for p in e.prohibits if action in [a.value for a in p.actions] for v in p.vehicles]
    excepted = [x.value for x in e.except_]
    value_applies = e.value is not None and any(sub(cls, c.value) for c in e.value.applies_to)
    conditional = value_applies or e.days is not None
    out = "yes"
    for sp in specs:
        s = sp.cls.value
        if sub(cls, s):
            if any(sub(cls, x) for x in excepted):
                continue
            if conditional or sp.conditions or any(sub(x, cls) and x != cls for x in excepted):
                out = "unknown" if out == "yes" else out
            else:
                return "no"
        elif sub(s, cls) and s != cls:
            out = "unknown" if out == "yes" else out
    return out


PRO = [c for c in stage_a_codes() if CAT.has(c) and CAT.get(c).category == "prohibitory"]
BAN_CASES = [(code, a.value, cls) for code in PRO for p in CAT.get(code).effect.prohibits
             for a in p.actions for cls in CLASSES]

# (code, action, class): engine verdict where it differs from the row-only oracle, and why.
KNOWN_DIFFERENCES: dict[tuple[str, str, str], tuple[str, str]] = {}


@pytest.mark.parametrize("code,action,cls", BAN_CASES)
def test_prohibitory_row_by_class(engine, code, action, cls):
    value = 10.0 if CAT.get(code).effect.value is not None else None
    a = engine.answer(scene(code, value), Permitted(action=action, vehicle=Vehicle(**{"class": cls})))
    want = oracle_ban(code, action, cls)
    if (code, action, cls) in KNOWN_DIFFERENCES:
        assert a.verdict.value == KNOWN_DIFFERENCES[(code, action, cls)][0]
        return
    assert a.verdict.value == want, (code, action, cls, a.verdict.value, a.note)
    if a.verdict is Verdict.no:
        assert any(c.article_id == CAT.get(code).source.article_id for c in a.citations)


SPEED = [c for c in PRO if CAT.get(c).effect.max_speed]


def oracle_speed(code: str, cls: str, over: bool) -> str:
    covered = [x.value for x in CAT.get(code).effect.max_speed]
    if any(sub(cls, x) for x in covered):
        return "no" if over else "yes"
    if any(sub(x, cls) for x in covered):
        return "unknown" if over else "yes"
    return "yes"


@pytest.mark.parametrize("code,cls,over", [(c, k, o) for c in SPEED for k in CLASSES for o in (True, False)])
def test_speed_row_by_class(engine, code, cls, over):
    a = engine.answer(scene(code, 50.0), SpeedOk(vehicle=Vehicle(**{"class": cls}), speed_kmh=60.0 if over else 40.0))
    assert a.verdict.value == oracle_speed(code, cls, over), (code, cls, over, a.verdict.value, a.note)


MAN = [c for c in stage_a_codes() if CAT.has(c) and CAT.get(c).category == "mandatory"]


def oracle_direction(code: str, action: str) -> str:
    e = CAT.get(code).effect
    if CAT.get(code).effect_unmodelled:
        return "unknown"
    allowed = list(e.only_directions)
    if e.placement is not None:
        std = getattr(e.placement, e.placement.standard, None) if e.placement.standard != "either" else None
        if std is not None:
            allowed = list(std.directions)
    if not allowed or action == "u_turn" and "u_turn" not in allowed and action not in ("go_straight", "turn_left",
                                                                                         "turn_right"):
        return "yes"
    if action == "u_turn":
        return "yes"                          # the R.301 family orders go_straight / turn_left / turn_right
    return "yes" if action in allowed else "no"


@pytest.mark.parametrize("code,action", [(c, d) for c in MAN for d in DIRECTIONS])
def test_mandatory_row_by_direction(engine, code, action):
    a = engine.answer(scene(code), Permitted(action=action, vehicle=Vehicle(**{"class": "motor_vehicle"})))
    assert a.verdict.value == oracle_direction(code, action), (code, action, a.verdict.value, a.note)
