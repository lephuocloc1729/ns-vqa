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

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator

SCHEMA_VERSION = "1.2"


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
    # Interpretation of Law 36 art. 34(2)(e) "xe tương tự": e.g. "xe 4 bánh thô sơ".
    # The law names no such class; proofs that use it cite it as an interpretation.
    similar_rudimentary = "similar_rudimentary"
    pedestrian = "pedestrian"            # người đi bộ (a road user, not a vehicle)
    # Not an ontology class: "các loại xe" / "mọi phương tiện". A claim about
    # every_vehicle holds only if it holds for every vehicle class. Unlike `vehicle`
    # (a vehicle of unknown kind).
    every_vehicle = "every_vehicle"


ONTOLOGY_CLASSES = [c for c in VehicleClass if c is not VehicleClass.every_vehicle]


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


# exact field -> (lower-bound field, upper-bound field); bounds are strict
_BOUNDS = {
    "seats": ("seats_gt", "seats_lt"),
    "load_t": ("load_gt", "load_lt"),
    "gross_t": ("gross_gt", "gross_lt"),
}


class Vehicle(_Model):
    """A vehicle being asked about. Unset attributes are unknown, not zero.

    A numeric attribute is either exact (``seats=45``) or bounded by strict
    comparisons (``seats_gt=29`` for "xe khách trên 29 chỗ"), never both.
    """

    cls: VehicleClass = Field(alias="class")
    load_t: float | None = None
    gross_t: float | None = None
    seats: int | None = None
    height_m: float | None = None
    width_m: float | None = None
    length_m: float | None = None
    seats_gt: int | None = None
    seats_lt: int | None = None
    load_gt: float | None = None
    load_lt: float | None = None
    gross_gt: float | None = None
    gross_lt: float | None = None
    priority: bool = False  # xe được quyền ưu tiên on an emergency mission

    @model_validator(mode="after")
    def _bounds(self) -> "Vehicle":
        for exact, (gt, lt) in _BOUNDS.items():
            lo, hi = getattr(self, gt), getattr(self, lt)
            if getattr(self, exact) is not None and (lo is not None or hi is not None):
                raise ValueError(f"{exact}: give an exact value or bounds, not both")
            if lo is not None and hi is not None and lo >= hi:
                raise ValueError(f"{exact}: empty range {gt}={lo}, {lt}={hi}")
        return self


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
    local = "local"          # non-standard plate (not in QCVN 41), e.g. red local text plates


class ConditionGroup(_Model):
    """One (vehicles, time) pair from a plate or board that lists several, e.g.
    "trucks <= 1.5 t: 6h-9h and 16h-19h30; trucks > 1.5 t: 6h-21h".
    Empty ``vehicles`` = every vehicle the sign covers; no time = all day."""

    vehicles: list[VehicleSpec] = []
    time_windows: list[TimeWindow] = []
    days: DayParity | None = None
    text: str | None = None


class Plate(_Model):
    """An auxiliary plate under a sign.

    kind=local is a non-standard plate (not in QCVN 41). Its text is kept verbatim
    and what it says is read into the fields: `vehicles` and `actions` replace the
    main sign's own vehicles and actions; `time_windows`/`days` work like an S.508
    plate; `rules` are condition groups. Proofs that use it are marked
    "non-standard plate" and Answer.basis gets "non_standard_plate".
    """

    kind: PlateKind
    text: str | None = None
    code: str | None = None  # e.g. "S.508a"
    time_windows: list[TimeWindow] = []
    days: DayParity | None = None
    vehicles: list[VehicleSpec] = []
    actions: list[Action] = []        # local plates only
    rules: list[ConditionGroup] = []  # local plates only
    lanes: list[int] = []
    distance_m: float | None = None

    @model_validator(mode="after")
    def _local_fields(self) -> "Plate":
        if self.kind == PlateKind.local and not self.text:
            raise ValueError("a local plate keeps its text")
        if self.kind != PlateKind.local and (self.actions or self.rules):
            raise ValueError("actions and rules are only read from local plates")
        return self


