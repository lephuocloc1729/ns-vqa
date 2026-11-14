"""Thin wrapper around the Anthropic SDK for structured-output calls.

- The API key comes from the environment (ANTHROPIC_API_KEY, or any credential
  source the SDK resolves); it is never passed in code or written anywhere.
- Before a request, its prompt is counted (messages.count_tokens) and the worst
  case (whole prompt as a cache write, full max_tokens out) is checked against
  the SpendGuard.
- After it, usage and cost are logged to logs/api_calls.jsonl.
- refusal and max_tokens stop reasons raise, since the output may not match the
  schema then.
"""

from __future__ import annotations

import json
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

    def __post_init__(self) -> None:
        if self.sdk is None:
            import anthropic
            self.sdk = anthropic.Anthropic()

    @staticmethod
    def system_blocks(stable: str) -> list[dict[str, Any]]:
        """The frozen system prompt as one cached text block."""
        return [{"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}}]

    def output_config(self, schema: dict[str, Any], effort: str | None) -> dict[str, Any]:
        cfg: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
        if effort:
            cfg["effort"] = effort
        return cfg

    def structured(self, *, system: str, user: str, schema: dict[str, Any],
                   max_tokens: int = 4096, effort: str | None = None,
                   purpose: str = "", extra_messages: list[dict] | None = None) -> CallResult:
        messages = [{"role": "user", "content": user}] + (extra_messages or [])
        sys_blocks = self.system_blocks(system)
        out_cfg = self.output_config(schema, effort)
        counted = self.sdk.messages.count_tokens(model=self.model, system=sys_blocks,
                                                 messages=messages, output_config=out_cfg)
        self.guard.check(worst_case_usd(self.model, counted.input_tokens, max_tokens), purpose)

        resp = self.sdk.messages.create(model=self.model, max_tokens=max_tokens, system=sys_blocks,
                                        messages=messages, output_config=out_cfg)
        u = resp.usage
        usage = {
            "input_tokens": u.input_tokens or 0,
            "output_tokens": u.output_tokens or 0,
            "cache_read_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cache_write_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
        }
        cost = cost_usd(self.model, **usage)
        self.guard.add(cost)
        rid = getattr(resp, "_request_id", None)
        log_call({"run_id": self.run_id, "purpose": purpose, "model": self.model, "batch": False,
                  "request_id": rid, "stop_reason": resp.stop_reason, "effort": effort,
                  **usage, "cost_usd": round(cost, 6)})

        if resp.stop_reason == "refusal":
            details = getattr(resp, "stop_details", None)
            raise LLMRefusal(f"model declined ({getattr(details, 'category', None)})")
        if resp.stop_reason == "max_tokens":
            raise LLMTruncated(f"output cut at max_tokens={max_tokens}")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"output is not JSON: {e}") from e
        return CallResult(data=data, cost_usd=cost, usage=usage, request_id=rid, raw_text=text)
