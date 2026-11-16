"""The scene call's reply format, and its conversion to a SceneGraph
(docs/plans/phase-3.md, item 3).

The model replies with one plain JSON object; no JSON schema is sent (a code enum
over the catalog would hit the API's strict-schema limits, as the parser did).
Everything is checked here, in Python, against the catalog and the enums in
vqa/schemas.py:

    {"signs": [{"code": "P.127", "confidence": "high", "value": 50, "unit": "km/h",
                "shape": "circle", "border": "red", "background": "white",
                "rank": 1, "side": "right", "lane": null, "box": [x0, y0, x1, y1],
                "plates": [{"kind": "time", "text": "6h-22h",
                            "time_windows": [{"start": "06:00", "end": "22:00"}]}],
                "rules": [], "lanes": [], "alt": {"code": "P.127b", "value": 50}}],
     "road": {"type": "urban", "lanes": 3, "intersection_ahead": false},
     "vehicles": [{"class": "truck", "lane": 2, "action": "overtake", "target": "motorbike"}]}

Codes: a catalog code or variant ("W.207c") is kept as written; a family stem that
names one row ("W.207") becomes that row's code; "UNKNOWN" is allowed. Anything
else is an error. A vehicle may be written as a bare class name ("car").

Two modes:
- strict: every problem is an error (for the one retry, which sends the errors);
- final (after the retry): an invalid code becomes UNKNOWN, with the raw reading
  kept in `raw_codes` beside the scene, not in it; any other invalid part (a field,
  a plate, a vehicle) is dropped and noted in `dropped`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from vqa.kb import Catalog, load_catalog
from vqa.schemas import (
    AltReading, ConditionGroup, LaneSpec, Plate, Position, Road, SceneGraph, SceneVehicle, Sign,
    VehicleClass,
)

SIGN_FIELDS = {"code", "confidence", "value", "unit", "shape", "border", "background", "rank",
               "side", "lane", "placement", "box", "plates", "rules", "lanes", "alt"}
_CLASSES = {c.value for c in VehicleClass}


@dataclass
class WireResult:
    scene: SceneGraph | None
    errors: list[str] = field(default_factory=list)       # strict mode: what the retry sends
    raw_codes: dict[str, str] = field(default_factory=dict)  # sign id -> invalid code as read
    dropped: list[str] = field(default_factory=list)      # final mode: parts left out

    @property
    def ok(self) -> bool:
        return self.scene is not None and not self.errors


PLACEHOLDER = "[previous reply not shown]"


def retry_messages(errors: list[str]) -> list[dict[str, Any]]:
    """The one retry (plan D4): only the error is sent; the rejected reply is not echoed
    back (the assistant turn is a placeholder). Used by the scene call and the fallback."""
    msg = ("That reply was not valid: " + "; ".join(errors[:12])
           + ". Reply again with only the corrected JSON object.")
    return [{"role": "assistant", "content": PLACEHOLDER}, {"role": "user", "content": msg}]


def resolve_code(code: Any, catalog: Catalog) -> tuple[str | None, str | None]:
    """(code to keep, error). A catalog code or variant is kept as written; a stem
    naming one row becomes the row code; UNKNOWN is allowed."""
    if not isinstance(code, str) or not code.strip():
        return None, "code is missing"
    code = code.strip()
    if code == "UNKNOWN" or catalog.has(code):
        return code, None
    try:
        rows = catalog.codes_matching(code)
    except KeyError:
        return None, f"unknown sign code {code!r}"
    if len(rows) > 1:
        return None, f"{code!r} names several catalog rows ({', '.join(rows)}); give the variant"
    return rows[0], None


def _vehicles(items: Any) -> Any:
    """Bare class names become {"class": name}; anything else is left for validation."""
    if not isinstance(items, list):
        return items
    return [{"class": v} if isinstance(v, str) and v in _CLASSES else v for v in items]


def _groups(items: Any) -> Any:
    if not isinstance(items, list):
        return items
    return [{**g, "vehicles": _vehicles(g.get("vehicles", []))} if isinstance(g, dict) else g
            for g in items]


def _msg(where: str, e: ValidationError) -> list[str]:
    out = []
    for x in e.errors():
        loc = ".".join(map(str, x["loc"]))
        out.append(f"{where}{': ' + loc if loc else ''}: {x['msg']}")
    return out


class _Collector:
    def __init__(self, final: bool):
        self.final, self.errors, self.dropped = final, [], []

    def bad(self, msgs: list[str], what: str) -> None:
        (self.dropped if self.final else self.errors).extend(
            [f"{m} ({what} dropped)" for m in msgs] if self.final else msgs)


def _plate(raw: Any, where: str, col: _Collector) -> Plate | None:
    if not isinstance(raw, dict):
        col.bad([f"{where}: a plate must be an object"], "plate")
        return None
    raw = {**raw, "vehicles": _vehicles(raw.get("vehicles", [])), "rules": _groups(raw.get("rules", []))}
    try:
        return Plate.model_validate(raw)
    except ValidationError as e:
        col.bad(_msg(where, e), "plate")
        return None


def _sign(raw: Any, sid: str, catalog: Catalog, col: _Collector, raw_codes: dict) -> Sign | None:
    where = f"sign {sid}"
    if not isinstance(raw, dict):
        col.bad([f"{where}: a sign must be an object"], "sign")
        return None
    if extra := sorted(set(raw) - SIGN_FIELDS):
        col.bad([f"{where}: unknown fields {extra}"], "fields")
    code, err = resolve_code(raw.get("code"), catalog)
    if err:
        if col.final:
            raw_codes[sid] = str(raw.get("code"))
            code = "UNKNOWN"
        else:
            col.errors.append(f"{where}: {err}")
            code = "UNKNOWN"
    plates = []
    for k, p in enumerate(raw.get("plates") or [], 1):
        if (pl := _plate(p, f"{where} plate {k}", col)) is not None:
            plates.append(pl)
    alts = []
    if raw.get("alt"):
        a = raw["alt"]
        acode, aerr = resolve_code(a.get("code") if isinstance(a, dict) else None, catalog)
        if aerr:
            col.bad([f"{where} alt: {aerr}"], "alternative")
        else:
            try:
                alts.append(AltReading.model_validate({**a, "code": acode}))
            except ValidationError as e:
                col.bad(_msg(f"{where} alt", e), "alternative")
    fields: dict[str, Any] = {"id": sid, "code": code, "plates": plates, "alternatives": alts}
    pos = {"rank_top_down": raw.get("rank"), "side": raw.get("side") or "unknown",
           "lane": raw.get("lane"), "placement": raw.get("placement"), "box": raw.get("box")}
    try:
        fields["position"] = Position.model_validate({k: v for k, v in pos.items() if v is not None})
    except ValidationError as e:
        col.bad(_msg(f"{where} position", e), "position")
    for name, model in (("rules", ConditionGroup), ("lanes", LaneSpec)):
        items = []
        src = _groups(raw.get(name) or []) if name == "rules" else raw.get(name) or []
        for k, it in enumerate(src, 1):
            if name == "lanes" and isinstance(it, dict):
                it = {**it, "vehicles": _vehicles(it.get("vehicles", []))}
            try:
                items.append(model.model_validate(it))
            except ValidationError as e:
                col.bad(_msg(f"{where} {name} {k}", e), name[:-1])
        fields[name] = items
    for name in ("confidence", "value", "unit", "shape", "border", "background"):
        if raw.get(name) is None:
            continue
        try:
            Sign.model_validate({"id": sid, "code": code, name: raw[name]})
            fields[name] = raw[name]
        except ValidationError as e:
            col.bad(_msg(where, e), name)
    try:
        return Sign.model_validate(fields)
    except ValidationError as e:      # cross-field rules, e.g. groups with vehicle/time plates
        col.bad(_msg(where, e), "sign")
        if col.final:
            return Sign.model_validate({**fields, "plates": [], "rules": []})
        return None


def to_scene(data: Any, scene_id: str, *, final: bool = False,
             catalog: Catalog | None = None) -> WireResult:
    """Convert a parsed reply to a SceneGraph (see the module docstring)."""
    catalog = catalog or load_catalog()
    col, raw_codes = _Collector(final), {}
    if not isinstance(data, dict):
        return WireResult(None, ["the reply must be a JSON object"])
    if extra := sorted(set(data) - {"signs", "road", "vehicles"}):
        col.bad([f"unknown top-level fields {extra}"], "fields")
    signs = []
    raw_signs = data.get("signs") or []
    if not isinstance(raw_signs, list):
        return WireResult(None, ["signs must be a list"])
    for k, raw in enumerate(raw_signs, 1):
        if (s := _sign(raw, f"s{k}", catalog, col, raw_codes)) is not None:
            signs.append(s)
    road = Road()
    if data.get("road") is not None:
        try:
            road = Road.model_validate(data["road"])
        except ValidationError as e:
            col.bad(_msg("road", e), "road")
    vehicles = []
    for k, v in enumerate(data.get("vehicles") or [], 1):
        v = {"class": v} if isinstance(v, str) else v
        try:
            vehicles.append(SceneVehicle.model_validate({**v, "id": f"v{k}"}))
        except (ValidationError, TypeError) as e:
            col.bad(_msg(f"vehicle v{k}", e) if isinstance(e, ValidationError)
                    else [f"vehicle v{k}: not an object"], "vehicle")
    if col.errors:
        return WireResult(None, col.errors, raw_codes, col.dropped)
    scene = SceneGraph(scene_id=scene_id, road=road, signs=signs, vehicles=vehicles)
    return WireResult(scene, [], raw_codes, col.dropped)
