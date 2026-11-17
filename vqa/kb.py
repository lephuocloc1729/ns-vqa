"""Sign catalog loader (kb/sign_catalog.yaml) and its Prolog facts."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from vqa.schemas import Action, Citation, CompareOp, VehicleAttr, VehicleClass, VehicleSpec, DayParity
from vqa.reasoning.terms import Term, atom, cond_term, spec_term

KB_DIR = Path(__file__).resolve().parent.parent / "kb"
CATALOG_PATH = KB_DIR / "sign_catalog.yaml"
MEANING_PATH = KB_DIR / "sign_catalog_meaning.yaml"  # meaning-only rows (W, I, IE)

_CODE_RE = re.compile(r"^(P|DP|R|W|IE|I|S)\.[0-9A-Za-z,()]+$")


def code_atom(code: str) -> str:
    """'P.127b' -> 'p127b', 'DP.133' -> 'dp133', 'S.H,6' -> 'sh_6'."""
    s = code.lower().replace(".", "")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Prohibition(_M):
    actions: list[Action]
    vehicles: list[VehicleSpec]


class ValueRule(_M):
    attr: VehicleAttr
    op: CompareOp
    unit: str
    applies_to: list[VehicleClass]


class Zone(_M):
    kind: Literal["expressway", "residential"]
    at: Literal["start", "end"]


class Effect(_M):
    prohibits: list[Prohibition] = []
    except_: list[VehicleClass] = Field(default=[], alias="except")
    priority_exempt: bool = True
    value: ValueRule | None = None
    days: DayParity | None = None
    max_speed: list[VehicleClass] = []
    min_speed: list[VehicleClass] = []
    lane_board: bool = False
    lane_reserved: list[VehicleClass] = []
    only_directions: list[Literal["go_straight", "turn_left", "turn_right"]] = []
    ends: list[str] = []
    placement: PlacementRules | None = None
    # phase 4.5 stage A (owner, 2026-11-17): family templates F3-F7
    zone: Zone | None = None          # F4: the sign starts or ends an expressway / residential zone
    conduct: list[str] = []             # F5: what the driver must do (stage B's `conduct` intent)
    permits: list[Action] = []          # F6: the sign marks a place where the action is allowed
    pass_side: Literal["as_shown"] | None = None   # F3b: R.302, pass the obstacle on the side shown
    yield_from: Literal["left", "right"] | None = None  # F3c: R.303, who yields at the roundabout
    informational: bool = False         # F7: a guide / information sign that orders nothing (KB-3)


Direction = Literal["go_straight", "turn_left", "turn_right", "u_turn"]
Placement = Literal["before_intersection", "after_intersection"]


class PlacementEffect(_M):
    directions: list[Direction]
    scope: Literal["intersection_behind", "intersection_ahead", "until_next_intersection"]


class PlacementRules(_M):
    """R.301 family (QCVN 41 D.1a): what the sign allows for each placement."""

    standard: Literal["before_intersection", "after_intersection", "either"]
    before_intersection: PlacementEffect | None = None
    after_intersection: PlacementEffect | None = None


class VehicleInterpretation(_M):
    """Our reading of the law where it names no class or rule: either a vehicle class
    (`class`, e.g. similar_rudimentary) or an attribute rule (`attribute_rule`, e.g.
    load_implies_gross: a load above x t means a gross mass above x t). Exactly one."""

    cls: VehicleClass | None = Field(default=None, alias="class")
    attribute_rule: Literal["load_implies_gross"] | None = None
    label_vi: str
    note: str
    source: Citation

    @model_validator(mode="after")
    def _one_kind(self) -> "VehicleInterpretation":
        if (self.cls is None) == (self.attribute_rule is None):
            raise ValueError("a vehicle interpretation names exactly one of class / attribute_rule")
        return self


class Visual(_M):
    shape: str
    border: str
    background: str


class CatalogSign(_M):
    code: str  # "P.104", or a family with its variants in QCVN notation: "W.207(a,b,c)"
    key: str
    tags: list[str] = []
    name_vi: str
    name_en: str | None = None
    category: Literal["prohibitory", "mandatory", "warning", "information", "auxiliary",
                      "end_of_restriction"]
    visual: Visual
    effect: Effect = Effect()
    meaning_only: bool = False  # names the sign; carries no rule effect
    # A sign with a legal effect the rules don't model yet (e.g. R.303 roundabout). It is
    # known by code and meaning, but closed-world claims treat it like an unreadable sign
    # of its visible kind, so it can't turn an "unknown" into a confident "yes".
    effect_unmodelled: bool = False
    note: str | None = None     # e.g. where a meaning is our reading rather than QCVN wording
    variants: list[str] = []    # letters a family row stands for
    source: Citation
    # Who checked the row's name, letters and citation; visual attributes are tracked
    # separately because corrections there may come from a different reviewer.
    reviewed_by: Literal["human", "assistant", "none"] = "none"
    visual_reviewed_by: Literal["human", "assistant", "none"] = "none"
    # who checked the row's effect, when it was added or changed after the name was checked
    # (phase 4.5: kb/sign_catalog_effects.yaml and edited rule rows)
    effect_reviewed_by: Literal["human", "assistant", "none"] = "none"
    # A row added after the phase-4 freeze (phase 4.5). Frozen prompt versions (scene v1-v4 with
    # their tiles and crops, parser v1-v6) don't list it, so their ids stay reproducible; scene
    # v5 and parser v7 on do (vqa.kb.FROZEN_PROMPT_VERSIONS).
    listed_from: Literal["phase45"] | None = None

    @property
    def base(self) -> str:
        return self.code.split("(")[0]

    def answers_to(self, code: str) -> bool:
        """True for the row's own code, or base + one of its variant letters."""
        return code == self.code or any(code == self.base + v for v in self.variants)

    @model_validator(mode="after")
    def _check(self) -> "CatalogSign":
        if not _CODE_RE.match(self.code):
            raise ValueError(f"bad sign code {self.code!r}")
        for c in self.effect.ends:
            if not _CODE_RE.match(c):
                raise ValueError(f"{self.code}: bad code in ends: {c!r}")
        if self.effect_unmodelled and (self.meaning_only or self.effect != Effect()):
            raise ValueError(f"{self.code}: effect_unmodelled rows have no effect and are not "
                             "meaning_only")
        return self

    @property
    def atom(self) -> str:
        return code_atom(self.code)


