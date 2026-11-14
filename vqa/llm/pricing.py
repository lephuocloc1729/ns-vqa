"""Token prices (USD per million tokens), first-party Claude API.

Source: Anthropic price list as cached in the claude-api reference on 2026-11-03.
Re-check https://platform.claude.com/docs/en/about-claude/pricing before relying
on these for budgeting; update PRICES_AS_OF when you do.

Cache writes (5-minute TTL) cost 1.25x the input price. Cache reads use the listed
price where Anthropic publishes one (Opus 5.5: $0.20), else 0.1x input.
The Batch API halves every rate.
"""

from __future__ import annotations

from dataclasses import dataclass

PRICES_AS_OF = "2026-11-03"
BATCH_DISCOUNT = 0.5


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    # Haiku 5.5 charges more for prompts over 100K tokens.
    long_threshold: int | None = None
    long_input: float | None = None
    long_output: float | None = None

    @property
    def cache_write(self) -> float:
        return self.input * 1.25


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(input=4.00, output=20.00, cache_read=0.20),
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_read=0.10),
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_read=0.01,
                              long_threshold=100_000, long_input=0.50, long_output=2.50),
}


def price_for(model: str) -> Price:
    try:
        return PRICES[model]
    except KeyError:
        raise KeyError(f"no price for {model!r}; add it to vqa/llm/pricing.py") from None


def cost_usd(model: str, *, input_tokens: int = 0, output_tokens: int = 0,
             cache_read_tokens: int = 0, cache_write_tokens: int = 0,
             batch: bool = False) -> float:
    """Cost of one request from its usage numbers."""
    p = price_for(model)
    prompt = input_tokens + cache_read_tokens + cache_write_tokens
    inp, out = p.input, p.output
    if p.long_threshold and prompt > p.long_threshold:
        inp, out = p.long_input, p.long_output
    total = (input_tokens * inp + output_tokens * out
             + cache_read_tokens * p.cache_read + cache_write_tokens * inp * 1.25) / 1e6
    return total * (BATCH_DISCOUNT if batch else 1.0)


def worst_case_usd(model: str, prompt_tokens: int, max_tokens: int, batch: bool = False) -> float:
    """Upper bound for one request: the whole prompt written to cache, full max_tokens out."""
    return cost_usd(model, cache_write_tokens=prompt_tokens, output_tokens=max_tokens, batch=batch)
