"""SceneGraph -> Prolog facts (the declarations live in kb/scene.pl)."""

from __future__ import annotations

import itertools

from vqa.kb import Catalog, code_atom
from vqa.reasoning.terms import Term, atom, cond_term, spec_term
from vqa.schemas import Confidence, PlateKind, SceneGraph, Sign

UNKNOWN_CODE = "UNKNOWN"


def _sign_lanes(sign: Sign) -> list[tuple[int, str]]:
    """(lane, origin) pairs; origin is 'plate' for an S.504 plate, else 'position'."""
    lanes = []
    if sign.position.lane is not None:
        lanes.append((sign.position.lane, "position"))
    for p in sign.plates:
        if p.kind == PlateKind.lane:
            lanes.extend((ln, "plate") for ln in p.lanes)
    return sorted(set(lanes))


def sign_facts(sign: Sign, catalog: Catalog) -> list[Term]:
    if sign.code == UNKNOWN_CODE:
        return []
    s = atom(sign.id)
    code = atom(code_atom(sign.code))
    out: list[Term] = [Term("sign", s, code, atom(sign.confidence.value))]
    if sign.value is not None:
        out.append(Term("sign_value", s, float(sign.value)))
    lanes = _sign_lanes(sign)
    entry = catalog.get(sign.code) if catalog.has(sign.code) else None
    reserves_lane = bool(entry and entry.effect.lane_reserved)
    if not reserves_lane:
        # For R.412 signs the lane says which lane is reserved, not where the sign applies.
        out += [Term("sign_lane", s, ln, atom(origin)) for ln, origin in lanes]

    for p in sign.plates:
        if p.kind == PlateKind.time:
            for w in p.time_windows:
                f, t = w.minutes()
                out.append(Term("plate_time", s, f, t))
            if p.days:
                out.append(Term("plate_days", s, atom(p.days.value)))
        elif p.kind == PlateKind.vehicle:
            out += [Term("plate_vehicle", s, spec_term(v)) for v in p.vehicles]
        elif p.kind == PlateKind.exception:
            out += [Term("plate_except", s, spec_term(v)) for v in p.vehicles]

    for i, g in enumerate(sign.rules, start=1):
        gid = atom(f"g{i}")
        out.append(Term("group", s, gid))
        out += [Term("group_vehicle", s, gid, spec_term(v)) for v in g.vehicles]
        for w in g.time_windows:
            f, t = w.minutes()
            out.append(Term("group_time", s, gid, f, t))
        if g.days:
            out.append(Term("group_days", s, gid, atom(g.days.value)))

    for row in sign.lanes:
        specs = [spec_term(v) for v in row.vehicles] or [atom("any")]
        for sp in specs:
            if row.max_speed is not None:
                out.append(Term("lane_limit", s, row.lane, sp, float(row.max_speed)))
            if row.min_speed is not None:
                out.append(Term("lane_min", s, row.lane, sp, float(row.min_speed)))
            if row.vehicles:
                out.append(Term("lane_vehicle", s, row.lane, sp))

    if reserves_lane:
        value_conds = []
        if entry.effect.value and sign.value is not None:
            v = entry.effect.value
            value_conds = [(set(c.value for c in v.applies_to), Term(
                "c", atom(v.attr.value), atom(v.op.value), float(sign.value)))]
        for ln in sorted({ln for ln, _ in lanes}):
            for cls in entry.effect.lane_reserved:
                conds = [c for classes, c in value_conds if cls.value in classes]
                out.append(Term("lane_vehicle", s, ln, Term("spec", atom(cls.value), conds)))
    return out


def scene_facts(scene: SceneGraph, catalog: Catalog,
                selection: list[str] | None = None) -> list[Term]:
    out: list[Term] = []
    for sign in scene.signs:
        out += sign_facts(sign, catalog)
    for v in scene.vehicles:
        # Actions outside the engine's Action vocabulary (driving, crossing_line)
        # are kept as atoms; kb/query.pl only checks those that are action/1.
        out.append(Term("scene_vehicle", atom(v.id), atom(v.cls.value),
                        v.lane, atom(v.action.value), None if v.speed_kmh is None else float(v.speed_kmh)))
    if selection is not None:
        out.append(Term("selection_active"))
        out += [Term("selected", atom(sid)) for sid in selection]
    return out


def reading_variants(scene: SceneGraph) -> list[tuple[SceneGraph, dict[str, str]]]:
    """One scene per combination of alternative sign readings (DESIGN.md, Verification).

    Returns (scene, {sign_id: code}) pairs; the first pair is the primary reading.
    """
    choices = []
    for s in scene.signs:
        if s.alternatives and s.confidence != Confidence.high:
            opts = [(s.code, s.value)] + [(a.code, a.value) for a in s.alternatives]
            choices.append((s.id, opts))
    if not choices:
        return [(scene, {})]
    variants = []
    for combo in itertools.islice(itertools.product(*[o for _, o in choices]), 32):
        sc = scene.model_copy(deep=True)
        picked = {}
        for (sid, _), (code, value) in zip(choices, combo):
            sg = sc.sign(sid)
            sg.code, sg.value = code, (value if value is not None else sg.value)
            picked[sid] = code
        variants.append((sc, picked))
    return variants


__all__ = ["scene_facts", "sign_facts", "reading_variants", "cond_term"]