class Catalog(_M):
    version: str
    law_versions: list[str]
    vehicle_interpretations: list[VehicleInterpretation] = []
    signs: list[CatalogSign]

    @model_validator(mode="after")
    def _unique(self) -> "Catalog":
        codes = [s.code for s in self.signs]
        dupes = {c for c in codes if codes.count(c) > 1}
        if dupes:
            raise ValueError(f"duplicate codes: {sorted(dupes)}")
        atoms = [s.atom for s in self.signs]
        if len(set(atoms)) != len(atoms):
            raise ValueError("two codes map to the same Prolog atom")
        keys = [s.key for s in self.signs]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate catalog keys")
        if set(keys) & {t for s in self.signs for t in s.tags}:
            raise ValueError("a tag must not reuse a catalog key")
        return self

    def codes_matching(self, code: str) -> list[str]:
        """Catalog codes a claimed code stands for: the code itself, or every row of a
        family ("W.221" matches W.221a and W.221b). Raises KeyError if none."""
        if self.has(code):
            return [self.get(code).code]
        fam = [s.code for s in self.signs
               if re.fullmatch(re.escape(code) + r"[a-z]", s.code) or s.base == code]
        if not fam:
            raise KeyError(f"unknown sign code {code!r}")
        return fam

    def code_selects(self, selector: str, scene_code: str) -> bool:
        """Does a selector's code pick out a scene sign with ``scene_code``? Sign
        selection only, not a legal decision.

        - Equal codes match ("W.207c" selects W.207c, and not W.207a).
        - A family stem or the full family row code selects every variant of the
          family ("W.207" and "W.207(a,...)" select W.207c).
        - A stem of separate rows selects each of them ("P.124" selects P.124c).
        - A scene code that is UNKNOWN or not in the catalog never matches, nor does
          a selector code the catalog cannot resolve.
        """
        if not self.has(scene_code):
            return False
        if selector == scene_code:
            return True
        try:
            targets = self.codes_matching(selector)
        except KeyError:
            return False
        if self.has(selector) and self.get(selector).code != selector:
            return False                    # a variant code selects only itself
        return self.get(scene_code).code in targets

    def codes_for_meaning(self, meaning: str) -> list[str]:
        """Codes whose key or tags match ``meaning``. Raises KeyError if none do."""
        codes = [s.code for s in self.signs if s.key == meaning or meaning in s.tags]
        if not codes:
            raise KeyError(f"unknown sign meaning {meaning!r}")
        return codes

    def get(self, code: str) -> CatalogSign:
        """The row for a code; a variant code ("W.207c") resolves to its family row."""
        for s in self.signs:
            if s.code == code:
                return s
        for s in self.signs:
            if s.answers_to(code):
                return s
        raise KeyError(code)

    def has(self, code: str) -> bool:
        return any(s.answers_to(code) for s in self.signs)

    def by_atom(self, a: str) -> CatalogSign:
        for s in self.signs:
            if s.atom == a:
                return s
        raise KeyError(a)

    # ------------------------------------------------------------------ facts
    def facts(self) -> list[Term]:
        out: list[Term] = []
        for s in self.signs:
            c = atom(s.atom)
            e = s.effect
            out.append(Term("catalog_sign", c, atom(s.category),
                            atom(s.source.law_id), atom(s.source.article_id)))
            out.append(Term("catalog_key", c, atom(s.key)))
            out += [Term("catalog_tag", c, atom(t)) for t in s.tags]
            by_action: dict[str, list] = {}
            for p in e.prohibits:
                for a in p.actions:
                    by_action.setdefault(a.value, []).extend(spec_term(v) for v in p.vehicles)
            for a, specs in by_action.items():
                out.append(Term("prohibits", c, atom(a), specs))
            for x in e.except_:
                out.append(Term("catalog_except", c, atom(x.value)))
            if not e.priority_exempt:
                out.append(Term("no_priority_exempt", c))
            if e.value:
                for cls in e.value.applies_to:
                    out.append(Term("value_cond", c, atom(cls.value),
                                    atom(e.value.attr.value), atom(e.value.op.value)))
            if e.days:
                out.append(Term("catalog_days", c, atom(e.days.value)))
            for cls in e.max_speed:
                out.append(Term("max_speed_for", c, atom(cls.value)))
            for cls in e.min_speed:
                out.append(Term("min_speed_for", c, atom(cls.value)))
            if e.lane_board:
                out.append(Term("lane_board", c))
            for cls in e.lane_reserved:
                out.append(Term("lane_reserved", c, atom(cls.value)))
            if e.only_directions:
                out.append(Term("direction_sign", c))
                for a in e.only_directions:
                    out.append(Term("only_direction", c, atom(a)))
            for ended in e.ends:
                out.append(Term("ends", c, atom(code_atom(ended))))
            if e.zone:
                out.append(Term("zone_sign", c, atom(e.zone.kind), atom(e.zone.at)))
            out += [Term("conduct", c, atom(x)) for x in e.conduct]
            out += [Term("permits_here", c, atom(a.value)) for a in e.permits]
            if e.pass_side:
                out.append(Term("pass_side", c, atom(e.pass_side)))
            if e.yield_from:
                out.append(Term("yield_from", c, atom(e.yield_from)))
            if e.informational:
                out.append(Term("informational", c))
            if e.placement:
                pl = e.placement
                if pl.standard != "either":
                    out.append(Term("standard_placement", c, atom(pl.standard)))
                for name in ("before_intersection", "after_intersection"):
                    eff = getattr(pl, name)
                    if eff:
                        out.append(Term("placement_effect", c, atom(name),
                                        [atom(d) for d in eff.directions], atom(eff.scope)))
        for vi in self.vehicle_interpretations:
            if vi.cls is not None:
                out.append(Term("class_interpretation", atom(vi.cls.value),
                                atom(vi.source.law_id), atom(vi.source.article_id)))
            else:
                out.append(Term("attr_interpretation", atom(vi.attribute_rule)))
        return out


