"""Thin wrapper around the Anthropic SDK for calls that reply with one JSON object.

- The API key comes from the environment (ANTHROPIC_API_KEY, or any credential
  source the SDK resolves); it is never passed in code or written anywhere.
- By default no JSON schema is sent (output_config.format). The API caps strict
  schemas at 24 optional and 16 union-typed parameters in total, far below what the
  query DSL needs, so the reply is plain text: a bare JSON object, or one in a
  ```json fence. Anything else raises LLMBadJSON; callers validate the object
  themselves. A caller with a small flat reply may pass `output_schema`, sent as
  output_config.format (json_schema); only the answer-level fallback from prompt v2
  on does (tuning T2, owner 2026-11-16).
- Before a request, its prompt is counted (messages.count_tokens) and the worst
  case (whole prompt as a cache write, full max_tokens out) is checked against
  the SpendGuard.
- Every request is logged to logs/api_calls.jsonl with a status: ok, refusal,
  max_tokens, bad_json, or http_error (cost 0: nothing was billed).
- refusal and max_tokens stop reasons raise, each with its own message.
- The user turn is text (the parser) or a list of content blocks, text and image
  (the scene call). Text is sent unchanged, as the parser always sent it.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from vqa.llm.pricing import cost_usd, worst_case_usd
from vqa.llm.spend import SpendGuard, log_call


class LLMError(RuntimeError):
    pass


class LLMRefusal(LLMError):
    pass


class LLMTruncated(LLMError):
    pass


class LLMBadJSON(LLMError):
    """The reply is not one JSON object (bare, or in a ```json fence)."""


_FENCE = re.compile(r"\A```json[ \t]*\n(.*)\n```\Z", re.S)


def parse_json_reply(text: str) -> dict[str, Any]:
    """The JSON object in a reply: the whole reply, or the inside of one ```json
    fence that is the whole reply. Raises LLMBadJSON otherwise."""
    body = text.strip()
    m = _FENCE.match(body)
    if m:
        body = m.group(1).strip()
    if not body.startswith("{"):
        raise LLMBadJSON("the reply must be only a JSON object (optionally in a ```json fence), "
                         "with no text around it")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise LLMBadJSON(f"the reply is not valid JSON: {e.msg} at line {e.lineno} column {e.colno}") from e
    if not isinstance(data, dict):
        raise LLMBadJSON("the reply must be a JSON object")
    return data


@dataclass
class CallResult:
    data: dict[str, Any]          # the parsed JSON output
    cost_usd: float
    usage: dict[str, int]
    request_id: str | None = None
    raw_text: str = ""


@dataclass
class LLMClient:
    """One model, one spend guard, one run id. `sdk` is an anthropic.Anthropic (or a
    stand-in with the same messages.create / messages.count_tokens in tests)."""

    model: str
    guard: SpendGuard = field(default_factory=SpendGuard)
    sdk: Any = None
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    last_usage: dict[str, int] | None = field(default=None, init=False)  # of the latest call, even if it raised

    def __post_init__(self) -> None:
        if self.sdk is None:
            import anthropic
            self.sdk = anthropic.Anthropic()

    @staticmethod
    def system_blocks(stable: str) -> list[dict[str, Any]]:
        """The frozen system prompt as one cached text block."""
        return [{"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}}]

    def _log(self, purpose: str, effort: str | None, status: str, **rec: Any) -> None:
        log_call({"run_id": self.run_id, "purpose": purpose, "model": self.model, "batch": False,
                  "effort": effort, "status": status, **rec})

    @staticmethod
    def check_user_content(user: str | list[dict[str, Any]]) -> None:
        """A user turn is a string, or a non-empty list of text and image blocks."""
        if isinstance(user, str):
            return
        if not isinstance(user, list) or not user:
            raise TypeError("user must be a string or a non-empty list of content blocks")
        for b in user:
            if not isinstance(b, dict) or b.get("type") not in ("text", "image"):
                raise TypeError(f"unsupported content block: {b!r:.80}")

    def json_reply(self, *, system: str, user: str | list[dict[str, Any]], max_tokens: int = 4096,
                   effort: str | None = None, purpose: str = "",
                   extra_messages: list[dict] | None = None,
                   output_schema: dict[str, Any] | None = None) -> CallResult:
        """One call whose reply must be a JSON object. Raises LLMRefusal,
        LLMTruncated, LLMBadJSON (after logging and counting the cost), or the
        SDK's own error for HTTP failures (logged with cost 0)."""
        self.check_user_content(user)
        images = 0 if isinstance(user, str) else sum(b["type"] == "image" for b in user)
        messages = [{"role": "user", "content": user}] + (extra_messages or [])
        sys_blocks = self.system_blocks(system)
        oc: dict[str, Any] = {"effort": effort} if effort else {}
        if output_schema is not None:
            oc["format"] = {"type": "json_schema", "schema": output_schema}
        kw: dict[str, Any] = {"output_config": oc} if oc else {}
        try:
            counted = self.sdk.messages.count_tokens(model=self.model, system=sys_blocks,
                                                     messages=messages, **kw)
        except Exception as e:
            self._log(purpose, effort, "http_error", call="count_tokens", cost_usd=0.0,
                      http_status=getattr(e, "status_code", None), error=str(e)[:500])
            raise
        self.guard.check(worst_case_usd(self.model, counted.input_tokens, max_tokens), purpose)
        try:
            resp = self.sdk.messages.create(model=self.model, max_tokens=max_tokens,
                                            system=sys_blocks, messages=messages, **kw)
        except Exception as e:
            self.last_usage = None
            self._log(purpose, effort, "http_error", call="create", cost_usd=0.0,
                      http_status=getattr(e, "status_code", None),
                      request_id=getattr(e, "request_id", None), error=str(e)[:500])
            raise
        u = resp.usage
        usage = {
            "input_tokens": u.input_tokens or 0,
            "output_tokens": u.output_tokens or 0,
            "cache_read_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cache_write_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
        }
        self.last_usage = usage
        cost = cost_usd(self.model, **usage)
        self.guard.add(cost)
        rid = getattr(resp, "_request_id", None)
        text = next((b.text for b in resp.content if b.type == "text"), "")
        status, err, data = "ok", None, None
        if resp.stop_reason == "refusal":
            details = getattr(resp, "stop_details", None)
            status, err = "refusal", LLMRefusal(f"model declined ({getattr(details, 'category', None)})")
        elif resp.stop_reason == "max_tokens":
            status, err = "max_tokens", LLMTruncated(
                f"the reply was cut off at max_tokens={max_tokens}; raise max_tokens")
        else:
            try:
                data = parse_json_reply(text)
            except LLMBadJSON as e:
                status, err = "bad_json", e
        self._log(purpose, effort, status, request_id=rid, stop_reason=resp.stop_reason,
                  **({"images": images} if images else {}), **usage, cost_usd=round(cost, 6))
        if err is not None:
            err.raw_text = text            # type: ignore[attr-defined]
            err.cost_usd = cost            # type: ignore[attr-defined]
            raise err
        return CallResult(data=data, cost_usd=cost, usage=usage, request_id=rid, raw_text=text)
