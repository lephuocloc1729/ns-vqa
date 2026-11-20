"""Parser v13 (owner, 2026-11-18: additive only): v12 plus one section of new forms. No few-shot was
added this round (the train working set was not searched for the new types; none may come from
owner_questions.txt). The owner2 gold rows are the file's lines at d427da1, verbatim. No API call."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from vqa.kb import listed_signs, load_catalog
from vqa.parsing.prompt import examples, system_prompt
from vqa.parsing.wire import from_wire, to_query

ROOT = Path(__file__).resolve().parents[1]
V12, V13 = (ROOT / "prompts/parser" / v / "spec.md" for v in ("v12", "v13"))


def test_v13_is_v12_plus_one_section():
    a, b = V12.read_text(encoding="utf-8"), V13.read_text(encoding="utf-8")
    assert b.startswith(a[:a.index("# Out of scope")])
    assert b.endswith(a[a.index("# Out of scope"):])
    assert b.count("# Parser v13 additions") == 1


def test_v13_fewshots_are_v12s():
    assert examples("v13") == examples("v12")


def test_v13_prompt_builds_and_lists_p116_only_from_v13():
    assert system_prompt("v13") != system_prompt("v12")
    cat = load_catalog()
    for kind, version, want in [("parser", "v13", True), ("parser", "v12", False), ("parser", "v6", False),
                                ("scene", "v6", False), ("scene", "v5", False)]:
        assert any(s.code == "P.116" for s in listed_signs(cat, kind, version)) is want, (kind, version)


def _words(t):
    return re.findall(r"\w+", t.lower())


def test_v13_additions_copy_no_owner_question_text():
    """No four-word run of an owner or owner2 question in the v13 section, except the law's own
    term for the officer ("người điều khiển giao thông")."""
    spec = V13.read_text(encoding="utf-8")
    add = spec[spec.index("# Parser v13 additions"):spec.index("# Out of scope")]
    grams = lambda t: {tuple(_words(t)[i:i + 4]) for i in range(len(_words(t)) - 3)}
    allowed = grams("người điều khiển giao thông")
    qs = [l.split("|")[-1] for l in (ROOT / "data/annotations/gold_v12_new/owner_questions.txt")
          .read_text(encoding="utf-8").splitlines() if "|" in l and not l.startswith("#")]
    for q in qs:
        assert not (grams(add) & grams(q)) - allowed, q


@pytest.mark.parametrize("wire", [
    {"intent": "count_is", "sign": {"category": "prohibitory"}, "n": 3, "op": "ge"},
    {"intent": "duties", "topic": "joining_road"},
    {"intent": "officer_signal", "gesture": "arms_sideways", "side": "back"},
    {"intent": "verify", "claim": {"intent": "officer_permits", "gesture": "right_arm_up"}, "expect": False},
    {"intent": "precedence", "between": ["light", "officer"]},
    {"intent": "precedence_is", "winner": "temporary_sign", "over": "permanent_sign"},
    {"intent": "right_of_way", "my_road": "branch"},
    {"intent": "must_yield", "other_from": "cross_road"},
    {"intent": "vehicle_class_is", "vehicle": {"vehicle_class": "motorbike", "design_speed_kmh": 45,
                                               "motor_kw": 3}, "of_class": "moped"},
    {"intent": "vehicle_class", "vehicle": {"vehicle_class": "car", "seats": 16}},
    {"intent": "permitted", "action": "enter", "vehicle": {"vehicle_class": "truck", "axle_t": 8},
     "sign": {"code": "P.116"}},
    {"intent": "meaning", "sign": {"relative": "below", "anchor": {"meaning": "no_parking"}}},
    {"intent": "forbidden", "action": "enter", "vehicle": {"vehicle_class": "coach"},
     "sign": {"relative": "left_of", "anchor": {"light": True}}},
])
def test_wire_v13_forms(wire):
    q = to_query(from_wire({"program": wire}), 2025)
    assert q.program.intent == wire["intent"]


def test_owner2_rows_are_the_file_lines_at_d427da1_verbatim():
    from eval import parser_newtypes as nt
    lines = subprocess.run(["git", "show", "705e24a4c1d4:data/annotations/gold_v12_new/owner_questions.txt"],
                           capture_output=True, text=True, cwd=ROOT, check=True).stdout.splitlines()
    rows = [r for r in nt.load() if r["source"] == "owner2"]
    assert len(rows) == 20
    types = {"4": "count_bound", "5": "joining_road", "6": "officer", "7": "relative_selector",
             "8": "right_of_way", "9": "precedence", "10": "vehicle_class", "11": "size_check"}
    for r in rows:
        assert r["file_commit"] == "d427da1"
        tag, t, q = [x.strip() for x in lines[r["line"] - 1].split("|")]
        assert (tag, types[t], q) == ("owner2", r["intent"], r["question"]), r["id"]


def test_owner2_decides_at_three():
    from eval import parser_newtypes as nt
    assert nt.GROUPS["owner2"] == (3, True)
    rows = [r for r in nt.load() if r["source"] == "owner2"]
    preds = [{"id": r["id"], "query": None} for r in rows]
    out = nt.score(preds, rows)["groups"]["owner2"]
    assert out["count_bound"]["rule"] == "below 80%" and out["joining_road"]["rule"].startswith("fewer than 3")


def test_v13_estimate_uses_the_measured_v12_run():
    from eval import parser_newtypes as nt
    rows = nt.select(nt.load(), ["train", "owner_written", "owner2"])
    est = nt.estimate(rows, "v13")
    assert est["questions"] == 76 and 0.35 < est["expected_usd"] < 0.45
    assert nt.estimate(nt.select(nt.load(), ["train", "owner_written"]))["expected_usd"] < 0.25   # v12 as before


def test_gate_gives_v13_forms_back_only_on_out_of_scope_gold():
    from eval import parser_eval as pe
    assert '"intent": "must_yield"' in pe.V13_FEATURES and '"relative":' in pe.V13_FEATURES
