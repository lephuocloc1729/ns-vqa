"""One-to-one pairing of two sign lists from the same image (docs/plans/phase-3.md,
items 4 and 5). Used by the low-confidence re-run (two readings of one image) and
by eval/perception_eval.py (gold vs prediction), so both pair signs the same way.

There are no pixel boxes in gold, so pairs are chosen by a fixed score:
- a pair is allowed only if both codes resolve to the same catalog row, or the two
  signs have the same visual category (shape plus border and background group);
- among allowed pairs: same catalog row first, then same visual category, then the
  same side, then the closest rank top-down, then order in the lists. (Side comes
  before rank since perception_gate_v2: a model that ranks one board differently
  shifts every rank by one, and rank-first then pairs signs across the road.)
Pairs are taken greedily by that score, which is deterministic.

Side gives credit only to two equal, known sides. "overhead" is a side of its own,
so a prediction that marks every gantry sign "overhead" gets no side credit with
any gold side, and rank decides, which is what treating "overhead" as compatible
with any side would also do. Gantry signs need left/center/right from the model
itself (a scene prompt change, proposed for v3), not a matching change.

Signs are plain mappings with "code", "shape", "border", "background", "rank"
(rank_top_down) and "side"; `sign_view` makes one from a schema Sign.
"""

from __future__ import annotations

from typing import Any, Iterable

from vqa.kb import Catalog, load_catalog


def visual_category(shape: str | None, border: str | None, background: str | None) -> str:
    """The same groups as Engine.visual_category (CLAUDE.md, unreadable signs)."""
    if shape == "circle" and border == "red":
        return "red_circle"
    if shape == "circle" and background == "blue":
        return "blue_circle"
    if shape in ("rectangle", "square"):
        return "board"
    if shape in ("triangle", "diamond"):
        return "warning"
    if shape == "octagon":
        return "octagon"
    if shape == "circle" and border == "black":
        return "end_of_restriction"
    return "unknown"


def row_of(code: str | None, catalog: Catalog) -> str | None:
    """The catalog row a code names (a variant resolves to its family row), else None."""
    if not code or code == "UNKNOWN":
        return None
    if catalog.has(code):
        return catalog.get(code).code
    try:
        rows = catalog.codes_matching(code)
    except KeyError:
        return None
    return rows[0] if len(rows) == 1 else None


def sign_view(sign) -> dict[str, Any]:
    """A schema Sign as the mapping this module reads."""
    val = lambda x: x.value if hasattr(x, "value") else x  # noqa: E731
    return {"code": sign.code, "shape": val(sign.shape), "border": val(sign.border),
            "background": val(sign.background), "rank": sign.position.rank_top_down,
            "side": val(sign.position.side)}


def _stem(code: str | None) -> str | None:
    """'P.127b' -> 'P.127', 'W.207(a,b)' -> 'W.207'."""
    if not code or code == "UNKNOWN":
        return None
    base = code.split("(")[0]
    return base[:-1] if base[-1:].isalpha() and base[-2:-1].isdigit() else base


def related(a: str | None, b: str | None, catalog: Catalog) -> bool:
    """Two readings of the same physical sign: the same catalog family (P.127 /
    P.127b), or one ends the other (DP.134 ends P.127, R.307 ends R.306)."""
    sa, sb = _stem(a), _stem(b)
    if sa is None or sb is None:
        return False
    if sa == sb:
        return True
    ra, rb = row_of(a, catalog), row_of(b, catalog)
    if ra is None or rb is None:
        return False
    ends_a = {row_of(c, catalog) for c in catalog.get(ra).effect.ends}
    ends_b = {row_of(c, catalog) for c in catalog.get(rb).effect.ends}
    return rb in ends_a or ra in ends_b


def _score(a: dict, b: dict, catalog: Catalog, relate: bool = False) -> tuple | None:
    ra, rb = row_of(a.get("code"), catalog), row_of(b.get("code"), catalog)
    same_row = ra is not None and ra == rb
    ca = visual_category(a.get("shape"), a.get("border"), a.get("background"))
    cb = visual_category(b.get("shape"), b.get("border"), b.get("background"))
    same_cat = ca == cb and ca != "unknown"
    rel = relate and not same_row and related(a.get("code"), b.get("code"), catalog)
    if not (same_row or same_cat or rel):
        return None
    rk_a, rk_b = a.get("rank"), b.get("rank")
    rank_gap = abs(rk_a - rk_b) if isinstance(rk_a, int) and isinstance(rk_b, int) else 99
    same_side = a.get("side") not in (None, "unknown") and a.get("side") == b.get("side")
    if relate:     # the re-run's pairing: related readings rank just below the same row
        return (same_row, rel, same_cat, same_side, -rank_gap)
    return (same_row, same_cat, same_side, -rank_gap)


def match(left: Iterable[dict], right: Iterable[dict], catalog: Catalog | None = None,
          relate: bool = False) -> list[tuple[int, int]]:
    """Pairs (i, j) of indexes into left and right, one to one. With relate=True (the
    low-confidence re-run, two readings of one image) readings in the same family or
    an end/limit pair may also be paired; the eval's gate matching never relates."""
    catalog = catalog or load_catalog()
    left, right = list(left), list(right)
    cands = []
    for i, a in enumerate(left):
        for j, b in enumerate(right):
            s = _score(a, b, catalog, relate)
            if s is not None:
                cands.append((s, -i, -j, i, j))
    cands.sort(reverse=True)
    used_l, used_r, pairs = set(), set(), []
    for _, _, _, i, j in cands:
        if i not in used_l and j not in used_r:
            used_l.add(i)
            used_r.add(j)
            pairs.append((i, j))
    return sorted(pairs)
