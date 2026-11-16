"""vqa/perception/scene.py with a fake SDK: plain JSON, one retry that sends only
the error, refusal / max_tokens without retry, spend guard, scene cache."""

import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from vqa.llm.client import LLMClient
from vqa.llm.spend import SpendGuard, SpendLimitExceeded
from vqa.perception.cache import SceneCache
from vqa.perception.scene import PLACEHOLDER, perceive

GOOD = json.dumps({"signs": [{"code": "P.127", "value": 50, "unit": "km/h", "shape": "circle",
                              "border": "red", "background": "white", "rank": 1, "side": "right"}],
                   "road": {"type": "urban"}, "vehicles": []})


class FakeSDK:
    def __init__(self, replies, prompt_tokens=11_000):
        self.replies, self.prompt_tokens, self.created = list(replies), prompt_tokens, []
        self.messages = self

    def count_tokens(self, **kw):
        return SimpleNamespace(input_tokens=self.prompt_tokens)

    def create(self, **kw):
        self.created.append(kw)
        text, stop = self.replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop,
                               stop_details=SimpleNamespace(category="test"), _request_id="req_t",
                               usage=SimpleNamespace(input_tokens=700, output_tokens=300,
                                                     cache_read_input_tokens=10_000,
                                                     cache_creation_input_tokens=0))


@pytest.fixture(autouse=True)
def tmp_log(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))


@pytest.fixture
def photo(tmp_path):
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (90, 120, 200)).save(buf, format="JPEG")
    p = tmp_path / "photo.jpg"
    p.write_bytes(buf.getvalue())
    return p


def run(photo, tmp_path, replies, **kw):
    sdk = FakeSDK(replies)
    client = LLMClient(model="claude-haiku-5-5", sdk=sdk, guard=kw.pop("guard", SpendGuard(1.0)))
    res = perceive(photo, client=client, cache=SceneCache(tmp_path / "cache"), **kw)
    return res, sdk


def test_a_good_reply_gives_a_scene_and_is_cached(photo, tmp_path):
    res, sdk = run(photo, tmp_path, [(GOOD, "end_turn")])
    assert res.ok and not res.retried and not res.cache_hit and res.cost_usd > 0
    assert res.scene.signs[0].code == "P.127" and res.scene.scene_id == res.image_sha256[:12]
    req = sdk.created[0]
    assert req["messages"][0]["content"][0]["type"] == "image"
    assert req["output_config"] == {"effort": "medium"} and "format" not in req.get("output_config", {})
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert res.prompt_id.startswith("scene/v1@")


def test_bad_json_gets_one_retry_that_sends_only_the_error(photo, tmp_path):
    bad = "Here are the signs: " + GOOD
    res, sdk = run(photo, tmp_path, [(bad, "end_turn"), (GOOD, "end_turn")])
    assert res.ok and res.retried and len(sdk.created) == 2
    msgs = sdk.created[1]["messages"]
    assert msgs[1] == {"role": "assistant", "content": PLACEHOLDER}
    assert "not valid" in msgs[2]["content"] and "Here are the signs" not in json.dumps(msgs)


def test_a_failed_check_is_retried_and_the_retry_is_converted_in_final_mode(photo, tmp_path):
    wrong = json.dumps({"signs": [{"code": "P.999", "shape": "circle", "rank": 1}]})
    still_wrong = json.dumps({"signs": [{"code": "LOCAL", "shape": "rectangle", "rank": 1}]})
    res, sdk = run(photo, tmp_path, [(wrong, "end_turn"), (still_wrong, "end_turn")], rerun=False)
    assert "unknown sign code 'P.999'" in sdk.created[1]["messages"][2]["content"]
    assert res.ok and res.retried and res.scene.signs[0].code == "UNKNOWN"
    assert res.raw_codes == {"s1": "LOCAL"}


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_refusal_and_truncation_are_errors_without_retry(photo, tmp_path, stop):
    res, sdk = run(photo, tmp_path, [(GOOD, stop)])
    assert not res.ok and res.scene is None and len(sdk.created) == 1
    assert ("LLMRefusal" if stop == "refusal" else "LLMTruncated") in res.error
    assert not list((tmp_path / "cache").rglob("*.json"))            # errors aren't cached


def test_two_bad_replies_give_an_error(photo, tmp_path):
    res, sdk = run(photo, tmp_path, [("no json", "end_turn"), ("still none", "end_turn")])
    assert not res.ok and res.retried and len(sdk.created) == 2 and "after the retry" in res.error


def test_a_cache_hit_makes_no_call_and_ignores_the_file_name(photo, tmp_path):
    run(photo, tmp_path, [(GOOD, "end_turn")])
    renamed = tmp_path / "another_name.jpg"
    renamed.write_bytes(photo.read_bytes())
    res, sdk = run(renamed, tmp_path, [])
    assert res.ok and res.cache_hit and sdk.created == [] and res.cost_usd == 0
    assert res.scene.signs[0].code == "P.127"
    res2, sdk2 = run(photo, tmp_path, [(GOOD, "end_turn")], use_cache=False)   # eval runs
    assert len(sdk2.created) == 1 and not res2.cache_hit


def test_the_spend_guard_stops_before_the_call(photo, tmp_path):
    with pytest.raises(SpendLimitExceeded):
        run(photo, tmp_path, [(GOOD, "end_turn")], guard=SpendGuard(0.0001))


LOW = json.dumps({"signs": [{"code": "P.127", "value": 50, "unit": "km/h", "confidence": "low",
                             "shape": "circle", "border": "red", "background": "white", "rank": 1}]})
AGREE = json.dumps({"signs": [{"code": "P.127", "value": 50, "unit": "km/h", "confidence": "high",
                               "shape": "circle", "border": "red", "background": "white", "rank": 1}]})
DISAGREE = json.dumps({"signs": [{"code": "P.127", "value": 60, "unit": "km/h", "confidence": "medium",
                                  "shape": "circle", "border": "red", "background": "white", "rank": 1}]})


def test_a_low_sign_triggers_one_rerun_and_agreement_keeps_it(photo, tmp_path):
    res, sdk = run(photo, tmp_path, [(LOW, "end_turn"), (AGREE, "end_turn")])
    assert len(sdk.created) == 2 and sdk.created[1]["messages"] == sdk.created[0]["messages"]
    s = res.scene.signs[0]
    assert s.value == 50 and s.alternatives == [] and s.confidence.value == "high"
    assert any("re-run agrees" in i for i in res.issues)
    assert [r["pass"] for r in res.replies] == ["first", "rerun"]


def test_disagreement_becomes_an_alternative_and_a_cache_hit_replays_it(photo, tmp_path):
    res, sdk = run(photo, tmp_path, [(LOW, "end_turn"), (DISAGREE, "end_turn")])
    s = res.scene.signs[0]
    assert s.value == 50 and [(a.code, a.value) for a in s.alternatives] == [("P.127", 60)]
    hit, sdk2 = run(photo, tmp_path, [])
    assert hit.cache_hit and sdk2.created == []
    assert [(a.code, a.value) for a in hit.scene.signs[0].alternatives] == [("P.127", 60)]


def test_no_rerun_when_every_sign_is_confident(photo, tmp_path):
    res, sdk = run(photo, tmp_path, [(AGREE, "end_turn")])
    assert len(sdk.created) == 1 and res.issues == []
