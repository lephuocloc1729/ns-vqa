"""The answer writer (docs/plans/phase-4.md, item 1; DESIGN.md section 7).

One Claude call (Haiku 5.5, D1) verbalises the engine's answer. It sees the
question and the proof digest only: no image, no scene beyond the digest.

Flow:
- call -> JSON object -> the faithfulness guard;
- a bad JSON reply or a guard failure gets **one** retry that sends only the
  failure (the rejected reply is not echoed back: the assistant turn is a
  placeholder, as in the scene call);
- a second failure, a refusal or a reply cut off at max_tokens gives the
  deterministic template answer (`vqa/answer/template.py`).

So at most two calls are made, and the shipped answer always has the engine's
verdict. `WriteResult.status` is `first_try`, `regenerated` or `template`; the
template rate counts toward the phase-4 gate (D5).

**Streaming (opt-in, the demo API).** When `on_event` is set, each attempt's call
streams, and the listener gets `("delta", {"attempt": n, "text": ...})` for the new
characters of the reply's "answer" field, then `("reset", {"attempt": n, "reason": ...})`
whenever that text is withdrawn: before a retry, and before the template answer. The
listener only displays text; the result (status, text, citations) is the same as
without it, and with `on_event` unset the calls are exactly the plain ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from vqa.answer import digest as digest_mod
from vqa.answer import prompt as answer_prompt
from vqa.answer.faithfulness import check, is_true_false
from vqa.answer.stream import FieldStream
from vqa.answer.template import template_reply
from vqa.kb import Catalog
from vqa.llm.client import LLMBadJSON, LLMClient, LLMError
from vqa.llm.spend import SpendGuard, SpendLimitExceeded
from vqa.perception.wire import retry_messages
from vqa.schemas import Answer, SceneGraph


@dataclass
class WriteResult:
    status: str                          # first_try | regenerated | template
    verdict: str
    text: str
    cited_signs: list[str] = field(default_factory=list)
    cited_rules: list[str] = field(default_factory=list)
    attempts: int = 0                    # writer calls made (0-2)
    errors: list[list[str]] = field(default_factory=list)   # the failures of each attempt
    cost_usd: float = 0.0
    raw: list[str] = field(default_factory=list)
    prompt_id: str = ""


class AnswerWriter:
    def __init__(self, *, llm: LLMClient | None = None, version: str = answer_prompt.DEFAULT_VERSION,
                 guard: SpendGuard | None = None, catalog: Catalog | None = None) -> None:
        cfg = answer_prompt.config(version)
        self.version = version
        self.llm = llm or LLMClient(model=cfg["model"], guard=guard or SpendGuard())
        self.effort = cfg.get("effort")
        self.max_tokens = int(cfg.get("max_tokens", 600))
        self.catalog = catalog
        self._system = answer_prompt.system_prompt(version)
        self.prompt_id = answer_prompt.prompt_id(version)
        self.on_event: Callable[[str, dict[str, Any]], None] | None = None

    def _emit(self, kind: str, payload: dict[str, Any]) -> None:
        if self.on_event is not None:
            try:
                self.on_event(kind, payload)
            except Exception:
                pass                      # a display listener never changes the answer

    def _stream_listener(self, attempt: int) -> Callable[[str], None] | None:
        if self.on_event is None:
            return None
        fs = FieldStream("answer")

        def on_text(delta: str) -> None:
            new = fs.feed(delta)
            if new:
                self._emit("delta", {"attempt": attempt, "text": new})
        return on_text

    def write(self, question: str, answer: Answer, scene: SceneGraph | None) -> WriteResult:
        dg = digest_mod.build(answer, scene, self.catalog)
        return self.write_digest(question, dg)

    def write_digest(self, question: str, dg: dict[str, Any]) -> WriteResult:
        tf = is_true_false(question)
        user = answer_prompt.user_text(question, dg, tf)
        res = WriteResult(status="template", verdict=dg["verdict"], text="", prompt_id=self.prompt_id)
        extra: list[dict] = []
        for attempt in (1, 2):
            res.attempts = attempt
            if attempt == 2:
                self._emit("reset", {"attempt": 1, "reason": "retry"})
            listener = self._stream_listener(attempt)
            stream_kw = {"on_text": listener} if listener is not None else {}
            try:
                call = self.llm.json_reply(system=self._system, user=user, max_tokens=self.max_tokens,
                                           effort=self.effort, purpose="answer", extra_messages=extra,
                                           **stream_kw)
            except SpendLimitExceeded:
                raise
            except LLMBadJSON as e:
                res.cost_usd += getattr(e, "cost_usd", 0.0)
                res.raw.append(getattr(e, "raw_text", ""))
                errs = [str(e)]
            except LLMError as e:                # refusal or max_tokens: no retry
                res.cost_usd += getattr(e, "cost_usd", 0.0)
                res.raw.append(getattr(e, "raw_text", ""))
                res.errors.append([str(e)])
                break
            else:
                res.cost_usd += call.cost_usd
                res.raw.append(call.raw_text)
                errs = check(call.data, dg, question)
                if not errs:
                    res.status = "first_try" if attempt == 1 else "regenerated"
                    res.text = call.data["answer"].strip()
                    res.cited_signs = list(call.data["cited_signs"])
                    res.cited_rules = list(call.data["cited_rules"])
                    return res
            res.errors.append(errs)
            extra = retry_messages(errs)
        self._emit("reset", {"attempt": res.attempts, "reason": "template"})
        tpl = template_reply(dg, question)
        res.status, res.text = "template", tpl["answer"]
        res.cited_signs, res.cited_rules = tpl["cited_signs"], tpl["cited_rules"]
        return res
