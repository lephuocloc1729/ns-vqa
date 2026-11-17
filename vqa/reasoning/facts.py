"""SceneGraph -> Prolog facts (the declarations live in kb/scene.pl)."""

from __future__ import annotations

import itertools

from vqa.kb import Catalog, code_atom
from vqa.reasoning.terms import Term, atom, cond_term, spec_term
from vqa.schemas import Confidence, PlateKind, SceneGraph, Sign


def board_read(sign) -> bool:
    """A rectangular, non-red board: its content is what the guide-board call reads (B6).
    Once a scene has `guide_boards`, such a board is no longer an unread sign."""
    shape = getattr(sign.shape, "value", sign.shape)
    colours = {getattr(sign.border, "value", sign.border), getattr(sign.background, "value", sign.background)}
    return shape in ("rectangle", "square") and "red" not in colours

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


def _group_facts(s, rules, prefix: str) -> list[Term]:
    out: list[Term] = []
    for i, g in enumerate(rules, start=1):
        gid = atom(f"{prefix}{i}")
        out.append(Term("group", s, gid))
        out += [Term("group_vehicle", s, gid, spec_term(v)) for v in g.vehicles]
        for w in g.time_windows:
            f, t = w.minutes()
            out.append(Term("group_time", s, gid, f, t))
        if g.days:
            out.append(Term("group_days", s, gid, atom(g.days.value)))
    return out


def sign_facts(sign: Sign, catalog: Catalog) -> list[Term]:
    if sign.code == UNKNOWN_CODE:
        return []
    s = atom(sign.id)
    # a variant code ("W.207c") uses its family row's atom
    code = atom(catalog.get(sign.code).atom if catalog.has(sign.code) else code_atom(sign.code))
    out: list[Term] = [Term("sign", s, code, atom(sign.confidence.value))]
    if sign.value is not None:
        out.append(Term("sign_value", s, float(sign.value)))
    if sign.position.placement:
        out.append(Term("sign_placement", s, atom(sign.position.placement)))
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
        elif p.kind == PlateKind.local:
            out.append(Term("local_plate", s, atom(p.text)))
            out += [Term("local_vehicle", s, spec_term(v)) for v in p.vehicles]
            out += [Term("local_action", s, atom(a.value)) for a in p.actions]
            for w in p.time_windows:
                f, t = w.minutes()
                out.append(Term("plate_time", s, f, t))
            if p.days:
                out.append(Term("plate_days", s, atom(p.days.value)))
            out += _group_facts(s, p.rules, "lg")

    out += _group_facts(s, sign.rules, "g")

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
    for sign in scene.signs:
        # phase 4.5: a sign that couldn't be read gets no sign/3 fact; this says it is there, so
        # road-type defaults (kb/rules/zones.pl) don't stand in for a limit it might post.
        # A warning triangle can't post a speed limit, so it is left out.
        if not catalog.has(sign.code) and getattr(sign.shape, "value", None) not in ("triangle",):
            if not (scene.guide_boards and board_read(sign)):      # B6: a board the guide call read
                out.append(Term("unread_sign", atom(sign.id)))
    if scene.road.divided is not None:
        out.append(Term("road_divided", atom("true" if scene.road.divided else "false")))
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


_RANK = {Confidence.high: 3, Confidence.medium: 2, Confidence.low: 1}


def top_reading(scene: SceneGraph) -> tuple[SceneGraph, dict[str, str], dict[str, list[tuple[str, str]]]]:
    """The scene with every low/medium-confidence sign set to its highest-confidence reading
    (phase 4.6, policy A, owner 2026-11-17). A tie keeps the first reading, perception's own
    choice. Returns (scene, {sign_id: chosen code}, {sign_id: [(other code, confidence), ...]})."""
    sc = scene.model_copy(deep=True)
    chosen, others = {}, {}
    for s in sc.signs:
        if not s.alternatives or s.confidence == Confidence.high:
            continue
        opts = [(s.code, s.value, s.confidence)] + [(a.code, a.value, a.confidence) for a in s.alternatives]
        best = max(range(len(opts)), key=lambda i: (_RANK[opts[i][2]], -i))
        code, value, conf = opts[best]
        others[s.id] = [(c, f.value) for i, (c, _, f) in enumerate(opts) if i != best]
        s.code, s.value, s.confidence = code, (value if value is not None else s.value), conf
        s.alternatives = []
        chosen[s.id] = code
    return sc, chosen, others


__all__ = ["scene_facts", "sign_facts", "reading_variants", "top_reading", "cond_term"]
