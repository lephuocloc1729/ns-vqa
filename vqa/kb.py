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

_CODE_RE = re.compile(r"^(P|DP|R|W|I|S)\.[0-9A-Za-z,()]+$")


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


class Visual(_M):
    shape: str
    border: str
    background: str


class CatalogSign(_M):
    code: str
    name_vi: str
    name_en: str
    category: Literal["prohibitory", "mandatory", "warning", "information", "auxiliary",
                      "end_of_restriction"]
    visual: Visual
    effect: Effect = Effect()
    source: Citation
    reviewed: bool = False

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
        return self

    def get(self, code: str) -> CatalogSign:
        for s in self.signs:
            if s.code == code:
                return s
        raise KeyError(code)

    def has(self, code: str) -> bool:
        return any(s.code == code for s in self.signs)

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
            for p in e.prohibits:
                for a in p.actions:
                    for v in p.vehicles:
                        out.append(Term("prohibits", c, atom(a.value), spec_term(v)))
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
        return out


@lru_cache(maxsize=4)
def load_catalog(path: str | Path = CATALOG_PATH) -> Catalog:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Catalog.model_validate(raw)


__all__ = ["Catalog", "CatalogSign", "load_catalog", "code_atom", "cond_term"]
