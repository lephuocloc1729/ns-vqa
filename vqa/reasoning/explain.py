"""Proof trees from the meta-interpreter -> ProofNode, citations, readable text."""

from __future__ import annotations

from typing import Any, Iterator

from vqa.schemas import Citation, ProofNode

# The law_id of rule_source entries that are our interpretations, not law text
# (kb/rules/common.pl). Proofs show them; citations leave them out.
INTERPRETATION = "interpretation"


def to_node(d: dict[str, Any]) -> ProofNode:
    return ProofNode(
        type=d["type"],
        goal=d.get("goal"),
        rule=d.get("rule"),
        source=Citation(**d["source"]) if d.get("source") else None,
        children=[to_node(c) for c in d.get("children", [])],
    )


def walk(node: ProofNode) -> Iterator[ProofNode]:
    yield node
    for c in node.children:
        yield from walk(c)


def citations(node: ProofNode | None) -> list[Citation]:
    """Every law article the proof relies on, in order of first use."""
    if node is None:
        return []
    seen: dict[tuple[str, str], Citation] = {}
    for n in walk(node):
        if n.source and n.source.law_id != INTERPRETATION and n.source.key() not in seen:
            seen[n.source.key()] = n.source
    return list(seen.values())


def rules_fired(node: ProofNode | None) -> list[str]:
    if node is None:
        return []
    return [n.rule for n in walk(node) if n.type == "cite" and n.rule]


def render(node: ProofNode, indent: int = 0) -> str:
    """Indented text form, for debugging and test failure messages."""
    pad = "  " * indent
    label = n_label(node)
    lines = [pad + label]
    for c in node.children:
        lines.append(render(c, indent + 1))
    return "\n".join(lines)


def n_label(n: ProofNode) -> str:
    src = f"  [{n.source.law_id} {n.source.article_id}]" if n.source else ""
    if n.type == "cite":
        return f"cite {n.rule}{src}"
    if n.type == "naf":
        return f"not {n.goal}"
    return f"{n.type} {n.goal}{src}"
