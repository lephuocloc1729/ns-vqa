"""Shared fixtures and builders for hand-written scene graphs."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest

from vqa.reasoning.engine import Engine
from vqa.schemas import (
    LaneSpec, Plate, SceneGraph, Sign, TimeWindow, Vehicle, VehicleSpec, When,
)

DATASET_DIR = Path(os.environ.get(
    "VQA_DATASET_DIR",
    Path(__file__).resolve().parent.parent / "VLSP2025-MLQA-Natural",
))


@pytest.fixture(scope="session")
def engine() -> Engine:
    return Engine()


def V(cls: str, **kw) -> Vehicle:
    return Vehicle(**{"class": cls, **kw})


def spec(cls: str, *conds: tuple[str, str, float]) -> VehicleSpec:
    return VehicleSpec(**{"class": cls,
                          "conditions": [{"attr": a, "op": o, "value": v} for a, o, v in conds]})


def times(*windows: tuple[str, str]) -> Plate:
    return Plate(kind="time", time_windows=[TimeWindow(start=a, end=b) for a, b in windows])


def only_for(*specs: VehicleSpec) -> Plate:
    return Plate(kind="vehicle", vehicles=list(specs))


def except_for(*specs: VehicleSpec) -> Plate:
    return Plate(kind="exception", vehicles=list(specs))


def lane(n: int, max_speed=None, min_speed=None, vehicles=()) -> LaneSpec:
    return LaneSpec(lane=n, max_speed=max_speed, min_speed=min_speed, vehicles=list(vehicles))


def scene(*signs: Sign, vehicles=(), lanes: int | None = None, **kw) -> SceneGraph:
    return SceneGraph(scene_id="test", signs=list(signs), vehicles=list(vehicles),
                      road={"lanes": lanes}, **kw)


def sign(sid: str, code: str, **kw) -> Sign:
    return Sign(id=sid, code=code, **kw)


def at(h: int, m: int = 0, date: dt.date | None = None) -> When:
    return When(time=dt.time(h, m), date=date)


def articles(answer) -> set[str]:
    return {c.article_id for c in answer.citations}
