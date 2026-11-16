"""tools/visual_review_sheet.py, offline: one card per D10 row on the real catalog and gold."""

import json
import re
import subprocess
from pathlib import Path

import pytest

import eval.gold_signs as gs
import tools.visual_review_sheet as vrs

ROOT = Path(__file__).resolve().parent.parent


def d10_rows():
    gold = [json.loads(line) for line in gs.GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    return gs.visual_review_rows(gold)


def test_one_card_per_d10_row(tmp_path):
    out = tmp_path / "sheet.html"
    res = vrs.build(out)
    rows = d10_rows()
    page = out.read_text(encoding="utf-8")
    ids = re.findall(r"<section class='card' id='([^']+)'>", page)
    assert res["cards"] == len(rows) == len(ids) and ids == rows
    assert len(rows) == 55                      # the list recorded in docs/status.md
    assert "P.102" in ids and "border convention for P.102" in page
    assert "How to record it" in page and "test_review_provenance" in page


def test_page_links_only_train_images_and_copies_nothing(tmp_path):
    out = tmp_path / "sheet.html"
    vrs.build(out)
    page = out.read_text(encoding="utf-8")
    assert "public_test_" not in page and "private_test" not in page
    assert sorted(p.name for p in tmp_path.iterdir()) == ["sheet.html"]


def test_figure_captions_name_the_row():
    cat = {s.code: s for s in vrs.load_catalog().signs}
    law = vrs.LAW
    if not law.exists():
        pytest.skip("dataset not available")
    articles = {(l["id"], a["id"]): a for l in json.loads(law.read_text(encoding="utf-8"))
                for a in l["articles"]}
    figs = vrs.figures_for(cat["P.102"], articles)
    assert figs and figs[0][0] == "image092.jpg" and "P.102" in figs[0][1]
    r403 = vrs.figures_for(cat["R.403a"], articles)          # D.11 sits inside D.10
    assert [f for f, _ in r403] == ["image316.jpg"]


def test_output_path_is_gitignored():
    r = subprocess.run(["git", "check-ignore", "-q", str(vrs.OUT)], cwd=ROOT)
    assert r.returncode == 0
