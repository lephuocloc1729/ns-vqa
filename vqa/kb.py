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
    """A vehicle class that is our reading of the law rather than a class it names."""

    cls: VehicleClass = Field(alias="class")
    label_vi: str
    note: str
    source: Citation


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
    variants: list[str] = []    # letters a family row stands for
    source: Citation
    reviewed: bool = False

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
            out.append(Term("class_interpretation", atom(vi.cls.value),
                            atom(vi.source.law_id), atom(vi.source.article_id)))
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
    return Catalog.model_validate(raw)


__all__ = ["Catalog", "CatalogSign", "load_catalog", "code_atom", "cond_term"]
