"""The parser's output format ("wire" schema) and its conversion to QueryProgram.

Structured outputs do not accept recursive JSON schemas, while the internal
Program type is recursive (all_of holds claims, which can be all_of again). The
wire schema caps nesting at one level, which covers every question form seen in
the audits:

    leaf claim  = permitted | forbidden | speed_ok | required | exists_violation | is_sign
    claim       = leaf claim | all_of(leaf claims) | any_of(leaf claims)
    program     = claim | verify(claim) | choose(options of claims)
                | lanes_for | lanes_where | ban_times | meaning | which_vehicles
                | lane_vehicles | speed_limit

Enums come from the ontology (vehicle classes, actions). Sign codes and meaning
keys/tags are plain strings in the JSON schema: as enums (219 codes, 232 keys)
they made the compiled grammar too large for the API. The system prompt's catalog
table lists them, and the Pydantic models check them against the catalog, with a
short error the parser's retry can act on.
Every field is required in the JSON schema sent to the API (nullable where the
DSL makes it optional); the Pydantic models keep defaults so compact examples
validate too.

Defaults the parser fills (recorded in QueryProgram.defaults_applied):
  year     a date with day and month but no year gets the context year
  vehicle  an intent that needs a vehicle gets motor_vehicle when none is named
"""

from __future__ import annotations

import copy
import datetime as dt
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, TypeAdapter, ValidationError

from vqa.kb import load_catalog
from vqa.schemas import Action, Colour, Program, QueryProgram, Shape, Side, VehicleClass

_CATALOG = load_catalog()

VehicleClassLit = Literal[tuple(c.value for c in VehicleClass)]  # type: ignore[valid-type]
ActionLit = Literal[tuple(a.value for a in Action)]  # type: ignore[valid-type]
_CODES = frozenset(s.code for s in _CATALOG.signs)
_MEANINGS = frozenset({s.key for s in _CATALOG.signs} | {t for s in _CATALOG.signs for t in s.tags})


def _known_code(v: str) -> str:
    if v not in _CODES:
        raise ValueError(f"unknown sign code {v!r}: use a code exactly as written in the "
                         "sign catalog table")
    return v


def _known_meaning(v: str) -> str:
    if v not in _MEANINGS:
        raise ValueError(f"unknown sign meaning {v!r}: use a key or tag exactly as written "
                         "in the sign catalog table")
    return v


CodeLit = Annotated[str, AfterValidator(_known_code)]
MeaningLit = Annotated[str, AfterValidator(_known_meaning)]
ShapeLit = Literal[tuple(s.value for s in Shape)]  # type: ignore[valid-type]
ColourLit = Literal[tuple(c.value for c in Colour)]  # type: ignore[valid-type]
SideLit = Literal[tuple(s.value for s in Side)]  # type: ignore[valid-type]
CategoryLit = Literal["prohibitory", "mandatory", "warning", "information", "auxiliary",
                      "end_of_restriction"]


