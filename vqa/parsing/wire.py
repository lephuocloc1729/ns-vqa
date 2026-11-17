"""The parser's output format ("wire" models) and its conversion to QueryProgram.

The model replies with one JSON object in plain text; no JSON schema is sent. The
API caps strict schemas (output_config.format) at 24 optional and 16 union-typed
parameters in total, far below what this DSL needs: three attempts on 2026-11-15
were rejected with "The compiled grammar is too large". These Pydantic models are
the contract instead: from_wire() validates a reply against them, and explain()
turns a validation error into a short message for the parser's retry.

Nesting is capped at one level (claims inside verify / choose / all_of / any_of
are plain claims). The cap first came from structured outputs rejecting recursive
schemas; no schema is sent any more, but the cap is kept for now:

    leaf claim  = permitted | forbidden | speed_ok | required | exists_violation | is_sign
    claim       = leaf claim | all_of(leaf claims) | any_of(leaf claims)
    program     = claim | verify(claim) | choose(options of claims)
                | lanes_for | lanes_where | ban_times | meaning | which_vehicles
                | lane_vehicles | speed_limit | guide
                | explain(claim | verify | choose)             (phase 4.6 I3)
                | multi(2-3 of the programs above but multi)   (phase 4.6 I1)
    phase 4.6 leaf claims add guide_claim (I2) and speed_limit_is (I4).

Vehicle classes and actions are enums from the ontology. Sign codes and meaning
keys/tags are strings checked against the catalog (the system prompt's catalog
table lists them), with a short error the retry can act on. The unions are
discriminated on `intent`, so an error names the variant the reply chose.

Defaults the parser fills (recorded in QueryProgram.defaults_applied):
  year     a date with day and month but no year gets the context year
  vehicle  an intent that needs a vehicle gets motor_vehicle when none is named
"""

from __future__ import annotations

import datetime as dt
import difflib
import re
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from vqa.kb import load_catalog
from vqa.schemas import Action, Colour, Place, Program, QueryProgram, Shape, Side, VehicleClass

_CATALOG = load_catalog()

VehicleClassLit = Literal[tuple(c.value for c in VehicleClass)]  # type: ignore[valid-type]
ActionLit = Literal[tuple(a.value for a in Action)]  # type: ignore[valid-type]
_MEANINGS = frozenset({s.key for s in _CATALOG.signs} | {t for s in _CATALOG.signs for t in s.tags})

# A program may name any sign code the engine resolves: Catalog.codes_matching is
# the single source of truth (a row code, a variant such as "W.207c", the stem of a
# family row such as "W.207", or a stem of separate rows such as "W.221" = W.221a or
# W.221b). The value is kept as written; the engine resolves it the same way in
# is_sign targets and in selectors (Catalog.code_selects).
def _resolves(code: str) -> bool:
    try:
        _CATALOG.codes_matching(code)
    except KeyError:
        return False
    return True


# Candidates for the "closest valid codes" hint only (acceptance never uses this):
# every row and variant code, and every stem, kept if the catalog resolves it.
_SUGGESTIONS = sorted(c for c in (
    {s.code for s in _CATALOG.signs}
    | {s.base + v for s in _CATALOG.signs for v in s.variants}
    | {s.base for s in _CATALOG.signs}
    | {re.sub(r"[a-z]$", "", s.code) for s in _CATALOG.signs}) if _resolves(c))


def _known_code(v: str) -> str:
    if _resolves(v):
        return v
    near = difflib.get_close_matches(v, _SUGGESTIONS, n=5, cutoff=0.6)
    hint = f"; closest valid codes: {', '.join(near)}" if near else ""
    raise ValueError(f"unknown sign code {v!r}: use a code from the sign catalog table{hint}")


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
    day_parity: Optional[Literal["even", "odd"]] = None   # phase 4.6: "vào ngày chẵn / lẻ", no date


