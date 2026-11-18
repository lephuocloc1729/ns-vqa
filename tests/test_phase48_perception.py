"""Phase 4.8 step 2 (owner, 2026-11-18): (a) voting several reads per sign
(vqa/perception/vote.py, eval/perception_vote.py) and (c) scene v7 (v5 plus visual notes for the
pairs Haiku swaps on set T, read off the QCVN 41 figures). Hand-made scenes; no API call."""

from __future__ import annotations

import json

import pytest

from vqa.perception import prompt as sp
from vqa.perception.fallback import config_for
from vqa.perception.vote import vote
from vqa.schemas import Position, SceneGraph, Sign


def S(sid, code, conf="high", rank=1, side="right", background="blue", border="red"):
    return Sign(id=sid, code=code, confidence=conf, shape="circle", border=border, background=background,
                position=Position(rank_top_down=rank, side=side))


def sc(*signs):
    return SceneGraph(scene_id="x", signs=list(signs))


def test_the_majority_code_wins_and_the_other_becomes_an_alternative():
    out = vote([sc(S("s1", "P.130")), sc(S("s1", "P.131a")), sc(S("s1", "P.131a"))])
    assert [s.code for s in out.signs] == ["P.131a"]
    assert [a.code for a in out.signs[0].alternatives] == ["P.130"]
    assert out.signs[0].confidence.value == "medium"          # the reads disagree


def test_reads_that_agree_keep_the_sign_unchanged():
    s = S("s1", "P.130")
    out = vote([sc(s), sc(s), sc(s)])
    assert out.signs == [s]


def test_a_sign_seen_in_one_read_of_three_is_dropped_and_one_in_two_is_kept():
    a = S("s1", "P.130")
    b = S("s2", "P.104", rank=2, background="white")
    out = vote([sc(a, b), sc(a), sc(a, b)])
    assert sorted(s.code for s in out.signs) == ["P.104", "P.130"]
    out = vote([sc(a, b), sc(a), sc(a)])
    assert [s.code for s in out.signs] == ["P.130"]


def test_a_three_way_split_keeps_the_first_reads_code_with_both_others_as_alternatives():
    out = vote([sc(S("s1", "P.130")), sc(S("s1", "P.131a")), sc(S("s1", "P.131b"))])
    assert out.signs[0].code == "P.130"
    assert sorted(a.code for a in out.signs[0].alternatives) == ["P.131a", "P.131b"]


def test_one_scene_is_returned_as_is_and_none_is_refused():
    s = sc(S("s1", "P.130"))
    assert vote([s]) is s
    with pytest.raises(ValueError):
        vote([])


def test_the_combiner_refuses_runs_of_different_configurations(tmp_path):
    from eval import perception_vote as pv
    def run(name, prompt):
        p = tmp_path / name
        head = {"run_id": name, "set": "T", "model": "m", "prompt_id": prompt, "fallback": {"policy": "crop_always"}}
        rows = [{"image_id": "i1", "scene": sc(S("s1", "P.130")).model_dump(mode="json", by_alias=True)}]
        p.write_text("\n".join(json.dumps(x) for x in [head, *rows]) + "\n", encoding="utf-8")
        return p
    a, b, c = run("a", "scene/v5@1"), run("b", "scene/v5@1"), run("c", "scene/v7@2")
    with pytest.raises(SystemExit, match="differ"):
        pv.combine([a, b, c], out_dir=tmp_path)
    out = pv.combine([a, b], out_dir=tmp_path)
    head = json.loads(out.read_text().splitlines()[0])
    assert head["vote"] == ["a", "b"] and "+fb+vote2_" in out.name


def test_scene_v7_is_v5_plus_the_three_visual_notes():
    for s in ("", "-tile", "-crop"):
        v5 = (sp.PROMPTS_DIR / f"v5{s}" / "spec.md").read_text(encoding="utf-8")
        v7 = (sp.PROMPTS_DIR / f"v7{s}" / "spec.md").read_text(encoding="utf-8")
        added = [ln for ln in v7.splitlines() if ln not in v5.splitlines()]
        assert len(added) == 3, s
        assert "an X" in added[0] and "two cars side by side" in added[1] and "never P.101" in added[2]
    assert config_for("v7").tile_version == "v7-tile" and config_for("v7").crop_version == "v7-crop"
    assert sp.prompt_id("v7") != sp.prompt_id("v5")