class Position(_Model):
    rank_top_down: int | None = None
    side: Side = Side.unknown
    lane: int | None = None  # lane the sign covers (1 = leftmost); None = whole road
    placement: Literal["before_intersection", "after_intersection"] | None = None
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
    # scene v6 (phase 4.7): the arrows an R.411 board shows on this lane (D.13). Left out of the
    # dump when empty, so stored scenes serialize as before.
    directions: list[Literal["straight", "left", "right", "u_turn", "slight_left", "slight_right"]] = []

    @model_serializer(mode="wrap")
    def _drop_empty_directions(self, handler):
        d = handler(self)
        if isinstance(d, dict) and not d.get("directions"):
            d.pop("directions", None)
        return d


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
    rules: list[ConditionGroup] = []  # the sign applies when any group matches
    lanes: list[LaneSpec] = []
    alternatives: list[AltReading] = []

    @model_validator(mode="after")
    def _rules_xor_plates(self) -> "Sign":
        groups = bool(self.rules) or any(p.rules for p in self.plates)
        if groups and any(p.kind in (PlateKind.vehicle, PlateKind.time) for p in self.plates):
            raise ValueError(f"{self.id}: use either condition groups (rules) or "
                             "vehicle/time plates, not both")
        if self.rules and any(p.rules for p in self.plates):
            raise ValueError(f"{self.id}: condition groups come from one place only")
        if sum(p.kind == PlateKind.local for p in self.plates) > 1:
            raise ValueError(f"{self.id}: at most one local plate")
        return self


class RoadType(str, Enum):
    urban = "urban"
    rural = "rural"
    expressway = "expressway"
    unknown = "unknown"


class RoadMarking(_Model):
    """Scene v6 (phase 4.7): a line on the road (QCVN 41 G.1). `kind`: center = the line between the
    two directions (G.1 1.x), lane_line = between lanes of one direction (2.x), edge (3.1),
    hatched = a channelising area (4.1-4.2), stop_line (G.2 7.1). `between`: the two lanes it
    separates (1 = leftmost), when it is a lane line."""

    kind: Literal["center", "lane_line", "edge", "hatched", "stop_line"]
    pattern: Literal["solid", "dashed", "double_solid", "solid_dashed", "dashed_solid"] | None = None
    colour: Literal["white", "yellow"] | None = None
    between: list[Annotated[int, Field(ge=1)]] = []
    confidence: Confidence = Confidence.medium


class TrafficSignal(_Model):
    """Scene v6 (phase 4.7): a traffic light facing the camera (QCVN 41 art. 6). `arrow`: the
    direction of an arrow light (none for a round one); `vehicle`: a light showing one vehicle
    type (6.4.2)."""

    kind: Literal["vehicle", "pedestrian"] = "vehicle"
    colour: Literal["red", "yellow", "green", "off"]
    arrow: Literal["none", "left", "straight", "right"] = "none"
    flashing: bool = False
    countdown: int | None = None
    confidence: Confidence = Confidence.medium


class Road(_Model):
    type: RoadType = RoadType.unknown
    lanes: int | None = None
    intersection_ahead: bool | None = None
    divided: bool | None = None
    markings: list[RoadMarking] = []       # scene v6 (phase 4.7); dropped from the dump when empty

    @model_serializer(mode="wrap")
    def _drop_empty_markings(self, handler):
        d = handler(self)
        if isinstance(d, dict) and not d.get("markings"):
            d.pop("markings", None)
        return d


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


class GuideEntry(_Model):
    """One destination / route line on a guide board (schema 1.3, phase 4.5 B6)."""

    text: str                                   # as printed, diacritics kept
    distance_m: float | None = None             # "61 KM" = 61000, "150 M" = 150
    direction: Literal["straight", "left", "right", "slight_left", "slight_right", "u_turn", "none"] = "none"


class BoardSpeed(_Model):
    kind: Literal["max", "min"]
    value: float


class GuideBoard(_Model):
    """A guide / information board read by the guide-board call (schema 1.3): its lines, the
    speed discs printed on or mounted with it, its route plate and other text. Scene-level:
    the board call returns no boxes, so boards are not tied to sign ids."""

    entries: list[GuideEntry] = []
    speeds: list[BoardSpeed] = []
    route: str | None = None
    other: list[str] = []


GUIDE_SCHEMA_VERSION = "1.3"


