"""The question parser: one Claude call turns a Vietnamese question into a
QueryProgram (DESIGN.md, "Question parsing"). The reply is one JSON object in plain
text (no JSON schema is sent: the API's strict-schema limits are far below what
the DSL needs); the typed wire models and the validator check it.

The parser never answers the question. It sees the question and, when available,
the list of sign codes in the scene (not the image). In phase 2 there is no
perception yet, so it sees the question only.

Flow: call -> JSON object -> wire models -> QueryProgram (defaults applied) ->
validator. Malformed JSON or a failed check gets exactly one retry carrying a short
error message (the retry is an ordinary call, so the spend guard checks it); a
second failure is reported as invalid. A refusal or a reply cut off at max_tokens
is reported as error, with no retry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from vqa.llm.client import LLMBadJSON, LLMClient, LLMError
from vqa.llm.spend import SpendGuard, SpendLimitExceeded
from vqa.parsing import validator
from vqa.parsing.prompt import system_prompt
from vqa.parsing.wire import explain, from_wire, to_query
from vqa.perception.wire import PLACEHOLDER
from vqa.reasoning.engine import Engine
from vqa.schemas import QueryProgram

# Owner's choice on 2026-11-15, after the gate runs: Sonnet 5.5 at medium passed the
# three-run gate on prompt v6 (93.6%); Haiku 5.5 at medium did not (89.4%).
DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_EFFORT = "medium"


@dataclass
class ParseResult:
    status: str                     # ok | out_of_scope | invalid | error
    query: QueryProgram | None = None
    errors: list[str] = field(default_factory=list)
    attempts: int = 0
    cost_usd: float = 0.0
    raw: list[str] = field(default_factory=list)   # the reply text of every attempt, in order
    usage: list[dict] = field(default_factory=list)  # token usage of every attempt, in order


class ClaudeParser:
    def __init__(self, *, llm: LLMClient | None = None, model: str = DEFAULT_MODEL,
                 effort: str | None = DEFAULT_EFFORT, prompt_version: str = "v6",
                 context_year: int | None = None, engine: Engine | None = None,
                 guard: SpendGuard | None = None, max_tokens: int = 4096) -> None:
        self.llm = llm or LLMClient(model=model, guard=guard or SpendGuard())
        self.effort = effort          # None = the model's default effort
        self.prompt_version = prompt_version
        self.context_year = context_year
        self.engine = engine or Engine()
        self.max_tokens = max_tokens
        self._system = system_prompt(prompt_version)

    def _user(self, question: str, signs: list[str] | None) -> str:
        text = f"Question: {question.strip()}"
        if signs:
            text += "\nSigns in the scene (catalog codes): " + ", ".join(signs)
        return text

    def _convert(self, data: dict[str, Any]) -> tuple[QueryProgram | None, list[str]]:
        try:
            q = to_query(from_wire(data), self.context_year)
        except ValidationError as e:
            return None, [f"invalid program: {explain(e)}"]
        except ValueError as e:
            return None, [f"invalid program: {e}"]
        errs = validator.check(q, self.engine)
        return (None, errs) if errs else (q, [])

    def parse(self, question: str, signs: list[str] | None = None) -> ParseResult:
        res = ParseResult(status="error")
        extra: list[dict] = []
        for attempt in (1, 2):
            res.attempts = attempt
            try:
                call = self.llm.json_reply(system=self._system, user=self._user(question, signs),
                                           max_tokens=self.max_tokens, effort=self.effort,
                                           purpose="parse", extra_messages=extra)
            except SpendLimitExceeded:
                raise
            except LLMBadJSON as e:
                res.usage.append(self.llm.last_usage or {})
                res.cost_usd += getattr(e, "cost_usd", 0.0)
                raw = getattr(e, "raw_text", "")
                res.raw.append(raw)
                q, errs = None, [str(e)]
            except LLMError as e:            # refusal, max_tokens: no retry
                res.usage.append(self.llm.last_usage or {})
                res.cost_usd += getattr(e, "cost_usd", 0.0)
                res.raw.append(getattr(e, "raw_text", ""))
                res.errors.append(str(e))
                res.status = "error"
                return res
            else:
                res.usage.append(call.usage)
                res.cost_usd += call.cost_usd
                raw = call.raw_text
                res.raw.append(raw)
                q, errs = self._convert(call.data)
            if q is not None:
                res.query = q
                res.status = "out_of_scope" if q.out_of_scope else "ok"
                res.errors = []
                return res
            res.errors = errs
            res.status = "invalid"
            extra = self._retry(raw, errs)
        return res

    # Prompts frozen before phase 4.5 echo the rejected reply back as the assistant turn; from
    # v7 on (B2) the retry sends only the error, with a placeholder assistant turn, so prose
    # around the JSON is not repeated (the scene call's retry, vqa/perception/wire.py).
    ECHO_VERSIONS = frozenset({"v1", "v2", "v3", "v4", "v5", "v6"})

    def _retry(self, raw: str, errs: list[str]) -> list[dict]:
        msg = "That answer is not valid: " + "; ".join(errs) + ". Reply with only the corrected JSON object."
        if self.prompt_version in self.ECHO_VERSIONS:
            return [{"role": "assistant", "content": raw or "(empty reply)"}, {"role": "user", "content": msg}]
        return [{"role": "assistant", "content": PLACEHOLDER}, {"role": "user", "content": msg}]
