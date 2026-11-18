"""Parser v14 (owner, 2026-11-18): v13 plus one spec line, after the v13 gate's all_of miss
(public_natural_0048: a ban asked about two vehicles came back as sign_applies). No API call."""

from __future__ import annotations

import re
from pathlib import Path

from vqa.kb import listed_signs, load_catalog
from vqa.parsing.prompt import examples, system_prompt

ROOT = Path(__file__).resolve().parents[1]
V13, V14 = (ROOT / "prompts/parser" / v / "spec.md" for v in ("v13", "v14"))


def test_v14_is_v13_plus_one_line():
    a = V13.read_text(encoding="utf-8").splitlines()
    b = V14.read_text(encoding="utf-8").splitlines()
    added = [l for l in b if l not in a]
    assert len(b) == len(a) + 1 and [l for l in b if l in a] == a
    assert len(added) == 1 and "`forbidden`" in added[0] and "`sign_applies`" in added[0]
    assert "áp dụng cho" in added[0] and "dành cho" in added[0]


def test_v14_fewshots_prompt_and_catalog():
    assert examples("v14") == examples("v13")
    assert system_prompt("v14") != system_prompt("v13")
    assert any(s.code == "P.116" for s in listed_signs(load_catalog(), "parser", "v14"))


def test_v14_line_copies_no_owner_question_text():
    words = lambda t: re.findall(r"\w+", t.lower())
    grams = lambda t: {tuple(words(t)[i:i + 4]) for i in range(len(words(t)) - 3)}
    a = V13.read_text(encoding="utf-8").splitlines()
    line = next(l for l in V14.read_text(encoding="utf-8").splitlines() if l not in a)
    qs = [l.split("|")[-1] for l in (ROOT / "data/annotations/gold_v12_new/owner_questions.txt")
          .read_text(encoding="utf-8").splitlines() if "|" in l and not l.startswith("#")]
    assert not any(grams(line) & grams(q) for q in qs)


def test_newtypes_runner_takes_v14():
    from eval import parser_newtypes as nt
    rows = nt.select(nt.load(), ["train", "owner_written", "owner2"])
    assert nt.estimate(rows, "v14") == nt.estimate(rows, "v13")