class SceneGraph(_Model):
    scene_id: str
    schema_version: str = SCHEMA_VERSION
    road: Road = Road()
    signs: list[Sign] = []
    vehicles: list[SceneVehicle] = []
    context: SceneContext = SceneContext()
    # schema 1.3 (phase 4.5 B6): boards read by the guide-board call. Left out of the dump when
    # empty, so scenes without boards serialize exactly as schema 1.2 did.
    guide_boards: list[GuideBoard] = []
    # scene v6 (phase 4.7): traffic lights; dropped from the dump when empty
    signals: list[TrafficSignal] = []

    @model_serializer(mode="wrap")
    def _drop_empty_boards(self, handler):
        d = handler(self)
        if isinstance(d, dict) and not d.get("guide_boards"):
            d.pop("guide_boards", None)
        if isinstance(d, dict) and not d.get("signals"):
            d.pop("signals", None)
        return d

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


class Quantifier(str, Enum):
    all = "all"  # the statement holds at every moment of the interval
    any = "any"  # the statement holds at some moment of the interval


class When(_Model):
    """When the question is about: a moment (``time``) or an interval
    (``start``..``end``, may run past midnight) with a quantifier. Any part may be
    missing (= unknown). The quantifier applies to what the program states:
    Permitted(all) = permitted throughout; Forbidden(all) = forbidden throughout."""

    date: dt.date | None = None
    time: dt.time | None = None
    start: dt.time | None = None
    end: dt.time | None = None
    quantifier: Quantifier | None = None
    # phase 4.6 (D3, train_84 wording): "vào ngày chẵn / lẻ" with no date; the engine takes a
    # day of that parity (P.131b / P.131c only depend on the parity, QCVN 41 B.31)
    day_parity: Literal["even", "odd"] | None = None

    @model_validator(mode="after")
    def _shape(self) -> "When":
        interval = self.start is not None or self.end is not None
        if interval and (self.start is None or self.end is None):
            raise ValueError("an interval needs both start and end")
        if interval and self.time is not None:
            raise ValueError("give either a time or an interval, not both")
        if interval and self.quantifier is None:
            raise ValueError("an interval needs a quantifier (all or any)")
        if not interval and self.quantifier is not None:
            raise ValueError("a quantifier only goes with an interval")
        return self

    @property
    def is_interval(self) -> bool:
        return self.start is not None


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
    meaning: str | None = None  # a catalog key or tag, e.g. "no_motorbikes", "speed_limit"
    # phase 4.5: the sign group ("biển cấm" = prohibitory, ...), e.g. "biển trong ảnh cấm hành vi gì?"
    category: Literal["prohibitory", "mandatory", "warning", "information", "auxiliary",
                      "end_of_restriction"] | None = None
    only: bool = False  # "đây là biển gì?" - the single sign in the image


def _question_lane(v: int | None) -> int | None:
    if v is not None and (v == 0 or v < -8):
        raise ValueError("lane: 1 = leftmost, -1 = rightmost (counted from the right); 0 is not a lane")
    return v


# A lane the question names (phase 4.5 B2, the lane fix): 1, 2, ... from the left; -1, -2, ...
# from the right ("làn ngoài cùng bên phải" = -1). The engine turns a negative lane into its
# number from the scene's lane count, and answers unknown when the count isn't known.
QuestionLane = Annotated[int, AfterValidator(_question_lane)]


class Permitted(_Model):
    intent: Literal["permitted"] = "permitted"
    action: Action
    vehicle: Vehicle
    when: When | None = None
    sign: Selector | None = None
    lane: QuestionLane | None = None  # 1 = leftmost, -1 = rightmost; lane rules then apply too


class Forbidden(_Model):
    """Direct form of "not permitted"; compiles to Verify(Permitted(...), expect=False)
    with the interval quantifier flipped (vqa/parsing/dsl.py)."""

    intent: Literal["forbidden"] = "forbidden"
    action: Action
    vehicle: Vehicle
    when: When | None = None
    sign: Selector | None = None
    lane: QuestionLane | None = None


class SpeedOk(_Model):
    intent: Literal["speed_ok"] = "speed_ok"
    vehicle: Vehicle
    speed_kmh: float
    lane: QuestionLane | None = None
    when: When | None = None
    road_divided: bool | None = None   # phase 4.5: "đường có / không có dải phân cách", stated in the question


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


class LaneVehicles(_Model):
    """ "Làn N dành cho những xe nào?": the vehicle classes allowed (or banned) on a lane,
    optionally at a speed."""

    intent: Literal["lane_vehicles"] = "lane_vehicles"
    lane: QuestionLane
    status: Literal["allowed", "banned"] = "allowed"
    speed_kmh: float | None = None
    when: When | None = None


