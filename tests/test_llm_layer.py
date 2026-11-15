"""API layer, offline: pricing, spend guard, usage log, client (with a fake SDK)."""

import json
from types import SimpleNamespace

import pytest

from vqa.llm.client import LLMBadJSON, LLMClient, LLMRefusal, LLMTruncated, parse_json_reply
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


def test_json_call_logs_and_parses(tmp_log):
    sdk = FakeSDK([('{"ok": true}', "end_turn", {})])
    c = LLMClient(model="claude-haiku-5-5", sdk=sdk, guard=SpendGuard(1.0))
    r = c.json_reply(system="SPEC", user="Q", effort="low", purpose="parse")
    assert r.data == {"ok": True} and r.cost_usd > 0
    req = sdk.created[0]
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert req["output_config"] == {"effort": "low"}              # no JSON schema is sent
    rec = json.loads(tmp_log.read_text().splitlines()[0])
    assert rec["purpose"] == "parse" and rec["cache_read_tokens"] == 900 and rec["status"] == "ok"
    assert rec["cost_usd"] == pytest.approx(r.cost_usd, abs=1e-6)
    assert "api_key" not in json.dumps(rec).lower()


def test_effort_left_out_means_model_default():
    sdk = FakeSDK([("{}", "end_turn", {})])
    LLMClient(model="claude-haiku-5-5", sdk=sdk).json_reply(system="S", user="Q")
    assert "output_config" not in sdk.created[0]


def test_guard_stops_before_sending():
    sdk = FakeSDK([("{}", "end_turn", {})], prompt_tokens=10_000_000)
    c = LLMClient(model="claude-opus-5-5", sdk=sdk, guard=SpendGuard(2.0))
    with pytest.raises(SpendLimitExceeded):
        c.json_reply(system="S", user="Q")
    assert sdk.created == []


def test_refusal_and_truncation_raise(tmp_log):
    c = LLMClient(model="claude-haiku-5-5", sdk=FakeSDK([("", "refusal", {})]))
    with pytest.raises(LLMRefusal):
        c.json_reply(system="S", user="Q")
    c = LLMClient(model="claude-haiku-5-5", sdk=FakeSDK([('{"a":', "max_tokens", {})]))
    with pytest.raises(LLMTruncated, match="cut off at max_tokens"):
        c.json_reply(system="S", user="Q")
    assert [json.loads(l)["status"] for l in tmp_log.read_text().splitlines()] == \
        ["refusal", "max_tokens"]


@pytest.mark.parametrize("text,data", [
    ('{"a": 1}', {"a": 1}),
    ('\n  {"a": 1}  \n', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('```json\n{\n  "a": [1, 2]\n}\n```\n', {"a": [1, 2]}),
])
def test_reply_parsing_accepts_bare_or_fenced_objects(text, data):
    assert parse_json_reply(text) == data


@pytest.mark.parametrize("text,msg", [
    ('Sure! {"a": 1}', "only a JSON object"),
    ('{"a": 1} Hope this helps.', "not valid JSON"),
    ('```\n{"a": 1}\n```', "only a JSON object"),            # a fence must say json
    ('```json\n{"a": 1}\n``` and more', "only a JSON object"),
    ('{"a": ', "not valid JSON"),
    ("[1, 2]", "only a JSON object"),
    ("", "only a JSON object"),
])
def test_reply_parsing_rejects_everything_else(text, msg):
    with pytest.raises(LLMBadJSON, match=msg):
        parse_json_reply(text)


def test_bad_json_is_billed_logged_and_raised(tmp_log):
    c = LLMClient(model="claude-haiku-5-5", sdk=FakeSDK([("not json", "end_turn", {})]))
    with pytest.raises(LLMBadJSON) as e:
        c.json_reply(system="S", user="Q")
    assert e.value.raw_text == "not json" and e.value.cost_usd > 0
    rec = json.loads(tmp_log.read_text())
    assert rec["status"] == "bad_json" and rec["cost_usd"] > 0


def test_http_errors_are_logged_with_zero_cost(tmp_log):
    class BadRequest(Exception):
        status_code, request_id = 400, "req_x"

    class Failing(FakeSDK):
        def create(self, **kw):
            raise BadRequest("The compiled grammar is too large")

    c = LLMClient(model="claude-opus-5-5", sdk=Failing([]), guard=SpendGuard(1.0))
    with pytest.raises(BadRequest):
        c.json_reply(system="S", user="Q", purpose="gold-intent draft")
    rec = json.loads(tmp_log.read_text())
    assert rec["status"] == "http_error" and rec["cost_usd"] == 0.0 and rec["http_status"] == 400
    assert rec["request_id"] == "req_x" and "grammar" in rec["error"] and c.guard.spent == 0
