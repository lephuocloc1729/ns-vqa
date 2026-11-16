"""Visual review sheet for the D10 catalog rows (docs/plans/phase-3.md, D10).

Offline authoring tool: no API calls. It writes one local HTML page with a card per
row on the D10 list (rows in the set-T gold, in tests/fixtures/train_*.json and in
train question text; eval/gold_signs.visual_review_rows). Each card shows the row's
code, Vietnamese name, the catalog's shape / border / background, its current
visual_reviewed_by, the official figure(s) from law_db (images.fld) and up to two
set-T or train-fixture images where the sign occurs. Images are linked from the
dataset folder, never copied. The page is gitignored.

    .venv/bin/python tools/visual_review_sheet.py      # -> data/annotations/visual_review/sheet.html

Only train images are linked (set T and train fixtures): the D10 list excludes rows
found only in the public_dev gold, and this page links no public image.
"""

from __future__ import annotations

import glob
import html
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import eval.gold_signs as gs  # noqa: E402
from vqa.kb import load_catalog  # noqa: E402

DATASET = Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural")) / "dataset"
LAW = DATASET / "law_db" / "vlsp2025_law.json"
FIGURES = DATASET / "law_db" / "images.fld"
OUT = ROOT / "data" / "annotations" / "visual_review" / "sheet.html"
FIXTURES = ROOT / "tests" / "fixtures"
MAX_EXAMPLES = 2
MAX_FIGURES = 3

NOTES = {
    "P.102": ("Open owner decision: the border convention for P.102 (border: red or border: none "
              "on a red disc). The catalog row says red; some labels said none."),
}

IMAGE_RE = re.compile(r"<<IMAGE:\s*(\S+)\s*/IMAGE>>\s*([^<\n]{0,120})")   # caption: rest of the line


def _stem(code: str) -> str:
    """'R.403a' -> 'R.403', 'W.207(a,b,c)' -> 'W.207', 'P.102' -> 'P.102'."""
    base = code.split("(")[0].replace(" ", "")
    return re.sub(r"(?<=\d)[a-z]$", "", base)


def figures_for(row, articles: dict) -> list[tuple[str, str]]:
    """(file name, caption) of the figures in the row's source article whose caption
    names the row's code; all of the article's figures if none does (at most 3)."""
    art = articles.get((row.source.law_id, row.source.article_id))
    if not art:
        return []
    found = [(f, " ".join(c.split())) for f, c in IMAGE_RE.findall(art.get("text", ""))]
    stem = _stem(row.code)
    named = [(f, c) for f, c in found
             if re.search(re.escape(stem) + r"(?![0-9])", c.replace(" ", ""))
             or stem in c.replace(" ", "")]
    return (named or found)[:MAX_FIGURES]


def examples_for(code: str, gold: list[dict], fixtures: dict[str, set[str]], cat) -> list[str]:
    """Up to two train image ids where the row occurs: set-T gold first, then fixtures."""
    out = []
    for g in gold:
        if g["split"] != "train":
            continue
        for s in g["signs"]:
            if s["code"] != "UNKNOWN" and code in {cat.get(r).code for r in cat.codes_matching(s["code"])}:
                if g["image_id"] not in out:
                    out.append(g["image_id"])
    for image_id, codes in sorted(fixtures.items()):
        if code in codes and image_id not in out:
            out.append(image_id)
    return out[:MAX_EXAMPLES]


def fixture_codes(cat) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for p in sorted(glob.glob(str(FIXTURES / "train_*.json"))):
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        scene = data.get("scene") or {}
        image_id = data.get("image_id") or scene.get("scene_id")
        for s in scene.get("signs", []):
            try:
                rows = cat.codes_matching(s.get("code", ""))
            except KeyError:
                continue
            out.setdefault(image_id, set()).update(cat.get(r).code for r in rows)
    return out


def train_image(image_id: str) -> Path | None:
    hits = sorted(glob.glob(str(gs.TRAIN_IMAGES / f"{glob.escape(image_id)}.*")))
    return Path(hits[0]) if hits else None