class SpeedLimit(_Model):
    """ "Tốc độ tối đa (tối thiểu) là bao nhiêu?": the binding limit for a vehicle,
    on a lane or (with no lane) overall and per lane."""

    intent: Literal["speed_limit"] = "speed_limit"
    vehicle: Vehicle = Field(default_factory=lambda: Vehicle(**{"class": "motor_vehicle"}))
    lane: QuestionLane | None = None
    kind: Literal["max", "min", "range"] = "max"   # phase 4.6 I4: "range" = both, "trong khoảng tốc độ nào"
    when: When | None = None
    road_divided: bool | None = None   # phase 4.5: stated in the question
    vehicles: list[Vehicle] = []       # phase 4.5: several vehicles at once ("ô tô con và xe tải ...")


class SpeedLimitIs(_Model):
    """Phase 4.6 I4: "tốc độ tối đa (tối thiểu) là X km/h, đúng không?": the binding limit
    for the vehicle (on the lane) equals the stated value."""

    intent: Literal["speed_limit_is"] = "speed_limit_is"
    kind: Literal["max", "min"] = "max"
    value_kmh: float
    vehicle: Vehicle = Field(default_factory=lambda: Vehicle(**{"class": "motor_vehicle"}))
    lane: QuestionLane | None = None


class BanTimes(_Model):
    intent: Literal["ban_times"] = "ban_times"
    vehicle: Vehicle
    action: Action = Action.enter
    sign: Selector | None = None


class Meaning(_Model):
    """What is the selected sign / what does it mean. Phase 4.5 aspects: its art. 11 group
    ("thuộc nhóm nào"), what it requires of the driver ("người lái xe cần làm gì"), where it
    takes effect ("có hiệu lực từ đâu đến đâu"), and where it is placed ("đặt ở đâu")."""

    intent: Literal["meaning"] = "meaning"
    sign: Selector
    # phase 4.6 I1: "article" = the QCVN 41 article the sign is set out in ("quy định ở điều nào")
    aspect: Literal["name", "group", "conduct", "scope", "placement", "article"] = "name"


GuideDirection = Literal["straight", "left", "right", "u_turn"]
GuideFeature = Literal["tunnel", "expressway", "junction", "roundabout", "exit"]
RoadKind = Literal["expressway", "national_road"]


class Guide(_Model):
    """Phase 4.5 B6: what a guide board in the photo says. `ask`: the direction to a
    destination, the distance to it, the destinations listed, or the route plate.
    Phase 4.6 I2: `road_type` (expressway / national road, from the signs, the route plate and
    the scene), and `destinations` filtered by the arrow `direction`."""

    intent: Literal["guide"] = "guide"
    ask: Literal["direction", "distance", "destinations", "route", "road_type"]
    destination: str | None = None
    direction: GuideDirection | None = None


class GuideClaim(_Model):
    """Phase 4.6 I2: a stated claim checked against the boards and signs, read from the scene
    data only. `about`:
    - `distance`: the board gives `distance_m` to `destination`;
    - `direction`: the board's arrow to `destination` points `direction`;
    - `listed`: the board names `destination` (a place, road or route);
    - `road_type`: this road is a `road_type` road;
    - `ahead`: a `feature` lies ahead (a sign for it, or a board line naming it)."""

    intent: Literal["guide_claim"] = "guide_claim"
    about: Literal["distance", "direction", "listed", "road_type", "ahead"]
    destination: str | None = None
    distance_m: float | None = None
    direction: GuideDirection | None = None
    road_type: RoadKind | None = None
    feature: GuideFeature | None = None

    @model_validator(mode="after")
    def _slots(self) -> "GuideClaim":
        need = {"distance": ("destination", "distance_m"), "direction": ("destination", "direction"),
                "listed": ("destination",), "road_type": ("road_type",), "ahead": ("feature",)}[self.about]
        if missing := [f for f in need if getattr(self, f) in (None, "")]:
            raise ValueError(f"guide_claim about={self.about} needs {', '.join(missing)}")
        return self


class Required(_Model):
    intent: Literal["required"] = "required"
    action: Action
    vehicle: Vehicle | None = None
    placement: Literal["before_intersection", "after_intersection"] | None = None


class ExistsViolation(_Model):
    intent: Literal["exists_violation"] = "exists_violation"
    when: When | None = None


SignCategory = Literal["prohibitory", "mandatory", "warning", "information", "auxiliary",
                       "end_of_restriction"]