class _W(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WVehicle(_W):
    vehicle_class: VehicleClassLit
    load_t: Optional[float] = None
    gross_t: Optional[float] = None
    seats: Optional[int] = None
    height_m: Optional[float] = None
    width_m: Optional[float] = None
    length_m: Optional[float] = None
    seats_gt: Optional[int] = None
    seats_lt: Optional[int] = None
    load_gt: Optional[float] = None
    load_lt: Optional[float] = None
    gross_gt: Optional[float] = None
    gross_lt: Optional[float] = None
    priority: bool = False


class WWhen(_W):
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None
    time: Optional[str] = None       # "HH:MM", a moment
    start: Optional[str] = None      # "HH:MM", an interval with end and quantifier
    end: Optional[str] = None
    quantifier: Optional[Literal["all", "any"]] = None


class WSelector(_W):
    code: Optional[CodeLit] = None
    meaning: Optional[MeaningLit] = None
    shape: Optional[ShapeLit] = None
    border: Optional[ColourLit] = None
    background: Optional[ColourLit] = None
    position: Optional[Literal["top", "bottom"]] = None
    rank_top_down: Optional[int] = None
    side: Optional[SideLit] = None
    only: bool = False


class WPermitted(_W):
    intent: Literal["permitted"]
    action: ActionLit
    vehicle: Optional[WVehicle] = None
    when: Optional[WWhen] = None
    sign: Optional[WSelector] = None
    lane: Optional[int] = None


class WForbidden(_W):
    intent: Literal["forbidden"]
    action: ActionLit
    vehicle: Optional[WVehicle] = None
    when: Optional[WWhen] = None
    sign: Optional[WSelector] = None
    lane: Optional[int] = None


class WSpeedOk(_W):
    intent: Literal["speed_ok"]
    speed_kmh: float
    vehicle: Optional[WVehicle] = None
    lane: Optional[int] = None
    when: Optional[WWhen] = None


class WRequired(_W):
    intent: Literal["required"]
    action: ActionLit
    vehicle: Optional[WVehicle] = None
    placement: Optional[Literal["before_intersection", "after_intersection"]] = None


class WExistsViolation(_W):
    intent: Literal["exists_violation"]
    when: Optional[WWhen] = None


class WIsSign(_W):
    intent: Literal["is_sign"]
    sign: WSelector
    code: Optional[CodeLit] = None
    meaning: Optional[MeaningLit] = None
    category: Optional[CategoryLit] = None


LeafClaim = Union[WPermitted, WForbidden, WSpeedOk, WRequired, WExistsViolation, WIsSign]


class WAllOf(_W):
    intent: Literal["all_of"]
    claims: list[LeafClaim]


class WAnyOf(_W):
    intent: Literal["any_of"]
    claims: list[LeafClaim]


Claim = Union[WPermitted, WForbidden, WSpeedOk, WRequired, WExistsViolation, WIsSign,
              WAllOf, WAnyOf]


class WVerify(_W):
    intent: Literal["verify"]
    claim: Claim
    expect: bool = True


class WChoiceOption(_W):
    label: str
    claim: Claim
    expect: bool = True


class WChoose(_W):
    intent: Literal["choose"]
    options: list[WChoiceOption]


class WLanesFor(_W):
    intent: Literal["lanes_for"]
    vehicle: Optional[WVehicle] = None
    speed_kmh: Optional[float] = None
    when: Optional[WWhen] = None


class WLanesWhere(_W):
    intent: Literal["lanes_where"]
    speed_kmh: float
    ok: bool = True
    vehicle: Optional[WVehicle] = None
    when: Optional[WWhen] = None


class WBanTimes(_W):
    intent: Literal["ban_times"]
    action: ActionLit = "enter"
    vehicle: Optional[WVehicle] = None
    sign: Optional[WSelector] = None


class WMeaning(_W):
    intent: Literal["meaning"]
    sign: WSelector


class WWhichVehicles(_W):
    intent: Literal["which_vehicles"]
    action: ActionLit = "enter"
    status: Literal["banned", "allowed"] = "banned"
    when: Optional[WWhen] = None
    sign: Optional[WSelector] = None


class WLaneVehicles(_W):
    intent: Literal["lane_vehicles"]
    lane: int
    status: Literal["allowed", "banned"] = "allowed"
    speed_kmh: Optional[float] = None
    when: Optional[WWhen] = None


class WSpeedLimit(_W):
    intent: Literal["speed_limit"]
    kind: Literal["max", "min"] = "max"
    vehicle: Optional[WVehicle] = None
    lane: Optional[int] = None
    when: Optional[WWhen] = None


WProgram = Union[WPermitted, WForbidden, WSpeedOk, WRequired, WExistsViolation, WIsSign,
                 WAllOf, WAnyOf, WVerify, WChoose, WLanesFor, WLanesWhere, WBanTimes,
                 WMeaning, WWhichVehicles, WLaneVehicles, WSpeedLimit]


class WParse(_W):
    """The parser's whole answer."""

    out_of_scope: bool = False
    out_of_scope_reason: Optional[str] = None
    missing_slots: list[str] = []
    program: Optional[WProgram] = None


# --------------------------------------------------------------------------- schema

def _strict(node: Any) -> Any:
    """Every object property required, no 'default' keys (nullable fields stay
    nullable through anyOf-null)."""
    if isinstance(node, dict):
        out = {k: _strict(v) for k, v in node.items() if k != "default"}
        if out.get("type") == "object" and "properties" in out:
            out["required"] = list(out["properties"])
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [_strict(x) for x in node]
    return node


def explain(e: ValidationError) -> str:
    """A short message for a wire validation error. The program is a union, so
    Pydantic reports a mismatch for every variant; the catalog errors (unknown code
    or meaning) are the useful part when present."""
    errs = e.errors()
    values = [x["msg"].removeprefix("Value error, ") for x in errs if x["type"] == "value_error"]
    if values:
        return "; ".join(dict.fromkeys(values))      # the same field fails in every variant
    return "; ".join(f"{'.'.join(str(p) for p in x['loc'])}: {x['msg']}" for x in errs[:3])


def json_schema() -> dict[str, Any]:
    """The JSON schema for output_config.format."""
    return _strict(copy.deepcopy(WParse.model_json_schema()))


# --------------------------------------------------------------------------- convert

_NEEDS_VEHICLE = {"permitted", "forbidden", "speed_ok", "lanes_for", "lanes_where", "ban_times"}
_ATTRS = ("load_t", "gross_t", "seats", "height_m", "width_m", "length_m", "seats_gt",
          "seats_lt", "load_gt", "load_lt", "gross_gt", "gross_lt")


class _Converter:
    def __init__(self, context_year: int) -> None:
        self.year = context_year
        self.defaults: set[str] = set()

    def vehicle(self, v: WVehicle | None, intent: str) -> dict | None:
        if v is None:
            if intent in _NEEDS_VEHICLE:
                self.defaults.add("vehicle")
                return {"class": "motor_vehicle"}
            return None
        out: dict[str, Any] = {"class": v.vehicle_class}
        out.update({a: getattr(v, a) for a in _ATTRS if getattr(v, a) is not None})
        if v.priority:
            out["priority"] = True
        return out

    def when(self, w: WWhen | None) -> dict | None:
        if w is None:
            return None
        out: dict[str, Any] = {}
        if w.day is not None and w.month is not None:
            year = w.year
            if year is None:
                year = self.year
                self.defaults.add("year")
            out["date"] = dt.date(year, w.month, w.day).isoformat()
        for k in ("time", "start", "end", "quantifier"):
            if getattr(w, k) is not None:
                out[k] = getattr(w, k)
        return out or None

    @staticmethod
    def selector(s: WSelector | None) -> dict | None:
        if s is None:
            return None
        out = {k: v for k, v in s.model_dump().items() if v not in (None, False)}
        if s.only:
            out["only"] = True
        return out

    def program(self, p: Any) -> dict[str, Any]:
        d: dict[str, Any] = {"intent": p.intent}
        for name in type(p).model_fields:
            if name == "intent":
                continue
            v = getattr(p, name)
            if name == "vehicle":
                v = self.vehicle(v, p.intent)
            elif name == "when":
                v = self.when(v)
            elif name == "sign":
                v = self.selector(v)
            elif name == "claims":
                v = [self.program(c) for c in v]
            elif name == "claim":
                v = self.program(v)
            elif name == "options":
                v = [{"label": o.label, "claim": self.program(o.claim), "expect": o.expect}
                     for o in v]
            if v is not None:
                d[name] = v
        return d


_PROGRAM = TypeAdapter(Program)


def to_query(w: WParse, context_year: int | None = None) -> QueryProgram:
    """Wire answer -> QueryProgram (validated by the internal schemas)."""
    conv = _Converter(context_year or dt.date.today().year)
    if w.out_of_scope or w.program is None:
        return QueryProgram(out_of_scope=True,
                            out_of_scope_reason=w.out_of_scope_reason or "no DSL intent fits",
                            missing_slots=w.missing_slots)
    program = _PROGRAM.validate_python(conv.program(w.program))
    return QueryProgram(program=program, missing_slots=w.missing_slots,
                        defaults_applied=sorted(conv.defaults))


def compact(w: WParse) -> dict[str, Any]:
    """The wire answer without nulls / defaults: how examples are shown in the prompt."""
    return w.model_dump(exclude_none=True, exclude_defaults=True)
