"""Follow-up questions (owner, 2026-11-24): "Còn xe khách thì sao?" after "Xe tải có được rẽ trái ở đây không?".

Neither the rules pipeline nor the RAG keeps a conversation: each answers one complete question about
one photo, as benchmarked. So before a question is queued, the API rewrites a follow-up into a complete
question with one small Haiku call (prompts/followup/<version>/spec.md), using the previous question
asked about the same photo in the same session. The rewritten question goes to the unchanged pipeline,
and the page shows it ("Hiểu câu hỏi là: …"), so what was answered is always visible.

- The first question about a photo is never rewritten (no call).
- A question that is already complete comes back unchanged.
- Any failure (no key, refusal, bad JSON, spend limit, an implausible reply) keeps the asker's own
  question: a follow-up then gets the answer it would have had before this module.
- The live setting `followup` (on by default; admin site → Cài đặt) turns it off.
- It runs in the request, before the answer slots, so it never holds one of them.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v1"
MODEL = "claude-haiku-5-5"
SCHEMA = {
    "type": "object",
    "properties": {"question": {"type": "string"}, "changed": {"type": "boolean"}},
    "required": ["question", "changed"],
    "additionalProperties": False,
}
log = logging.getLogger(__name__)


def make_client(guard: Any) -> Any:
    """The real Haiku client (tests replace this, tests/conftest.py)."""
    from vqa.llm.client import LLMClient
    return LLMClient(model=MODEL, guard=guard)


def spec(version: str = VERSION) -> str:
    return (ROOT / "prompts" / "followup" / version / "spec.md").read_text(encoding="utf-8")


def prompt_id(version: str = VERSION) -> str:
    return f"followup/{version}@{hashlib.sha256(spec(version).encode()).hexdigest()[:12]}"


@dataclass
class Rewrite:
    question: str            # what goes to the pipeline
    changed: bool            # True: a follow-up was rewritten
    status: str              # skipped | unchanged | rewritten | failed | rejected
    cost_usd: float = 0.0
    error: str | None = None


def plausible(new: str, rewritten: str, max_chars: int) -> bool:
    """A rewrite must be a non-empty question of reasonable length (not an answer or an essay)."""
    r = rewritten.strip()
    return bool(r) and len(r) <= min(max_chars, 2 * len(new) + 300)


class Followup:
    def __init__(self, llm: Callable[[], Any], *, version: str = VERSION, max_chars: int = 1000) -> None:
        self._llm = llm                  # returns an LLMClient-like object (json_reply)
        self.version = version
        self.max_chars = max_chars
        self._system = spec(version)

    def rewrite(self, question: str, previous: str | None) -> Rewrite:
        if not previous:
            return Rewrite(question, False, "skipped")
        user = f"Previous: {previous}\nNew: {question}"
        try:
            call = self._llm().json_reply(system=self._system, user=user, max_tokens=400,
                                          purpose="followup", output_schema=SCHEMA)
        except Exception as e:               # no key, refusal, bad JSON, spend limit, HTTP
            cost = float(getattr(e, "cost_usd", 0.0) or 0.0)
            log.warning("follow-up rewrite failed: %s", type(e).__name__)
            return Rewrite(question, False, "failed", cost, f"{type(e).__name__}: {str(e)[:200]}")
        data = call.data or {}
        out, changed = str(data.get("question") or "").strip(), bool(data.get("changed"))
        if not changed or out == question.strip():
            return Rewrite(question, False, "unchanged", call.cost_usd)
        if not plausible(question, out, self.max_chars):
            return Rewrite(question, False, "rejected", call.cost_usd, "implausible rewrite")
        return Rewrite(out, True, "rewritten", call.cost_usd)
