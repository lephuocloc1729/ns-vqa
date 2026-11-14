"""Python side of the rule engine: loads kb/ into SWI-Prolog through janus,
asserts a scene, runs a QueryProgram and returns an Answer with proofs.

The engine decides every legal conclusion in Prolog. Python only resolves
sign selectors, loops over lanes and over alternative sign readings, and
packs the results into an Answer.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from vqa.kb import KB_DIR, Catalog, load_catalog
from vqa.reasoning import explain
from vqa.reasoning.facts import reading_variants, scene_facts
from vqa.reasoning.terms import Term, atom, to_prolog, vehicle_term
from vqa.parsing.dsl import normalize
from vqa.schemas import (
    Answer, BanTimes, Choose, ExistsViolation, LanesFor, LanesWhere, Meaning, Permitted,
    Program, QueryProgram, Reason, Required, SceneGraph, Selector, SpeedOk, Verdict,
    Verify, When,
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


def _ctx(when: When | None, scene: SceneGraph) -> Term:
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
    return Term("ctx", minute, day)


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
            if sel.code and s.code != sel.code:
                continue
            if codes is not None and s.code not in codes:
                continue
            if sel.shape and s.shape != sel.shape:
                continue
            if sel.border and s.border != sel.border:
                continue
            if sel.background and s.background != sel.background:
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

    # ------------------------------------------------------------------ entry point
    def answer(self, scene: SceneGraph, query: QueryProgram | Program) -> Answer:
        program = normalize(query.program if isinstance(query, QueryProgram) else query)
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
    def _run(self, scene: SceneGraph, p: Program) -> Answer:
        when = getattr(p, "when", None)
        if when is not None and when.is_interval and not isinstance(p, Permitted):
            return Answer(verdict=Verdict.unknown,
                          note="time intervals are supported for permitted/forbidden only")
        if isinstance(p, Choose):
            return self._choose(scene, p)
        if isinstance(p, Verify):
            return self._verify(scene, p)
        if isinstance(p, Permitted):
            return self._permitted(scene, p)
        if isinstance(p, SpeedOk):
            self.load_scene(scene)
            out = self.call(Term("q_speed", vehicle_term(p.vehicle), float(p.speed_kmh),
                                 p.lane, _ctx(p.when, scene)))
            return _verdict_answer(out)
        if isinstance(p, (LanesFor, LanesWhere)):
            return self._lanes(scene, p)
        if isinstance(p, BanTimes):
            return self._ban_times(scene, p)
        if isinstance(p, Meaning):
            return self._meaning(scene, p)
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
                                 _minute(p.when.start), _minute(p.when.end), d1, d2,
                                 atom(p.when.quantifier.value)))
            ans = _verdict_answer(out)
            return ans.model_copy(update={"value": {
                "decided_at": _fmt_min(out["minute"]), "moments_checked": out["checked"]}})
        out = self.call(Term("q_permitted", atom(p.action.value), vehicle_term(p.vehicle),
                             _ctx(p.when, scene)))
        return _verdict_answer(out)

    def _lanes(self, scene: SceneGraph, p: LanesFor | LanesWhere) -> Answer:
        n = scene_lane_count(scene)
        if not n:
            return Answer(verdict=Verdict.unknown, note="the scene does not say how many lanes there are")
        self.load_scene(scene)
        speed = None if p.speed_kmh is None else float(p.speed_kmh)
        per_lane, reasons = [], []
        for lane in range(1, n + 1):
            out = self.call(Term("q_lane", vehicle_term(p.vehicle), lane,
                                 atom("none") if speed is None else speed, _ctx(p.when, scene)))
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
                      citations=_cites(reasons))

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
                      reasons=reasons + clears, citations=_cites(support))

    def _meaning(self, scene: SceneGraph, p: Meaning) -> Answer:
        ids = self.resolve(scene, p.sign)
        if p.sign.only and len(ids) != 1:
            return Answer(verdict=Verdict.unknown, value={"candidates": ids},
                          note="expected exactly one sign in the scene")
        out, cites = [], []
        for sid in ids:
            s = scene.sign(sid)
            if not self.catalog.has(s.code):
                out.append({"sign_id": sid, "code": s.code, "known": False})
                continue
            e = self.catalog.get(s.code)
            out.append({"sign_id": sid, "code": e.code, "name_vi": e.name_vi,
                        "name_en": e.name_en, "category": e.category, "value": s.value,
                        "known": True})
            cites.append(e.source)
        if not out:
            return Answer(verdict=Verdict.unknown, note="no sign in the scene matches the selector")
        verdict = Verdict.value if all(o["known"] for o in out) else Verdict.unknown
        return Answer(verdict=verdict, value=out, citations=cites)

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
        return Answer(verdict=Verdict.value, value=value, reasons=reasons, citations=cites)

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


def _verdict_answer(out: dict[str, Any]) -> Answer:
    reasons = [_reason(r) for r in out["reasons"]] + [_reason(c) for c in out["clears"]]
    return Answer(verdict=Verdict(out["verdict"]), reasons=reasons,
                  citations=_cites(_supporting(out)))


def _same(a: Answer, b: Answer) -> bool:
    return a.verdict == b.verdict and a.value == b.value