def build(out: Path = OUT) -> dict:
    cat = load_catalog()
    gold = [json.loads(line) for line in gs.GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = gs.visual_review_rows(gold)
    by = {s.code: s for s in cat.signs}
    meaning_file = {s.code for s in cat.signs if s.meaning_only}
    articles = {}
    if LAW.exists():
        articles = {(law["id"], a["id"]): a
                    for law in json.loads(LAW.read_text(encoding="utf-8")) for a in law["articles"]}
    fixtures = fixture_codes(cat)
    cards = []
    for code in rows:
        r = by[code]
        v = r.visual
        figs = "".join(
            f"<figure><img src='{(FIGURES / f).resolve().as_uri()}' alt='{html.escape(f)}'>"
            f"<figcaption>{html.escape(c)}</figcaption></figure>"
            for f, c in figures_for(r, articles)) or "<p class='muted'>no figure found in law_db</p>"
        ex = []
        for image_id in examples_for(code, gold, fixtures, cat):
            p = train_image(image_id)
            ex.append(f"<a href='{p.resolve().as_uri()}'>{html.escape(image_id)}</a>" if p
                      else html.escape(image_id))
        where = ("meaning row: tools/draft_catalog_rows.py" if code in meaning_file
                 else "rule row: kb/sign_catalog.yaml")
        note = f"<p class='note'>{html.escape(NOTES[code])}</p>" if code in NOTES else ""
        cards.append(
            f"<section class='card' id='{html.escape(code)}'><h2>{html.escape(code)}</h2>"
            f"<p class='name'>{html.escape(r.name_vi)}</p>"
            f"<table><tr><th>shape</th><td>{v.shape}</td></tr><tr><th>border</th><td>{v.border}</td></tr>"
            f"<tr><th>background</th><td>{v.background}</td></tr>"
            f"<tr><th>visual_reviewed_by</th><td>{r.visual_reviewed_by}</td></tr>"
            f"<tr><th>source</th><td>{html.escape(r.source.article_id)}</td></tr>"
            f"<tr><th>edit in</th><td>{html.escape(where)}</td></tr></table>{note}"
            f"<div class='figs'>{figs}</div>"
            f"<p>gold examples: {', '.join(ex) or '<span class=muted>none in set T or fixtures</span>'}</p>"
            "</section>")
    howto = (
        "<div class='howto'><h1>D10 visual check</h1>"
        f"<p>{len(rows)} rows: those in the set-T gold, in tests/fixtures/train_*.json and in train "
        "question text. Rows found only in the public_dev gold are not here (they stay record-only).</p>"
        "<p><b>How to record it.</b> Compare the catalog's shape / border / background with the "
        "figure and the gold examples.</p><ul>"
        "<li><b>Meaning rows</b> (W, I, IE): in <code>tools/draft_catalog_rows.py</code>, fix a wrong "
        "look in <code>VISUAL_OVERRIDES</code> and mark the row as checked, then regenerate with "
        "<code>.venv/bin/python tools/draft_catalog_rows.py</code>. The tool can't write "
        "<code>visual_reviewed_by: human</code> yet (it writes <code>assistant</code> for rows in "
        "<code>VISUAL_OVERRIDES</code> only), so it needs a small change first, such as a "
        "<code>VISUAL_REVIEWED</code> set.</li>"
        "<li><b>Rule rows</b> (P, R, DP): edit <code>kb/sign_catalog.yaml</code> directly: fix "
        "<code>visual</code> and add <code>visual_reviewed_by: human</code>.</li></ul>"
        "<p>After that, the pinned review test (<code>tests/test_meaning_rows.py::"
        "test_review_provenance</code>, which lists the visual_reviewed_by values) needs updating, "
        "and the catalog-based prompt hashes move (record them in docs/status.md).</p></div>")
    page = (
        "<!doctype html><meta charset='utf-8'><title>D10 visual check</title><style>"
        "body{font:14px system-ui;margin:16px;max-width:1100px}"
        ".card{border-top:1px solid #ccc;padding:12px 0}.card h2{margin:0}.name{margin:2px 0 8px}"
        "table{border-collapse:collapse;margin:6px 0}th{text-align:left;padding:2px 10px 2px 0;"
        "color:#555;font-weight:500}td{padding:2px 0}.figs{display:flex;flex-wrap:wrap;gap:12px}"
        "figure{margin:0;max-width:260px}figure img{max-width:260px;max-height:200px}"
        "figcaption{font-size:12px;color:#555}.note{color:#b00020;font-weight:600}.muted{color:#888}"
        ".howto{background:#f4f4f4;padding:8px 14px;border-radius:6px}code{font-size:13px}</style>"
        + howto + "".join(cards))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return {"rows": rows, "cards": len(cards), "path": out}


if __name__ == "__main__":
    res = build()
    print(f"{res['cards']} cards -> {res['path']}")
