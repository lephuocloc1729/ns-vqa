"""Python side of the rule engine: loads kb/ into SWI-Prolog through janus,
asserts a scene, runs a QueryProgram and returns an Answer with proofs.

The engine decides every legal conclusion in Prolog. Python only resolves
sign selectors, loops over lanes and over alternative sign readings, and
packs the results into an Answer.
"""

from __future__ import annotations

import datetime as dt
import itertools
from pathlib import Path
from typing import Any

from vqa.kb import KB_DIR, Catalog, load_catalog
from vqa.reasoning import explain
from vqa.reasoning.facts import board_read, reading_variants, scene_facts, top_reading
from vqa.reasoning.terms import Term, atom, to_prolog, vehicle_term
from vqa.parsing.dsl import normalize
from vqa.schemas import (MustYield, OfficerPermits, OfficerSignal, Precedence, PrecedenceIs,  # parser v13
                         RightOfWay, VehicleClassIs, VehicleClassOf)
from vqa.schemas import AltReading, Confidence  # noqa: E402  phase 4.8 A1
from vqa.schemas import Action, LanesOnly, ViolationKind  # noqa: E402  parser v17 (phase 4.8c)
from vqa.schemas import LaneReservedIs  # noqa: E402  parser v18 (owner, 2026-11-20)
from vqa.schemas import (
    AllOf, Answer, AnyOf, AppliesTo, BanTimes, Choose, Count, CountIs, Duties, MarkingIs, MarkingMeaning,
    RulePermitted, SignalMeaning, SignApplies, Citation, ExistsViolation, Explain, Guide, GuideClaim, IsSign,
    LanesFor, LanesWhere, LaneVehicles, Meaning, Multi, Permitted, Present, SpeedLimit, SpeedLimitIs,
    ONTOLOGY_CLASSES, Forbidden, Program, QueryProgram, Reason, Required, SceneGraph, Selector,
    SpeedOk, Vehicle, VehicleClass, Verdict, Verify, When, WhichVehicles,
)

try:
    import janus_swi as janus
except ImportError as e:  # pragma: no cover - environment problem, not a code path
    raise ImportError(
        "janus_swi is not installed. Install it into the project venv with:\n"
        "  .venv/bin/pip install janus-swi\n"
        "(needs SWI-Prolog >= 9.1 on PATH, e.g. `brew install swi-prolog`)"
    ) from e

_LOADED_CATALOG: str | None = None  # janus has one Prolog per process


class EngineError(RuntimeError):
    pass


class UndecidedSelection(Exception):
    """Parser v13: a relative selector ("biển ngay dưới biển cấm đỗ") the scene's positions can't
    resolve; the answer is unknown."""


def _load_kb(catalog: Catalog) -> None:
    global _LOADED_CATALOG
    if _LOADED_CATALOG is None:
        janus.consult(str(KB_DIR / "load.pl"))
    if _LOADED_CATALOG != catalog.version:
        janus.query_once("clear_catalog")
        _assert(catalog.facts())
        _LOADED_CATALOG = catalog.version


def _assert(facts: list[Term]) -> None:
    if not facts:
        return
    r = janus.query_once("add_facts(T)", {"T": to_prolog(list(facts))})
    if not r.get("truth"):
        raise EngineError("asserting facts failed")


# Phase 4.6 (D3): a day of the stated parity, for "vào ngày chẵn / lẻ" with no date. The
# P.131b / P.131c rules depend on the parity only (QCVN 41 B.31).
_PARITY_DAY = {"even": 2, "odd": 1}


def _days(when: When | None) -> tuple[int | None, int | None]:
    """Day of month for the interval's start and for after midnight."""
    if when is not None and when.date is None and when.day_parity:
        d = _PARITY_DAY[when.day_parity]
        return d, d + 1
    if when is None or when.date is None:
        return None, None
    return when.date.day, (when.date + dt.timedelta(days=1)).day


def _minute(t: dt.time) -> int:
    return t.hour * 60 + t.minute


def _ctx(when: When | None, scene: SceneGraph, lane: int | None = None) -> Term:
    minute: int | None = None
    day: int | None = None
    if when is not None:
        if when.time is not None:
            minute = when.time.hour * 60 + when.time.minute
        if when.date is not None:
            day = when.date.day
        elif when.day_parity:
            day = _PARITY_DAY[when.day_parity]
    elif scene.context.datetime is not None:
        t: dt.datetime = scene.context.datetime
        minute, day = t.hour * 60 + t.minute, t.day
    return Term("ctx", minute, day, lane)


# Fix 2026-11-20 (kb/rules/fixes50.pl): the asked date's kinds for exception-day plates. Public
# holidays are calendar facts, not traffic rules: the fixed solar ones (1/1, 30/4, 1/5, 2/9) are
# holidays; the day next to 2/9 and the January-April windows of the lunar holidays (Tết, Hùng
# Kings' day) are maybe_holiday. Flagged for the owner.
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_FIXED_HOLIDAYS = {(1, 1), (4, 30), (5, 1), (9, 2)}


def _day_kinds(d: dt.date) -> list[str]:
    kinds = [_WEEKDAYS[d.weekday()]]
    md = (d.month, d.day)
    if md in _FIXED_HOLIDAYS:
        kinds.append("holiday")
    elif md in {(9, 1), (9, 3)} or (1, 15) <= md <= (2, 25) or (3, 25) <= md <= (4, 29):
        kinds.append("maybe_holiday")
    return kinds


