"""Build the reference pictograms for a scene prompt version (offline; reads law_db).

    .venv/bin/python tools/build_scene_pictograms.py --version v3

For each row in ROWS it finds the row's official figure(s) in law_db (figures whose
caption names the code, as tools/visual_review_sheet.py does), resizes each to at
most 320 px on the long edge, and writes:

- prompts/scene/<version>/pictograms/<figure>.png   local copies, gitignored (the
  law_db figures are dataset files and are never committed; CLAUDE.md exception)
- prompts/scene/<version>/pictograms.yaml           the committed manifest: per row,
  its code, name, source article, and per figure the source name, caption, local
  file name and the sha256 of the resized copy

vqa/perception/prompt.py reads only the manifest and the copies, and refuses to
build the version if a copy is missing or its sha256 differs.

Rows: the confused rows of the set-T errors (Haiku v1/v2, Sonnet v2) and the other
side of every observed confusion, so no look-alike pair is half-pictured (owner,
2026-11-15).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from PIL import Image  # noqa: E402

import tools.visual_review_sheet as vrs  # noqa: E402
from vqa.kb import load_catalog  # noqa: E402

MAX_EDGE = 320

ROWS = [
    # the 41 confused rows of the proposal
    "P.103a", "P.104", "P.106a", "P.110a", "P.111a", "P.111b", "P.125",
    "P.103c", "P.123a", "P.123b", "P.124a", "P.124b", "P.124c",
    "P.117", "P.118", "P.119", "P.130", "P.131a",
    "DP.134", "R.307", "R.404a",
    "P.127b", "P.127c", "R.415a", "I.417(a,b,c)",
    "I.407(a,b,c)", "I.409", "I.414(a,b,c,d)", "I.415", "I.444(a,b,c,d,e,f,g,h,i,j,k,l,m)",
    "IE.452", "IE.454", "IE.464", "IE.465", "IE.466",
    "W.203(a,b,c)", "W.205(a,b,c,d,e)", "W.207(a,b,c,d,e,f,g,h,i,k,l)", "W.233", "W.244", "W.245a",
    # the other side of confusions, added by the owner
    "P.106b", "P.107", "P.127", "R.306", "IE.464b", "R.403a", "R.412b",
    # the other side of the remaining observed confusions (the owner's no-half-pair rule)
    "I.401", "IE.451b", "IE.474", "P.115", "W.246(a,b,c)",
]


# Figures chosen by hand where caption matching picks the wrong ones (checked against
# the article text, 2026-11-15):
# - IE.452: article 47 describes it as "Hình 9a/9b"; only image026 (9b) is in law_db.
#   Without a caption naming IE.452, matching fell back to IE.450 / IE.451 figures.
# - R.415a: its own figure (a); matching also took R.415b's (b).
# W.244 needs no override: image284 is in article C.44 "Đoạn đường hay xảy ra tai nạn";
# its caption's "W.224" is a typo in law_db (W.224 has image240 in C.24).
FIGURE_OVERRIDES = {"IE.452": ["image026.jpg"], "R.415a": ["image332.jpg"]}


def out_dir(version: str) -> Path:
    return ROOT / "prompts" / "scene" / version


def resized_png(src: Path) -> bytes:
    with Image.open(src) as im:
        im = im.convert("RGB")
        w, h = im.size
        s = min(1.0, MAX_EDGE / max(w, h))
        if s < 1.0:
            im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def build(version: str) -> dict:
    cat = load_catalog()
    by = {s.code: s for s in cat.signs}
    articles = {(law["id"], a["id"]): a for law in json.loads(vrs.LAW.read_text(encoding="utf-8"))
                for a in law["articles"]}
    pic_dir = out_dir(version) / "pictograms"
    pic_dir.mkdir(parents=True, exist_ok=True)
    rows, written = [], {}
    for code in ROWS:
        row = by[code]
        figs = vrs.figures_for(row, articles)
        if code in FIGURE_OVERRIDES:
            art = articles[(row.source.law_id, row.source.article_id)]
            caps = {f: " ".join(c.split()) for f, c in vrs.IMAGE_RE.findall(art.get("text", ""))}
            figs = [(f, caps.get(f, "")) for f in FIGURE_OVERRIDES[code]]
        if not figs:
            raise SystemExit(f"{code}: no figure found in law_db")
        entries = []
        for fig, caption in figs:
            name = Path(fig).stem + ".png"
            if name not in written:
                data = resized_png(vrs.FIGURES / fig)
                (pic_dir / name).write_bytes(data)
                written[name] = hashlib.sha256(data).hexdigest()
            entries.append({"source": fig, "caption": caption, "file": name, "sha256": written[name]})
        rows.append({"code": row.code, "name_vi": row.name_vi, "article": row.source.article_id,
                     "figures": entries})
    manifest = {"version": version, "max_long_edge": MAX_EDGE,
                "note": "Copies are local and gitignored; build them with tools/build_scene_pictograms.py.",
                "rows": rows}
    (out_dir(version) / "pictograms.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")
    return {"rows": len(rows), "files": len(written)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    a = ap.parse_args()
    print(build(a.version))
