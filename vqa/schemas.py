"""Contracts between the neural and symbolic sides (DESIGN.md, "Symbolic scene graph").

Three models live here:

* ``SceneGraph``  - what perception writes and the rule engine reads.
* ``QueryProgram`` - the typed question DSL the parser produces.
* ``Answer``       - the engine verdict plus its proof and citations.

All vocabulary that reaches Prolog (vehicle classes, actions, attributes) is an
enum, so the JSON schemas generated from these models only allow terms the
rule engine knows.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.1"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --------------------------------------------------------------------------- #
# Shared vocabulary (must match kb/ontology.pl)
# --------------------------------------------------------------------------- #


class VehicleClass(str, Enum):
    """Vehicle classes from Law 36/2024/QH15 art. 34 and the QCVN 41 sign texts."""

    vehicle = "vehicle"                  # any road vehicle
    motor_vehicle = "motor_vehicle"      # xe cơ giới
    car = "car"                          # xe ô tô (any kind)
    passenger_car = "passenger_car"      # xe ô tô con
    taxi = "taxi"                        # xe ô tô taxi
    bus = "bus"                          # xe ô tô chở khách in general (includes city buses)
    coach = "coach"                      # xe khách that is not a city bus ("xe khách 45 chỗ")
    city_bus = "city_bus"                # xe buýt
    truck = "truck"                      # xe ô tô tải
    motorbike = "motorbike"              # xe máy (mô tô + gắn máy)
    motorcycle = "motorcycle"            # xe mô tô hai bánh
    moped = "moped"                      # xe gắn máy
    sidecar = "sidecar"                  # xe máy 3 bánh có thùng
    motor_tricycle = "motor_tricycle"    # xe ba bánh có động cơ (xe lam, xích lô máy)
    special_machine = "special_machine"  # xe máy chuyên dùng
    tractor = "tractor"                  # máy kéo
    rudimentary = "rudimentary"          # xe thô sơ
    bicycle = "bicycle"                  # xe đạp
    cargo_bicycle = "cargo_bicycle"      # xe đạp thồ
    cyclo = "cyclo"                      # xe ba bánh không động cơ (xích lô)
    hand_cart = "hand_cart"              # xe người kéo, đẩy
    animal_cart = "animal_cart"          # xe vật nuôi kéo
    pedestrian = "pedestrian"            # người đi bộ (a road user, not a vehicle)


class Action(str, Enum):
    enter = "enter"              # đi vào / đi qua / lưu thông trên đoạn đường
    go_straight = "go_straight"
    turn_left = "turn_left"
    turn_right = "turn_right"
    u_turn = "u_turn"
    overtake = "overtake"
    stop = "stop"                # dừng xe
    park = "park"                # đỗ xe
    honk = "honk"


class VehicleAttr(str, Enum):
    load_t = "load_t"        # khối lượng chuyên chở (tonnes)
    gross_t = "gross_t"      # trọng tải toàn bộ (tonnes)
    seats = "seats"          # số chỗ ngồi
    height_m = "height_m"
    width_m = "width_m"
    length_m = "length_m"


class CompareOp(str, Enum):
    gt = "gt"
    ge = "ge"
    lt = "lt"
    le = "le"


class Condition(_Model):
    """A numeric condition on a vehicle attribute, e.g. seats > 29."""

    attr: VehicleAttr
    op: CompareOp
    value: float


class VehicleSpec(_Model):
    """A class of vehicles, optionally narrowed by conditions (plates, lane boards)."""

    cls: VehicleClass = Field(alias="class")
    conditions: list[Condition] = []


class Vehicle(_Model):
    """A concrete vehicle being asked about. Unset attributes are unknown, not zero."""

    cls: VehicleClass = Field(alias="class")
    load_t: float | None = None
    gross_t: float | None = None
    seats: int | None = None
    height_m: float | None = None
    width_m: float | None = None
    length_m: float | None = None
    priority: bool = False  # xe được quyền ưu tiên on an emergency mission


# --------------------------------------------------------------------------- #
# Scene graph
# --------------------------------------------------------------------------- #


class Confidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Shape(str, Enum):
    circle = "circle"
    triangle = "triangle"
    rectangle = "rectangle"
    square = "square"
    octagon = "octagon"
    diamond = "diamond"
    other = "other"


class Colour(str, Enum):
    red = "red"
    white = "white"
    blue = "blue"
    yellow = "yellow"
    black = "black"
    green = "green"
    none = "none"
    other = "other"


class Side(str, Enum):
    left = "left"
    right = "right"
    overhead = "overhead"
    center = "center"
    unknown = "unknown"


_HHMM = r"^([01]\d|2[0-4]):[0-5]\d$"


class TimeWindow(_Model):
    """A time-of-day window from an S.508 plate. ``end`` may be before ``start`` (overnight)."""

    start: Annotated[str, Field(pattern=_HHMM)]
    end: Annotated[str, Field(pattern=_HHMM)]

    def minutes(self) -> tuple[int, int]:
        def m(s: str) -> int:
            h, mm = s.split(":")
            return int(h) * 60 + int(mm)

        return m(self.start), m(self.end)


class DayParity(str, Enum):
    even = "even"
    odd = "odd"


class PlateKind(str, Enum):
    time = "time"            # S.508
    vehicle = "vehicle"      # S.505a: sign applies only to these vehicles
    exception = "exception"  # S.H,6: sign does not apply to these vehicles
    lane = "lane"            # S.504: sign applies only to these lanes
    distance = "distance"    # S.502
    text = "text"            # S.509 or anything else


class Plate(_Model):
    kind: PlateKind
    text: str | None = None
    code: str | None = None  # e.g. "S.508a"
    time_windows: list[TimeWindow] = []
    days: DayParity | None = None
    vehicles: list[VehicleSpec] = []
    lanes: list[int] = []
    distance_m: float | None = None


class Position(_Model):
    rank_top_down: int | None = None
    side: Side = Side.unknown
    lane: int | None = None  # lane the sign covers (1 = leftmost); None = whole road
    box: tuple[int, int, int, int] | None = None  # debug only, pixel x0,y0,x1,y1


class LaneSpec(_Model):
    """One row of a lane board (P.127b / P.127c / R.412 families).

    ``vehicles`` empty means the row applies to every vehicle on that lane.
    Several LaneSpec rows may share a lane when the board lists vehicle groups.
    """

    lane: Annotated[int, Field(ge=1)]
    vehicles: list[VehicleSpec] = []
    max_speed: float | None = None
    min_speed: float | None = None


class AltReading(_Model):
    """An alternative reading of a low-confidence sign (DESIGN.md, Verification)."""

    code: str
    value: float | None = None
    confidence: Confidence = Confidence.low


class Sign(_Model):
    id: str
    code: str  # catalog code, e.g. "P.127", or "UNKNOWN"
    value: float | None = None
    unit: str | None = None
    confidence: Confidence = Confidence.high
    shape: Shape | None = None
    border: Colour | None = None
    background: Colour | None = None
    position: Position = Position()
    plates: list[Plate] = []
    lanes: list[LaneSpec] = []
    alternatives: list[AltReading] = []


class RoadType(str, Enum):
    urban = "urban"
    rural = "rural"
    expressway = "expressway"
    unknown = "unknown"


class Road(_Model):
    type: RoadType = RoadType.unknown
    lanes: int | None = None
    intersection_ahead: bool | None = None
    divided: bool | None = None


class VehicleAction(str, Enum):
    driving = "driving"
    go_straight = "go_straight"
    turn_left = "turn_left"
    turn_right = "turn_right"
    u_turn = "u_turn"
    overtake = "overtake"
    stop = "stop"
    park = "park"
    crossing_line = "crossing_line"
    unknown = "unknown"


class SceneVehicle(_Model):
    id: str
    cls: VehicleClass = Field(alias="class")
    lane: int | None = None
    action: VehicleAction = VehicleAction.unknown
    speed_kmh: float | None = None
    target: VehicleClass | None = None
    confidence: Confidence = Confidence.medium


class SceneContext(_Model):
    datetime: dt.datetime | None = None
    weather: str | None = None


class SceneGraph(_Model):
    scene_id: str
    schema_version: str = SCHEMA_VERSION
    road: Road = Road()
    signs: list[Sign] = []
    vehicles: list[SceneVehicle] = []
    context: SceneContext = SceneContext()

    @model_validator(mode="after")
    def _unique_ids(self) -> "SceneGraph":
        ids = [s.id for s in self.signs] + [v.id for v in self.vehicles]
        if len(ids) != len(set(ids)):
            raise ValueError("sign and vehicle ids must be unique within a scene")
        return self

    def sign(self, sign_id: str) -> Sign:
        for s in self.signs:
            if s.id == sign_id:
                return s
        raise KeyError(sign_id)


# --------------------------------------------------------------------------- #
# Query program (DESIGN.md, "Question parsing")
# --------------------------------------------------------------------------- #


class When(_Model):
    """When the question is about. Either part may be missing (= unknown)."""

    date: dt.date | None = None
    time: dt.time | None = None


class Selector(_Model):
    """Points at signs in the scene by code or by how they look/where they are."""

    sign_id: str | None = None
    code: str | None = None
    shape: Shape | None = None
    border: Colour | None = None
    background: Colour | None = None
    rank_top_down: int | None = None
    position: Literal["top", "bottom"] | None = None
    side: Side | None = None
    only: bool = False  # "đây là biển gì?" - the single sign in the image


class Permitted(_Model):
    intent: Literal["permitted"] = "permitted"
    action: Action
    vehicle: Vehicle
    when: When | None = None
    sign: Selector | None = None


class SpeedOk(_Model):
    intent: Literal["speed_ok"] = "speed_ok"
    vehicle: Vehicle
    speed_kmh: float
    lane: int | None = None
    when: When | None = None


class LanesFor(_Model):
    """Which lanes may this vehicle use (optionally at this speed)?"""

    intent: Literal["lanes_for"] = "lanes_for"
    vehicle: Vehicle
    speed_kmh: float | None = None
    when: When | None = None


class LanesWhere(_Model):
    """Lanes where speed is OK (ok=True) or not OK (ok=False) for a vehicle."""

    intent: Literal["lanes_where"] = "lanes_where"
    vehicle: Vehicle
    speed_kmh: float
    ok: bool = True
    when: When | None = None


class BanTimes(_Model):
    intent: Literal["ban_times"] = "ban_times"
    vehicle: Vehicle
    action: Action = Action.enter
    sign: Selector | None = None


class Meaning(_Model):
    intent: Literal["meaning"] = "meaning"
    sign: Selector


class Required(_Model):
    intent: Literal["required"] = "required"
    action: Action
    vehicle: Vehicle | None = None
    placement: Literal["before_intersection", "after_intersection"] | None = None


class ExistsViolation(_Model):
    intent: Literal["exists_violation"] = "exists_violation"
    when: When | None = None


Claim = Annotated[
    Union[Permitted, SpeedOk, Required, ExistsViolation],
    Field(discriminator="intent"),
]


class Verify(_Model):
    """A true/false claim. ``expect`` False encodes 'not(...)' claims."""

    intent: Literal["verify"] = "verify"
    claim: Claim
    expect: bool = True


Program = Annotated[
    Union[Permitted, SpeedOk, LanesFor, LanesWhere, BanTimes, Meaning, Required,
          ExistsViolation, Verify],
    Field(discriminator="intent"),
]


class QueryProgram(_Model):
    program: Program
    missing_slots: list[str] = []
    out_of_scope: bool = False


# --------------------------------------------------------------------------- #
# Answer
# --------------------------------------------------------------------------- #


class Verdict(str, Enum):
    yes = "yes"
    no = "no"
    unknown = "unknown"
    uncertain = "uncertain"  # alternative sign readings disagree
    value = "value"          # the answer is in Answer.value


class Citation(_Model):
    law_id: str
    article_id: str

    def key(self) -> tuple[str, str]:
        return (self.law_id, self.article_id)


class ProofNode(_Model):
    """One node of the proof tree returned by the meta-interpreter (kb/meta.pl)."""

    type: Literal["rule", "fact", "cite", "naf", "builtin", "leaf"]
    goal: str | None = None
    rule: str | None = None
    source: Citation | None = None
    children: list["ProofNode"] = []


class Reason(_Model):
    """One sign-level reason behind a verdict, with its proof."""

    sign_id: str | None = None
    truth: Literal["true", "false", "unknown"]
    detail: str | None = None
    proof: ProofNode | None = None


class Answer(_Model):
    verdict: Verdict
    value: Any = None
    reasons: list[Reason] = []
    citations: list[Citation] = []
    uncertain_signs: list[str] = []
    note: str | None = None

    @field_validator("citations")
    @classmethod
    def _dedupe(cls, v: list[Citation]) -> list[Citation]:
        seen, out = set(), []
        for c in v:
            if c.key() not in seen:
                seen.add(c.key())
                out.append(c)
        return out
