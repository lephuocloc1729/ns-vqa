"""API layer, offline: pricing, spend guard, usage log, client (with a fake SDK)."""

import json
from types import SimpleNamespace

import pytest

from vqa.llm.client import LLMClient, LLMRefusal, LLMTruncated
from vqa.llm.pricing import cost_usd, worst_case_usd
from vqa.llm.spend import SpendGuard, SpendLimitExceeded


class FakeSDK:
    """Stands in for anthropic.Anthropic: records requests, returns canned replies."""

    def __init__(self, replies, prompt_tokens=1000):
        self.replies = list(replies)
        self.prompt_tokens = prompt_tokens
        self.created = []
        self.messages = self

    def count_tokens(self, **kw):
        return SimpleNamespace(input_tokens=self.prompt_tokens)

    def create(self, **kw):
        self.created.append(kw)
        text, stop, usage = self.replies.pop(0)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)], stop_reason=stop,
            stop_details=None, _request_id="req_test",
            usage=SimpleNamespace(**{"input_tokens": 100, "output_tokens": 50,
                                     "cache_read_input_tokens": 900,
                                     "cache_creation_input_tokens": 0, **usage}))


@pytest.fixture(autouse=True)
def tmp_log(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path))
    return tmp_path / "api_calls.jsonl"


def test_prices():
    assert cost_usd("claude-opus-5-5", input_tokens=1_000_000) == pytest.approx(4.0)
    assert cost_usd("claude-opus-5-5", output_tokens=1_000_000, batch=True) == pytest.approx(10.0)
    assert cost_usd("claude-opus-5-5", cache_read_tokens=1_000_000) == pytest.approx(0.20)
    assert cost_usd("claude-haiku-5-5", input_tokens=50_000) == pytest.approx(0.005)
    # Haiku 5.5 charges $0.50/M input over 100K prompt tokens
    assert cost_usd("claude-haiku-5-5", input_tokens=200_000) == pytest.approx(0.10)
    assert worst_case_usd("claude-haiku-5-5", 10_000, 1000) == pytest.approx(
        (10_000 * 0.125 + 1000 * 0.5) / 1e6)
    with pytest.raises(KeyError):
        cost_usd("claude-unknown", input_tokens=1)


def test_spend_guard(monkeypatch):
    g = SpendGuard(1.0)
    g.check(0.6)
    g.add(0.6)
    with pytest.raises(SpendLimitExceeded):
        g.check(0.5)
    monkeypatch.setenv("VQA_SPEND_LIMIT", "0.25")
    assert SpendGuard().limit == 0.25
    monkeypatch.delenv("VQA_SPEND_LIMIT")
    assert SpendGuard().limit == 2.0


def test_structured_call_logs_and_parses(tmp_log):
    sdk = FakeSDK([('{"ok": true}', "end_turn", {})])
    c = LLMClient(model="claude-haiku-5-5", sdk=sdk, guard=SpendGuard(1.0))
    r = c.structured(system="SPEC", user="Q", schema={"type": "object"}, effort="low",
                     purpose="parse")
    assert r.data == {"ok": True} and r.cost_usd > 0
    req = sdk.created[0]
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert req["output_config"] == {"format": {"type": "json_schema", "schema": {"type": "object"}},
                                    "effort": "low"}
    rec = json.loads(tmp_log.read_text().splitlines()[0])
    assert rec["purpose"] == "parse" and rec["cache_read_tokens"] == 900
    assert rec["cost_usd"] == pytest.approx(r.cost_usd, abs=1e-6)
    assert "api_key" not in json.dumps(rec).lower()


def test_effort_left_out_means_model_default():
    sdk = FakeSDK([("{}", "end_turn", {})])
    LLMClient(model="claude-haiku-5-5", sdk=sdk).structured(system="S", user="Q", schema={})
    assert "effort" not in sdk.created[0]["output_config"]


def test_guard_stops_before_sending():
    sdk = FakeSDK([("{}", "end_turn", {})], prompt_tokens=10_000_000)
    c = LLMClient(model="claude-opus-5-5", sdk=sdk, guard=SpendGuard(2.0))
    with pytest.raises(SpendLimitExceeded):
        c.structured(system="S", user="Q", schema={})
    assert sdk.created == []


def test_refusal_and_truncation_raise():
    c = LLMClient(model="claude-haiku-5-5", sdk=FakeSDK([("", "refusal", {})]))
    with pytest.raises(LLMRefusal):
        c.structured(system="S", user="Q", schema={})
    c = LLMClient(model="claude-haiku-5-5", sdk=FakeSDK([('{"a":', "max_tokens", {})]))
    with pytest.raises(LLMTruncated):
        c.structured(system="S", user="Q", schema={})
