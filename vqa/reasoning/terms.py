"""Tiny Prolog term writer: Python values -> Prolog source text.

Facts and queries are sent to SWI-Prolog as text and parsed there with
``term_string/2``. Writing them here keeps quoting in one place.

Mapping: ``str`` -> atom, ``int``/``float`` -> number, ``None`` -> ``unknown``,
``list``/``tuple`` -> list, ``Term`` -> compound.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

_PLAIN_ATOM = re.compile(r"^[a-z][a-zA-Z0-9_]*$")


@dataclass(frozen=True)
class Atom:
    name: str


@dataclass(frozen=True)
class Term:
    name: str
    args: tuple[Any, ...]

    def __init__(self, name: str, *args: Any) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "args", tuple(args))

    def __str__(self) -> str:
        return to_prolog(self)


def atom(name: str) -> Atom:
    return Atom(name)


def _quote_atom(s: str) -> str:
    if _PLAIN_ATOM.match(s):
        return s
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def to_prolog(v: Any) -> str:
    if isinstance(v, Term):
        if not v.args:
            return _quote_atom(v.name)
        return f"{_quote_atom(v.name)}({', '.join(to_prolog(a) for a in v.args)})"
    if isinstance(v, Atom):
        return _quote_atom(v.name)
    if v is None:
        return "unknown"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError(f"non-finite number {v}")
        return repr(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, str):
        return _quote_atom(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(to_prolog(x) for x in v) + "]"
    if hasattr(v, "value") and isinstance(v.value, str):  # Enum
        return _quote_atom(v.value)
    raise TypeError(f"cannot write {type(v).__name__} as Prolog")


def cond_term(c: Any) -> Term:
    """Condition(attr, op, value) -> c(Attr, Op, Value)."""
    return Term("c", atom(c.attr.value), atom(c.op.value), c.value)


def spec_term(s: Any) -> Term:
    """VehicleSpec -> spec(Class, [c(...), ...])."""
    return Term("spec", atom(s.cls.value), [cond_term(c) for c in s.conditions])


# Bounds written as an interval iv(Lo, LoIncluded, Hi, HiIncluded); BIG stands for infinity.
BIG = 1.0e18
_BOUNDED = {  # attr -> (lower-bound field, upper-bound field, integer valued?)
    "seats": ("seats_gt", "seats_lt", True),
    "load_t": ("load_gt", "load_lt", False),
    "gross_t": ("gross_gt", "gross_lt", False),
}


def _interval(lo: float | None, hi: float | None, integer: bool) -> Term:
    if integer:  # seats > 29 means seats >= 30
        return Term("iv", float(lo + 1) if lo is not None else -BIG, atom("true"),
                    float(hi - 1) if hi is not None else BIG, atom("true"))
    return Term("iv", float(lo) if lo is not None else -BIG, atom("false"),
                float(hi) if hi is not None else BIG, atom("false"))


def vehicle_term(v: Any) -> Term:
    """Vehicle -> veh(Class, [a(Attr, Value), ...]); unset attributes are left out (unknown).
    Value is a number, or iv(Lo, LoIn, Hi, HiIn) when only bounds are known."""
    if v.cls.value == "every_vehicle":
        raise ValueError("every_vehicle is expanded per class by the engine, never sent to Prolog")
    attrs = []
    for name in ("load_t", "gross_t", "seats", "height_m", "width_m", "length_m"):
        val = getattr(v, name)
        if val is not None:
            attrs.append(Term("a", atom(name), float(val)))
        elif name in _BOUNDED:
            gt, lt, integer = _BOUNDED[name]
            lo, hi = getattr(v, gt), getattr(v, lt)
            if lo is not None or hi is not None:
                attrs.append(Term("a", atom(name), _interval(lo, hi, integer)))
    if v.priority:
        attrs.append(Term("a", atom("priority"), atom("true")))
    return Term("veh", atom(v.cls.value), attrs)