class WSelector(_W):
    code: Optional[CodeLit] = None
    meaning: Optional[MeaningLit] = None
    shape: Optional[ShapeLit] = None
    border: Optional[ColourLit] = None
    background: Optional[ColourLit] = None
    position: Optional[Literal["top", "bottom"]] = None
    rank_top_down: Optional[int] = None
    side: Optional[SideLit] = None
    category: Optional[CategoryLit] = None     # phase 4.5: "biển cấm trong ảnh ..."
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
    road_divided: Optional[bool] = None


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


class WPresent(_W):
    intent: Literal["present"]
    code: Optional[CodeLit] = None
    meaning: Optional[MeaningLit] = None
    category: Optional[CategoryLit] = None


GuideDirectionLit = Literal["straight", "left", "right", "u_turn"]


class WGuideClaim(_W):                       # phase 4.6 I2
    intent: Literal["guide_claim"]
    about: Literal["distance", "direction", "listed", "road_type", "ahead"]
    destination: Optional[str] = None
    distance_m: Optional[float] = None
    direction: Optional[GuideDirectionLit] = None
    road_type: Optional[Literal["expressway", "national_road"]] = None
    feature: Optional[Literal["tunnel", "expressway", "junction", "roundabout", "exit"]] = None


class WSpeedLimitIs(_W):                     # phase 4.6 I4
    intent: Literal["speed_limit_is"]
    kind: Literal["max", "min"] = "max"
    value_kmh: float
    vehicle: Optional[WVehicle] = None
    lane: Optional[int] = None


class WCountIs(_W):                          # phase 4.7
    intent: Literal["count_is"]
    sign: Optional[WSelector] = None
    n: int
    vehicle: Optional[WVehicle] = None


class WSignApplies(_W):                      # phase 4.7
    intent: Literal["sign_applies"]
    sign: Optional[WSelector] = None
    vehicles: list[WVehicle]


PlaceLit = Literal[tuple(x.value for x in Place)]  # type: ignore[valid-type]


class WRulePermitted(_W):                    # phase 4.7 step 1c
    intent: Literal["rule_permitted"]
    action: ActionLit = "enter"
    vehicle: Optional[WVehicle] = None
    place: Optional[PlaceLit] = None
    lane: Optional[int] = None
    speed_kmh: Optional[float] = None
    area: Optional[Literal["outside_residential"]] = None
    road_divided: Optional[bool] = None
    stop_reason: Optional[Literal["breakdown", "other"]] = None
    maneuver: Optional[Literal["cross_center", "change_lane"]] = None
    past_stop_line: Optional[bool] = None


class WDuties(_W):                           # phase 4.7 step 1c
    intent: Literal["duties"]
    topic: Literal["speed_and_distance", "lane_change", "overtaking", "turning", "stopping_parking",
                   "priority_vehicle_signal", "expressway"]


_MKIND = Literal["center", "lane_line", "edge", "hatched", "stop_line"]
_MPAT = Literal["solid", "dashed", "double_solid", "solid_dashed", "dashed_solid"]


class WMarkingIs(_W):                        # phase 4.7 step 1d (scene v6)
    intent: Literal["marking_is"]
    pattern: Optional[_MPAT] = None
    kind: Optional[_MKIND] = None
    separates: Literal["same_direction_lanes", "opposite_directions"]


class WSignalMeaning(_W):                    # phase 4.7 step 1d
    intent: Literal["signal_meaning"]


class WMarkingMeaning(_W):                   # phase 4.7 step 1d
    intent: Literal["marking_meaning"]
    kind: Optional[_MKIND] = None
    pattern: Optional[_MPAT] = None


class WCount(_W):                            # phase 4.7
    intent: Literal["count"]
    sign: Optional[WSelector] = None
    vehicle: Optional[WVehicle] = None


class WAppliesTo(_W):                        # phase 4.7
    intent: Literal["applies_to"]
    sign: Optional[WSelector] = None


_LEAF_MODELS = (WPermitted, WForbidden, WSpeedOk, WRequired, WExistsViolation, WIsSign, WPresent,
                WGuideClaim, WSpeedLimitIs, WCountIs, WSignApplies, WRulePermitted, WMarkingIs)
