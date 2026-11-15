"""Deterministic checks on a scene from the scene call (docs/plans/phase-3.md, item 4).

verify(scene) -> (scene, issues)

- Values, per catalog row: speeds 5-120 km/h in steps of 5 (signs and lane rows);
  weights > 0 and <= 60 t; heights and widths > 0 and <= 10 m; lengths > 0 and
  <= 30 m; seats 1-100. A value out of range is dropped and the sign lowered to
  low. A value on a rule row that takes none is dropped. A value-bearing row with
  no value is lowered to low.
- Look vs catalog: a reported shape / border / background that differs from the
  row's visual is always recorded; it lowers the sign to low only on rows with
  visual_reviewed_by: human (plan D10). The reported look is kept.
- Plates: a sign whose code is an auxiliary plate (S.504, S.505a, S.508a/b, S.H,6)
  is a plate the model didn't attach. It goes under the sign directly above it on
  the same side (else directly above).
- Lane rows: sorted and numbered 1..n from the left with no gaps; more lanes than
  road.lanes is recorded.
- Ids: renumbered s1, s2, ... top-down (by rank), and v1, v2, ...

needs_rerun(scene) says whether any sign is low or UNKNOWN; merge_rerun(first,
second) pairs the two readings (vqa/perception/matching.py): agreement keeps the
sign, disagreement keeps the first reading with the second as an AltReading, and a
sign seen in only one reading is kept at low. Every change is returned as an issue.
"""

from __future__ import annotations

from vqa.kb import Catalog, load_catalog
from vqa.perception.matching import match, row_of, sign_view
from vqa.schemas import AltReading, Confidence, LaneSpec, Plate, PlateKind, SceneGraph, Sign

VALUE_RANGES = {            # attr -> (low exclusive, high inclusive)
    "gross_t": (0, 60), "load_t": (0, 60), "height_m": (0, 10), "width_m": (0, 10),
    "length_m": (0, 30), "seats": (0, 100),
}
PLATE_KINDS = {"S.504": PlateKind.lane, "S.505a": PlateKind.vehicle, "S.508a": PlateKind.time,
               "S.508b": PlateKind.time, "S.H,6": PlateKind.exception}


def ok_speed(v: float | None) -> bool:
    return v is not None and 5 <= v <= 120 and float(v) % 5 == 0


def _row(code: str, catalog: Catalog):
    r = row_of(code, catalog)
    return catalog.get(r) if r else None


def _check_values(s: Sign, row, issues: list[str]) -> Sign:
    upd: dict = {}
    e = row.effect
    if e.max_speed or e.min_speed:
        if s.value is None:
            upd["confidence"] = Confidence.low
            issues.append(f"{s.id} {s.code}: no speed value read; lowered to low")
        elif not ok_speed(s.value):
            upd.update(value=None, confidence=Confidence.low)
            issues.append(f"{s.id} {s.code}: speed {s.value} out of range; dropped, lowered to low")
    elif e.value:
        lo, hi = VALUE_RANGES[e.value.attr.value]
        if s.value is None:
            upd["confidence"] = Confidence.low
            issues.append(f"{s.id} {s.code}: no {e.value.attr.value} value read; lowered to low")
        elif not (lo < s.value <= hi):
            upd.update(value=None, confidence=Confidence.low)
            issues.append(f"{s.id} {s.code}: {e.value.attr.value} {s.value} out of range; "
                          "dropped, lowered to low")
    elif s.value is not None and not row.meaning_only and not e.lane_board:
        upd.update(value=None, unit=None)
        issues.append(f"{s.id} {s.code}: the row takes no value; {s.value} dropped")
    if s.lanes:
        lanes = []
        for ln in s.lanes:
            bad = [k for k in ("max_speed", "min_speed")
                   if getattr(ln, k) is not None and not ok_speed(getattr(ln, k))]
            if bad:
                issues.append(f"{s.id} {s.code}: lane {ln.lane} {', '.join(bad)} out of range; dropped")
                upd["confidence"] = Confidence.low
                ln = ln.model_copy(update={k: None for k in bad})
            lanes.append(ln)
        upd["lanes"] = lanes
    return s.model_copy(update=upd) if upd else s


def _check_look(s: Sign, row, issues: list[str]) -> Sign:
    val = lambda x: x.value if hasattr(x, "value") else x  # noqa: E731
    diffs = [f"{k} {val(getattr(s, k))} (catalog {getattr(row.visual, k)})"
             for k in ("shape", "border", "background")
             if getattr(s, k) is not None and val(getattr(s, k)) != getattr(row.visual, k)]
    if not diffs:
        return s
    if row.visual_reviewed_by == "human":
        issues.append(f"{s.id} {s.code}: look differs from the catalog: {', '.join(diffs)}; lowered to low")
        return s.model_copy(update={"confidence": Confidence.low})
    issues.append(f"{s.id} {s.code}: look differs from the catalog: {', '.join(diffs)} "
                  "(row not visually reviewed; recorded only)")
    return s


