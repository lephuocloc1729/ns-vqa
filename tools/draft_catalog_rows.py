"""Draft meaning-only catalog rows for warning (W), information (I) and expressway
information (IE) signs from the dataset's law_db, with citations.

Authoring tool, run by hand; the output is reviewed and committed as
kb/sign_catalog_meaning.yaml. Not inference code.

    .venv/bin/python tools/draft_catalog_rows.py                # writes the YAML
    .venv/bin/python tools/draft_catalog_rows.py --review-list  # also (re)writes the review list
    .venv/bin/python tools/draft_catalog_rows.py --dry-run      # prints stats only

The review list (kb/review/meaning_rows_review.md) holds review results added by
hand, so it is only written with --review-list.

Sources:
  W.2xx  names from QCVN 41 art. 28 list, cited to the appendix C article that
         describes the sign (fallback: art. 28)
  I.4xx  names from art. 36 list, cited to the appendix E article (fallback: art. 36)
  IE.4xx names from the descriptions in art. 47, cited to art. 47

A row is flagged for review when the variant letters are not described one by
one in the text (they may differ only in a figure), when no appendix article
was found, or when an expressway name had to be cut from a longer sentence.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAW = Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural")) / "dataset" / "law_db" / "vlsp2025_law.json"
OUT = ROOT / "kb" / "sign_catalog_meaning.yaml"
REVIEW = ROOT / "kb" / "review" / "meaning_rows_review.md"
QCVN = "QCVN 41:2024/BGTVT"

# Expressway rows whose name cannot be cut from the text automatically. Each name is
# taken from QCVN 41 art. 47 as written (sentence or figure caption).
# Entries: code -> (name, review flags, note written into the row).
IE_OVERRIDES = {
    "IE.463a": ("Chỉ dẫn khoảng cách đến Công trình kiểm soát tải trọng xe", [], None),
    "IE.463b": ("Chỉ dẫn hướng rẽ vào nơi đặt Công trình kiểm soát tải trọng xe", [], None),
    "IE.464b": ("Chỉ dẫn hướng ra tại lối ra",
                ["name from figure caption Hình 11', which prints the code as 'E.464b'"], None),
    # set in review (2026-11-14): the drafted name was cut from a sentence
    "IE.473": ("Chỉ dẫn giảm tốc độ", ["name set in review from Hình 32"], None),
    # set in review (2026-11-14): the IE.472 family split into its two variants
    "IE.472a": ("Chỉ dẫn khoảng cách đến trạm thu phí",
                ["variant split in review"],
                "The sign shows a distance to the toll station, e.g. '750 m' (Hình 31a)."),
    "IE.472b": ("Chỉ dẫn trạm thu phí phía trước",
                ["variant split in review; meaning is our reading of the figure"],
                "QCVN 41 art. 47 names the IE.472 family 'Chỉ dẫn khoảng cách đến trạm thu "
                "phí'. This variant shows only 'TRẠM THU PHÍ / Toll Plaza' with no distance "
                "(Hình 31b), so 'the toll station itself / toll plaza ahead' is our reading "
                "of the figure, not a name QCVN gives."),
}
IE_FAMILIES: dict = {}
IE_DROP: set = set()

# Visual attributes that differ from the family default, from the figures (review 2026-11-14).
VISUAL_OVERRIDES = {
    "W.242(a,b)": {"shape": "other", "border": "red", "background": "white"},       # crossbuck
    "W.243(a,b,c)": {"shape": "rectangle", "border": "red", "background": "white"},  # striped marker
    "IE.451a": {"shape": "rectangle", "border": "none", "background": "blue"},
    "IE.471": {"shape": "rectangle", "border": "black", "background": "yellow"},
    "IE.473": {"shape": "rectangle", "border": "black", "background": "yellow"},
}

# Rows the project owner checked on 2026-11-14 (all flagged rows and the 12-row sample):
# reviewed_by: human. The other rows stay reviewed_by: none. The visual corrections in
# VISUAL_OVERRIDES came from an assistant review of the figures: visual_reviewed_by:
# assistant until the owner checks them.
REVIEWED = {
    "W.201(c,d)", "W.202(a,b)", "W.203(a,b,c)", "W.205(a,b,c,d,e)",
    "W.207(a,b,c,d,e,f,g,h,i,k,l)", "W.223(a,b)", "W.228(a,b)", "W.242(a,b)", "W.243(a,b,c)",
    "W.246(a,b,c)", "I.405(a,b,c)", "I.407(a,b,c)", "I.413(b,c)", "I.414(a,b,c,d)",
    "I.417(a,b,c)", "I.423(a,b)", "I.424(a,b)", "I.424(c,d)", "I.433(b,c,d)", "I.441(a,b,c)",
    "I.444(a,b,c,d,e,f,g,h,i,j,k,l,m)", "I.445(a,b,c,d,e,f,g,h)", "I.447(a,b,c,d)",
    "IE.464b", "IE.472a", "IE.472b", "IE.473",
    "W.233", "W.234", "W.235", "I.432", "I.434b", "I.442", "I.449",
    "IE.451a", "IE.453a", "IE.463c", "IE.471", "IE.474",
}

VISUAL = {
    "warning": {"shape": "triangle", "border": "red", "background": "yellow"},
    "information": {"shape": "rectangle", "border": "none", "background": "blue"},
    "expressway": {"shape": "rectangle", "border": "none", "background": "green"},
}


def fold(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def clean(t: str) -> str:
    t = re.sub(r"<<TABLE:.*?>>", " ", t, flags=re.S)
    return re.sub(r"<<IMAGE:[^>]*>>", " ", t)


def norm_code(c: str) -> str:
    return re.sub(r"\s+", "", c)


def appendix_article(articles: dict, prefix: str, family: str) -> str | None:
    """The appendix article (C.x / E.x) whose title names this code family."""
    fam = norm_code(family)
    for aid, a in articles.items():
        if not aid.startswith(prefix):
            continue
        title = norm_code(a["title"]).replace("W", "W").replace(" ", "")
        if re.search(re.escape(fam) + r"(?![0-9])", title):
            return aid
    return None


def bullet_names(text: str, family: str) -> dict[str, str]:
    """'- Biển số W.201a chỗ ngoặt nguy hiểm vòng bên trái;' -> {'a': '...'}."""
    out = {}
    fam = re.escape(family)
    for m in re.finditer(r"^\s*-\s*Biển số\s*" + fam + r"([a-z])\s*[:“\"]?\s*([^;\n]+)",
                         text, flags=re.M):
        name = m.group(2).strip().strip('”"').strip()
        if name and not name.lower().startswith(("đặt", "dùng", "được")):
            out[m.group(1)] = name
    return out


def list_rows(articles: dict, art: str, kind: str, appendix: str) -> list[dict]:
    rows = []
    for line in clean(articles[art]["text"]).split("\n"):
        m = re.match(r"\s*-\s*Biển số\s*((?:W|I)\.\s?\d+)\s*(\(([a-z,\s]+)\)|([a-z]))?\s*:\s*(.+?)[;.]?\s*$",
                     line)
        if not m:
            continue
        family = norm_code(m.group(1))
        letters = ([x.strip() for x in m.group(3).split(",") if x.strip()] if m.group(3)
                   else [m.group(4)] if m.group(4) else [])
        names = [n.strip() for n in m.group(5).split(";") if n.strip()]
        tries = ([f"{family}({','.join(letters)})"] if len(letters) > 1 else []) \
            + ([family + letters[0]] if letters else []) + [family]
        aid = next((a for a in (appendix_article(articles, appendix, t) for t in tries) if a), None)
        source = aid or art
        base_flags = [] if aid else [f"no appendix article found; cited to art. {art}"]
        text = clean(articles[aid]["text"]) if aid else ""
        if len(letters) <= 1:
            rows.append(row(family + (letters[0] if letters else ""), names[0], kind, source, base_flags))
            continue
        per = {}
        if len(names) == len(letters):
            per = dict(zip(letters, names))
        else:
            bn = bullet_names(text, family)
            if all(l in bn for l in letters):
                per = {l: bn[l] for l in letters}
        if not per and len(names) == 1:
            # "Đi chậm (a), Đi chậm có chỉ dẫn tiếng Anh (b)"
            tagged = dict((l, n.strip(" ,")) for n, l in
                          re.findall(r"([^()]+?)\s*\(([a-z])\)", names[0]))
            if set(tagged) == set(letters):
                per = tagged
        if per:
            for l in letters:
                rows.append(row(family + l, per[l], kind, source, base_flags))
        else:
            rows.append(row(f"{family}({','.join(letters)})", names[0], kind, source,
                            base_flags + ["variant letters " + ",".join(letters)
                                          + " are not described one by one in the text"],
                            variants=letters))
    return rows


def expressway_rows(articles: dict) -> list[dict]:
    text = clean(articles["47"]["text"])
    seen: dict[str, dict] = {}
    for m in re.finditer(r"Biển số\s*(IE\.\s?\d+[a-z]?)\s*([“\"]([^”\"]+)[”\"]|([^.;(\n]+))", text):
        code = norm_code(m.group(1))
        if code in seen:
            continue
        name = (m.group(3) or m.group(4) or "").strip()
        name = re.split(r"\s+(?:dùng để|được đặt|đặt|Biển này|bao gồm|được sử dụng|để báo|"
                        r"được bố trí|được lắp đặt|\(Hình)", name)[0].strip(" ,:")
        if not name or name.lower().startswith(("tại", "sử dụng", "(")) or len(name.split()) < 2:
            continue
        flags = []
        if len(name.split()) > 20:
            name = " ".join(name.split()[:20])
            flags.append("name cut from a longer sentence")
        seen[code] = row(code, name, "expressway", "47", flags)
    for code, (name, flags, note) in IE_OVERRIDES.items():
        seen[code] = row(code, name, "expressway", "47", flags, note=note)
    for code, (name, letters, flags) in IE_FAMILIES.items():
        seen[code] = row(f"{code}({','.join(letters)})", name, "expressway", "47", flags,
                         variants=letters)
    for code in IE_DROP:
        seen.pop(code, None)
    # a family row is dropped when two or more lettered rows exist (it repeats a caption)
    bases = [re.sub(r"[a-z]$", "", c) for c in seen if re.search(r"\d[a-z]$", c)]
    lettered = {b for b in bases if bases.count(b) >= 2}
    out = [r for c, r in seen.items() if c not in lettered]
    return sorted(out, key=lambda r: r["code"])


def row(code: str, name: str, kind: str, source: str, flags: list[str],
        variants: list[str] | None = None, note: str | None = None) -> dict:
    name = re.sub(r"\s+", " ", name).strip().strip('“”"').rstrip(".;")
    name = name[:1].upper() + name[1:]
    return {"code": code, "name_vi": name, "kind": kind, "source": source,
            "flags": flags, "variants": variants or [], "note": note}


def to_yaml(rows: list[dict]) -> str:
    out = [
        "# Meaning-only catalog rows: warning (W.2xx), information (I.4xx) and expressway",
        "# information (IE.4xx) signs. Drafted by tools/draft_catalog_rows.py from QCVN 41",
        "# art. 28, 36 and 47 and appendix C/E; every row cites its article.",
        "# These rows carry no rule effect: they let the engine name a sign, check",
        "# identity claims and report sign categories. Review list:",
        "# kb/review/meaning_rows_review.md. reviewed_by: human | assistant | none says who",
        "# checked the name, letters and citation; visual_reviewed_by does the same for the",
        "# visual attributes.",
        "",
        "signs:",
    ]
    keys = set()
    for r in rows:
        key = fold(r["name_vi"])[:60].strip("_")
        if key in keys:
            key = f"{key}_{fold(r['code'])}"
        keys.add(key)
        cat = "warning" if r["kind"] == "warning" else "information"
        v = VISUAL_OVERRIDES.get(r["code"], VISUAL[r["kind"]])
        out += [
            f"  - code: {r['code']}",
            f"    key: {key}",
            f"    name_vi: {json.dumps(r['name_vi'], ensure_ascii=False)}",
            f"    category: {cat}",
            f"    visual: {{shape: {v['shape']}, border: {v['border']}, background: {v['background']}}}",
            "    meaning_only: true",
        ]
        if r["variants"]:
            out.append(f"    variants: [{', '.join(r['variants'])}]")
        if r.get("note"):
            out.append(f"    note: {json.dumps(r['note'], ensure_ascii=False)}")
        out.append(f"    source: {{law_id: \"{QCVN}\", article_id: \"{r['source']}\"}}")
        out.append(f"    reviewed_by: {'human' if r['code'] in REVIEWED else 'none'}")
        if r["code"] in VISUAL_OVERRIDES:
            out.append("    visual_reviewed_by: assistant")
        out.append("")
    return "\n".join(out)


def review_md(rows: list[dict], seed: int = 1611) -> str:
    flagged = [r for r in rows if r["flags"]]
    clean_rows = [r for r in rows if not r["flags"]]
    k = max(1, round(len(clean_rows) * 0.10))
    sample = sorted(random.Random(seed).sample(clean_rows, k), key=lambda r: rows.index(r))
    lines = [
        "# Meaning-only rows: review list",
        "",
        f"{len(rows)} rows drafted ({sum(r['kind']=='warning' for r in rows)} W, "
        f"{sum(r['kind']=='information' for r in rows)} I, "
        f"{sum(r['kind']=='expressway' for r in rows)} IE). "
        f"{len(flagged)} flagged, plus a random 10% sample ({k}) of the unflagged rows "
        f"(seed {seed}) to spot-check.",
        "",
        "## Flagged rows",
        "",
        "| Code | Name (vi) | Cited | Why flagged |",
        "| --- | --- | --- | --- |",
    ]
    for r in flagged:
        lines.append(f"| {r['code']} | {r['name_vi']} | {r['source']} | {'; '.join(r['flags'])} |")
    lines += ["", "## Random sample of unflagged rows", "",
              "| Code | Name (vi) | Cited |", "| --- | --- | --- |"]
    for r in sample:
        lines.append(f"| {r['code']} | {r['name_vi']} | {r['source']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--review-list", action="store_true", help="also rewrite the review list")
    args = ap.parse_args()
    law = json.loads(LAW.read_text(encoding="utf-8"))
    qcvn = {a["id"]: a for a in law[0]["articles"]}
    rows = (list_rows(qcvn, "28", "warning", "C.") + list_rows(qcvn, "36", "information", "E.")
            + expressway_rows(qcvn))
    print(f"{len(rows)} rows, {sum(bool(r['flags']) for r in rows)} flagged")
    if args.dry_run:
        for r in rows:
            print(r["code"], r["variants"], r["source"], r["name_vi"][:60], r["flags"])
        return
    OUT.write_text(to_yaml(rows), encoding="utf-8")
    print(f"-> {OUT.relative_to(ROOT)}")
    missing = REVIEWED - {r["code"] for r in rows}
    if missing:
        raise SystemExit(f"reviewed codes not in the draft: {sorted(missing)}")
    if args.review_list:
        REVIEW.parent.mkdir(parents=True, exist_ok=True)
        REVIEW.write_text(review_md(rows), encoding="utf-8")
        print(f"-> {REVIEW.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