@lru_cache(maxsize=4)
def load_catalog(path: str | Path = CATALOG_PATH,
                 meaning_path: str | Path | None = MEANING_PATH) -> Catalog:
    """The rule catalog, plus the meaning-only rows when that file exists."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if meaning_path and Path(meaning_path).exists():
        with open(meaning_path, encoding="utf-8") as f:
            raw["signs"] = raw["signs"] + yaml.safe_load(f)["signs"]
    if meaning_path and EFFECTS_PATH.exists():
        merge_effects(raw["signs"], yaml.safe_load(EFFECTS_PATH.read_text(encoding="utf-8"))["effects"])
    return Catalog.model_validate(raw)


EFFECTS_PATH = Path(__file__).resolve().parents[1] / "kb" / "sign_catalog_effects.yaml"

# Prompt versions frozen before phase 4.5: their catalog listings leave out rows marked
# `listed_from: phase45`, so the prompt ids pinned in tests, caches and freeze records still hold.
FROZEN_PROMPT_VERSIONS = {"scene": {"v1", "v2", "v3", "v4", "v4-tile", "v4-crop"},
                          "parser": {"v1", "v2", "v3", "v4", "v5", "v6"}}


def listed_signs(catalog: "Catalog", kind: str, version: str | None) -> list[CatalogSign]:
    """The rows a prompt of `kind` ("scene" or "parser") at `version` lists."""
    frozen = version is None or version in FROZEN_PROMPT_VERSIONS[kind]
    return [s for s in catalog.signs if not (frozen and s.listed_from)]


def merge_effects(signs: list[dict], effects: list[dict]) -> None:
    """Phase 4.5 stage A: effects for rows of the generated meaning file, kept apart so the
    generator (tools/draft_catalog_rows.py) can't overwrite them. Each entry names a row by
    its exact code; its effect keys are added, and the row is no longer meaning-only."""
    by_code = {s["code"]: s for s in signs}
    for e in effects:
        row = by_code.get(e["code"])
        if row is None:
            raise ValueError(f"sign_catalog_effects.yaml: no catalog row {e['code']!r}")
        row["effect"] = {**(row.get("effect") or {}), **e.get("effect", {})}
        row["meaning_only"] = False
        row["effect_unmodelled"] = False
        row["effect_reviewed_by"] = e.get("effect_reviewed_by", "none")
        if e.get("note"):
            row["note"] = (row.get("note") + " | " if row.get("note") else "") + e["note"]


__all__ = ["Catalog", "CatalogSign", "load_catalog", "code_atom", "cond_term"]
