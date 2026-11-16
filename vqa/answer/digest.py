"""The proof digest: what the answer writer sees, and what the guard checks against
(docs/plans/phase-4.md, item 1; DESIGN.md, "Grounded answer generation").

The engine's Answer carries a proof tree of raw Prolog goals. The writer needs
something small and readable, so the digest keeps:

- the verdict and the value;
- the signs the answer rests on (id, code, Vietnamese name, value, plate texts);
- the rules that fired (`cite` nodes), each with its source article;
- the reasons (sign, truth, the check that decided it);
- the citations, the uncertain signs, the note and the basis.

It is built from the Answer and the scene graph only (no image, no gold). The
guard allows a sign code or a number in the answer text only if it occurs in the
digest or in the question.
"""

from __future__ import annotations

import json
from typing import Any

from vqa.kb import Catalog, load_catalog
from vqa.reasoning.explain import walk
from vqa.schemas import Answer, SceneGraph


def _sign_ids_in(value: Any) -> list[str]:
    """Sign ids named inside an Answer value (`sign_id` keys, `signs` / `candidates` lists)."""
    out: list[str] = []

    def visit(v: Any, key: str | None = None) -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                visit(x, k)
        elif isinstance(v, list):
            for x in v:
                visit(x, key)
        elif isinstance(v, str) and key in ("sign_id", "signs", "candidates"):
            out.append(v)

    visit(value)
    return out


def _sign_entry(scene: SceneGraph, sid: str, catalog: Catalog) -> dict[str, Any] | None:
    try:
        s = scene.sign(sid)
    except (KeyError, ValueError, StopIteration):
        return None
    if s is None:
        return None
    known = catalog.has(s.code)
    entry: dict[str, Any] = {"id": s.id, "code": catalog.get(s.code).code if known else s.code,
                             "readable": known}
    if known:
        entry["name_vi"] = catalog.get(s.code).name_vi
    if s.value is not None:
        entry["value"] = s.value
        if s.unit:
            entry["unit"] = s.unit
    plates = [p.text for p in s.plates if getattr(p, "text", None)]
    if plates:
        entry["plates"] = plates
    if s.lanes:
        entry["lane_board"] = [ln.model_dump(mode="json", exclude_none=True) for ln in s.lanes]
    return entry


def build(answer: Answer, scene: SceneGraph | None, catalog: Catalog | None = None) -> dict[str, Any]:
    """The digest of one engine answer, as a JSON-ready dict."""
    catalog = catalog or load_catalog()
    ids: list[str] = []
    for r in answer.reasons:
        if r.sign_id and r.sign_id not in ids:
            ids.append(r.sign_id)
    for sid in [*answer.uncertain_signs, *_sign_ids_in(answer.value)]:
        if sid not in ids:
            ids.append(sid)
    signs = []
    if scene is not None:
        for sid in ids:
            if (e := _sign_entry(scene, sid, catalog)) is not None:
                signs.append(e)

    rules: dict[str, dict[str, Any]] = {}
    for r in answer.reasons:
        if r.proof is None:
            continue
        for n in walk(r.proof):
            if n.type == "cite" and n.rule and n.rule not in rules:
                rules[n.rule] = {"rule": n.rule,
                                 **({"source": f"{n.source.law_id} {n.source.article_id}"}
                                    if n.source else {})}

    reasons = []
    for r in answer.reasons:
        item = {"sign_id": r.sign_id, "truth": r.truth, "detail": r.detail}
        item = {k: v for k, v in item.items() if v is not None}
        if item not in reasons:
            reasons.append(item)

    out: dict[str, Any] = {
        "verdict": answer.verdict.value,
        "value": answer.value,
        "signs": signs,
        "rules": list(rules.values()),
        "reasons": reasons,
        "citations": [f"{c.law_id} {c.article_id}" for c in answer.citations],
    }
    if answer.uncertain_signs:
        out["uncertain_signs"] = list(answer.uncertain_signs)
    if answer.note:
        out["note"] = answer.note
    if answer.basis:
        out["basis"] = list(answer.basis)
    if scene is not None:
        out["signs_in_scene"] = len(scene.signs)
    return out


def to_text(digest: dict[str, Any]) -> str:
    """The digest as the writer sees it (compact JSON, Vietnamese kept as is)."""
    return json.dumps(digest, ensure_ascii=False, separators=(",", ":"), default=str)