def _asked_dates(obj: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "date" and isinstance(v, str):
                out.add(v)
            else:
                out |= _asked_dates(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _asked_dates(v)
    return out


def day_kind_facts(program: Any) -> list[Term]:
    """query_day_kind/1 facts when the program asks about exactly one date."""
    dates = _asked_dates(program.model_dump(mode="json")) if program is not None else set()
    if len(dates) != 1:
        return []
    return [Term("query_day_kind", atom(k)) for k in _day_kinds(dt.date.fromisoformat(dates.pop()))]


def _fmt_min(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


READING_POLICIES = ("all", "higher_confidence")


V6_FIELDS = ("signals", "markings", "arrows")   # phase 4.7: switchable scene v6 fields


def v6_fields_off_from_kb() -> tuple[str, ...]:
    """The scene v6 fields the owner switched off (kb/v6_fields_47.yaml)."""
    import yaml
    path = Path(__file__).resolve().parents[2] / "kb" / "v6_fields_47.yaml"
    return tuple((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("off") or [])


def switches_from_kb() -> dict[str, Any]:
    """Phase 4.8 engine switches (kb/switches_48.yaml)."""
    import yaml
    path = Path(__file__).resolve().parents[2] / "kb" / "switches_48.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def stated_exceptions_from_kb() -> set[str]:
    """Phase 4.8c B3 (kb/stated_exceptions_48.yaml): QCVN 41 articles whose text excepts priority
    vehicles ("trừ các xe được ưu tiên theo quy định")."""
    import yaml
    path = Path(__file__).resolve().parents[2] / "kb" / "stated_exceptions_48.yaml"
    return {r["article_id"] for r in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("articles", [])}


def confusables_from_kb(catalog: Catalog) -> dict[str, list[str]]:
    """Phase 4.8 A1 (kb/confusables_48.yaml): catalog row -> the rows it is swapped with."""
    import yaml
    path = Path(__file__).resolve().parents[2] / "kb" / "confusables_48.yaml"
    out: dict[str, list[str]] = {}
    for pair in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("pairs", []):
        rows = [catalog.get(c).code for c in pair["codes"]]
        for r in rows:
            out.setdefault(r, []).extend(x for x in rows if x != r and x not in out.get(r, []))
    return out


class Engine:
    """`reading_policy` (phase 4.6, D1): what to do when alternative sign readings disagree.
    "all" (the default, the frozen phase-4.5 behaviour): the verdict is `uncertain`.
    "higher_confidence" (policy A): answer with each sign's highest-confidence reading (a tie
    keeps the first reading); the answer lists those signs in `uncertain_signs`, says which
    reading it used in `note`, and carries `basis: ["reading_choice"]`."""

    def __init__(self, catalog: Catalog | None = None, reading_policy: str = "all",
                 v6_fields_off: tuple[str, ...] | None = None, several_signs: bool | None = None,
                 confusable_pairs: bool | None = None, sign_charts: int | bool | None = None,
                 one_sign_g1: bool | None = None, stated_exceptions: bool | None = None) -> None:
        if reading_policy not in READING_POLICIES:
            raise ValueError(f"reading_policy must be one of {READING_POLICIES}")
        # phase 4.7: scene v6 fields switched off (kb/v6_fields_47.yaml unless given); their facts
        # are dropped, so their rules give unknown
        off = tuple(v6_fields_off) if v6_fields_off is not None else v6_fields_off_from_kb()
        if set(off) - set(V6_FIELDS):
            raise ValueError(f"v6_fields_off must be among {V6_FIELDS}")
        self.v6_fields_off = off
        # phase 4.8 G1 (kb/switches_48.yaml unless given): several readable signs under `only`
        self.several_signs = (bool(switches_from_kb().get("several_signs", False))
                              if several_signs is None else several_signs)
        self.catalog = catalog or load_catalog()
        self.reading_policy = reading_policy
        self._look_note: str | None = None
        # phase 4.8 A1 (kb/switches_48.yaml unless given): the confusable-sign table
        on = (bool(switches_from_kb().get("confusable_pairs", False)) if confusable_pairs is None
              else confusable_pairs)
        self.confusables = confusables_from_kb(self.catalog) if on else {}
        # phase 4.8c B (kb/switches_48.yaml unless given): sign charts (B1), one sign under G1
        # (B2), the signs' stated priority exceptions and board notes (B3)
        sw = switches_from_kb()
        if sign_charts is None:
            sign_charts = int(sw.get("sign_chart_signs", 20)) if sw.get("sign_charts", False) else False
        elif sign_charts is True:
            sign_charts = int(sw.get("sign_chart_signs", 20))
        self.sign_chart_n: int | None = int(sign_charts) if sign_charts else None
        self.one_sign_g1 = bool(sw.get("one_sign_g1", False)) if one_sign_g1 is None else one_sign_g1
        self.stated_exceptions = (bool(sw.get("stated_exceptions", False)) if stated_exceptions is None
                                  else stated_exceptions)
        _load_kb(self.catalog)

    @staticmethod
    def _drop_lane_row_discs(scene: SceneGraph) -> SceneGraph:
        """Fix 2026-11-20: a guide-board disc (id g1, g2, ...) whose value repeats exactly one lane
        row's limit on a board with per-lane rows is that row's limit, not one for every lane: it
        is placed over that lane (position.lane), so the speed rules apply it there only. Scene
        cleanup, not a legal decision."""
        rows: dict[tuple[str, float], set[int]] = {}
        for sg in scene.signs:
            for r in sg.lanes:
                if r.max_speed is not None:
                    rows.setdefault(("P.127", r.max_speed), set()).add(r.lane)
                if r.min_speed is not None:
                    rows.setdefault(("R.306", r.min_speed), set()).add(r.lane)
        if len({v for _, v in rows}) < 2:
            return scene
        out, changed = [], False
        for sg in scene.signs:
            lanes = rows.get((sg.code, sg.value)) if sg.id.startswith("g") and sg.value is not None else None
            if lanes and len(lanes) == 1 and sg.position.lane is None:
                sg = sg.model_copy(update={"position": sg.position.model_copy(update={"lane": next(iter(lanes))})})
                changed = True
            out.append(sg)
        return scene.model_copy(update={"signs": out}) if changed else scene

    def _strip_v6(self, scene: SceneGraph) -> SceneGraph:
        if not self.v6_fields_off:
            return scene
        upd: dict[str, Any] = {}
        if "signals" in self.v6_fields_off and scene.signals:
            upd["signals"] = []
        if "markings" in self.v6_fields_off and scene.road.markings:
            upd["road"] = scene.road.model_copy(update={"markings": []})
        if "arrows" in self.v6_fields_off and any(r.directions for s in scene.signs for r in s.lanes):
            upd["signs"] = [s.model_copy(update={"lanes": [r.model_copy(update={"directions": []}) for r in s.lanes]})
                            for s in scene.signs]
        return scene.model_copy(update=upd) if upd else scene

    # ------------------------------------------------------------------ low level
    def load_scene(self, scene: SceneGraph, selection: list[str] | None = None) -> None:
        janus.query_once("clear_scene")
        _assert(scene_facts(scene, self.catalog, selection) + list(getattr(self, "_day_facts", [])))

    def call(self, goal: Term) -> dict[str, Any]:
        r = janus.query_once("solve_text(T, Out)", {"T": to_prolog(goal)})
        if not r.get("truth"):
            raise EngineError(f"query failed: {to_prolog(goal)}")
        return r["Out"]

    # ------------------------------------------------------------------ selectors
    def resolve(self, scene: SceneGraph, sel: Selector) -> list[str]:
        signs = [s for s in scene.signs
                 if not (self.catalog.has(s.code)
                         and self.catalog.get(s.code).category == "auxiliary")]
        if sel.sign_id:
            return [s.id for s in signs if s.id == sel.sign_id]
        codes = None
        if sel.meaning:
            try:
                codes = set(self.catalog.codes_for_meaning(sel.meaning))
            except KeyError as e:
                raise EngineError(str(e)) from None
        out = []
        for s in signs:
            if sel.code and not self.catalog.code_selects(sel.code, s.code):
                continue
            if codes is not None and s.code not in codes:
                continue
            if sel.shape and s.shape != sel.shape:
                continue
            if sel.category and not (self.catalog.has(s.code) and self.catalog.get(s.code).category == sel.category):
                continue
            if not self._colours_match(sel, s):
                continue
            if sel.side and s.position.side != sel.side:
                continue
            if sel.rank_top_down and s.position.rank_top_down != sel.rank_top_down:
                continue
            out.append(s)
        if sel.position in ("top", "bottom"):
            ranked = [s for s in out if s.position.rank_top_down is not None]
            if ranked:
                pick = min if sel.position == "top" else max
                r = pick(s.position.rank_top_down for s in ranked)
                out = [s for s in ranked if s.position.rank_top_down == r]
        if sel.relative is not None:                         # parser v13
            out = self._relative(scene, sel, out)
        return [s.id for s in out]

    # Phase 4.8 B6 (owner, 2026-11-18): the look a group word in a question usually names
    # (QCVN 41 art. 22, 28, 32, 36: the groups' shapes and colours).
    _CATEGORY_LOOK = {"information": ("board",), "prohibitory": ("red_circle", "red_board"),
                      "mandatory": ("blue_circle",), "warning": ("warning",)}

    def resolve_value(self, scene: SceneGraph, sel: Selector) -> list[str]:
        """For value questions only (meaning, applies_to, which_vehicles): when a group word
        ("biển chỉ dẫn" for an R.4xx board) selects nothing, the readable signs with that group's
        usual look are used, answered by their real group, and the answer says so. Claims about a
        group (is_sign, present, count) keep the strict selection."""
        ids = self.resolve(scene, sel)
        if ids or not sel.category or sel.category not in self._CATEGORY_LOOK:
            return ids
        loose = self.resolve(scene, sel.model_copy(update={"category": None}))
        looks = self._CATEGORY_LOOK[sel.category]
        hit = [i for i in loose if self.catalog.has(scene.sign(i).code)
               and self.visual_category(scene.sign(i)) in looks]
        if hit:
            groups = sorted({sign_group_vi(self.catalog.get(scene.sign(i).code).code) or
                             self.catalog.get(scene.sign(i).code).category for i in hit})
            self._look_note = (f"no sign of the group the question names ({sel.category}) is in the photo; "
                               f"answered for the sign(s) that look like one, whose group is {', '.join(groups)}")
        return hit

    def _relative(self, scene: SceneGraph, sel: Selector, cands: list) -> list:
        """Parser v13: the candidates placed `sel.relative` to the anchor. Only the vertical order
        on a post is recorded (rank_top_down, with the side): "above" / "below" pick the sign one
        rank up or down from a single ranked anchor on the same side. A light has no recorded
        position, and left / right / next to are not recorded, so those raise UndecidedSelection."""
        a = sel.anchor
        if a is None:
            raise UndecidedSelection("the question places the sign relative to something it does not name")
        if a.light:
            raise UndecidedSelection("the scene records no position for traffic lights, so the sign "
                                     "next to the light can't be picked")
        if sel.relative not in ("above", "below"):
            raise UndecidedSelection("the scene records only the order of signs on a post, not "
                                     "what is left or right of a sign")
        anchors = self.resolve(scene, Selector(code=a.code, meaning=a.meaning, shape=a.shape, border=a.border,
                                               background=a.background, category=a.category))
        if len(anchors) != 1 or scene.sign(anchors[0]).position.rank_top_down is None:
            raise UndecidedSelection("the sign the question places it against is not one ranked sign")
        anc = scene.sign(anchors[0])
        want = anc.position.rank_top_down + (1 if sel.relative == "below" else -1)
        hit = [s for s in cands if s.id != anc.id and s.position.rank_top_down == want
               and (s.position.side == anc.position.side or "unknown" in (s.position.side.value,
                                                                           anc.position.side.value))]
        if len(hit) != 1:
            raise UndecidedSelection("the positions in the scene don't pick out one sign there")
        return hit

    @staticmethod
    def _colours_match(sel: Selector, s) -> bool:
        """Border and background as asked. Phase 4.5 rank 3: when that fails, a colour the
        question names still matches if the sign shows it as border or background ("biển đỏ
        có vạch trắng" is P.102: red face, no border). Selection only, not a legal decision."""
        want = [c for c in (sel.border, sel.background) if c]
        if not want:
            return True
        if (not sel.border or s.border == sel.border) and (not sel.background or s.background == sel.background):
            return True
        shown = {c for c in (s.border, s.background) if c}
        return all(c in shown for c in want)

    def single_sign(self, scene: SceneGraph, ids: list[str]) -> tuple[list[str] | None, list[str]]:
        """Resolve a single-sign selector (`only`: "Đây là biển gì?") over its candidates
        (owner, 2026-11-16, plan item 1b): unreadable signs are dropped; if every
        readable candidate has the same catalog code, they are the selection and the
        unreadable ones are returned for `uncertain_signs`; if the readable codes
        differ (or none is readable), the selection is None and the answer stays
        unknown. A lone candidate is returned as is. Selector resolution only: what
        the sign means or forbids is still decided by the catalog and Prolog."""
        if len(ids) == 1:
            return ids, []
        readable = [i for i in ids if self.catalog.has(scene.sign(i).code)]
        unread = [i for i in ids if i not in readable]
        codes = {self.catalog.get(scene.sign(i).code).code for i in readable}
        if len(codes) != 1:
            return None, unread
        return readable, unread

    # ------------------------------------------------------------------ entry point
    def answer(self, scene: SceneGraph, query: QueryProgram | Program) -> Answer:
        scene = self._drop_lane_row_discs(self._strip_v6(scene))
        if isinstance(query, QueryProgram) and query.out_of_scope:
            return Answer(verdict=Verdict.unknown, note="out of scope for the rules: "
                          + (query.out_of_scope_reason or "no DSL intent fits"))
        program = normalize(query.program if isinstance(query, QueryProgram) else query)
        self._day_facts = day_kind_facts(program)       # fix 2026-11-20, kb/rules/fixes50.pl
        program, from_right = resolve_lanes(program, scene_lane_count(scene))
        if program is None:
            return Answer(verdict=Verdict.unknown, note="the question counts lanes from the right "
                          f"({', '.join(map(str, from_right))}), and the scene does not say how many lanes there are")
        scene, confusable_ids = self._add_confusables(scene)
        variants = reading_variants(scene)
        answers = [(picked, self._run(sc, program)) for sc, picked in variants]
        first = answers[0][1]
        if len(answers) == 1:
            return first
        if all(_same(first, a) for _, a in answers[1:]):
            return first
        uncertain = sorted({sid for picked, _ in answers for sid in picked})
        differ = {sid for picked, a in answers[1:] if not _same(first, a)
                  for sid, code in picked.items() if code != answers[0][0].get(sid)}
        if differ & confusable_ids:
            # phase 4.8 A1: a sign Haiku is known to swap reads differently under its partner code
            ids = sorted(differ & confusable_ids)
            return Answer(verdict=Verdict.unknown, reasons=first.reasons, uncertain_signs=uncertain,
                          value={"readings": [{"signs": p, "verdict": a.verdict.value, "value": a.value}
                                              for p, a in answers]},
                          note="these signs are often confused with another sign, and the other reading "
                               "gives a different answer: " + ", ".join(ids))
        if self.reading_policy == "higher_confidence":
            return self._higher_confidence(scene, program, answers, uncertain)
        return Answer(
            verdict=Verdict.uncertain,
            value={"readings": [{"signs": p, "verdict": a.verdict.value, "value": a.value}
                                for p, a in answers]},
            reasons=first.reasons,
            citations=[c for _, a in answers for c in a.citations],
            uncertain_signs=uncertain,
            note="alternative readings of these signs lead to different answers",
        )

    def _add_confusables(self, scene: SceneGraph) -> tuple[SceneGraph, set[str]]:
        """Phase 4.8 A1: a low- or medium-confidence sign with no alternative, read as a code in
        the confusable table, gets the partner code(s) as low-confidence alternatives."""
        if not self.confusables:
            return scene, set()
        signs, ids = [], set()
        for s in scene.signs:
            row = self.catalog.get(s.code).code if self.catalog.has(s.code) else None
            if row in self.confusables and not s.alternatives and s.confidence != Confidence.high:
                alts = [AltReading(code=c, value=s.value, confidence=Confidence.low) for c in self.confusables[row]]
                signs.append(s.model_copy(update={"alternatives": alts}))
                ids.add(s.id)
            else:
                signs.append(s)
        return (scene.model_copy(update={"signs": signs}) if ids else scene), ids

    def _higher_confidence(self, scene: SceneGraph, program, answers, uncertain: list[str]) -> Answer:
        """Policy A: the readings disagree; answer with the highest-confidence reading of each sign."""
        top, chosen, others = top_reading(scene)
        ans = next((a for picked, a in answers if picked == chosen), None) or self._run(top, program)
        used = ", ".join(f"{sid} {code}" for sid, code in sorted(chosen.items()))
        alt = "; ".join(f"{sid}: " + ", ".join(f"{c} ({conf})" for c, conf in others[sid]) for sid in sorted(others))
        note = (f"alternative readings disagree; answered with the higher-confidence reading ({used}); "
                f"other readings: {alt}")
        return ans.model_copy(update={
            "uncertain_signs": sorted(set(ans.uncertain_signs) | set(uncertain)),
            "note": note + (f"; {ans.note}" if ans.note else ""),
            "basis": list(dict.fromkeys([*ans.basis, "reading_choice"]))})

    # ------------------------------------------------------------------ per program
    # Claims whose verdict rests on "no visible sign says otherwise" (closed world):
    # the verdict that an unreadable sign could overturn.
    # phase 4.8c B1: claims a single sign decides (Forbidden arrives as Verify(Permitted))
    _CHART_CLAIMS = (Permitted, SpeedOk, Required, ExistsViolation, IsSign, Present, SignApplies,
                     SpeedLimitIs, RulePermitted, LanesOnly)

    _CLOSED_WORLD = {Permitted: Verdict.yes, SpeedOk: Verdict.yes,
                     Required: Verdict.no, ExistsViolation: Verdict.no}

    def unreadable_signs(self, scene: SceneGraph) -> list[str]:
        """Signs that could not be read. Phase 4.5 B6: when the guide-board call read the photo,
        an unread blue / green / white / yellow board is one it transcribed, so it no longer
        counts (red boards, local ban notices, still do)."""
        return [sg.id for sg in scene.signs if not self.catalog.has(sg.code)
                and not (scene.guide_boards and board_read(sg))]

    def unmodelled_signs(self, scene: SceneGraph) -> list[str]:
        """Catalogued signs whose legal effect the rules don't model (effect_unmodelled)."""
        return [sg.id for sg in scene.signs
                if self.catalog.has(sg.code) and self.catalog.get(sg.code).effect_unmodelled]

    @staticmethod
    def visual_category(sign) -> str:
        """What an unreadable sign could be, from how it looks (QCVN 41 sign groups):
        red_circle (prohibitory, incl. P.130/P.131 on blue), blue_circle (mandatory),
        red_board (a rectangle with a red background or border: local ban notices and
        red plates, treated as prohibitory; owner, 2026-11-16, plan item 1b.4),
        board (blue/green/white rectangle: information, lane boards, plates),
        warning (triangle), octagon (R.122 stop), or unknown (nothing recorded).
        Relevance only: the gate's matching (vqa.perception.matching) keeps its own
        groups, where every rectangle is a board."""
        shape = sign.shape.value if sign.shape else None
        border = sign.border.value if sign.border else None
        bg = sign.background.value if sign.background else None
        return Engine.category_of(shape, border, bg)

    @staticmethod
    def category_of(shape: str | None, border: str | None, bg: str | None) -> str:
        """visual_category from plain look strings (also used for catalog visuals)."""
        if shape == "circle" and border == "red":
            return "red_circle"
        if shape == "circle" and bg == "blue":
            return "blue_circle"
        if shape in ("rectangle", "square") and "red" in (border, bg):
            return "red_board"
        if shape in ("rectangle", "square"):
            return "board"
        if shape in ("triangle", "diamond"):
            return "warning"
        if shape == "octagon":
            return "octagon"
        if shape == "circle" and border == "black":
            return "end_of_restriction"   # lifts restrictions; cannot add one
        return "unknown"

    @staticmethod
    def could_matter(category: str, p: Program) -> bool:
        """Could an unreadable sign of this category overturn a closed-world verdict
        for program p? Conservative: an unknown category always could."""
        if category == "unknown":
            return True
        if category in ("warning", "end_of_restriction"):
            return False
        lane = getattr(p, "lane", None)
        if category == "red_board":          # counts as prohibitory (plan item 1b.4)
            category = "red_circle"
        if isinstance(p, Permitted):
            if category == "red_circle":
                return True
            if category == "blue_circle":   # mandatory directions (R.301), R.302 ...
                return p.action.value in ("go_straight", "turn_left", "turn_right", "u_turn")
            if category == "board":          # lane boards: P.127c, R.412, R.415a
                return lane is not None
            if category == "octagon":
                return p.action.value == "stop"
        if isinstance(p, SpeedOk):           # P.127 (red circle), R.306 (blue), lane boards
            return category in ("red_circle", "blue_circle", "board")
        if isinstance(p, Required):
            return category in ("blue_circle", "octagon")
        if isinstance(p, ExistsViolation):
            return True
        return False

    def _lane_directions_matter(self, sign, p: Program) -> bool:
        """Phase 4.5 rank 1: a lane-directions board (R.411, D.13: "bắt buộc người tham gia
        giao thông phải đi đúng làn đường đã được chỉ dẫn hướng") orders the direction on
        every lane, so its unmodelled effect bears on any direction claim, a lane asked or
        not. Without its lane rows the claim stays unknown instead of a closed-world yes."""
        return (isinstance(p, Permitted) and p.action.value in ("go_straight", "turn_left", "turn_right", "u_turn")
                and self.catalog.has(sign.code) and self.catalog.get(sign.code).key == "lane_directions")

    def _r411_arrows_decide_in(self, scene: SceneGraph, sign, p: Program) -> bool:
        if isinstance(p, ExistsViolation):
            lanes = [v.lane for v in scene.vehicles]
            return (sign.code.startswith("R.411") and bool(lanes)
                    and all(l is not None and any(r.lane == l and r.directions for r in sign.lanes) for l in lanes))
        return self._r411_arrows_decide(sign, p)

    @staticmethod
    def _r411_arrows_decide(sign, p: Program) -> bool:
        """Phase 4.7 (scene v6): an R.411 board whose arrows were read for the lane a claim asks
        about is modelled for that claim (kb/rules/signals47.pl, D.13). Without arrows, or with no
        lane asked, it stays unmodelled as before."""
        lane = getattr(p, "lane", None)
        if not sign.code.startswith("R.411"):
            return False
        return (lane is not None and any(row.lane == lane and row.directions for row in sign.lanes))

    def _run(self, scene: SceneGraph, p: Program) -> Answer:
        """Dispatch, then: a closed-world verdict becomes unknown when the scene has an
        unreadable sign whose visible category could bear on the claim, since that
        sign might say otherwise. Others (e.g. a blue information board for a turn
        question) are ignored."""
        self._look_note = None
        try:
            ans = self._dispatch(scene, p)
        except UndecidedSelection as e:                     # parser v13: relative selectors
            return Answer(verdict=Verdict.unknown, note=str(e))
        if self._look_note:                                 # phase 4.8 B6: category word set aside
            ans = ans.model_copy(update={"note": self._look_note + (f"; {ans.note}" if ans.note else "")})
        if (self.sign_chart_n and len(scene.signs) > self.sign_chart_n
                and isinstance(p, self._CHART_CLAIMS) and ans.verdict in (Verdict.yes, Verdict.no)):
            # phase 4.8c B1: a photo of a sign chart (more signs than any road scene in the train
            # evidence) is not a road: a claim one sign would decide is not answered from it
            return ans.model_copy(update={
                "verdict": Verdict.unknown,
                "note": f"the photo shows {len(scene.signs)} signs, like a sign chart; a claim one sign "
                        "would decide is not answered from it"})
        cw = self._CLOSED_WORLD.get(type(p))
        unread = [sid for sid in self.unreadable_signs(scene)
                  if self.could_matter(self.visual_category(scene.sign(sid)), p)]
        unmodelled = [sid for sid in self.unmodelled_signs(scene)
                      if (self.could_matter(self.visual_category(scene.sign(sid)), p)
                          or self._lane_directions_matter(scene.sign(sid), p))
                      and not self._r411_arrows_decide_in(scene, scene.sign(sid), p)]
        if cw is not None and (unread or unmodelled) and ans.verdict == cw:
            note = ("a sign in the scene could not be read; it may change this answer" if unread
                    else "a sign in the scene has an effect the rules don't model; "
                         "it may change this answer")
            ans = ans.model_copy(update={
                "verdict": Verdict.unknown,
                "uncertain_signs": sorted(set(ans.uncertain_signs) | set(unread) | set(unmodelled)),
                "note": note})
        return ans

    def _dispatch(self, scene: SceneGraph, p: Program) -> Answer:
        v = getattr(p, "vehicle", None)
        if v is not None and v.cls is VehicleClass.every_vehicle:
            return self._for_every_vehicle(scene, p)
        when = getattr(p, "when", None)
        if when is not None and when.is_interval and not isinstance(p, Permitted):
            return Answer(verdict=Verdict.unknown,
                          note="time intervals are supported for permitted/forbidden only")
        if isinstance(p, Choose):
            return self._choose(scene, p)
        if isinstance(p, IsSign):
            return self._is_sign(scene, p)
        if isinstance(p, WhichVehicles):
            return self._which_vehicles(scene, p)
        if isinstance(p, LaneVehicles):
            return self._lane_vehicles(scene, p)
        if isinstance(p, SpeedLimit):
            return self._speed_limit(scene, p)
        if isinstance(p, (AllOf, AnyOf)):
            return self._connective(scene, p)
        if isinstance(p, Verify):
            return self._verify(scene, p)
        if isinstance(p, Permitted):
            return self._permitted(scene, p)
        if isinstance(p, SpeedOk):
            return self._speed_ok(scene, p)
        if isinstance(p, (LanesFor, LanesWhere)):
            return self._lanes(scene, p)
        if isinstance(p, BanTimes):
            return self._ban_times(scene, p)
        if isinstance(p, Meaning):
            return self._meaning(scene, p) if p.aspect == "name" else self._meaning_aspect(scene, p)
        if isinstance(p, Present):
            return self._present(scene, p)
        if isinstance(p, (Count, CountIs)):          # phase 4.7 step 1b
            return self._count(scene, p)
        if isinstance(p, (AppliesTo, SignApplies)):  # phase 4.7 step 1b
            return self._applies_to(scene, p)
        if isinstance(p, RulePermitted):               # phase 4.7 step 1c
            return self._rule_permitted(scene, p)
        if isinstance(p, (SignalMeaning, MarkingMeaning, MarkingIs)):   # phase 4.7 step 1d
            return self._v6_meaning(scene, p)
        if isinstance(p, Duties):                      # phase 4.7 step 1c
            from vqa.reasoning import sign_info as si
            row = si.duties(p.topic)
            return Answer(verdict=Verdict.value, value={"topic": p.topic, "duties": row["items"]},
                          citations=[Citation(**row["source"])]
                          + [Citation(**c) for c in row.get("also_sources", [])])      # parser v13
        if isinstance(p, (OfficerSignal, OfficerPermits, Precedence, PrecedenceIs, RightOfWay, MustYield,
                          VehicleClassOf, VehicleClassIs)):            # parser v13
            return self._v13(scene, p)
        if isinstance(p, Guide):
            return self._guide(scene, p)
        if isinstance(p, GuideClaim):
            return self._guide_claim(scene, p)
        if isinstance(p, SpeedLimitIs):
            return self._speed_limit_is(scene, p)
        if isinstance(p, Multi):
            return self._multi(scene, p)
        if isinstance(p, Explain):
            return self._explain(scene, p)
        if isinstance(p, ExistsViolation):
            return self._violations(scene, p)
        if isinstance(p, Required):
            return self._required(scene, p)
        if isinstance(p, LanesOnly):                   # parser v17 (phase 4.8c)
            return self._lanes_only(scene, p)
        if isinstance(p, ViolationKind):               # parser v17 (phase 4.8c)
            return self._violation_kind(scene, p)
        if isinstance(p, LaneReservedIs):              # parser v18 (owner, 2026-11-20)
            return self._lane_reserved_is(scene, p)
        raise EngineError(f"unsupported program {type(p).__name__}")

    _RANK = {"high": 0, "medium": 1, "low": 2}

    def _the_pointed_sign(self, scene: SceneGraph, ids: list[str]) -> list[str]:
        """Phase 4.8c B2 (switch one_sign_g1): the question points at one sign ("biển trong ảnh"),
        and several readable signs with different codes match. Speed discs printed on a guide
        board (ids g1, g2 ... added by the board call) are part of that board, not signs of their
        own, so they are dropped when a sign remains; then a sign read with strictly higher
        confidence than every other is the one named. Otherwise every sign stays (G1).
        Selection only: what the sign means still comes from the catalog."""
        own = [i for i in ids if not (scene.guide_boards and i.startswith("g"))] or ids
        rank = {i: self._RANK[scene.sign(i).confidence.value] for i in own}
        top = [i for i in own if rank[i] == min(rank.values())]
        codes = {self.catalog.get(scene.sign(i).code).code for i in top}
        return top if len(codes) == 1 else own

    # ------------------------------------------------------------------ parser v17 (phase 4.8c)
    _LANE_RISK = ("unknown", "red_circle", "red_board", "blue_circle", "board")

    def _lanes_only(self, scene: SceneGraph, p: LanesOnly) -> Answer:
        """The vehicle may use only the lanes in `lanes` (and one of them). Python packages the
        per-lane answers of `q_lane` (the same rules as `lanes_for`); the rules decide each lane.
        A verdict that rests on a lane being open is a closed-world conclusion, so an unreadable
        or unmodelled sign that could bear on lanes makes it unknown."""
        n = scene_lane_count(scene)
        if not n:
            return Answer(verdict=Verdict.unknown, note="the scene does not say how many lanes there are")
        lanes = sorted(set(p.lanes))
        if any(l < 1 or l > n for l in lanes):
            return Answer(verdict=Verdict.unknown, note=f"the scene shows {n} lanes")
        base = self._lanes(scene, LanesFor(vehicle=p.vehicle, speed_kmh=p.speed_kmh, when=p.when))
        per = {x["lane"]: x["verdict"] for x in base.value["per_lane"]}
        inside = [per[l] for l in lanes]
        outside = [per[l] for l in range(1, n + 1) if l not in lanes]
        if any(v == "yes" for v in outside):
            verdict, on_open = Verdict.no, True
        elif all(v == "no" for v in inside):
            verdict, on_open = Verdict.no, False
        elif all(v == "no" for v in outside) and any(v == "yes" for v in inside):
            verdict, on_open = Verdict.yes, True
        else:
            verdict, on_open = Verdict.unknown, False
        value = {"lanes": lanes, "open_lanes": base.value["lanes"], "conditional": base.value["conditional"],
                 "per_lane": base.value["per_lane"], "lane_count": n}
        ans = Answer(verdict=verdict, value=value, reasons=base.reasons, citations=base.citations,
                     basis=base.basis)
        risky = [sid for sid in self.unreadable_signs(scene) + self.unmodelled_signs(scene)
                 if self.visual_category(scene.sign(sid)) in self._LANE_RISK]
        if on_open and risky:
            ans = ans.model_copy(update={
                "verdict": Verdict.unknown, "uncertain_signs": sorted(set(risky)),
                "note": "a sign in the scene could not be read or has an effect the rules don't model; "
                        "it may change which lanes are open"})
        return ans

    def _lane_reserved_is(self, scene: SceneGraph, p: LaneReservedIs) -> Answer:
        """Lane X is reserved for Y: the per-class lane answers of `lane_vehicles` (the rules
        decide each class); Python only sorts the classes into Y's own (Y, its kinds, the classes
        Y belongs to) and the others. Closed-world like lanes_only: an unreadable or unmodelled
        sign that could bear on lanes makes a yes unknown."""
        n = scene_lane_count(scene)
        if not n:
            return Answer(verdict=Verdict.unknown, note="the scene does not say how many lanes there are")
        if p.lane < 1 or p.lane > n:
            return Answer(verdict=Verdict.unknown, note=f"the scene shows {n} lanes")
        results = self._lane_class_results(scene, p.lane, p.when, None)
        per = {c: v for c, (v, _) in results.items()}
        y = p.vehicle.cls.value
        related = {c for c in per if janus.query_once(f"(subclass_of({c}, {y}) ; subclass_of({y}, {c}))")["truth"]}
        others = {c: v for c, v in per.items() if c not in related and c not in ("pedestrian",)}
        mine = per.get(y, "unknown")
        if mine == "no" or any(v == "yes" for v in others.values()):
            verdict = Verdict.no
        elif mine == "yes" and others and all(v == "no" for v in others.values()):
            verdict = Verdict.yes
        else:
            verdict = Verdict.unknown
        keys = [y] + ([c for c, v in others.items() if v == "yes"] if verdict is Verdict.no and mine != "no"
                      else list(others) if verdict is Verdict.yes else [])
        support = [r for c in keys for r in _supporting(results[c][1])]
        value = {"lane": p.lane, "vehicle": y, "open_to_others": sorted(c for c, v in others.items() if v == "yes")}
        ans = Answer(verdict=verdict, value=value, reasons=support, citations=_cites(support), basis=_basis(support))
        risky = [sid for sid in self.unreadable_signs(scene) + self.unmodelled_signs(scene)
                 if self.visual_category(scene.sign(sid)) in self._LANE_RISK]
        if verdict is Verdict.yes and risky:
            ans = ans.model_copy(update={
                "verdict": Verdict.unknown, "uncertain_signs": sorted(set(risky)),
                "note": "a sign in the scene could not be read or has an effect the rules don't model; "
                        "it may change which vehicles the lane is open to"})
        return ans

    _VIOLATION_ACTIONS = (Action.enter, Action.go_straight, Action.turn_left, Action.turn_right,
                          Action.u_turn, Action.overtake, Action.stop, Action.park, Action.honk)

    def _violation_kind(self, scene: SceneGraph, p: ViolationKind) -> Answer:
        """What the signs ban the named vehicle from doing: each action asked of the rules as a
        permission (`q_permitted`, closed world as for `permitted`). Banned = the rules answer no;
        the answer is unknown when no action is surely banned."""
        banned, conditional, reasons = [], [], []
        for act in self._VIOLATION_ACTIONS:
            a = self._run(scene, Permitted(action=act, vehicle=p.vehicle, when=p.when))
            if a.verdict is Verdict.no:
                ids = sorted({r.sign_id for r in a.reasons if r.sign_id and r.truth == "true"})
                banned.append({"action": act.value, "sign_ids": ids})
                reasons += [r for r in a.reasons if r.truth == "true"]
            elif a.verdict is Verdict.unknown and any(r.truth == "unknown" and r.sign_id for r in a.reasons):
                conditional.append(act.value)
        value = {"vehicle": p.vehicle.cls.value, "violations": banned, "conditional_actions": conditional}
        if not banned:
            return Answer(verdict=Verdict.unknown, value=value,
                          note="no sign in the photo surely bans this vehicle from any action")
        return Answer(verdict=Verdict.value, value=value, reasons=reasons, citations=_cites(reasons),
                      basis=_basis(reasons))

    def _permitted(self, scene: SceneGraph, p: Permitted) -> Answer:
        selection = None
        if p.sign is not None:
            selection = self.resolve(scene, p.sign)
            if not selection:
                return Answer(verdict=Verdict.unknown, note="no sign in the scene matches the selector")
        self.load_scene(scene, selection)
        if p.when is not None and p.when.is_interval:
            d1, d2 = _days(p.when)
            out = self.call(Term("q_permitted_iv", atom(p.action.value), vehicle_term(p.vehicle),
                                 _minute(p.when.start), _minute(p.when.end), d1, d2, p.lane,
                                 atom(p.when.quantifier.value)))
            ans = _verdict_answer(out)
            return ans.model_copy(update={"value": {
                "decided_at": _fmt_min(out["minute"]), "moments_checked": out["checked"]}})
        out = self.call(Term("q_permitted", atom(p.action.value), vehicle_term(p.vehicle),
                             _ctx(p.when, scene, p.lane)))
        return _verdict_answer(out)

    @staticmethod
    def _with_divider(scene: SceneGraph, divided: bool | None) -> SceneGraph:
        """The question's "có / không có dải phân cách" (phase 4.5) overrides the scene's."""
        if divided is None:
            return scene
        return scene.model_copy(update={"road": scene.road.model_copy(update={"divided": divided})})

    def _speed_ok(self, scene: SceneGraph, p: SpeedOk) -> Answer:
        scene = self._with_divider(scene, p.road_divided)
        self.load_scene(scene)
        out = self.call(Term("q_speed", vehicle_term(p.vehicle), float(p.speed_kmh),
                             p.lane, _ctx(p.when, scene, p.lane)))
        ans = _verdict_answer(out)
        n = scene_lane_count(scene)
        if p.lane is not None or ans.verdict is not Verdict.unknown or not n \
                or not any(s.position.lane for s in scene.signs):
            return ans
        # KB-6 (phase 4.5, owner 2026-11-17): speed signs over some lanes and no lane in the
        # claim: decided when every lane gives the same verdict (signs over lanes apply per
        # lane; an interpretation, no law sentence says it).
        per = [self._speed_ok(scene, p.model_copy(update={"lane": lane})) for lane in range(1, n + 1)]
        vs = {a.verdict for a in per}
        if len(vs) == 1 and vs <= {Verdict.yes, Verdict.no}:
            first = per[0]
            return first.model_copy(update={
                "value": {"per_lane": [a.verdict.value for a in per], "rule": "kb6_every_lane_agrees"},
                "citations": [c for a in per for c in a.citations],
                "note": "every lane gives the same answer (interpretation KB-6)"})
        return ans

    def _lanes(self, scene: SceneGraph, p: LanesFor | LanesWhere) -> Answer:
        n = scene_lane_count(scene)
        if not n:
            return Answer(verdict=Verdict.unknown, note="the scene does not say how many lanes there are")
        self.load_scene(scene)
        speed = None if p.speed_kmh is None else float(p.speed_kmh)
        per_lane, reasons = [], []
        for lane in range(1, n + 1):
            out = self.call(Term("q_lane", vehicle_term(p.vehicle), lane,
                                 atom("none") if speed is None else speed,
                                 _ctx(p.when, scene, lane)))
            per_lane.append({"lane": lane, "verdict": out["verdict"]})
            reasons += _supporting(out)
        want = "yes" if isinstance(p, LanesFor) or p.ok else "no"
        value = {
            "lanes": [x["lane"] for x in per_lane if x["verdict"] == want],
            "conditional": [x["lane"] for x in per_lane if x["verdict"] == "unknown"],
            "per_lane": per_lane,
            "lane_count": n,
        }
        return Answer(verdict=Verdict.value, value=value, reasons=reasons,
                      citations=_cites(reasons), basis=_basis(reasons))

    def _ban_times(self, scene: SceneGraph, p: BanTimes) -> Answer:
        selection = self.resolve(scene, p.sign) if p.sign else None
        self.load_scene(scene, selection)
        out = self.call(Term("q_ban_times", atom(p.action.value), vehicle_term(p.vehicle)))
        items, reasons = [], []
        clears = [_reason(c) for c in out["clears"]]
        for it in out["items"]:
            if it["truth"] == "false":
                continue
            items.append({
                "sign_id": it["sign_id"],
                "windows": [[_fmt_min(f), _fmt_min(t)] for f, t in it["windows"]],
                "days": it["days"] or None,
                "always": not it["windows"] and not it["days"] and it["truth"] == "true",
                "truth": it["truth"],
            })
            if isinstance(it.get("proof"), dict):
                reasons.append(Reason(sign_id=it["sign_id"], truth=it["truth"],
                                      proof=explain.to_node(it["proof"])))
        support = reasons if items else clears
        return Answer(verdict=Verdict.value, value={"bans": items, "banned": bool(items)},
                      reasons=reasons + clears, citations=_cites(support), basis=_basis(support))

    def _meaning(self, scene: SceneGraph, p: Meaning) -> Answer:
        ids = self.resolve_value(scene, p.sign)
        unread_only: list[str] = []
        if p.sign.only:
            chosen, unread_only = self.single_sign(scene, ids)
            if chosen is None:
                readable = [i for i in ids if self.catalog.has(scene.sign(i).code)]
                if not (self.several_signs and readable):
                    return Answer(verdict=Verdict.unknown, value={"candidates": ids},
                                  uncertain_signs=unread_only,
                                  note="expected exactly one sign in the scene")
                # phase 4.8 G1: several readable signs with different codes: one meaning each
                # (one per code), the unreadable ones listed as uncertain
                if self.one_sign_g1:
                    readable = self._the_pointed_sign(scene, readable)
                by_code: dict[str, str] = {}
                for i in readable:
                    by_code.setdefault(self.catalog.get(scene.sign(i).code).code, i)
                chosen = list(by_code.values())
                several_note = "several signs in the scene: the meaning of each is given"
            else:
                chosen, several_note = chosen[:1], None   # same code: one meaning
            ids = chosen
        else:
            several_note = None
        out, cites = [], []
        for sid in ids:
            s = scene.sign(sid)
            if not self.catalog.has(s.code):
                out.append({"sign_id": sid, "code": s.code, "known": False})
                continue
            e = self.catalog.get(s.code)
            out.append({"sign_id": sid, "code": e.code, "name_vi": e.name_vi,
                        "name_en": e.name_en, "category": e.category, "group_vi": sign_group_vi(e.code),
                        "value": s.value, "known": True})
            cites.append(e.source)
        if not out:
            return Answer(verdict=Verdict.unknown, note="no sign in the scene matches the selector")
        # plan item 1b.2: answer for the readable signs; the unreadable ones stay in the
        # value (known: false) and are listed in uncertain_signs
        unread = unread_only + [o["sign_id"] for o in out if not o["known"]]
        verdict = Verdict.value if any(o["known"] for o in out) else Verdict.unknown
        return Answer(verdict=verdict, value=out, citations=cites, uncertain_signs=unread, note=several_note)

    # ------------------------------------------------------------------ phase 4.5 B1 + B6
    def _meaning_aspect(self, scene: SceneGraph, p: Meaning) -> Answer:
        """group (art. 11), conduct (the catalog's effects and conduct items), scope and
        placement (kb/sign_info.yaml) of the selected signs. With `only` and several signs, all
        readable candidates are used; the unreadable ones are listed as uncertain."""
        from vqa.reasoning import sign_info as si

        ids = self.resolve_value(scene, p.sign)
        readable = [i for i in ids if self.catalog.has(scene.sign(i).code)]
        unread = [i for i in ids if i not in readable]
        if not readable:
            return Answer(verdict=Verdict.unknown, uncertain_signs=unread,
                          note="no readable sign in the scene matches the selector")
        entries = [(i, self.catalog.get(scene.sign(i).code)) for i in readable]
        if p.aspect == "limit":
            return self._limit_values(scene, entries, unread)
        if p.aspect == "article":
            # Phase 4.6 I1: the QCVN 41 article listing the sign's group (art. 22.1 prohibitory,
            # 28.1 warning, 32.1 mandatory, 36.1 information, 41 / 42 auxiliary and text signs;
            # IE rows: their own art. 47), and the appendix article the catalog row cites.
            rows = []
            for i, e in entries:
                art = group_article(e.code)
                if art is None:
                    continue
                rows.append({"sign_id": i, "code": e.code, "name_vi": e.name_vi, "article": art[0],
                             "appendix": e.source.article_id if e.source.article_id != art[1] else None})
            if not rows:
                return Answer(verdict=Verdict.unknown, uncertain_signs=unread, note="no article for these signs")
            cites = [Citation(law_id="QCVN 41:2024/BGTVT", article_id=group_article(r["code"])[1]) for r in rows]
            cites += [e.source for _, e in entries]
            return Answer(verdict=Verdict.value, value={"article": rows}, uncertain_signs=unread,
                          citations=list({(c.law_id, c.article_id): c for c in cites}.values()))
        if p.aspect == "group":
            # Decided when every readable selected sign falls in one art. 11 group; unreadable
            # candidates are dropped and listed, as for single-sign questions (Engine.single_sign).
            # Alternative readings are handled by Engine.answer (one run per reading).
            groups = {sign_group_vi(e.code) for _, e in entries}
            if len(groups) != 1 or None in groups:
                return Answer(verdict=Verdict.unknown, value={"groups": sorted(g for g in groups if g)},
                              uncertain_signs=unread,
                              note="the selected signs are not all in one group")
            return Answer(verdict=Verdict.value, value={"group": groups.pop()},
                          citations=[si.ART11] + list({e.source.article_id: e.source for _, e in entries}.values()),
                          uncertain_signs=unread)
        out, cites = self._aspect_lines(scene, p, entries, extended=False)
        if not out:
            # phase 4.7 step 1a: kb/sign_info_47.yaml, only when no selected sign has a line
            out, cites = self._aspect_lines(scene, p, entries, extended=True)
        if not out:
            return Answer(verdict=Verdict.unknown, uncertain_signs=unread,
                          note=f"no {p.aspect} rule for the selected signs")
        cites = list({(c.law_id, c.article_id): c for c in cites}.values())
        return Answer(verdict=Verdict.value, value={p.aspect: out}, citations=cites, uncertain_signs=unread)

    def _limit_values(self, scene: SceneGraph, entries, unread: list[str]) -> Answer:
        """Phase 4.8 B3: the limit each selected sign sets: the number read on it with the catalog
        row's attribute, comparison and unit (e.g. P.115: gross_t > 13 t, B.15). Speed signs are
        left to speed_limit. A limit sign whose number was not read is unknown."""
        rows, cites, missing = [], [], []
        for i, e in entries:
            v = e.effect.value
            if v is None or v.unit == "km/h":
                continue
            s = scene.sign(i)
            if s.value is None:
                missing.append(i)
                continue
            rows.append({"sign_id": i, "code": e.code, "name_vi": e.name_vi, "attr": v.attr.value,
                         "op": v.op.value, "value": s.value, "unit": v.unit,
                         "applies_to": [c.value for c in v.applies_to]})
            cites.append(e.source)
        if missing:
            return Answer(verdict=Verdict.unknown, uncertain_signs=sorted(set(unread) | set(missing)),
                          note="the number on a limit sign was not read")
        if not rows:
            return Answer(verdict=Verdict.unknown, uncertain_signs=unread,
                          note="no selected sign sets a size or weight limit")
        return Answer(verdict=Verdict.value, value={"limit": rows}, citations=cites, uncertain_signs=unread)

    def _aspect_lines(self, scene: SceneGraph, p: Meaning, entries, extended: bool):
        from vqa.reasoning import sign_info as si
        out, cites = [], []
        for i, e in entries:
            if p.aspect == "conduct":
                items, c = si.conduct_items(e, self.catalog, extended=extended)
                if items:
                    out.append({"sign_id": i, "code": e.code, "name_vi": e.name_vi, "conduct": items})
                    cites += c
            else:
                hit = si.lookup(p.aspect, e.code, e.category, extended=extended)
                if hit:
                    text = hit[0]
                    s = scene.sign(i)
                    if p.aspect == "scope":
                        # S.501 (F.1) gives the length of the section; S.502 is the distance
                        # to it, not the scope, so only S.501 counts here.
                        d = next((pl.distance_m for pl in s.plates if pl.distance_m and pl.code == "S.501"), None)
                        if d:
                            text += f"; biển phụ S.501 ghi phạm vi {d:g} m"
                            cites.append(si.F1)
                    out.append({"sign_id": i, "code": e.code, "name_vi": e.name_vi, p.aspect: text})
                    cites += [e.source, hit[1]]
        return out, cites

    # ------------------------------------------------------------------ phase 4.7 step 1b
    def _could_match(self, scene: SceneGraph, sel: Selector, sid: str) -> bool:
        """An unread sign could be one the selector picks: it passes the look filters, and its
        look is that of a catalog row the group / name / code filters allow."""
        look_only = sel.model_copy(update={"category": None, "meaning": None, "code": None})
        if sid not in self.resolve(scene, look_only):
            return False
        rows = self.catalog.signs
        if sel.category:
            cat = sel.category.value if hasattr(sel.category, "value") else sel.category
            rows = [r for r in rows if r.category == cat]
        if sel.meaning:
            try:
                codes = set(self.catalog.codes_for_meaning(sel.meaning))
            except KeyError as e:
                raise EngineError(str(e)) from None
            rows = [r for r in rows if r.code in codes]
        if sel.code:
            rows = [r for r in rows if r.code in self.catalog.codes_matching(sel.code)]
        looks = {self.category_of(r.visual.shape, r.visual.border, r.visual.background) for r in rows}
        vc = self.visual_category(scene.sign(sid))
        return vc == "unknown" or vc in looks

    def _covers(self, scene: SceneGraph, ids: list[str], veh: Vehicle) -> tuple[str, list[Reason]]:
        """yes / no / unknown / none over the selected signs (kb/rules/coverage47.pl)."""
        self.load_scene(scene)
        verdicts, reasons = [], []
        for sid in ids:
            out = self.call(Term("q_covers", sid, vehicle_term(veh)))
            verdicts.append(out["verdict"])
            reasons += [_reason(r) for r in out["reasons"]]
        for v in ("yes", "unknown", "no"):
            if v in verdicts:
                return v, reasons
        return "none", reasons

    def _count(self, scene: SceneGraph, p: Count | CountIs) -> Answer:
        sel = p.sign.model_copy(update={"only": False})
        ids = self.resolve(scene, sel)
        readable = [i for i in ids if self.catalog.has(scene.sign(i).code)]
        unread = [i for i in self.unreadable_signs(scene) if self._could_match(scene, sel, i)]
        reasons: list[Reason] = []
        if p.vehicle is not None:
            kept, maybe = [], []
            for i in readable:
                v, r = self._covers(scene, [i], p.vehicle)
                reasons += r
                if v == "yes":
                    kept.append(i)
                elif v in ("unknown", "none"):
                    maybe.append(i)
            readable, unread = kept, unread + maybe
        lo, hi = len(readable), len(readable) + len(unread)
        cites = [Citation(law_id="QCVN 41:2024/BGTVT", article_id="11")] if sel.category else []
        cites += list({self.catalog.get(scene.sign(i).code).source.key(): self.catalog.get(scene.sign(i).code).source
                       for i in readable}.values())
        cites += _cites(reasons)
        value = {"count": lo, "signs": readable} if lo == hi else {"at_least": lo, "at_most": hi, "signs": readable}
        if isinstance(p, Count):
            if lo == hi:
                return Answer(verdict=Verdict.value, value=value, reasons=reasons, citations=cites)
            return Answer(verdict=Verdict.unknown, value=value, uncertain_signs=unread, reasons=reasons,
                          citations=cites, note="a sign that could not be read may be one of them")
        if p.op != "eq":                                     # parser v13: a bound on the count
            import operator
            cmp = {"ge": operator.ge, "gt": operator.gt, "le": operator.le, "lt": operator.lt}[p.op]
            held = {cmp(k, p.n) for k in range(lo, hi + 1)}
            if held == {True}:
                return Answer(verdict=Verdict.yes, value=value, reasons=reasons, citations=cites)
            if held == {False}:
                return Answer(verdict=Verdict.no, value=value, reasons=reasons, citations=cites,
                              uncertain_signs=unread)
            return Answer(verdict=Verdict.unknown, value=value, uncertain_signs=unread, reasons=reasons,
                          citations=cites, note="a sign that could not be read may be one of them")
        if lo == hi == p.n:
            return Answer(verdict=Verdict.yes, value=value, reasons=reasons, citations=cites)
        if p.n < lo or p.n > hi:
            return Answer(verdict=Verdict.no, value=value, reasons=reasons, citations=cites,
                          uncertain_signs=unread)
        return Answer(verdict=Verdict.unknown, value=value, uncertain_signs=unread, reasons=reasons,
                      citations=cites, note="a sign that could not be read may be one of them")

    def _applies_to(self, scene: SceneGraph, p: AppliesTo | SignApplies) -> Answer:
        ids = self.resolve_value(scene, p.sign) if isinstance(p, AppliesTo) else self.resolve(scene, p.sign)
        if not ids:
            return Answer(verdict=Verdict.unknown, note="no sign in the scene matches the selector")
        unread: list[str] = []
        if p.sign.only:
            chosen, unread = self.single_sign(scene, ids)
            if chosen is None:
                return Answer(verdict=Verdict.unknown, uncertain_signs=unread,
                              note="expected exactly one sign in the scene")
            ids = chosen
        ids = [i for i in ids if self.catalog.has(scene.sign(i).code)]
        if not ids:
            return Answer(verdict=Verdict.unknown, uncertain_signs=unread, note="the sign could not be read")
        # phase 4.7: R.411's order is addressed to every road user (D.13 "bắt buộc người tham gia giao
        # thông"), so who it applies to is known though its directions need the lane arrows
        if any(self.catalog.get(scene.sign(i).code).effect_unmodelled
               and not scene.sign(i).code.startswith("R.411") for i in ids):
            return Answer(verdict=Verdict.unknown, uncertain_signs=unread,
                          note="a selected sign has an effect the rules don't model")
        if isinstance(p, SignApplies):
            per = [(v, *self._covers(scene, ids, v)) for v in p.vehicles]
            reasons = [r for _, _, rs in per for r in rs]
            verdicts = [v for _, v, _ in per]
            if "none" in verdicts:
                return Answer(verdict=Verdict.unknown, uncertain_signs=unread,
                              note="who this sign is addressed to is not modelled")
            verdict = (Verdict.no if "no" in verdicts else Verdict.unknown if "unknown" in verdicts
                       else Verdict.yes)
            return Answer(verdict=verdict, value={"per_vehicle": {v.cls.value: x for v, x, _ in per}},
                          reasons=reasons, citations=_cites(reasons), basis=_basis(reasons),
                          uncertain_signs=unread)
        results = {}
        for c in ONTOLOGY_CLASSES:
            v, rs = self._covers(scene, ids, Vehicle(**{"class": c}))
            if v == "none":
                return Answer(verdict=Verdict.unknown, uncertain_signs=unread,
                              note="who this sign is addressed to is not modelled")
            results[c.value] = (v, rs)
        hits, conditional = self.report_classes(results, "yes")
        support = [r for c in hits + conditional for r in results[c][1] if r.truth in ("true", "unknown")]
        e = self.catalog.get(scene.sign(ids[0]).code)
        exceptions = [x.value for x in e.effect.except_]
        return Answer(verdict=Verdict.value,
                      value={"applies_to": hits, "conditional": conditional, "exceptions": exceptions,
                             "priority_exempt": e.effect.priority_exempt,
                             "per_class": {c: v for c, (v, _) in results.items()}},
                      reasons=support, citations=_cites(support) or [e.source], basis=_basis(support),
                      uncertain_signs=unread)

    def _goal(self, goal: Term) -> Reason | None:
        """A phase-4.7 helper goal proved with its proof, or None when it fails."""
        out = self.call(Term("q_goal", goal))
        if out["ok"] not in (True, "true"):
            return None
        return Reason(truth="true", proof=explain.to_node(out["proof"]))

    def _rule_permitted(self, scene: SceneGraph, p: RulePermitted) -> Answer:
        """Signs (Permitted / SpeedOk) and Law 36's general rules (kb/rules/general47.pl), each
        part three-valued; no when any part forbids, yes when every part allows."""
        veh = vehicle_term(p.vehicle)
        n = scene_lane_count(scene)
        lane = p.lane
        if lane is not None and lane < 0:
            if not n:
                return Answer(verdict=Verdict.unknown, note="the question counts lanes from the right, "
                              "and the scene does not say how many lanes there are")
            lane = n + 1 + lane
        parts: list[tuple[str, list[Reason], str]] = []          # (yes|no|unknown, reasons, what)
        self.load_scene(scene)
        if p.maneuver == "reverse":
            # Law 36 art. 16.2: reversing is banned at the listed places; no sign regulates it, and
            # without a place the answer is unknown
            if p.place is None:
                parts.append(("unknown", [], "art. 16.2: no place given"))
            else:
                out = self.call(Term("q_general", atom("reverse"), veh, atom(p.place.value)))
                rs = [_reason(r) for r in out["reasons"]]
                parts.append(("yes" if out["verdict"] == "none" else out["verdict"], rs, "art. 16.2"))
        elif p.place is not None:
            if p.place.value == "tunnel" and p.action.value in ("stop", "park"):
                # Law 36 art. 26.2, the emergency-lane pattern: only a breakdown allows it
                reason = atom(p.stop_reason or "unknown")
                for t in ("true", "false", "unknown"):
                    r = self._goal(Term("tunnel_stop", reason, atom(t)))
                    if r is not None:
                        parts.append(({"true": "no", "false": "yes", "unknown": "unknown"}[t],
                                      [r.model_copy(update={"truth": t})], "art. 26.2"))
                        break
            elif p.place.value == "emergency_lane" and p.action.value in ("stop", "park"):
                reason = atom(p.stop_reason or "unknown")
                rs = []
                for t in ("true", "false", "unknown"):
                    r = self._goal(Term("emergency_stop", reason, atom(t)))
                    if r is not None:
                        rs = [r.model_copy(update={"truth": t})]
                        parts.append(({"true": "no", "false": "yes", "unknown": "unknown"}[t], rs, "art. 25.2"))
                        break
            else:
                out = self.call(Term("q_general", atom(p.action.value), veh, atom(p.place.value)))
                rs = [_reason(r) for r in out["reasons"]]
                parts.append(("yes" if out["verdict"] == "none" else out["verdict"], rs, "general rule"))
        if lane is not None and n:          # the rule itself checks the vehicle is rudimentary
            for t in ("true", "false"):
                r = self._goal(Term("rudimentary_lane", veh, lane, n, atom(t)))
                if r is not None:
                    parts.append(("no" if t == "true" else "yes", [r.model_copy(update={"truth": t})], "art. 13.3"))
        if p.speed_kmh is not None:
            exempt = self._goal(Term("priority_exempt_speed", veh)) if p.vehicle.priority else None
            if exempt is not None:
                parts.append(("yes", [exempt.model_copy(update={"truth": "false", "detail": "priority_on_duty"})],
                              "art. 27.4"))
            else:
                a = self._run(scene, SpeedOk(vehicle=p.vehicle, speed_kmh=p.speed_kmh, lane=lane,
                                             road_divided=p.road_divided))
                posted = any(self.catalog.has(sg.code) and (self.catalog.get(sg.code).effect.max_speed
                                                            or self.catalog.get(sg.code).effect.lane_board)
                             for sg in scene.signs)
                # Circular 38's defaults hold only where no speed sign is posted ("signs override")
                if not posted and p.area == "outside_residential" and p.road_divided is not None:
                    self.load_scene(scene)
                    out = self.call(Term("q_c38", veh, atom(str(p.road_divided).lower())))
                    lim = None if out["limit"] in ("none", None) else float(out["limit"])
                    if lim is None:              # the vehicle's group (e.g. a truck's mass) is not stated
                        parts.append(("unknown", [], "Circular 38 art. 7"))
                        a = None
                    else:
                        ok = p.speed_kmh <= lim
                        parts.append(("yes" if ok else "no",
                                      [Reason(truth="false" if ok else "true", detail=f"limit_{lim:g}",
                                              proof=explain.to_node(out["proof"]))], "Circular 38 art. 7"))
                        a = None
                if a is not None:
                    parts.append((a.verdict.value if a.verdict.value in ("yes", "no") else "unknown",
                                  a.reasons, "signs"))
        elif p.maneuver is None:
            a = self._run(scene, Permitted(action=p.action, vehicle=p.vehicle, lane=lane))
            parts.append((a.verdict.value if a.verdict.value in ("yes", "no") else "unknown", a.reasons, "signs"))
        if scene.signals and p.maneuver is None and p.speed_kmh is None:      # scene v6: art. 6
            self.load_scene(scene)
            past = atom("unknown" if p.past_stop_line is None else str(p.past_stop_line).lower())
            out = self.call(Term("q_v6", Term("light", atom(p.action.value), veh, past)))
            if out["verdict"] != "none":
                parts.append((out["verdict"], [_reason(r) for r in out["reasons"]], "art. 6 lights"))
            elif p.at_signal:
                parts.append(("unknown", [], "art. 6 lights: no vehicle light read"))
        elif p.at_signal and p.maneuver is None and p.speed_kmh is None:
            # art. 6: passing a light depends on the light; none was read, so no yes from signs alone
            parts.append(("unknown", [], "art. 6 lights: no light read"))
        if p.at_signal and any(w == "art. 6 lights" and v == "yes" for v, _, w in parts):
            # parser v13: QCVN 41 art. 4.1 / Law 36 art. 11.2, the light comes before the sign. Only a
            # green arrow for this very action overrides a sign's "no"; a round green does not.
            r = self._goal(Term("light_overrides_sign", atom(p.action.value)))
            if r is not None:
                parts = [(("yes", [r], "art. 4.1: the light before the sign") if w == "signs" and v == "no"
                          else (v, rs, w)) for v, rs, w in parts]
        if p.maneuver in ("cross_center", "change_lane"):                   # scene v6: G.1
            self.load_scene(scene)
            out = self.call(Term("q_v6", Term("marking", atom(p.maneuver), lane if lane is not None else atom("none"))))
            parts.append(("unknown" if out["verdict"] == "none" else out["verdict"],
                          [_reason(r) for r in out["reasons"]], "G.1 markings"))
        verdicts = [v for v, _, _ in parts]
        verdict = (Verdict.no if "no" in verdicts else Verdict.unknown if ("unknown" in verdicts or not parts)
                   else Verdict.yes)
        want = {"no": "no", "yes": "yes", "unknown": "unknown"}[verdict.value]
        support = [r for v, rs, _ in parts if v == want or verdict is Verdict.yes for r in rs]
        cites = _cites(support)
        if verdict is Verdict.yes and p.place is not None and not cites:
            art = "16" if p.maneuver == "reverse" else {"overtake": "14", "u_turn": "15", "stop": "18",
                                                        "park": "18"}.get(p.action.value)
            if art:
                cites = [Citation(law_id="36/2024/QH15", article_id=art)]
        no_light = verdict is Verdict.unknown and any(w.startswith("art. 6 lights: no") for _, _, w in parts)
        if no_light:
            cites = cites or [Citation(law_id="QCVN 41:2024/BGTVT", article_id="6")]
        return Answer(verdict=verdict, value={"parts": [{"what": w, "verdict": v} for v, _, w in parts]},
                      reasons=support, citations=cites, basis=_basis(support),
                      note="the question is about a traffic light, and none was read in the photo" if no_light
                      else None)

    # ------------------------------------------------------------------ parser v13 (owner, 2026-11-18)
    def _truth(self, goal: Term) -> tuple[str, list[Reason]]:
        out = self.call(Term("q_truth", goal))
        t = out["truth"]
        proof = out.get("proof")
        rs = [Reason(truth=t, proof=explain.to_node(proof))] if isinstance(proof, dict) else []
        return t, rs

    def _v13(self, scene: SceneGraph, p) -> Answer:
        """kb/rules/v13_47.pl: the officer's gestures, which signalling means wins, who yields, and
        vehicle classes. Every verdict comes from Prolog; Python only packages it."""
        self.load_scene(scene)
        unk = atom("unknown")
        verdict_of = {"true": Verdict.yes, "false": Verdict.no, "unknown": Verdict.unknown}
        if isinstance(p, OfficerPermits):
            t, rs = self._truth(Term("officer_forbids", atom(p.gesture), atom(p.side) if p.side else unk,
                                     atom(p.action.value)))
            v = {"true": Verdict.no, "false": Verdict.yes, "unknown": Verdict.unknown}[t]
            return Answer(verdict=v, reasons=rs, citations=_cites(rs),
                          note=None if p.side or t != "unknown" else "the question does not say on which "
                          "side of the officer the driver is")
        if isinstance(p, OfficerSignal):
            out = self.call(Term("q_officer_says", atom(p.gesture)))
            rows = {r["side"]: r["says"] for r in out["rows"]}
            rs = [Reason(truth="true", proof=explain.to_node(out["proof"]))]
            value = {"gesture": p.gesture, "by_side": rows}
            if p.side:
                value["your_side"] = {"side": p.side, "says": rows[p.side]}
            return Answer(verdict=Verdict.value, value=value, reasons=rs, citations=_cites(rs))
        if isinstance(p, (Precedence, PrecedenceIs)):
            a, b = (p.between if isinstance(p, Precedence) else (p.winner, p.over))
            t, rs = self._truth(Term("precedence_truth", atom(a), atom(b)))
            if isinstance(p, PrecedenceIs):
                return Answer(verdict=verdict_of[t], reasons=rs, citations=_cites(rs))
            if t == "unknown":
                return Answer(verdict=Verdict.unknown, reasons=rs, citations=_cites(rs),
                              note="the law's order does not rank these two")
            return Answer(verdict=Verdict.value, value={"follow": a if t == "true" else b, "over": b if t == "true" else a},
                          reasons=rs, citations=_cites(rs))
        if isinstance(p, (RightOfWay, MustYield)):
            my = atom(p.my_road) if p.my_road else unk
            rnd = atom("unknown" if p.roundabout is None else str(p.roundabout).lower())
            if isinstance(p, MustYield):
                t, rs = self._truth(Term("must_yield", atom(p.other_from) if p.other_from else unk, my, rnd))
                return Answer(verdict=verdict_of[t], reasons=rs, citations=_cites(rs))
            out = self.call(Term("q_row_basis", my, rnd))
            rs = [Reason(truth="true", proof=explain.to_node(out["proof"]))]
            basis = out["basis"].split("(")[0]
            yields = {"yield_sign": "you_yield_to_the_major_road", "branch": "you_yield_to_the_major_road",
                      "priority_sign": "others_yield_to_you", "main": "others_yield_to_you",
                      "roundabout": "yield_to_vehicles_from_the_left", "equal": "yield_to_vehicles_from_the_right",
                      "signal": "follow_the_traffic_light"}
            if basis == "conflict":
                return Answer(verdict=Verdict.unknown, reasons=rs, citations=_cites(rs),
                              note="the signs and the question's facts point both ways")
            return Answer(verdict=Verdict.value, value={"rule": yields[basis], "basis": out["basis"]},
                          reasons=rs, citations=_cites(rs))
        if isinstance(p, VehicleClassIs):
            t, rs = self._truth(Term("vehicle_class_truth", vehicle_term(p.vehicle), atom(p.of_class.value)))
            return Answer(verdict=verdict_of[t], reasons=rs, citations=_cites(rs))
        # VehicleClassOf: the classes the vehicle belongs to, and moped / motorcycle by art. 34.1 g
        out = self.call(Term("q_vehicle_ancestors", atom(p.vehicle.cls.value)))
        classes = list(out["classes"])
        rs: list[Reason] = []
        if p.vehicle.cls.value == "motorbike":
            t, rs = self._truth(Term("vehicle_class_truth", vehicle_term(p.vehicle), atom("moped")))
            if t == "true":
                classes.insert(0, "moped")
            elif t == "false":
                classes.insert(0, "motorcycle")
        cites = _cites(rs) or [Citation(law_id="36/2024/QH15", article_id="34")]
        return Answer(verdict=Verdict.value, value={"classes": classes}, reasons=rs, citations=cites)

    def _v6_meaning(self, scene: SceneGraph, p) -> Answer:
        """Scene v6: lights (art. 6) and markings (G.1, G.2) in the photo, from
        kb/signals_markings_47.yaml. Unknown when perception read none."""
        from vqa.reasoning import sign_info as si
        data = si.signals_markings()
        if isinstance(p, SignalMeaning):
            rows = []
            for g in scene.signals:
                if g.kind != "vehicle":
                    continue
                key = (g.colour + "_arrow") if g.arrow != "none" else (
                    "yellow_flashing" if g.colour == "yellow" and g.flashing else g.colour)
                if key in data["signals"]:
                    rows.append({"colour": g.colour, "arrow": g.arrow, "meaning": data["signals"][key]["text"]})
            if not rows:
                return Answer(verdict=Verdict.unknown, note="no traffic light was read in the photo")
            return Answer(verdict=Verdict.value, value={"signals": rows},
                          citations=[Citation(law_id="QCVN 41:2024/BGTVT", article_id="6")])
        marks = [m for m in scene.road.markings if (p.kind is None or m.kind == p.kind)
                 and (p.pattern is None or m.pattern == p.pattern)]
        if isinstance(p, MarkingIs):
            if not marks:
                return Answer(verdict=Verdict.unknown, note="no such marking was read in the photo")
            seps = {data["separates"].get(m.kind) for m in marks}
            verdict = (Verdict.yes if seps == {p.separates} else
                       Verdict.no if p.separates not in seps and None not in seps else Verdict.unknown)
            return Answer(verdict=verdict, value={"markings": [m.kind for m in marks]},
                          citations=[Citation(law_id="QCVN 41:2024/BGTVT", article_id="G.1")])
        if p.kind is None and p.pattern is None and len(scene.road.markings) > 1:
            # owner, 2026-11-18 (rule-only, after the v14 new-types run): a question that names no
            # marking is answered only when the photo shows exactly one; otherwise it may be about a
            # marking perception does not read (painted arrows), so unknown
            return Answer(verdict=Verdict.unknown, value={"markings_read": len(scene.road.markings)},
                          note="the question did not say which marking, and more than one was read in the photo")
        rows, arts = [], set()
        for m in marks:
            key = f"{m.kind}/{m.pattern}" if f"{m.kind}/{m.pattern}" in data["markings"] else m.kind
            if key in data["markings"]:
                rows.append({"kind": m.kind, "pattern": m.pattern, "meaning": data["markings"][key]["text"]})
                arts.add(data["markings"][key]["article"])
        if not rows:
            return Answer(verdict=Verdict.unknown, note="no such marking was read in the photo")
        # art. 51: a marking alone is followed as it is; with lights or signs, all of them, in art. 4's order
        return Answer(verdict=Verdict.value, value={"markings": rows, "effect": data["marking_effect"]["text"]},
                      citations=[Citation(law_id="QCVN 41:2024/BGTVT", article_id=a)
                                 for a in sorted(arts | {data["marking_effect"]["article"]})])

    def _present(self, scene: SceneGraph, p: Present) -> Answer:
        """Is a sign of this code / meaning / category in the photo? Closed world over the
        readable signs (a sign counts by its own code, so P.124a does not stand for P.124b even
        where they share a family row). An unread sign whose look could be the target makes a
        "no" unknown. Alternative readings run through Engine.answer."""
        try:
            if p.code:
                self.catalog.codes_matching(p.code)            # unknown codes are an error
                match = lambda s: self.catalog.code_selects(p.code, s.code)  # noqa: E731
                rows = [self.catalog.get(c) for c in self.catalog.codes_matching(p.code)]
            elif p.meaning:
                codes = set(self.catalog.codes_for_meaning(p.meaning))
                match = lambda s: self.catalog.has(s.code) and self.catalog.get(s.code).code in codes  # noqa: E731
                rows = [self.catalog.get(c) for c in codes]
            else:
                cat = p.category.value if hasattr(p.category, "value") else p.category
                match = lambda s: self.catalog.has(s.code) and self.catalog.get(s.code).category == cat  # noqa: E731
                rows = [s for s in self.catalog.signs if s.category == cat]
        except KeyError as e:
            raise EngineError(str(e)) from None
        hits = [s for s in scene.signs if match(s)]
        if hits:
            return Answer(verdict=Verdict.yes, value={"signs": [s.id for s in hits]},
                          citations=list({self.catalog.get(s.code).source.article_id: self.catalog.get(s.code).source
                                          for s in hits}.values()))
        looks = {self.category_of(r.visual.shape, r.visual.border, r.visual.background) for r in rows}
        unread = set(self.unreadable_signs(scene))
        # Phase 4.6 F2 (owner, 2026-11-17): a red board is a local notice written in free text
        # (CLAUDE.md: counted as prohibitory), so its look rules nothing out: unread, it could
        # state any order or direction, and a "no" stays unknown.
        maybe = [s.id for s in scene.signs if s.id in unread
                 and self.visual_category(s) in (looks | {"unknown", "red_board"})]
        if maybe:
            return Answer(verdict=Verdict.unknown, uncertain_signs=maybe,
                          note="a sign that could not be read might be it")
        return Answer(verdict=Verdict.no, value={"signs": []},
                      citations=list({r.source.article_id: r.source for r in rows}.values())[:3])

    def _guide(self, scene: SceneGraph, p: Guide) -> Answer:
        """What a guide board says (B6). Read from the board data; no legal conclusion."""
        from vqa.reasoning import sign_info as si

        if p.ask == "road_type":
            kind, cites = self.road_kind(scene)
            if kind is None:
                return Answer(verdict=Verdict.unknown, note="nothing in the photo says what kind of road this is")
            return Answer(verdict=Verdict.value, value={"road_type": kind}, citations=cites)
        boards = scene.guide_boards
        if not boards:
            return Answer(verdict=Verdict.unknown, note="no guide board was read in the photo")
        cites = [self.catalog.get(s.code).source for s in scene.signs
                 if self.catalog.has(s.code) and self.catalog.get(s.code).effect.informational][:2] or [si.ART11]
        entries = [e for b in boards for e in b.entries]
        if p.ask == "destinations":
            if p.direction:
                entries = [e for e in entries if _same_direction(e.direction, p.direction)]
            if not entries:
                return Answer(verdict=Verdict.unknown, note="the boards list no destinations"
                              + (f" with a {p.direction} arrow" if p.direction else ""))
            return Answer(verdict=Verdict.value, citations=cites, value={"destinations": [
                {"text": e.text, "direction": e.direction, "distance_m": e.distance_m,
                 "distance": distance_text(e.distance_m)} for e in entries]})
        if p.ask == "route":
            routes = [b.route for b in boards if b.route]
            if not routes:
                return Answer(verdict=Verdict.unknown, note="no route plate was read")
            return Answer(verdict=Verdict.value, value={"routes": routes}, citations=cites)
        hit = si.find_entry(entries, p.destination or "")
        if hit is None:
            return Answer(verdict=Verdict.unknown, note="no board line names that destination")
        if p.ask == "distance" and hit.distance_m is None:
            return Answer(verdict=Verdict.unknown, value={"destination": hit.text},
                          note="the board gives no distance for that destination")
        if p.ask == "direction" and hit.direction == "none":
            return Answer(verdict=Verdict.unknown, value={"destination": hit.text},
                          note="the board shows no arrow for that destination")
        value = {"destination": hit.text, "direction": hit.direction, "distance_m": hit.distance_m,
                 "distance": distance_text(hit.distance_m)}
        if self.stated_exceptions and p.ask == "direction":
            # phase 4.8c B3: the rest of what the board holding this line gives (e.g. "30M" on a
            # route diagram), so every step it shows reaches the answer; board text only
            notes = [t for b in boards if any(e is hit for e in b.entries) for t in b.other if t.strip()]
            if notes:
                value["board_notes"] = notes
        return Answer(verdict=Verdict.value, citations=cites, value=value)

    # ------------------------------------------------------------------ phase 4.6 I1-I4
    def road_kind(self, scene: SceneGraph) -> tuple[str | None, list[Citation]]:
        """What kind of road this is, from scene data only (phase 4.6 I2):
        - an expressway guide sign (code IE, QCVN 41 art. 45-47: IE signs are the expressway
          ones; art. 36.1: "I" is for roads that are not expressways), or the scene's road type;
        - a national road: a route plate "QL ..." (art. 46, a board's route number).
        Returns (kind, citations) or (None, [])."""
        ie = [s for s in scene.signs if s.code.startswith("IE.") and self.catalog.has(s.code)]
        if ie or scene.road.type.value == "expressway":
            return "expressway", [_ART(45)] + [self.catalog.get(s.code).source for s in ie][:2]
        routes = [b.route for b in scene.guide_boards if b.route]
        if any(fold_text(r).startswith("ql") for r in routes):
            return "national_road", [_ART(46)]
        if scene.road.type.value in ("urban", "rural"):
            return scene.road.type.value, []
        return None, []

    def _guide_claim(self, scene: SceneGraph, p: GuideClaim) -> Answer:
        """A stated claim against the boards and signs (phase 4.6 I2). Scene data only; no legal
        conclusion. A destination the boards don't name leaves distance and direction claims
        unknown; `listed` is no only when boards were read and no board sign is left unread."""
        from vqa.reasoning import sign_info as si

        if p.about == "road_type":
            kind, cites = self.road_kind(scene)
            if kind is None:
                return Answer(verdict=Verdict.unknown, note="nothing in the photo says what kind of road this is")
            if kind == p.road_type:
                return Answer(verdict=Verdict.yes, value={"road_type": kind}, citations=cites)
            if p.road_type == "national_road" and kind == "expressway" or p.road_type == "expressway":
                return Answer(verdict=Verdict.no, value={"road_type": kind}, citations=cites or [_ART(45)])
            return Answer(verdict=Verdict.unknown, value={"road_type": kind},
                          note="the photo does not show whether this is a national road")
        if p.about == "ahead":
            return self._ahead(scene, p)
        boards = scene.guide_boards
        if not boards:
            return Answer(verdict=Verdict.unknown, note="no guide board was read in the photo")
        cites = [self.catalog.get(s.code).source for s in scene.signs
                 if self.catalog.has(s.code) and self.catalog.get(s.code).effect.informational][:2] or [si.ART11]
        entries = [e for b in boards for e in b.entries]
        lines = entries + [si_entry(t) for b in boards for t in ([b.route] if b.route else []) + list(b.other)]
        hit = si.find_entry(lines, p.destination or "")
        if p.about == "listed":
            if hit is not None:
                return Answer(verdict=Verdict.yes, value={"destination": hit.text}, citations=cites)
            if self.unreadable_signs(scene):
                return Answer(verdict=Verdict.unknown, uncertain_signs=self.unreadable_signs(scene),
                              note="no board read names it, but a sign could not be read")
            return Answer(verdict=Verdict.no, value={"destination": None}, citations=cites)
        if hit is None:
            return Answer(verdict=Verdict.unknown, note="no board line names that destination")
        if p.about == "distance":
            if hit.distance_m is None:
                return Answer(verdict=Verdict.unknown, value={"destination": hit.text},
                              note="the board gives no distance for that destination")
            ok = abs(hit.distance_m - p.distance_m) <= max(10.0, 0.01 * p.distance_m)
            return Answer(verdict=Verdict.yes if ok else Verdict.no, citations=cites, value={
                "destination": hit.text, "distance_m": hit.distance_m, "distance": distance_text(hit.distance_m),
                "stated": distance_text(p.distance_m)})
        if hit.direction == "none":
            return Answer(verdict=Verdict.unknown, value={"destination": hit.text},
                          note="the board shows no arrow for that destination")
        ok = _same_direction(hit.direction, p.direction)
        return Answer(verdict=Verdict.yes if ok else Verdict.no, citations=cites,
                      value={"destination": hit.text, "direction": hit.direction, "stated": p.direction})

    def _ahead(self, scene: SceneGraph, p: GuideClaim) -> Answer:
        """Does `feature` lie ahead? Yes from a sign for it (its catalog row cites its article) or
        a board line naming it. No when no sign or board shows it and nothing unread could
        (closed world over the readable signs, as elsewhere). Codes and words: AHEAD_FEATURES."""
        codes, words = AHEAD_FEATURES[p.feature]
        hits = [s for s in scene.signs if self.catalog.has(s.code)
                and any(self.catalog.code_selects(c, s.code) for c in codes)]
        if hits:
            return Answer(verdict=Verdict.yes, value={"signs": [s.id for s in hits]},
                          citations=list({self.catalog.get(s.code).source.article_id: self.catalog.get(s.code).source
                                          for s in hits}.values()))
        texts = [fold_text(e.text) for b in scene.guide_boards for e in b.entries] + \
                [fold_text(t) for b in scene.guide_boards for t in b.other]
        if any(f" {w} " in f" {t} " for t in texts for w in words):     # whole words only
            return Answer(verdict=Verdict.yes, value={"board_line": True}, citations=[_ART(46)])
        rows = [self.catalog.get(c) for c in codes if self.catalog.has(c)]
        looks = {self.category_of(r.visual.shape, r.visual.border, r.visual.background) for r in rows} | {"board"}
        maybe = [sid for sid in self.unreadable_signs(scene)
                 if self.visual_category(scene.sign(sid)) in (looks | {"unknown", "red_board"})]
        if maybe:
            return Answer(verdict=Verdict.unknown, uncertain_signs=maybe,
                          note="a sign that could not be read might show it")
        return Answer(verdict=Verdict.no, value={"signs": []},
                      citations=list({r.source.article_id: r.source for r in rows}.values())[:3])

    def _speed_limit_is(self, scene: SceneGraph, p: SpeedLimitIs) -> Answer:
        """Phase 4.6 I4: the binding limit equals the stated value (QCVN 41 B.27, D.6)."""
        a = self._speed_limit(scene, SpeedLimit(vehicle=p.vehicle, lane=p.lane, kind=p.kind))
        lim = a.value.get("limit") if isinstance(a.value, dict) else None
        if a.verdict is not Verdict.value or lim is None:
            return a.model_copy(update={"verdict": Verdict.unknown,
                                        "note": a.note or "the limit depends on a condition not in the photo"})
        verdict = Verdict.yes if abs(lim - p.value_kmh) < 0.5 else Verdict.no
        return a.model_copy(update={"verdict": verdict, "value": {**a.value, "stated": p.value_kmh}})

    def _speed_range(self, scene: SceneGraph, p: SpeedLimit) -> Answer:
        """Phase 4.6 I4: the maximum and the minimum together ("trong khoảng tốc độ nào").
        Decided when the maximum is known; the minimum is reported when a sign or rule sets one,
        and as none when no minimum applies (no R.306, no expressway default, nothing unread)."""
        hi = self._speed_limit(scene, p.model_copy(update={"kind": "max"}))
        lo = self._speed_limit(scene, p.model_copy(update={"kind": "min"}))
        max_v = hi.value.get("limit") if isinstance(hi.value, dict) else None
        min_v = lo.value.get("limit") if isinstance(lo.value, dict) and lo.verdict is Verdict.value else None
        value = {"kind": "range", "max": max_v, "min": min_v, "lane": p.lane}
        if hi.verdict is not Verdict.value or max_v is None:
            return Answer(verdict=Verdict.unknown, value=value, note="the maximum is not known")
        if min_v is None and (lo.verdict is Verdict.value or self.unreadable_signs(scene)):
            return Answer(verdict=Verdict.unknown, value=value, note="the minimum is not known")
        return Answer(verdict=Verdict.value, value=value, reasons=hi.reasons + lo.reasons,
                      citations=hi.citations + lo.citations, basis=sorted(set(hi.basis) | set(lo.basis)))

    def _multi(self, scene: SceneGraph, p: Multi) -> Answer:
        """Phase 4.6 I1: each part on its own; decided when every part is."""
        parts = [self._run(scene, normalize(x)) for x in p.parts]
        done = all(a.verdict in (Verdict.yes, Verdict.no, Verdict.value) for a in parts)
        value = {"parts": [{"intent": x.intent, "verdict": a.verdict.value, "value": a.value}
                           for x, a in zip(p.parts, parts)]}
        return Answer(verdict=Verdict.value if done else Verdict.unknown, value=value,
                      reasons=[r for a in parts for r in a.reasons],
                      citations=[c for a in parts for c in a.citations],
                      uncertain_signs=sorted({s for a in parts for s in a.uncertain_signs}),
                      basis=sorted({b for a in parts for b in a.basis}),
                      note=None if done else "; ".join(a.note for a in parts if a.note) or "a part is not decided")

    def _explain(self, scene: SceneGraph, p: Explain) -> Answer:
        """Phase 4.6 I3: the inner answer, with the reasons that decide it."""
        inner = self._run(scene, normalize(p.program))
        if inner.verdict not in (Verdict.yes, Verdict.no, Verdict.value):
            return inner
        because = []
        for r in inner.reasons:
            if r.sign_id is None:
                continue
            s = scene.sign(r.sign_id) if any(x.id == r.sign_id for x in scene.signs) else None
            row = self.catalog.get(s.code) if s is not None and self.catalog.has(s.code) else None
            item = {"sign_id": r.sign_id, "truth": r.truth, "detail": r.detail,
                    "code": row.code if row else None, "name_vi": row.name_vi if row else None}
            if item not in because:
                because.append(item)
        return inner.model_copy(update={"verdict": Verdict.value, "value": {
            "answer": inner.verdict.value, "inner": inner.value, "because": because}})

    def _violations(self, scene: SceneGraph, p: ExistsViolation) -> Answer:
        self.load_scene(scene)
        out = self.call(Term("q_violations", _ctx(p.when, scene)))
        reasons, found = [], []
        for it in out["items"]:
            proof = explain.to_node(it["proof"]) if it.get("proof") else None
            reasons.append(Reason(sign_id=it["sign_id"], truth=it["truth"],
                                  detail=f"{it['vehicle_id']}:{it['kind']}", proof=proof))
            found.append(it["truth"])
        clears = []
        for c in out["clears"]:
            r = _reason(c)
            if c.get("vehicle_id"):
                r.detail = f"{c['vehicle_id']}:{c['kind']}:{c['why']}"
            clears.append(r)
        verdict = (Verdict.yes if "true" in found
                   else Verdict.unknown if "unknown" in found else Verdict.no)
        if verdict is Verdict.no and not scene.vehicles:
            # Phase 4.8 (dev2 train_502): with no vehicle read, "no violation" rests on a missing
            # fact, so it is unknown (three-valued logic), not no.
            return Answer(verdict=Verdict.unknown, reasons=reasons + clears,
                          note="no vehicle was read in the photo", value={"violations": []})
        want = {"yes": "true", "unknown": "unknown"}.get(verdict.value)
        support = [r for r in reasons if r.truth == want] if want else clears
        return Answer(verdict=verdict, reasons=reasons + clears, citations=_cites(support),
                      value={"violations": [r.detail for r in reasons if r.truth == "true"]})

    def _required(self, scene: SceneGraph, p: Required) -> Answer:
        self.load_scene(scene)
        vehicle = vehicle_term(p.vehicle) if p.vehicle else Term("veh", atom("vehicle"), [])
        out = self.call(Term("q_required", atom(p.action.value), vehicle,
                             atom(p.placement) if p.placement else None, _ctx(None, scene)))
        reasons = [_reason(r) for r in out["reasons"]] + [_reason(c) for c in out["clears"]]
        v = out["verdict"]
        if v == "yes":
            support = [_reason(r) for r in out["reasons"] if r["truth"] == "true"]
        elif v == "unknown":
            support = [_reason(r) for r in out["reasons"] if r["truth"] == "unknown"]
        else:
            support = [_reason(c) for c in out["clears"]]
        return Answer(verdict=Verdict(v), value={"signs": out["details"]}, reasons=reasons,
                      citations=_cites(support))

    # ------------------------------------------------------------------ vehicle classes
    def _hierarchy(self) -> dict[str, str]:
        if not hasattr(self, "_parents"):
            r = janus.query_once("findall(_C-_P, is_a(_C, _P), L)")
            self._parents = {c: p for c, p in r["L"]}
        return self._parents

    def report_classes(self, results: dict[str, tuple[str, dict[str, Any]]],
                       want: str) -> tuple[list[str], list[str]]:
        """Classes whose verdict is `want`, at the broadest level (a class is left out
        when its parent has the same verdict), and the conditional ones (unknown, with
        no child that has a definite verdict, so the condition is about this class)."""
        parents = self._hierarchy()
        children: dict[str, list[str]] = {}
        for c, p in parents.items():
            children.setdefault(p, []).append(c)

        def verdict(c: str) -> str:
            return results[c][0]

        hits = [c for c in results if verdict(c) == want
                and not (c in parents and verdict(parents[c]) == want)]
        conditional = [c for c in results if verdict(c) == "unknown"
                       and all(verdict(k) == "unknown" for k in children.get(c, []))
                       and not (c in parents and verdict(parents[c]) == "unknown"
                                and all(verdict(k) == "unknown" for k in children.get(parents[c], [])))]
        order = [c.value for c in ONTOLOGY_CLASSES]
        return sorted(hits, key=order.index), sorted(conditional, key=order.index)

    # ------------------------------------------------------------------ every vehicle
    def _thresholds(self, scene: SceneGraph) -> dict[str, list[float]]:
        """Every number the scene's rules compare a vehicle attribute with: sign values
        (catalog value_cond), plate / group / local-plate / lane-row conditions, and
        fixed catalog conditions (P.126: load > 3.5 t)."""
        out: dict[str, set[float]] = {}

        def add(attr: str, v: float) -> None:
            out.setdefault(attr, set()).add(float(v))

        def specs(vs) -> None:
            for vs_ in vs:
                for c in vs_.conditions:
                    add(c.attr.value, c.value)

        for sg in scene.signs:
            if self.catalog.has(sg.code):
                e = self.catalog.get(sg.code).effect
                if e.value and sg.value is not None:
                    add(e.value.attr.value, sg.value)
                for pr in e.prohibits:
                    specs(pr.vehicles)
            for pl in sg.plates:
                specs(pl.vehicles)
                for g in pl.rules:
                    specs(g.vehicles)
            for g in sg.rules:
                specs(g.vehicles)
            for row in sg.lanes:
                specs(row.vehicles)
        return {a: sorted(v) for a, v in out.items()}

    _INT_ATTRS = {"seats"}
    _ATTR_FIELD = {"seats": "seats", "load_t": "load_t", "gross_t": "gross_t",
                   "height_m": "height_m", "width_m": "width_m", "length_m": "length_m",
                   "axle_t": "axle_t"}                                        # parser v13

    def _witnesses(self, vehicle: Vehicle, thresholds: dict[str, list[float]]) -> list[dict]:
        """Attribute values on both sides of (and at) each threshold, for the attributes
        the question leaves unstated. One dict per combination (capped)."""
        axes = []
        for attr, ts in thresholds.items():
            field = self._ATTR_FIELD[attr]
            if getattr(vehicle, field) is not None or any(
                    getattr(vehicle, f, None) is not None for f in (f"{attr.split('_')[0]}_gt",
                                                                    f"{attr.split('_')[0]}_lt")):
                continue  # the question fixes this attribute
            step = 1 if attr in self._INT_ATTRS else 0.01
            vals = sorted({max(0.0, round(t + d, 2)) for t in ts for d in (-step, 0, step)})
            if attr in self._INT_ATTRS:
                vals = sorted({int(v) for v in vals})
            axes.append([(field, v) for v in vals])
        combos = [dict(c) for c in itertools.islice(itertools.product(*axes), 256)] if axes else []
        return combos

    @staticmethod
    def _region(witness: dict, thresholds: dict[str, list[float]]) -> str:
        """Describe the attribute region a witness falls in, e.g. 'seats > 29'."""
        parts = []
        for field, v in witness.items():
            ts = thresholds.get(field, [])
            lo = max((t for t in ts if t < v), default=None)
            hi = min((t for t in ts if t > v), default=None)
            if v in ts:
                parts.append(f"{field} = {v:g}")
            elif lo is not None and hi is not None:
                parts.append(f"{lo:g} < {field} < {hi:g}")
            elif lo is not None:
                parts.append(f"{field} > {lo:g}")
            elif hi is not None:
                parts.append(f"{field} < {hi:g}")
        return ", ".join(parts)

    def _for_every_vehicle(self, scene: SceneGraph, p: Program) -> Answer:
        """A claim about every_vehicle: it must hold for every member of every vehicle
        class (pedestrians are not vehicles), combined with AND.

        A class whose answer depends on unstated weight / seats has members on both
        sides, so its members are tried at the scene's thresholds: if some member
        fails, the class is a counterexample, reported with its condition (e.g.
        "seats > 29"). The answer is unknown only when it depends on something unknown
        in the scene (time, day, lane, an unreadable sign), not on attribute ranges."""
        if not isinstance(p, (Permitted, Forbidden, SpeedOk, Required)):
            raise EngineError("every_vehicle is for claims: permitted, forbidden, speed_ok, required")
        thresholds = self._thresholds(scene)

        def run(c: VehicleClass, attrs: dict | None = None) -> Answer:
            veh = p.vehicle.model_copy(update={"cls": c, **(attrs or {})})
            a = self._run(scene, normalize(p.model_copy(update={"vehicle": veh})))
            return a

        def short(a: Answer) -> str:
            return a.verdict.value if a.verdict.value in ("yes", "no") else "unknown"

        results: dict[str, tuple[str, Answer]] = {}
        conditions: dict[str, str] = {}
        for c in ONTOLOGY_CLASSES:
            if c is VehicleClass.pedestrian:
                continue
            a = run(c)
            v = short(a)
            if v == "unknown":
                tried = [(w, run(c, w)) for w in self._witnesses(p.vehicle, thresholds)]
                failing = [(w, b) for w, b in tried if short(b) == "no"]
                if failing:
                    w, a = failing[0]
                    v = "no"
                    conditions[c.value] = self._region(w, thresholds)
                elif tried and all(short(b) == "yes" for _, b in tried):
                    v, a = "yes", tried[0][1]
            results[c.value] = (v, a)
        verdicts = {v for v, _ in results.values()}
        verdict = "no" if "no" in verdicts else "unknown" if "unknown" in verdicts else "yes"
        counter, _ = self.report_classes(results, "no")
        _, unknown = self.report_classes(results, "unknown")  # the classes whose own answer is open
        if verdict == "unknown" and not unknown:
            unknown = [c for c, (v, _) in results.items() if v == "unknown"]
        decisive = {"no": counter, "unknown": unknown, "yes": list(results)}[verdict]
        support = [results[c][1] for c in decisive]
        seen, reasons = set(), []
        for a in support:
            for r in a.reasons:
                k = (r.sign_id, r.truth, r.detail)
                if k not in seen:
                    seen.add(k)
                    reasons.append(r)
        return Answer(verdict=Verdict(verdict),
                      value={"every_vehicle": verdict,
                             "counterexamples": [{"class": c, "condition": conditions.get(c)}
                                                 for c in counter],
                             "unknown": unknown,
                             "per_class": {c: v for c, (v, _) in results.items()}},
                      reasons=reasons, citations=[c for a in support for c in a.citations],
                      basis=sorted({b for a in support for b in a.basis}))

    def _which_vehicles(self, scene: SceneGraph, p: WhichVehicles) -> Answer:
        selection = None
        if p.sign is not None:
            selection = self.resolve_value(scene, p.sign)
            if not selection:
                return Answer(verdict=Verdict.unknown, note="no sign in the scene matches the selector")
        self.load_scene(scene, selection)
        ctx = _ctx(p.when, scene)
        results = {}
        for c in ONTOLOGY_CLASSES:
            out = self.call(Term("q_permitted", atom(p.action.value), Term("veh", atom(c.value), []), ctx))
            results[c.value] = (out["verdict"], out)
        want = "no" if p.status == "banned" else "yes"
        hits, conditional = self.report_classes(results, want)
        support = [r for c in hits + conditional for r in _supporting(results[c][1])]
        value = {p.status: hits, "conditional": conditional,
                 "per_class": {c: v for c, (v, _) in results.items()}}
        if self.stated_exceptions and p.status == "banned" and hits:
            value.update(self._stated_priority_exception(scene, support))
        return Answer(verdict=Verdict.value, value=value,
                      reasons=support, citations=_cites(support), basis=_basis(support))

    def _stated_priority_exception(self, scene: SceneGraph, support: list[Reason]) -> dict[str, Any]:
        """Phase 4.8c B3 (switch stated_exceptions): the bans' own articles say "trừ các xe được ưu
        tiên theo quy định" (kb/stated_exceptions_48.yaml, quoting QCVN 41): the answer names
        that exception. Only when every banning sign's article states it."""
        ids = {r.sign_id for r in support if r.sign_id and r.truth == "true"}
        arts = []
        for sid in sorted(ids):
            sg = scene.sign(sid)
            if not self.catalog.has(sg.code):
                return {}
            arts.append(self.catalog.get(sg.code).source.article_id)
        stated = stated_exceptions_from_kb()
        if not arts or not all(a in stated for a in arts):
            return {}
        return {"except_priority": True, "exception_articles": sorted(set(arts))}

    def _lane_class_results(self, scene: SceneGraph, lane: int, when, speed_kmh) -> dict[str, tuple]:
        """q_lane's answer for every ontology class on one lane: {class: (verdict, out)}."""
        self.load_scene(scene)
        ctx = _ctx(when, scene, lane)
        speed = atom("none") if speed_kmh is None else float(speed_kmh)
        results = {}
        for c in ONTOLOGY_CLASSES:
            out = self.call(Term("q_lane", Term("veh", atom(c.value), []), lane, speed, ctx))
            results[c.value] = (out["verdict"], out)
        return results

    def _lane_vehicles(self, scene: SceneGraph, p: LaneVehicles) -> Answer:
        n = scene_lane_count(scene)
        if n and p.lane > n:
            return Answer(verdict=Verdict.unknown, note=f"the scene shows {n} lanes")
        results = self._lane_class_results(scene, p.lane, p.when, p.speed_kmh)
        hits, conditional = self.report_classes(results, "yes" if p.status == "allowed" else "no")
        support = [r for c in hits + conditional for r in _supporting(results[c][1])]
        return Answer(verdict=Verdict.value,
                      value={p.status: hits, "conditional": conditional, "lane": p.lane},
                      reasons=support, citations=_cites(support), basis=_basis(support))

    def _speed_limit(self, scene: SceneGraph, p: SpeedLimit) -> Answer:
        if p.kind == "range" and not p.vehicles:
            return self._speed_range(scene, p)
        if p.vehicles:
            # phase 4.5: several vehicles at once; decided when every vehicle's limit is
            per = [(v, self._speed_limit(scene, p.model_copy(update={"vehicle": v, "vehicles": []}))) for v in p.vehicles]
            value = {"kind": p.kind, "per_vehicle": [{"vehicle": v.cls.value, "limit": a.value.get("limit") if isinstance(a.value, dict) else None,
                                                      "conditional": (a.value or {}).get("conditional", []) if isinstance(a.value, dict) else [],
                                                      "verdict": a.verdict.value} for v, a in per]}
            decided = all(a.verdict is Verdict.value for _, a in per)
            return Answer(verdict=Verdict.value if decided else Verdict.unknown, value=value,
                          reasons=[r for _, a in per for r in a.reasons],
                          citations=[c for _, a in per for c in a.citations],
                          note=None if decided else "the limit is not known for every vehicle")
        scene = self._with_divider(scene, p.road_divided)
        self.load_scene(scene)
        veh = vehicle_term(p.vehicle)

        def limit(lane: int | None) -> tuple[dict[str, Any], list[Reason]]:
            out = self.call(Term("q_speed_limit", veh, atom(p.kind), _ctx(p.when, scene, lane)))
            return out, [_reason(r) for r in out["reasons"]]

        def first(xs: list) -> Any:
            return xs[0] if xs else None

        out, reasons = limit(p.lane)
        value: dict[str, Any] = {"kind": p.kind, "lane": p.lane, "limit": first(out["limit"]),
                                 "sign_id": first(out["sign_id"]), "conditional": out["conditional"]}
        has_board = any(self.catalog.has(s.code) and self.catalog.get(s.code).effect.lane_board
                        for s in scene.signs)
        if p.lane is None and has_board and (n := scene_lane_count(scene)):
            value["per_lane"] = []
            for lane in range(1, n + 1):
                o, r = limit(lane)
                value["per_lane"].append({"lane": lane, "limit": first(o["limit"]),
                                          "conditional": o["conditional"]})
                reasons += r
        found = value["limit"] is not None or any(x["limit"] is not None
                                                 for x in value.get("per_lane", []))
        if not found and not out["conditional"]:
            return Answer(verdict=Verdict.unknown, value=value,
                          note="no speed sign applies; limits by road type are not modelled")
        return Answer(verdict=Verdict.value, value=value, reasons=reasons,
                      citations=_cites(reasons), basis=_basis(reasons))

    def _is_sign(self, scene: SceneGraph, p: IsSign) -> Answer:
        ids = self.resolve(scene, p.sign)
        if not ids:
            return Answer(verdict=Verdict.unknown, note="no sign in the scene matches the selector")
        unread_only: list[str] = []
        several = False
        if p.sign.only:
            chosen, unread_only = self.single_sign(scene, ids)
            if chosen is None:
                # Phase 4.6 F1 (owner, 2026-11-17), following the single-sign rule: unreadable
                # signs are dropped; yes if every readable sign is the named one, no if none is,
                # unknown if mixed or if no readable sign is left.
                chosen = [i for i in ids if self.catalog.has(scene.sign(i).code)]
                if not chosen:
                    return Answer(verdict=Verdict.unknown, value={"candidates": ids},
                                  uncertain_signs=unread_only,
                                  note="no readable sign is left to check")
                several = len(chosen) > 1
            ids = chosen
        unread = [i for i in ids if not self.catalog.has(scene.sign(i).code)]
        if unread:
            return Answer(verdict=Verdict.unknown, uncertain_signs=unread,
                          note="the sign could not be identified, so the claim cannot be checked")
        try:
            if p.code:
                target = Term("codes", [atom(self.catalog.get(c).atom)
                                        for c in self.catalog.codes_matching(p.code)])
            elif p.meaning:
                self.catalog.codes_for_meaning(p.meaning)  # rejects unknown meanings
                target = Term("meaning", atom(p.meaning))
            else:
                target = Term("category", atom(p.category))
        except KeyError as e:
            raise EngineError(str(e)) from None
        self.load_scene(scene, ids)
        out = self.call(Term("q_is_sign", target))
        reasons = [_reason(r) for r in out["reasons"]]
        actual = [{"sign_id": i, "code": self.catalog.get(scene.sign(i).code).code,
                   "name_vi": self.catalog.get(scene.sign(i).code).name_vi} for i in ids]
        verdict = Verdict(out["verdict"])
        if not p.sign.only and len(ids) > 1 and verdict is Verdict.no:
            # fix 2026-11-20: "biển ở phía bên phải là ..." names one sign; when the selector's
            # attributes leave several, the claim holds if one of them is the named sign
            truths = {r.truth for r in reasons}
            if "true" in truths:
                verdict = Verdict.yes
        if several:
            truths = {r.truth for r in reasons}
            verdict = (Verdict.yes if truths == {"true"} else Verdict.no if truths == {"false"}
                       else Verdict.unknown)
        return Answer(verdict=verdict, value={"signs": actual}, reasons=reasons, citations=_cites(reasons),
                      uncertain_signs=unread_only,
                      note="the selected signs differ: some are the named sign and some are not"
                      if verdict is Verdict.unknown and several else None)

    def _connective(self, scene: SceneGraph, p: AllOf | AnyOf) -> Answer:
        """Three-valued AND / OR over claims. Citations come from the parts that decide."""
        if self.several_signs and isinstance(p, AnyOf) and (per := self._any_is_sign_per_sign(scene, p)):
            return per
        parts = [self._run(scene, normalize(c)) for c in p.claims]
        vs = [a.verdict if a.verdict in (Verdict.yes, Verdict.no) else Verdict.unknown
              for a in parts]
        decide, other = ((Verdict.no, Verdict.yes) if isinstance(p, AllOf)
                         else (Verdict.yes, Verdict.no))
        if decide in vs:
            verdict, support = decide, [a for a, v in zip(parts, vs) if v == decide]
        elif Verdict.unknown in vs:
            verdict, support = Verdict.unknown, [a for a, v in zip(parts, vs) if v == Verdict.unknown]
        else:
            verdict, support = other, parts
        return Answer(verdict=verdict, value={"parts": [v.value for v in vs]},
                      reasons=[r for a in parts for r in a.reasons],
                      citations=[c for a in support for c in a.citations],
                      basis=sorted({b for a in parts for b in a.basis}))

    def _any_is_sign_per_sign(self, scene: SceneGraph, p: AnyOf) -> Answer | None:
        """Phase 4.8 G1: "Đây có phải là một trong các biển X, Y, Z không?" over several signs.
        When every claim is `is_sign` on the same `only` selector and it selects several readable
        signs, each sign is checked against the claims (OR): yes if every readable sign meets one,
        no if none does, unknown otherwise or if a selected sign is unreadable. None: not this form."""
        claims = p.claims
        if not claims or not all(isinstance(c, IsSign) and c.sign.only for c in claims):
            return None
        if any(c.sign != claims[0].sign for c in claims[1:]):
            return None
        ids = self.resolve(scene, claims[0].sign)
        readable = [i for i in ids if self.catalog.has(scene.sign(i).code)]
        if len(readable) < 2 or len({self.catalog.get(scene.sign(i).code).code for i in readable}) < 2:
            return None
        unread = [i for i in ids if i not in readable]
        one = claims[0].sign.model_copy(update={"only": False})
        per, reasons, cites = [], [], []
        for sid in readable:
            sub = scene.model_copy(update={"signs": [scene.sign(sid)]})
            parts = [self._is_sign(sub, c.model_copy(update={"sign": one})) for c in claims]
            vs = {a.verdict for a in parts}
            v = Verdict.yes if Verdict.yes in vs else Verdict.no if vs == {Verdict.no} else Verdict.unknown
            per.append({"sign_id": sid, "code": self.catalog.get(scene.sign(sid).code).code, "verdict": v.value})
            reasons += [r for a in parts for r in a.reasons]
            cites += [c for a in parts if a.verdict is v for c in a.citations]
        vs = {x["verdict"] for x in per}
        verdict = (Verdict.unknown if unread else Verdict.yes if vs == {"yes"}
                   else Verdict.no if vs == {"no"} else Verdict.unknown)
        return Answer(verdict=verdict, value={"per_sign": per}, reasons=reasons,
                      citations=list({(c.law_id, c.article_id): c for c in cites}.values()),
                      uncertain_signs=unread,
                      note="each sign checked against the claims" if verdict is not Verdict.unknown
                      else "the selected signs differ, or one could not be read")

    def _choose(self, scene: SceneGraph, p: Choose) -> Answer:
        options, reasons, cites = [], [], []
        for o in p.options:
            a = self._verify(scene, Verify(claim=o.claim, expect=o.expect))
            options.append({"label": o.label, "verdict": a.verdict.value})
            reasons += a.reasons
            cites += a.citations
        value = {
            "holding": [o["label"] for o in options if o["verdict"] == "yes"],
            "not_holding": [o["label"] for o in options if o["verdict"] == "no"],
            "unknown": [o["label"] for o in options if o["verdict"] not in ("yes", "no")],
            "options": options,
        }
        if value["unknown"]:
            # KB-7 (phase 4.5, owner 2026-11-17): an answer that picks among options is
            # only decided when every option is; three-valued logic, not a law text.
            return Answer(verdict=Verdict.unknown, value=value, reasons=reasons, citations=cites,
                          basis=_basis(reasons), note="some options could not be decided")
        return Answer(verdict=Verdict.value, value=value, reasons=reasons, citations=cites,
                      basis=_basis(reasons))

    def _verify(self, scene: SceneGraph, p: Verify) -> Answer:
        inner = self._run(scene, p.claim)
        value = {"claim": inner.verdict.value}
        if isinstance(inner.value, dict) and "decided_at" in inner.value:
            value.update(inner.value)
        if inner.verdict not in (Verdict.yes, Verdict.no):
            return inner.model_copy(update={"value": value})
        holds = inner.verdict == Verdict.yes
        verdict = Verdict.yes if holds == p.expect else Verdict.no
        return inner.model_copy(update={"verdict": verdict, "value": value})


# ---------------------------------------------------------------------- helpers

# QCVN 41:2024 art. 11: the five sign groups, by code prefix (DP "hết cấm" rows are in the
# prohibitory appendix B; R end rows such as R.307, R.404 are mandatory, appendix D).
_GROUPS_VI = [("DP.", "biển báo cấm"), ("IE.", "biển chỉ dẫn"), ("P.", "biển báo cấm"), ("R.", "biển hiệu lệnh"),
              ("W.", "biển báo nguy hiểm và cảnh báo"), ("I.", "biển chỉ dẫn"), ("S.", "biển phụ, biển viết bằng chữ")]


def sign_group_vi(code: str) -> str | None:
    """The art. 11 group name of a catalog code (phase 4.5 rank 1)."""
    return next((name for pre, name in _GROUPS_VI if code.startswith(pre)), None)


def resolve_lanes(p, n: int | None):
    """Phase 4.5 lane fix: a lane counted from the right (-1 = rightmost) becomes its number
    from the left, n - k + 1, given the scene's lane count n. Returns (program, negative lanes
    seen); the program is None when one can't be numbered (no count, or more than n)."""
    from pydantic import BaseModel

    seen: list[int] = []

    def walk(x):
        if isinstance(x, list):
            out = [walk(y) for y in x]
            return None if any(o is None for o, y in zip(out, x) if y is not None) else out
        if not isinstance(x, BaseModel):
            return x
        upd = {}
        for name in type(x).model_fields:
            v = getattr(x, name)
            if name == "lane" and isinstance(v, int) and v < 0:
                seen.append(v)
                if n is None or -v > n:
                    return None
                upd[name] = n + v + 1
            elif name == "lanes" and isinstance(v, list) and all(isinstance(i, int) for i in v):
                # parser v17 lanes_only: a set of lanes, each counted from the left or the right
                if any(i < 0 for i in v):
                    neg = [i for i in v if i < 0]
                    seen.extend(neg)
                    if n is None or any(-i > n for i in neg):
                        return None
                    upd[name] = [n + i + 1 if i < 0 else i for i in v]
            elif isinstance(v, (BaseModel, list)):
                w = walk(v)
                if w is None:
                    return None
                if w is not v:
                    upd[name] = w
        return x.model_copy(update=upd) if upd else x

    out = walk(p)
    return out, seen


def _ART(n: int | str) -> Citation:
    return Citation(law_id="QCVN 41:2024/BGTVT", article_id=str(n))


def fold_text(t: str | None) -> str:
    """Board text folded for matching: no diacritics, lower case, words split by single spaces."""
    from vqa.reasoning.sign_info import fold
    return fold(t or "").lower()


def si_entry(text: str):
    from vqa.schemas import GuideEntry
    return GuideEntry(text=text)


# Phase 4.6 I2: what "lies ahead" questions name, by sign codes (their catalog rows cite the
# article) and board words (folded, no diacritics). QCVN 41 C.38 W.238 "Đường cao tốc phía
# trước", C.40 W.240 "Đường hầm", C.5 W.205 "Đường giao nhau", C.6 W.206 / D.3 R.303 (vòng
# xuyến), art. 47 IE.454 / IE.455 / IE.464b / IE.474 (lối ra).
AHEAD_FEATURES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "tunnel": (("W.240",), ("ham",)),
    "expressway": (("W.238", "IE.450a", "IE.450b", "IE.451a", "IE.451b", "IE.452"), ("cao toc",)),
    "junction": (("W.205", "W.207", "W.208", "W.234"), ("nga ba", "nga tu", "nut giao")),
    "roundabout": (("W.206", "R.303"), ("vong xuyen",)),
    "exit": (("IE.454", "IE.455", "IE.464b", "IE.474"), ("loi ra", "exit")),
}

_DIRECTION_GROUP = {"straight": {"straight"}, "left": {"left", "slight_left"},
                    "right": {"right", "slight_right"}, "u_turn": {"u_turn"}}


def _same_direction(board: str, stated: str | None) -> bool:
    return stated is not None and board in _DIRECTION_GROUP.get(stated, {stated})


# Phase 4.6 I1: the QCVN 41 article that lists each sign group (from the law text): art. 22.1 P / DP,
# 28.1 W, 32.1 R, 36.1 I, 47 IE, 41 S (auxiliary plates). Returns (text, article id).
_GROUP_ARTICLES = [("DP.", ("22.1", "22")), ("IE.", ("47", "47")), ("P.", ("22.1", "22")),
                   ("W.", ("28.1", "28")), ("R.", ("32.1", "32")), ("I.", ("36.1", "36")), ("S.", ("41", "41"))]


def group_article(code: str) -> tuple[str, str] | None:
    return next((a for p, a in _GROUP_ARTICLES if code.startswith(p)), None)


def distance_text(m: float | None) -> str | None:
    """A board distance as it would be printed: 5000 -> "5 km", 5800 -> "5.8 km", 150 -> "150 m"."""
    if m is None:
        return None
    if m >= 1000:
        return f"{m / 1000:g} km"
    return f"{m:g} m"


def scene_lane_count(scene: SceneGraph) -> int | None:
    if scene.road.lanes:
        return scene.road.lanes
    lanes = [row.lane for s in scene.signs for row in s.lanes]
    lanes += [s.position.lane for s in scene.signs if s.position.lane]
    return max(lanes) if lanes else None


def _reason(r: dict[str, Any]) -> Reason:
    """A reason against the claim (truth true/unknown) or a clearing one (truth false, why)."""
    proof = r.get("proof")
    return Reason(sign_id=r.get("sign_id") or None, truth=r["truth"], detail=r.get("why"),
                  proof=explain.to_node(proof) if isinstance(proof, dict) else None)


def _supporting(out: dict[str, Any]) -> list[Reason]:
    """The reasons that back the verdict: clears for yes, true reasons for no,
    unknown reasons for unknown."""
    v = out["verdict"]
    if v == "yes":
        return [_reason(c) for c in out["clears"]]
    want = "true" if v == "no" else "unknown"
    return [_reason(r) for r in out["reasons"] if r["truth"] == want]


def _cites(reasons: list[Reason]):
    return [c for r in reasons for c in explain.citations(r.proof)]


def _basis(reasons: list[Reason]) -> list[str]:
    """Flags for what the answer rests on beyond QCVN 41 / Law 36."""
    flags = set()
    for r in reasons:
        if r.proof and any(n.type == "fact" and n.goal and n.goal.startswith("local_plate(")
                           for n in explain.walk(r.proof)):
            flags.add("non_standard_plate")
    return sorted(flags)


def _verdict_answer(out: dict[str, Any]) -> Answer:
    reasons = [_reason(r) for r in out["reasons"]] + [_reason(c) for c in out["clears"]]
    support = _supporting(out)
    return Answer(verdict=Verdict(out["verdict"]), reasons=reasons,
                  citations=_cites(support), basis=_basis(support))


def _same(a: Answer, b: Answer) -> bool:
    return a.verdict == b.verdict and a.value == b.value
