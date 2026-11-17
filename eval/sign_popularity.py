"""The most popular sign codes in train (owner, 2026-11-17; phase-4.5 section 11, stage A step 1).

Train only, never private or public. The validation set's questions are left out of every
count (it is aggregate only); its images are never read here. Three sources:
- **text:** codes written in train question and answer text;
- **gold:** set-T gold sign labels (train images);
- **perception:** codes read by perception on train images in stored runs (set-T runs and
  the dev run), one count per image.

A question "touches" a code when its text names the code, or its image has the code in
gold or in a perception reading. Codes are normalised to their catalog row when the catalog
has one (`W.207c` -> `W.207(a,...)`); others are kept as written.

    .venv/bin/python eval/sign_popularity.py [--top 80]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import gold_signs as gs  # noqa: E402
from eval import perception_eval as pe  # noqa: E402
from vqa.kb import load_catalog  # noqa: E402
from vqa.perception.matching import row_of  # noqa: E402

CODE = re.compile(r"\b(IE|DP|P|R|W|I|S)\s?\.\s?(\d{3})\s?([a-z])?(?![\w])", re.I)
VALIDATION = ROOT / "data" / "splits" / "train_validation.json"
DEV_RUN = ROOT / "eval" / "runs" / "e2e" / "dev_frozen_13ded0d75451.jsonl"


def norm(code: str, catalog) -> str:
    r = row_of(code, catalog)
    return r if r else code


def text_codes(text: str) -> set[str]:
    return {f"{m.group(1).upper()}.{m.group(2)}{(m.group(3) or '').lower()}" for m in CODE.finditer(text or "")}


def status(code: str, catalog) -> str:
    if not catalog.has(code):
        return "missing"
    s = catalog.get(code)
    if s.effect_unmodelled:
        return "effect_unmodelled"
    if s.meaning_only:
        return "meaning_only"
    e = s.effect
    has = any([e.prohibits, e.max_speed, e.min_speed, e.lane_board, e.lane_reserved, e.only_directions,
               e.ends, e.placement, e.value])
    return "modelled" if has else "no_effect"


def count(top: int = 80) -> dict[str, Any]:
    catalog = load_catalog()
    val = set(json.loads(VALIDATION.read_text(encoding="utf-8"))["questions"])
    val_imgs = set(json.loads(VALIDATION.read_text(encoding="utf-8"))["images"])
    rows = [q for q in json.loads(gs.TRAIN_QA.read_text(encoding="utf-8")) if q["id"] not in val]
    by_img = defaultdict(list)
    for q in rows:
        by_img[q["image_id"]].append(q["id"])
    text, gold, perc = Counter(), Counter(), Counter()
    touched: dict[str, set[str]] = defaultdict(set)
    for q in rows:
        for c in text_codes(q["question"] + " " + str(q.get("answer") or "")):
            c = norm(c, catalog)
            text[c] += 1
            touched[c].add(q["id"])
    for g in pe.gold_rows().values():
        if g.get("split") != "train" or g["image_id"] in val_imgs:
            continue
        for s in g["signs"]:
            if s.get("code") and s["code"] != "UNKNOWN":
                c = norm(s["code"], catalog)
                gold[c] += 1
                touched[c] |= set(by_img.get(g["image_id"], []))
    seen: dict[str, set[str]] = defaultdict(set)              # code -> train images perception read it on
    files = sorted(pe.RUNS.glob("T_*.jsonl"))
    for f in files:
        _, rs = pe.load_run(f)
        for r in rs:
            for s in (r.get("scene") or {}).get("signs", []):
                if s.get("code") and s["code"] != "UNKNOWN" and r["image_id"] not in val_imgs:
                    seen[norm(s["code"], catalog)].add(r["image_id"])
    if DEV_RUN.exists():
        for line in DEV_RUN.read_text(encoding="utf-8").splitlines()[1:]:
            r = json.loads(line)
            for s in (r.get("scene") or {}).get("signs", []):
                if s.get("code") and s["code"] != "UNKNOWN":
                    seen[norm(s["code"], catalog)].add(r["image_id"])
    for c, imgs in seen.items():
        perc[c] = len(imgs)
        for i in imgs:
            touched[c] |= set(by_img.get(i, []))
    codes = set(text) | set(gold) | set(perc)
    ranked = sorted(codes, key=lambda c: (-len(touched[c]), -(text[c] + gold[c] + perc[c]), c))
    out = []
    for c in ranked[:top]:
        s = catalog.get(c) if catalog.has(c) else None
        out.append({"code": c, "name_vi": s.name_vi if s else None, "category": s.category if s else None,
                    "status": status(c, catalog), "questions_touched": len(touched[c]),
                    "text": text[c], "gold": gold[c], "perception_images": perc[c],
                    "catalog_file": None if not s else ("meaning" if s.meaning_only and s.reviewed_by != "human"
                                                         and c in _meaning_codes() else "main")})
    return {"train_questions_counted": len(rows), "perception_files": len(files) + int(DEV_RUN.exists()),
            "codes_seen": len(codes), "top": out,
            "status_counts": dict(Counter(x["status"] for x in out))}


def _meaning_codes() -> set[str]:
    import yaml
    return {r["code"] for r in yaml.safe_load((ROOT / "kb" / "sign_catalog_meaning.yaml").read_text(encoding="utf-8"))["signs"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=80)
    print(json.dumps(count(ap.parse_args().top), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