class IsSign(_Model):
    """ "Đây là biển X, đúng hay sai?": the selected sign is X, given as a catalog code
    (a family code like "W.221" also matches its variants), a catalog meaning
    (key or tag), or a category ("biển cấm" = prohibitory, ...). Exactly one."""

    intent: Literal["is_sign"] = "is_sign"
    sign: Selector
    code: str | None = None
    meaning: str | None = None
    category: SignCategory | None = None

    @model_validator(mode="after")
    def _one_target(self) -> "IsSign":
        if sum(x is not None for x in (self.code, self.meaning, self.category)) != 1:
            raise ValueError("is_sign needs exactly one of code, meaning, category")
        return self


class Present(_Model):
    """Phase 4.5: is a sign of this code / meaning / category in the photo? Closed world over
    the readable signs; an unread sign that could be it makes the answer unknown."""

    intent: Literal["present"] = "present"
    code: str | None = None
    meaning: str | None = None
    category: SignCategory | None = None

    @model_validator(mode="after")
    def _one_target(self) -> "Present":
        if sum(x is not None for x in (self.code, self.meaning, self.category)) != 1:
            raise ValueError("present needs exactly one of code, meaning, category")
        return self


class Place(str, Enum):
    """Phase 4.7 step 1c: places named in Law 36/2024's general rules (kb/rules/general47.pl):
    art. 14.6 (no overtaking), 15.4 (no U-turns), 18.4 (no stopping or parking), 25 (expressways)."""
    bridge = "bridge"                                     # "trên cầu"
    narrow_one_lane_bridge = "narrow_one_lane_bridge"     # "cầu hẹp có một làn đường"
    bridge_head = "bridge_head"                           # "đầu cầu"
    under_overpass = "under_overpass"                     # "gầm cầu vượt"
    ford = "ford"                                         # "ngầm"
    tunnel = "tunnel"                                     # "hầm đường bộ"
    intersection = "intersection"                         # "nơi đường giao nhau"
    railway_crossing = "railway_crossing"                 # "giao nhau cùng mức với đường sắt"
    railway_safety_zone = "railway_safety_zone"           # "phạm vi an toàn của đường sắt"
    pedestrian_crossing = "pedestrian_crossing"           # "phần đường dành cho người đi bộ qua đường"
    curve_limited_view = "curve_limited_view"             # "đường cong có tầm nhìn bị hạn chế / che khuất"
    hill_crest_limited_view = "hill_crest_limited_view"   # "đỉnh dốc / gần đầu dốc, tầm nhìn bị hạn chế"
    slope = "slope"                                       # "đường dốc"
    narrow_road = "narrow_road"                           # "đường hẹp"
    one_lane_width = "one_lane_width"                     # "chiều rộng chỉ đủ cho một làn xe cơ giới"
    one_way_road = "one_way_road"                         # "đường một chiều"
    one_way_road_left_side = "one_way_road_left_side"     # "bên trái đường một chiều"
    expressway = "expressway"                             # "đường cao tốc"
    emergency_lane = "emergency_lane"                     # "làn dừng xe khẩn cấp"
    pickup_point = "pickup_point"                         # "điểm đón, trả khách"
    bus_lane = "bus_lane"                                 # "đường dành riêng cho xe buýt"


class RulePermitted(_Model):
    """Phase 4.7 step 1c: may the vehicle do this, under the signs in the photo and Law 36's
    general rules? ("Xe có được quay đầu trên cầu không?", "Xe cứu thương làm nhiệm vụ có được chạy
    70 km/h không?", "Xe đạp có được đi ở làn trái không?"). No when a sign or a general rule forbids
    it; yes when the signs allow it and no general rule the question's facts trigger forbids it.
    `stop_reason` is for stops in the emergency lane (art. 25.2: only on a breakdown).
    `area: outside_residential` with `road_divided` gives Circular 38 art. 7's limits
    (interpretation) when no speed sign applies."""

    intent: Literal["rule_permitted"] = "rule_permitted"
    action: Action = Action.enter
    vehicle: Vehicle = Field(default_factory=lambda: Vehicle(**{"class": "motor_vehicle"}))
    place: Place | None = None
    lane: QuestionLane | None = None
    speed_kmh: float | None = None
    area: Literal["outside_residential"] | None = None
    road_divided: bool | None = None
    stop_reason: Literal["breakdown", "other"] | None = None
    # scene v6 (phase 4.7 step 1d): crossing the centre line ("lấn sang làn ngược chiều, đè vạch")
    # or changing lanes across a lane line (G.1); and, for a yellow light, whether the vehicle is
    # already on or past the stop line (art. 6.3.2)
    maneuver: Literal["cross_center", "change_lane"] | None = None
    past_stop_line: bool | None = None
    # the question asks about passing a traffic light ("gặp đèn tín hiệu ... có được đi tiếp không"):
    # with no light read in the photo the answer is unknown, never a yes from the signs alone (art. 6)
    at_signal: bool = False