def _lanes(s: Sign, road_lanes: int | None, issues: list[str]) -> Sign:
    if not s.lanes:
        return s
    order = sorted({ln.lane for ln in s.lanes})
    renum = {old: i for i, old in enumerate(order, 1)}
    if order != list(range(1, len(order) + 1)):
        issues.append(f"{s.id} {s.code}: lanes {order} renumbered 1..{len(order)}")
    lanes = sorted((ln.model_copy(update={"lane": renum[ln.lane]}) for ln in s.lanes),
                   key=lambda ln: ln.lane)
    if road_lanes is not None and len(order) > road_lanes:
        issues.append(f"{s.id} {s.code}: {len(order)} lane rows but the road has {road_lanes} lanes")
    return s.model_copy(update={"lanes": lanes})


def _attach_plates(signs: list[Sign], issues: list[str]) -> list[Sign]:
    plates = [s for s in signs if s.code in PLATE_KINDS]
    mains = [s for s in signs if s.code not in PLATE_KINDS]
    for p in plates:
        rank = p.position.rank_top_down
        above = [m for m in mains if m.position.rank_top_down is not None and rank is not None
                 and m.position.rank_top_down < rank]
        same_side = [m for m in above if m.position.side == p.position.side]
        pick = max(same_side or above, key=lambda m: m.position.rank_top_down, default=None)
        if pick is None:
            issues.append(f"{p.id} {p.code}: a plate with no sign above it; left out")
            continue
        plate = Plate(kind=PLATE_KINDS[p.code], code=p.code)
        i = mains.index(pick)
        mains[i] = pick.model_copy(update={"plates": [*pick.plates, plate]})
        issues.append(f"{p.id} {p.code}: plate listed as a sign; attached to {pick.id} {pick.code}")
    return mains


def verify(scene: SceneGraph, catalog: Catalog | None = None) -> tuple[SceneGraph, list[str]]:
    catalog = catalog or load_catalog()
    issues: list[str] = []
    signs = _attach_plates(list(scene.signs), issues)
    out = []
    for s in signs:
        row = _row(s.code, catalog)
        if row is not None:
            s = _check_values(s, row, issues)
            s = _check_look(s, row, issues)
        s = _lanes(s, scene.road.lanes, issues)
        out.append(s)
    order = sorted(range(len(out)), key=lambda i: (out[i].position.rank_top_down is None,
                                                     out[i].position.rank_top_down or 0, i))
    renamed = [out[i].model_copy(update={"id": f"s{n}"}) for n, i in enumerate(order, 1)]
    if [s.id for s in renamed] != [out[i].id for i in order]:
        issues.append("sign ids renumbered top-down: "
                      + ", ".join(f"{out[i].id}->s{n}" for n, i in enumerate(order, 1)
                                  if out[i].id != f"s{n}"))
    vehicles = [v.model_copy(update={"id": f"v{n}"}) for n, v in enumerate(scene.vehicles, 1)]
    return scene.model_copy(update={"signs": renamed, "vehicles": vehicles}), issues


def needs_rerun(scene: SceneGraph) -> bool:
    return any(s.code == "UNKNOWN" or s.confidence == Confidence.low for s in scene.signs)


def merge_rerun(first: SceneGraph, second: SceneGraph,
                catalog: Catalog | None = None) -> tuple[SceneGraph, list[str]]:
    """Pair two readings of one image; see the module docstring."""
    catalog = catalog or load_catalog()
    issues: list[str] = []
    a, b = list(first.signs), list(second.signs)
    pairs = dict(match([sign_view(s) for s in a], [sign_view(s) for s in b], catalog))
    out = []
    for i, s in enumerate(a):
        j = pairs.get(i)
        if j is None:
            out.append(s.model_copy(update={"confidence": Confidence.low}))
            issues.append(f"{s.id} {s.code}: seen in the first reading only; kept at low")
            continue
        t = b[j]
        if (s.code, s.value) == (t.code, t.value):
            if s.code != "UNKNOWN" and s.confidence == Confidence.low and t.confidence != Confidence.low:
                s = s.model_copy(update={"confidence": t.confidence})
            out.append(s)
            issues.append(f"{s.id} {s.code}: the re-run agrees")
        else:
            alt = AltReading(code=t.code, value=t.value, confidence=t.confidence)
            out.append(s.model_copy(update={"alternatives": [*s.alternatives, alt]}))
            issues.append(f"{s.id} {s.code}: the re-run read {t.code}"
                          + (f" {t.value}" if t.value is not None else "") + "; kept as an alternative")
    for j, t in enumerate(b):
        if j not in pairs.values():
            out.append(t.model_copy(update={"confidence": Confidence.low, "id": f"r{j + 1}"}))
            issues.append(f"{t.id} {t.code}: seen in the re-run only; kept at low")
    merged, more = verify(first.model_copy(update={"signs": out}), catalog)
    return merged, issues + [m for m in more if "renumbered" in m]
