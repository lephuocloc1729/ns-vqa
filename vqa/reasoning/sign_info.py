"""What a sign requires, where it takes effect and where it is placed, and guide-board lookups
(phase 4.5 B1 + B6; owner, 2026-11-17). Data in kb/sign_info.yaml; the catalog rows supply the
conduct items (F5), banned actions and allowed directions. Pure lookups: the legal content is
the cited articles' wording; the engine decides nothing here that a rule should."""

from __future__ import annotations

import difflib
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from vqa.kb import KB_DIR, Catalog
from vqa.schemas import Citation, GuideEntry

INFO_PATH = KB_DIR / "sign_info.yaml"
ART11 = Citation(law_id="QCVN 41:2024/BGTVT", article_id="11")
F1 = Citation(law_id="QCVN 41:2024/BGTVT", article_id="F.1")


@lru_cache(maxsize=1)
def info() -> dict[str, Any]:
    return yaml.safe_load(Path(INFO_PATH).read_text(encoding="utf-8"))


def _cite(d: dict) -> Citation:
    return Citation(law_id=d["law_id"], article_id=d["article_id"])


def _num(code: str) -> tuple[str, int] | None:
    m = re.match(r"^([A-Z]+)\.(\d{3})", code)
    return (m.group(1), int(m.group(2))) if m else None


def _row_matches(row: dict, code: str, category: str) -> bool:
    if "codes" in row:
        return any(code == c or code.startswith(c + "(") or re.fullmatch(re.escape(c) + r"[a-z]?", code)
                   or code.split("(")[0] == c for c in row["codes"])
    if "range" in row:
        a, b, n = _num(row["range"][0]), _num(row["range"][1]), _num(code)
        return bool(n and a and b and n[0] == a[0] and a[1] <= n[1] <= b[1])
    return row.get("category") == category


def lookup(kind: str, code: str, category: str) -> tuple[str, Citation] | None:
    """The scope or placement line for a catalog row code."""
    for row in info()[kind]:
        if _row_matches(row, code, category):
            return row["text"], _cite(row["source"])
    return None


def conduct_items(entry, catalog: Catalog) -> tuple[list[str], list[Citation]]:
    """What a catalog row requires of the driver, in Vietnamese, with the rules it rests on."""
    data, e = info(), entry.effect
    items, cites = [], [entry.source]
    items += [data["conduct_vi"].get(c, c) for c in e.conduct]
    if e.prohibits:
        acts = sorted({a.value for p in e.prohibits for a in p.actions})
        items.append("không được " + ", ".join(data["action_vi"].get(a, a) for a in acts))
    if e.only_directions:
        items.append("chỉ được " + ", ".join(data["action_vi"].get(a, a) for a in e.only_directions))
    if e.max_speed:
        items.append("không chạy quá tốc độ ghi trên biển")
    if e.min_speed:
        items.append("không chạy chậm hơn tốc độ ghi trên biển")
    rule = data["conduct_rule"].get(entry.category if entry.category != "end_of_restriction" else "", None)
    if items and rule:
        cites.append(_cite(rule))
    return items, cites


# ---------------------------------------------------------------- guide boards

def fold(text: str | None) -> str:
    t = unicodedata.normalize("NFD", str(text or "")).replace("Đ", "D").replace("đ", "d")
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    t = re.sub(r"[^A-Z0-9]+", " ", t.upper()).strip()
    # common abbreviations on boards
    return re.sub(r"\bQUOC LO\b", "QL", re.sub(r"\bTHANH PHO\b", "TP", t))


def find_entry(entries: list[GuideEntry], destination: str, threshold: float = 0.8) -> GuideEntry | None:
    """The board line naming `destination`: equal or contained after folding, else the most
    alike line at or above `threshold`."""
    want = fold(destination)
    if not want:
        return None
    for e in entries:
        got = fold(e.text)
        if got == want or (len(want) >= 3 and (want in got or got in want)):
            return e
    best, hit = 0.0, None
    for e in entries:
        r = difflib.SequenceMatcher(None, want, fold(e.text)).ratio()
        if r > best:
            best, hit = r, e
    return hit if best >= threshold else None


def parse_distance_m(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(km|m)\b", str(text), re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return v * 1000 if m.group(2).lower() == "km" else v