DutyTopic = Literal["speed_and_distance", "lane_change", "overtaking", "turning", "stopping_parking",
                    "priority_vehicle_signal", "expressway"]


class Duties(_Model):
    """Phase 4.7 step 1c: what Law 36's general rules require of the driver in a situation
    ("Khi chuyển làn, người lái xe phải làm gì?"), from kb/general_duties_47.yaml."""

    intent: Literal["duties"] = "duties"
    topic: DutyTopic


class SignalMeaning(_Model):
    """Scene v6 (phase 4.7 step 1d): what the traffic light in the photo shows and means (art. 6)."""

    intent: Literal["signal_meaning"] = "signal_meaning"


MarkingKind = Literal["center", "lane_line", "edge", "hatched", "stop_line"]
MarkingPattern = Literal["solid", "dashed", "double_solid", "solid_dashed", "dashed_solid"]


class MarkingMeaning(_Model):
    """Scene v6: what a road marking in the photo means (G.1, G.2), optionally only those of a
    kind or pattern ("vạch liền trong ảnh có ý nghĩa gì?")."""

    intent: Literal["marking_meaning"] = "marking_meaning"
    kind: MarkingKind | None = None
    pattern: MarkingPattern | None = None


class MarkingIs(_Model):
    """Scene v6 claim: the markings of this pattern (or kind) in the photo separate
    `separates` ("Vạch liền trong ảnh có dùng để phân chia các làn xe cùng chiều không?")."""

    intent: Literal["marking_is"] = "marking_is"
    pattern: MarkingPattern | None = None
    kind: MarkingKind | None = None
    separates: Literal["same_direction_lanes", "opposite_directions"]


class Count(_Model):
    """Phase 4.7 (owner, 2026-11-17): "Trong ảnh có bao nhiêu biển cấm?": how many signs match the
    selector (group, look, name or code). Plates are not counted as signs (art. 41). An unread sign
    that could match makes the count a range, and the answer unknown with that range. With
    `vehicle`: only the signs whose effect is addressed to that vehicle ("áp dụng cho xe máy")."""

    intent: Literal["count"] = "count"
    sign: Selector = Selector()
    vehicle: Vehicle | None = None


class CountIs(_Model):
    """Phase 4.7: the claim form of `count`: "Trong ảnh có hai biển cấm, đúng không?". Yes when the
    count is exactly n, no when n is outside the possible range, unknown otherwise."""

    intent: Literal["count_is"] = "count_is"
    sign: Selector = Selector()
    n: Annotated[int, Field(ge=0)]
    vehicle: Vehicle | None = None


class AppliesTo(_Model):
    """Phase 4.7: "Biển này áp dụng cho những loại xe nào?": the vehicle classes the selected
    sign's effect is addressed to (bans, mandatory directions, maximum speeds), with its stated
    exceptions. Who, not when: time and day plates are left out (kb/rules/coverage47.pl)."""

    intent: Literal["applies_to"] = "applies_to"
    sign: Selector = Selector(only=True)


class SignApplies(_Model):
    """Phase 4.7: the claim form: "Biển này áp dụng cho cả xe cơ giới lẫn xe thô sơ, đúng không?".
    Yes when the sign is addressed to every listed vehicle, no when it surely isn't to one."""

    intent: Literal["sign_applies"] = "sign_applies"
    sign: Selector = Selector(only=True)
    vehicles: Annotated[list[Vehicle], Field(min_length=1)]


class AllOf(_Model):
    """A and B (and ...): yes when every claim holds."""

    intent: Literal["all_of"] = "all_of"
    claims: Annotated[list["Claim"], Field(min_length=2)]


class AnyOf(_Model):
    """A or B (or ...): yes when some claim holds."""

    intent: Literal["any_of"] = "any_of"
    claims: Annotated[list["Claim"], Field(min_length=2)]


