"""Phase 4.8 step 2 (a) (owner, 2026-11-18): several independent reads of one image, voted per sign.

`vote(scenes)` clusters the signs of the reads (the same physical sign in different reads, paired
with `matching.match(..., relate=True)` against each cluster's first reading), keeps a cluster
seen in at least half of the reads, and gives it the most frequent catalog row (a tie keeps the
earliest read's). Codes the other reads gave become alternative readings, so the engine's
reading policy decides with them. Everything else in the scene (road, vehicles, boards) is the
first read's. Selection only: what a sign means is still the catalog's.
"""

from __future__ import annotations

from collections import Counter

from vqa.kb import Catalog, load_catalog
from vqa.perception.matching import match, row_of, sign_view
from vqa.schemas import AltReading, Confidence, SceneGraph, Sign

_RANK = {"high": 3, "medium": 2, "low": 1}


def _conf(s: Sign) -> int:
    return _RANK.get(getattr(s.confidence, "value", s.confidence), 0)


def vote(scenes: list[SceneGraph], catalog: Catalog | None = None) -> SceneGraph:
    if not scenes:
        raise ValueError("vote needs at least one scene")
    if len(scenes) == 1:
        return scenes[0]
    catalog = catalog or load_catalog()
    clusters: list[list[tuple[int, Sign]]] = []
    for k, sc in enumerate(scenes):
        reps = [c[0][1] for c in clusters]
        pairs = match([sign_view(s) for s in reps], [sign_view(s) for s in sc.signs], catalog, relate=True)
        taken = {}
        for i, j in pairs:
            if all(m != k for m, _ in clusters[i]):
                taken[j] = i
        for j, s in enumerate(sc.signs):
            if j in taken:
                clusters[taken[j]].append((k, s))
            else:
                clusters.append([(k, s)])
    need = (len(scenes) + 1) // 2
    out: list[Sign] = []
    for c in clusters:
        if len({k for k, _ in c}) < need:
            continue
        rows = Counter(row_of(s.code, catalog) for _, s in c)
        first_row = {}
        for k, s in c:
            first_row.setdefault(row_of(s.code, catalog), k)
        top = max(rows, key=lambda r: (rows[r], r is not None, -first_row[r]))
        winners = [s for _, s in c if row_of(s.code, catalog) == top]
        rep = max(winners, key=_conf)
        alts = list(rep.alternatives)
        seen = {row_of(rep.code, catalog)} | {row_of(a.code, catalog) for a in alts}
        for _, s in c:
            r = row_of(s.code, catalog)
            if r is not None and r not in seen:
                alts.append(AltReading(code=s.code, value=s.value, confidence="low"))
                seen.add(r)
        disagree = len(rows) > 1
        upd = {"alternatives": alts}
        if disagree and _conf(rep) > _RANK["medium"]:
            upd["confidence"] = Confidence.medium          # the reads disagree: not a high-confidence reading
        out.append(rep.model_copy(update=upd))
    base = scenes[0]
    ids = [s.id for s in out]
    if len(set(ids)) != len(ids):                 # ids from different reads may collide
        out = [s.model_copy(update={"id": f"s{n}"}) for n, s in enumerate(out, 1)]
    return base.model_copy(update={"signs": out})
