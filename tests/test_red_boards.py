"""Plan item 1b.4 (owner, 2026-11-16): an unreadable rectangle with a red background
or a red border counts as prohibitory (permissions, speed, violations). Scenes
modelled on train_529 ("Xe máy có được đi vào đoạn đường này không?") with a red
local notice board nobody can read."""

import pytest

from vqa.perception.matching import visual_category as gate_category
from vqa.reasoning.engine import Engine
from vqa.schemas import Permitted, Required, SpeedOk, Verdict

from conftest import V, scene, sign


def board(sid, border, background):
    return sign(sid, "UNKNOWN", shape="rectangle", border=border, background=background)


@pytest.mark.parametrize("border, bg", [("none", "red"), ("red", "white"), ("red", "red")])
def test_an_unreadable_red_rectangle_makes_a_permission_unknown(engine, border, bg):
    sc = scene(sign("s1", "P.104"), board("s2", border, bg))
    a = engine.answer(sc, Permitted(action="enter", vehicle=V("passenger_car")))
    assert a.verdict == Verdict.unknown and a.uncertain_signs == ["s2"]


def test_a_blue_board_still_does_not(engine):
    sc = scene(sign("s1", "P.104"), board("s2", "none", "blue"))
    assert engine.answer(sc, Permitted(action="enter", vehicle=V("passenger_car"))).verdict == Verdict.yes


def test_a_red_rectangle_bears_on_speed_but_not_on_required(engine):
    sc = scene(sign("s1", "P.127", value=60, unit="km/h"), board("s2", "none", "red"))
    assert engine.answer(sc, SpeedOk(vehicle=V("passenger_car"), speed_kmh=50)).verdict == Verdict.unknown
    req = engine.answer(scene(board("s2", "none", "red")), Required(action="turn_right"))
    assert req.uncertain_signs == []


def test_categories():
    from types import SimpleNamespace as N
    e = N(shape=N(value="rectangle"), border=N(value="none"), background=N(value="red"))
    assert Engine.visual_category(e) == "red_board"
    assert Engine.could_matter("red_board", Permitted(action="turn_right", vehicle=V("motorbike")))
    # the perception gate's matching groups are unchanged (GATE scoring)
    assert gate_category("rectangle", "none", "red") == "board"