Claim = Annotated[
    Union[Permitted, Forbidden, SpeedOk, Required, ExistsViolation, IsSign, Present, GuideClaim,
          SpeedLimitIs, AllOf, AnyOf, CountIs, SignApplies, RulePermitted, MarkingIs],
    Field(discriminator="intent"),
]
AllOf.model_rebuild()
AnyOf.model_rebuild()


class Verify(_Model):
    """A true/false claim. ``expect`` False encodes 'not(...)' claims."""

    intent: Literal["verify"] = "verify"
    claim: Claim
    expect: bool = True


class WhichVehicles(_Model):
    """ "Phương tiện nào bị cấm / được phép ...?": the vehicle classes (and road users)
    for which the action is banned, or allowed. Classes are checked one by one and
    reported at the broadest level that holds as a whole."""

    intent: Literal["which_vehicles"] = "which_vehicles"
    action: Action = Action.enter
    status: Literal["banned", "allowed"] = "banned"
    when: When | None = None
    sign: Selector | None = None


class ChoiceOption(_Model):
    label: str
    claim: Claim
    expect: bool = True  # the option "holds" when the claim's answer matches, as in Verify


class Choose(_Model):
    """ "Trong các ..., ... nào ...?": returns the options that hold."""

    intent: Literal["choose"] = "choose"
    options: Annotated[list[ChoiceOption], Field(min_length=1)]


class Explain(_Model):
    """Phase 4.6 I3: "vì sao", "xe nào bị phạt và vì sao": the wrapped claim (or choice) is
    answered with the reasons the proof gives. "Bị phạt" is read as "breaks the rule"; fine
    amounts are not modelled."""

    intent: Literal["explain"] = "explain"
    program: Annotated[Union[Permitted, Forbidden, SpeedOk, Required, ExistsViolation, IsSign, Present,
                             GuideClaim, SpeedLimitIs, AllOf, AnyOf, Verify, Choose, CountIs, SignApplies,
                             RulePermitted, MarkingIs],
                       Field(discriminator="intent")]


_PART = Annotated[
    Union[Permitted, Forbidden, SpeedOk, LanesFor, LanesWhere, BanTimes, Meaning, Required,
          ExistsViolation, Verify, Choose, IsSign, AllOf, AnyOf, WhichVehicles, LaneVehicles,
          SpeedLimit, Present, Guide, GuideClaim, SpeedLimitIs, Explain, Count, CountIs, AppliesTo,
          SignApplies, RulePermitted, Duties, SignalMeaning, MarkingMeaning, MarkingIs],
    Field(discriminator="intent"),
]


class Multi(_Model):
    """Phase 4.6 I1: two or three asks in one question. Each part is answered on its own;
    the question is decided only when every part is."""

    intent: Literal["multi"] = "multi"
    parts: Annotated[list[_PART], Field(min_length=2, max_length=3)]


Program = Annotated[
    Union[Permitted, Forbidden, SpeedOk, LanesFor, LanesWhere, BanTimes, Meaning, Required,
          ExistsViolation, Verify, Choose, IsSign, AllOf, AnyOf, WhichVehicles, LaneVehicles,
          SpeedLimit, Present, Guide, GuideClaim, SpeedLimitIs, Explain, Multi, Count, CountIs,
          AppliesTo, SignApplies, RulePermitted, Duties, SignalMeaning, MarkingMeaning, MarkingIs],
    Field(discriminator="intent"),
]


class QueryProgram(_Model):
    """What the parser returns. A question no DSL intent can express comes back as
    out_of_scope with no program, so it can go to the fallback."""

    program: Program | None = None
    missing_slots: list[str] = []
    out_of_scope: bool = False
    out_of_scope_reason: str | None = None
    # values the question left out and the parser filled in, e.g. ["year", "vehicle"]
    defaults_applied: list[str] = []

    @model_validator(mode="after")
    def _program_xor_out_of_scope(self) -> "QueryProgram":
        if self.out_of_scope == (self.program is not None):
            raise ValueError("give a program, or out_of_scope=true with no program")
        return self


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
    # What the answer rests on beyond QCVN 41 / Law 36, e.g. "non_standard_plate".
    basis: list[str] = []

    @field_validator("citations")
    @classmethod
    def _dedupe(cls, v: list[Citation]) -> list[Citation]:
        seen, out = set(), []
        for c in v:
            if c.key() not in seen:
                seen.add(c.key())
                out.append(c)
        return out