LeafClaim = Annotated[Union[_LEAF_MODELS], Field(discriminator="intent")]


class WAllOf(_W):
    intent: Literal["all_of"]
    claims: list[LeafClaim]


class WAnyOf(_W):
    intent: Literal["any_of"]
    claims: list[LeafClaim]


_CLAIM_MODELS = _LEAF_MODELS + (WAllOf, WAnyOf)
Claim = Annotated[Union[_CLAIM_MODELS], Field(discriminator="intent")]


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
    aspect: Literal["name", "group", "conduct", "scope", "placement", "article"] = "name"


class WGuide(_W):
    intent: Literal["guide"]
    ask: Literal["direction", "distance", "destinations", "route", "road_type"]
    destination: Optional[str] = None
    direction: Optional[GuideDirectionLit] = None        # phase 4.6: destinations by arrow


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
    kind: Literal["max", "min", "range"] = "max"
    vehicle: Optional[WVehicle] = None
    lane: Optional[int] = None
    when: Optional[WWhen] = None
    road_divided: Optional[bool] = None
    vehicles: list[WVehicle] = []


class WExplain(_W):                          # phase 4.6 I3
    intent: Literal["explain"]
    program: Annotated[Union[_CLAIM_MODELS + (WVerify, WChoose)], Field(discriminator="intent")]


_PART_MODELS = _CLAIM_MODELS + (WVerify, WChoose, WLanesFor, WLanesWhere, WBanTimes,
                                WMeaning, WWhichVehicles, WLaneVehicles, WSpeedLimit, WGuide, WExplain,
                                WCount, WAppliesTo, WDuties, WSignalMeaning, WMarkingMeaning)
Part = Annotated[Union[_PART_MODELS], Field(discriminator="intent")]


class WMulti(_W):                            # phase 4.6 I1
    intent: Literal["multi"]
    parts: list[Part]


_PROGRAM_MODELS = _PART_MODELS + (WMulti,)
WProgram = Annotated[Union[_PROGRAM_MODELS], Field(discriminator="intent")]


class WParse(_W):
    """The parser's whole answer."""

    out_of_scope: bool = False
    out_of_scope_reason: Optional[str] = None
    missing_slots: list[str] = []
    program: Optional[WProgram] = None


# --------------------------------------------------------------------------- parse

def explain(e: ValidationError) -> str:
    """A short message for a wire validation error. The program is a union, so
    Pydantic reports a mismatch for every variant; the catalog errors (unknown code
    or meaning) are the useful part when present."""
    errs = e.errors()
    values = [x["msg"].removeprefix("Value error, ") for x in errs if x["type"] == "value_error"]
    if values:
        return "; ".join(dict.fromkeys(values))      # the same field fails in every variant
    return "; ".join(f"{'.'.join(str(p) for p in x['loc'])}: {x['msg']}" for x in errs[:3])


def _drop_nulls(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _drop_nulls(v) for k, v in node.items() if v is not None}
    if isinstance(node, list):
        return [_drop_nulls(x) for x in node]
    return node


def from_wire(data: dict[str, Any]) -> WParse:
    """A reply object as a typed WParse. Null fields are dropped, so they take the
    models' defaults. Raises ValidationError on a field the intent does not use."""
    return WParse.model_validate(_drop_nulls(data))


# --------------------------------------------------------------------------- convert

_NEEDS_VEHICLE = {"permitted", "forbidden", "speed_ok", "lanes_for", "lanes_where", "ban_times",
                  "rule_permitted"}
# speed_limit and speed_limit_is default to motor_vehicle in the schema itself (no default recorded)
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
        for k in ("time", "start", "end", "quantifier", "day_parity"):
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
            elif name in ("claim", "program"):
                v = self.program(v)
            elif name == "parts":
                v = [self.program(x) for x in v]
            elif name == "vehicles":
                v = [self.vehicle(x, "speed_limit") for x in v] or None
            elif name == "aspect" and v == "name":
                v = None
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
