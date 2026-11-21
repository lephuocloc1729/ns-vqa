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


# --- CI without local data -------------------------------------------------
# A clean checkout has neither the dataset nor the gitignored pictogram copies.
# With VQA_NO_LOCAL_DATA=1 (set in CI) the tests listed in needs_local_data.txt
# are skipped with a reason; without it, every test runs as before.
NO_LOCAL_DATA = os.environ.get("VQA_NO_LOCAL_DATA") == "1"
_NEEDS_LOCAL_DATA_FILE = Path(__file__).with_name("needs_local_data.txt")

# test_dev2 reads the train QA file at import time, so it cannot be collected.
collect_ignore = ["test_dev2.py"] if NO_LOCAL_DATA else []


def _needs_local_data() -> set[str]:
    lines = _NEEDS_LOCAL_DATA_FILE.read_text(encoding="utf-8").splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def pytest_collection_modifyitems(config, items):
    if not NO_LOCAL_DATA:
        return
    listed = _needs_local_data()
    skip = pytest.mark.skip(reason="needs the dataset or local pictogram copies")
    for item in items:
        if item.nodeid in listed:
            item.add_marker(skip)
