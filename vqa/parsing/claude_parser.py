"""The question parser: one Claude call with structured output turns a Vietnamese
question into a QueryProgram (DESIGN.md, "Question parsing").

The parser never answers the question. It sees the question and, when available,
the list of sign codes in the scene (not the image). In phase 2 there is no
perception yet, so it sees the question only.

Flow: call -> wire JSON -> QueryProgram (defaults applied) -> validator. If any step
fails, one retry with the error message; a second failure is reported as invalid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from vqa.llm.client import LLMClient, LLMError
from vqa.llm.spend import SpendGuard, SpendLimitExceeded
from vqa.parsing import validator
from vqa.parsing.prompt import system_prompt
from vqa.parsing.wire import WParse, json_schema, to_query
from vqa.reasoning.engine import Engine
from vqa.schemas import QueryProgram

DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_EFFORT = "low"


@dataclass
class ParseResult:
    status: str                     # ok | out_of_scope | invalid | error
    query: QueryProgram | None = None
    errors: list[str] = field(default_factory=list)
    attempts: int = 0
    cost_usd: float = 0.0
    raw: list[str] = field(default_factory=list)


class ClaudeParser:
    def __init__(self, *, llm: LLMClient | None = None, model: str = DEFAULT_MODEL,
                 effort: str | None = DEFAULT_EFFORT, prompt_version: str = "v2",
                 context_year: int | None = None, engine: Engine | None = None,
                 guard: SpendGuard | None = None, max_tokens: int = 4096) -> None:
        self.llm = llm or LLMClient(model=model, guard=guard or SpendGuard())
        self.effort = effort          # None = the model's default effort
        self.prompt_version = prompt_version
        self.context_year = context_year
        self.engine = engine or Engine()
        self.max_tokens = max_tokens
        self._system = system_prompt(prompt_version)
        self._schema = json_schema()

    def _user(self, question: str, signs: list[str] | None) -> str:
        text = f"Question: {question.strip()}"
        if signs:
            text += "\nSigns in the scene (catalog codes): " + ", ".join(signs)
        return text

    def _convert(self, data: dict[str, Any]) -> tuple[QueryProgram | None, list[str]]:
        try:
            q = to_query(WParse.model_validate(data), self.context_year)
        except (ValidationError, ValueError) as e:
            return None, [f"invalid program: {e}"]
        errs = validator.check(q, self.engine)
        return (None, errs) if errs else (q, [])

    def parse(self, question: str, signs: list[str] | None = None) -> ParseResult:
        res = ParseResult(status="error")
        extra: list[dict] = []
        for attempt in (1, 2):
            res.attempts = attempt
            try:
                call = self.llm.structured(system=self._system, user=self._user(question, signs),
                                           schema=self._schema, max_tokens=self.max_tokens,
                                           effort=self.effort, purpose="parse",
                                           extra_messages=extra)
            except SpendLimitExceeded:
                raise
            except LLMError as e:
                res.errors.append(str(e))
                res.status = "error"
                return res
            res.cost_usd += call.cost_usd
            res.raw.append(call.raw_text)
            q, errs = self._convert(call.data)
            if q is not None:
                res.query = q
                res.status = "out_of_scope" if q.out_of_scope else "ok"
                res.errors = []
                return res
            res.errors = errs
            res.status = "invalid"
            extra = [{"role": "assistant", "content": call.raw_text},
                     {"role": "user", "content": "That answer is not valid: "
                      + "; ".join(errs) + ". Return a corrected answer."}]
        return res
