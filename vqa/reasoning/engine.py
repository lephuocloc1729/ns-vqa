"""Python side of the rule engine: loads kb/ into SWI-Prolog through janus,
asserts a scene, runs a QueryProgram and returns an Answer with proofs.

The engine decides every legal conclusion in Prolog. Python only resolves
sign selectors, loops over lanes and over alternative sign readings, and
packs the results into an Answer.
"""

from __future__ import annotations

import datetime as dt
import itertools
from typing import Any

from vqa.kb import KB_DIR, Catalog, load_catalog
from vqa.reasoning import explain
from vqa.reasoning.facts import board_read, reading_variants, scene_facts
from vqa.reasoning.terms import Term, atom, to_prolog, vehicle_term
from vqa.parsing.dsl import normalize
from vqa.schemas import (
    AllOf, Answer, AnyOf, BanTimes, Choose, Citation, ExistsViolation, Guide, IsSign, LanesFor, LanesWhere,
    LaneVehicles, Meaning, Permitted, Present, SpeedLimit,
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


def _days(when: When | None) -> tuple[int | None, int | None]:
    """Day of month for the interval's start and for after midnight."""
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
    elif scene.context.datetime is not None:
        t: dt.datetime = scene.context.datetime
        minute, day = t.hour * 60 + t.minute, t.day
    return Term("ctx", minute, day, lane)


def _fmt_min(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


class Engine:
    def __init__(self, catalog: Catalog | None = None) -> None:
        self.catalog = catalog or load_catalog()
        _load_kb(self.catalog)

    # ------------------------------------------------------------------ low level
    def load_scene(self, scene: SceneGraph, selection: list[str] | None = None) -> None:
        janus.query_once("clear_scene")
        _assert(scene_facts(scene, self.catalog, selection))

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
        return [s.id for s in out]

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
        if isinstance(query, QueryProgram) and query.out_of_scope:
            return Answer(verdict=Verdict.unknown, note="out of scope for the rules: "
                          + (query.out_of_scope_reason or "no DSL intent fits"))
        program = normalize(query.program if isinstance(query, QueryProgram) else query)
        program, from_right = resolve_lanes(program, scene_lane_count(scene))
        if program is None:
            return Answer(verdict=Verdict.unknown, note="the question counts lanes from the right "
                          f"({', '.join(map(str, from_right))}), and the scene does not say how many lanes there are")
        variants = reading_variants(scene)
        answers = [(picked, self._run(sc, program)) for sc, picked in variants]
        first = answers[0][1]
        if len(answers) == 1:
            return first
        if all(_same(first, a) for _, a in answers[1:]):
            return first
        uncertain = sorted({sid for picked, _ in answers for sid in picked})
        return Answer(
            verdict=Verdict.uncertain,
            value={"readings": [{"signs": p, "verdict": a.verdict.value, "value": a.value}
                                for p, a in answers]},
            reasons=first.reasons,
            citations=[c for _, a in answers for c in a.citations],
            uncertain_signs=uncertain,
            note="alternative readings of these signs lead to different answers",
        )

    # ------------------------------------------------------------------ per program
    # Claims whose verdict rests on "no visible sign says otherwise" (closed world):
    # the verdict that an unreadable sign could overturn.
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

    def _run(self, scene: SceneGraph, p: Program) -> Answer:
        """Dispatch, then: a closed-world verdict becomes unknown when the scene has an
        unreadable sign whose visible category could bear on the claim, since that
        sign might say otherwise. Others (e.g. a blue information board for a turn
        question) are ignored."""
        ans = self._dispatch(scene, p)
        cw = self._CLOSED_WORLD.get(type(p))
        unread = [sid for sid in self.unreadable_signs(scene)
                  if self.could_matter(self.visual_category(scene.sign(sid)), p)]
        unmodelled = [sid for sid in self.unmodelled_signs(scene)
                      if self.could_matter(self.visual_category(scene.sign(sid)), p)
                      or self._lane_directions_matter(scene.sign(sid), p)]
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
        if isinstance(p, Guide):
            return self._guide(scene, p)
        if isinstance(p, ExistsViolation):
            return self._violations(scene, p)
        if isinstance(p, Required):
            return self._required(scene, p)
        raise EngineError(f"unsupported program {type(p).__name__}")

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
        ids = self.resolve(scene, p.sign)
        unread_only: list[str] = []
        if p.sign.only:
            chosen, unread_only = self.single_sign(scene, ids)
            if chosen is None:
                return Answer(verdict=Verdict.unknown, value={"candidates": ids},
                              uncertain_signs=unread_only,
                              note="expected exactly one sign in the scene")
            ids = chosen[:1]               # same code: one meaning
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
        return Answer(verdict=verdict, value=out, citations=cites, uncertain_signs=unread)

    # ------------------------------------------------------------------ phase 4.5 B1 + B6
    def _meaning_aspect(self, scene: SceneGraph, p: Meaning) -> Answer:
        """group (art. 11), conduct (the catalog's effects and conduct items), scope and
        placement (kb/sign_info.yaml) of the selected signs. With `only` and several signs, all
        readable candidates are used; the unreadable ones are listed as uncertain."""
        from vqa.reasoning import sign_info as si

        ids = self.resolve(scene, p.sign)
        readable = [i for i in ids if self.catalog.has(scene.sign(i).code)]
        unread = [i for i in ids if i not in readable]
        if not readable:
            return Answer(verdict=Verdict.unknown, uncertain_signs=unread,
                          note="no readable sign in the scene matches the selector")
        entries = [(i, self.catalog.get(scene.sign(i).code)) for i in readable]
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
        out, cites = [], []
        for i, e in entries:
            if p.aspect == "conduct":
                items, c = si.conduct_items(e, self.catalog)
                if items:
                    out.append({"sign_id": i, "code": e.code, "name_vi": e.name_vi, "conduct": items})
                    cites += c
            else:
                hit = si.lookup(p.aspect, e.code, e.category)
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
        if not out:
            return Answer(verdict=Verdict.unknown, uncertain_signs=unread,
                          note=f"no {p.aspect} rule for the selected signs")
        cites = list({(c.law_id, c.article_id): c for c in cites}.values())
        return Answer(verdict=Verdict.value, value={p.aspect: out}, citations=cites, uncertain_signs=unread)

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
        maybe = [s.id for s in scene.signs if s.id in unread
                 and (self.visual_category(s) == "unknown" or self.visual_category(s) in looks)]
        if maybe:
            return Answer(verdict=Verdict.unknown, uncertain_signs=maybe,
                          note="a sign that could not be read might be it")
        return Answer(verdict=Verdict.no, value={"signs": []},
                      citations=list({r.source.article_id: r.source for r in rows}.values())[:3])

    def _guide(self, scene: SceneGraph, p: Guide) -> Answer:
        """What a guide board says (B6). Read from the board data; no legal conclusion."""
        from vqa.reasoning import sign_info as si

        boards = scene.guide_boards
        if not boards:
            return Answer(verdict=Verdict.unknown, note="no guide board was read in the photo")
        cites = [self.catalog.get(s.code).source for s in scene.signs
                 if self.catalog.has(s.code) and self.catalog.get(s.code).effect.informational][:2] or [si.ART11]
        entries = [e for b in boards for e in b.entries]
        if p.ask == "destinations":
            if not entries:
                return Answer(verdict=Verdict.unknown, note="the boards list no destinations")
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
        return Answer(verdict=Verdict.value, citations=cites, value={
            "destination": hit.text, "direction": hit.direction, "distance_m": hit.distance_m,
            "distance": distance_text(hit.distance_m)})

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
                   "height_m": "height_m", "width_m": "width_m", "length_m": "length_m"}

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
            selection = self.resolve(scene, p.sign)
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
        return Answer(verdict=Verdict.value,
                      value={p.status: hits, "conditional": conditional,
                             "per_class": {c: v for c, (v, _) in results.items()}},
                      reasons=support, citations=_cites(support), basis=_basis(support))

    def _lane_vehicles(self, scene: SceneGraph, p: LaneVehicles) -> Answer:
        n = scene_lane_count(scene)
        if n and p.lane > n:
            return Answer(verdict=Verdict.unknown, note=f"the scene shows {n} lanes")
        self.load_scene(scene)
        ctx = _ctx(p.when, scene, p.lane)
        speed = atom("none") if p.speed_kmh is None else float(p.speed_kmh)
        results = {}
        for c in ONTOLOGY_CLASSES:
            out = self.call(Term("q_lane", Term("veh", atom(c.value), []), p.lane, speed, ctx))
            results[c.value] = (out["verdict"], out)
        hits, conditional = self.report_classes(results, "yes" if p.status == "allowed" else "no")
        support = [r for c in hits + conditional for r in _supporting(results[c][1])]
        return Answer(verdict=Verdict.value,
                      value={p.status: hits, "conditional": conditional, "lane": p.lane},
                      reasons=support, citations=_cites(support), basis=_basis(support))

    def _speed_limit(self, scene: SceneGraph, p: SpeedLimit) -> Answer:
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
        if p.sign.only:
            chosen, unread_only = self.single_sign(scene, ids)
            if chosen is None:
                return Answer(verdict=Verdict.unknown, value={"candidates": ids},
                              uncertain_signs=unread_only,
                              note="expected exactly one sign in the scene")
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
        return Answer(verdict=Verdict(out["verdict"]), value={"signs": actual},
                      reasons=reasons, citations=_cites(reasons), uncertain_signs=unread_only)

    def _connective(self, scene: SceneGraph, p: AllOf | AnyOf) -> Answer:
        """Three-valued AND / OR over claims. Citations come from the parts that decide."""
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
            elif isinstance(v, (BaseModel, list)):
                w = walk(v)
                if w is None:
                    return None
                if w is not v:
                    upd[name] = w
        return x.model_copy(update=upd) if upd else x

    out = walk(p)
    return out, seen


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
