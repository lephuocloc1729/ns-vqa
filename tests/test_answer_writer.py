"""Phase-4 item 1: the proof digest, the faithfulness guard, the template answer and
the answer writer (with a fake SDK; no API call). Scenes are the hand-written
train fixtures and hand-made digests modelled on train questions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter

from vqa.answer import prompt as answer_prompt
from vqa.answer.digest import build, to_text
from vqa.answer.faithfulness import (check, codes_in, is_true_false, leading_polarity,
                                     numbers_in)
from vqa.answer.template import VEHICLE_VI, template_answer, template_reply
from vqa.answer.writer import AnswerWriter
from vqa.llm.client import LLMClient
from vqa.llm.spend import SpendGuard, SpendLimitExceeded
from vqa.perception.wire import PLACEHOLDER
from vqa.reasoning.engine import Engine
from vqa.schemas import Program, SceneGraph, VehicleClass

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = sorted((ROOT / "tests" / "fixtures").glob("train_*.json"))
DATASET_DIR = Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural"))
TRAIN_FILE = DATASET_DIR / "dataset" / "train data" / "vlsp_2025_train.json"
_program = TypeAdapter(Program)



@pytest.fixture(scope="module")
def engine():
    return Engine()


@pytest.fixture(scope="module")
def digests(engine):
    """(fixture id, case index, digest) for every fixture case."""
    out = []
    for p in FIXTURES:
        fx = json.loads(p.read_text(encoding="utf-8"))
        scene = SceneGraph.model_validate(fx["scene"])
        for i, c in enumerate(fx["cases"]):
            out.append((p.stem, i, build(engine.answer(scene, _program.validate_python(c["program"])), scene)))
    return out


def _dg(stem, digests):
    return next(d for s, i, d in digests if s == stem and i == 0)


# ---------------------------------------------------------------- digest

def test_digest_keeps_signs_rules_and_citations_but_no_raw_goals(digests):
    d = _dg("train_1", digests)
    assert d["verdict"] == "value"
    assert [s["code"] for s in d["signs"]] == ["P.107a"]
    assert d["signs"][0]["name_vi"] and d["signs"][0]["plates"]
    assert {r["rule"] for r in d["rules"]} >= {"r_prohibition", "r_time_plate"}
    assert "QCVN 41:2024/BGTVT B.7a" in d["citations"]
    text = to_text(d)
    assert "veh(" not in text and "ctx(" not in text and "iv(" not in text


def test_digest_lists_clearing_signs_of_a_yes(digests):
    d = _dg("train_181", digests)
    assert d["verdict"] == "yes"
    assert {"s4", "s2"} <= {s["id"] for s in d["signs"]}
    assert {"sign_id": "s2", "truth": "false", "detail": "vehicle_not_covered"} in d["reasons"]


def test_digest_of_an_unreadable_sign_marks_it():
    scene = SceneGraph.model_validate({"scene_id": "t", "signs": [
        {"id": "s1", "code": "UNKNOWN", "shape": "circle", "border": "red", "background": "white",
         "position": {"rank_top_down": 1}}]})
    ans = Engine().answer(scene, _program.validate_python(
        {"intent": "permitted", "action": "turn_left", "vehicle": {"class": "car"}}))
    d = build(ans, scene)
    assert d["verdict"] == "unknown"
    assert d["signs"] == [{"id": "s1", "code": "UNKNOWN", "readable": False}]


# ---------------------------------------------------------------- guard

YES = {"verdict": "yes", "signs": [{"id": "s4", "code": "P.103a", "readable": True,
                                    "name_vi": "Cấm xe ô tô", "plates": ["6:00-22:00"]}],
       "rules": [{"rule": "r_prohibition", "source": "QCVN 41:2024/BGTVT 22"}],
       "reasons": [{"sign_id": "s4", "truth": "true"}], "value": None,
       "citations": ["QCVN 41:2024/BGTVT B.3", "QCVN 41:2024/BGTVT 22"]}
Q = "Đường này có cấm ô tô từ 6:00 đến 22:00 không?"


def reply(text, **kw):
    return {"verdict": "yes", "answer": text, "cited_signs": ["s4"], "cited_rules": ["r_prohibition"], **kw}


def test_a_faithful_reply_passes():
    assert check(reply("Có. Biển P.103a (Cấm xe ô tô) có biển phụ 6:00-22:00."), YES, Q) == []


def test_the_verdict_must_be_the_engines():
    errs = check(reply("Có.", verdict="no"), YES, Q)
    assert any("verdict must be 'yes'" in e for e in errs)


def test_cited_signs_and_rules_must_be_in_the_proof():
    errs = check(reply("Có.", cited_signs=["s9"], cited_rules=["r_made_up"]), YES, Q)
    assert any("cited_signs not in the proof: s9" in e for e in errs)
    assert any("cited_rules not in the proof: r_made_up" in e for e in errs)


def test_an_invented_code_fails():
    errs = check(reply("Có. Biển P.104 cấm ô tô."), YES, Q)
    assert any("P.104" in e for e in errs)


def test_an_invented_number_fails_but_question_numbers_pass():
    assert any("50" in e for e in check(reply("Có. Tốc độ tối đa 50 km/h."), YES, Q))
    assert check(reply("Có, từ 6 giờ đến 22 giờ ô tô bị cấm."), YES, Q) == []


def test_decimal_comma_matches_the_proof_value():
    d = {**YES, "signs": [{**YES["signs"][0], "value": 1.25}]}
    assert check(reply("Có. Xe trên 1,25 tấn bị cấm."), d, "Xe tải có bị cấm không?") == []
    assert check(reply("Có. Xe trên 1,5 tấn bị cấm."), d, "Xe tải có bị cấm không?") != []


def test_true_false_questions_start_with_dung_or_sai():
    q = "Ô tô bị cấm đi vào đường này từ 6:00 đến 22:00, đúng hay sai?"
    assert is_true_false(q) and not is_true_false(Q)
    assert check(reply("Đúng. Biển P.103a cấm ô tô."), YES, q) == []
    assert any("starting with 'Đúng'" in e for e in check(reply("Có. Biển P.103a cấm ô tô."), YES, q))
    no = {**YES, "verdict": "no"}
    assert check(reply("Sai.", verdict="no"), no, q) == []


def test_yes_no_answers_open_with_the_verdicts_polarity():
    assert any("opens with a no word" in e for e in check(reply("Không. Biển P.103a."), YES, Q))
    assert any("starts with its verdict word" in e for e in check(reply("Biển P.103a cấm ô tô."), YES, Q))
    assert leading_polarity("Không được.") is False and leading_polarity("Được đi.") is True
    assert leading_polarity("Làn 1.") is None


def test_unknown_must_not_open_with_a_yes_or_no_word():
    unk = {**YES, "verdict": "unknown"}
    assert check(reply("Chưa xác định được: còn tùy giờ.", verdict="unknown"), unk, Q) == []
    assert check(reply("Không xác định được.", verdict="unknown"), unk, Q) != []


def test_the_reply_shape_is_checked():
    assert check("Có", YES, Q) == ["the reply must be a JSON object"]
    errs = check({"verdict": "yes", "answer": "", "extra": 1}, YES, Q)
    assert any("missing keys" in e for e in errs) and any("unexpected keys: extra" in e for e in errs)
    assert any("non-empty" in e for e in errs)


def test_code_and_number_extraction():
    assert codes_in("biển p.127b và IE.452, điều B.25") == {"P.127b", "IE.452", "B.25"}
    assert {6.0, 30.0, 1.5} <= numbers_in("6:30, 1,5 tấn")


# ---------------------------------------------------------------- template

def test_vehicle_names_cover_every_class():
    assert set(VEHICLE_VI) == {c.value for c in VehicleClass}


def test_template_passes_the_guard_on_every_fixture(digests):
    for stem, i, d in digests:
        for q in ("Câu hỏi?", "Câu hỏi, đúng hay sai?"):
            r = template_reply(d, q)
            assert check(r, d, q) == [], (stem, i, r)


def test_template_wording(digests):
    assert template_answer(_dg("train_1", digests), "?").startswith(
        "Từ 6:30 đến 8:00 và từ 16:30 đến 18:30.")
    assert template_answer(_dg("train_181", digests), Q).startswith("Có. Căn cứ: biển P.103a")
    assert template_answer(_dg("train_182", digests), "?").startswith("Không.")
    assert template_answer(_dg("train_217", digests), "?").startswith("Làn 1.")
    assert template_answer(_dg("train_92", digests), "?").startswith("2 tấn.")


@pytest.mark.parametrize("d, start", [
    ({"verdict": "unknown", "signs": [{"id": "s1", "code": "UNKNOWN", "readable": False}],
      "rules": [], "reasons": [], "citations": [], "value": None, "uncertain_signs": ["s1"]},
     "Chưa xác định được, vì có biển chưa đọc được."),
    ({"verdict": "uncertain", "signs": [], "rules": [], "reasons": [], "citations": [],
      "value": {}, "uncertain_signs": ["s2"]}, "Chưa chắc chắn: biển s2"),
    ({"verdict": "value", "signs": [], "rules": [], "reasons": [], "citations": [],
      "value": [{"sign_id": "s1", "code": "P.131a", "name_vi": "Cấm đỗ xe", "known": True}]},
     "Cấm đỗ xe (P.131a)."),
    ({"verdict": "value", "signs": [], "rules": [], "reasons": [], "citations": [],
      "value": {"kind": "max", "lane": None, "limit": 60, "sign_id": "s1", "conditional": []}},
     "Tốc độ tối đa 60 km/h."),
    ({"verdict": "value", "signs": [], "rules": [], "reasons": [], "citations": [],
      "value": {"banned": ["motorbike", "truck"], "conditional": [], "per_class": {}}},
     "Xe máy và xe ô tô tải."),
    ({"verdict": "value", "signs": [], "rules": [], "reasons": [], "citations": [],
      "value": {"bans": [], "banned": False}}, "Không bị cấm vào khung giờ nào."),
])
def test_template_for_other_verdicts_and_values(d, start):
    text = template_answer(d, "Câu hỏi?")
    assert text.startswith(start), text
    assert check(template_reply(d, "Câu hỏi?"), d, "Câu hỏi?") == []


# ---------------------------------------------------------------- prompt

def test_examples_are_train_only_and_pass_the_guard():
    exs = answer_prompt.examples("v1")
    assert exs and all(e["question_id"].startswith("train_") for e in exs)
    for e in exs:
        assert e["true_false"] == is_true_false(e["question"])
        assert check(e["reply"], e["engine"], e["question"]) == [], e["question_id"]


def test_examples_use_the_datasets_exact_question_text():
    if not TRAIN_FILE.exists():
        pytest.skip("dataset not available")
    train = {x["id"]: x for x in json.loads(TRAIN_FILE.read_text(encoding="utf-8"))}
    for e in answer_prompt.examples("v1"):
        assert e["question"] == train[e["question_id"]]["question"]


def test_v1_is_pinned():
    pid = answer_prompt.prompt_id("v1")
    assert pid == "answer/v1@" + V1_SHA[:12], f"prompt v1 changed: {pid}; make a new version"


# Pinned (plan item 1): a prompt change is a new version under prompts/answer/.
V1_SHA = "aed34f731e7f9340e6b6fc3c687fb2c21cb18d7c9fa39d98858ff3226cd675fa"


def test_the_prompt_is_text_only_and_the_same_for_every_question():
    sys1 = answer_prompt.system_prompt("v1")
    assert "image" not in answer_prompt.user_text("Q?", YES, False).lower()
    assert sys1 == answer_prompt.system_prompt("v1")
    assert answer_prompt.config("v1")["model"] == "claude-haiku-5-5"      # D1


# ---------------------------------------------------------------- writer (fake SDK)

class FakeSDK:
    def __init__(self, replies):
        self.replies, self.created = list(replies), []
        self.messages = self

    def count_tokens(self, **kw):
        return SimpleNamespace(input_tokens=3000)

    def create(self, **kw):
        self.created.append(kw)
        text, stop = self.replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop,
                               stop_details=SimpleNamespace(category="test"), _request_id="req_t",
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=80,
                                                     cache_read_input_tokens=2000,
                                                     cache_creation_input_tokens=0))


@pytest.fixture(autouse=True)
def tmp_log(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))


def writer(replies, limit=1.0):
    sdk = FakeSDK(replies)
    return AnswerWriter(llm=LLMClient(model="claude-haiku-5-5", sdk=sdk, guard=SpendGuard(limit))), sdk


GOOD = json.dumps({"verdict": "yes", "answer": "Có. Biển P.103a (Cấm xe ô tô) có biển phụ 6:00-22:00.",
                   "cited_signs": ["s4"], "cited_rules": ["r_prohibition"]}, ensure_ascii=False)
WRONG_VERDICT = json.dumps({"verdict": "no", "answer": "Không.", "cited_signs": [], "cited_rules": []})


def test_first_try():
    w, sdk = writer([(GOOD, "end_turn")])
    r = w.write_digest(Q, YES)
    assert (r.status, r.attempts, r.verdict) == ("first_try", 1, "yes")
    assert r.text.startswith("Có.") and r.cited_signs == ["s4"] and r.cost_usd > 0
    msgs = sdk.created[0]["messages"]
    assert len(msgs) == 1 and isinstance(msgs[0]["content"], str)       # text only, no image
    assert "Engine result:" in msgs[0]["content"]


def test_a_guard_failure_is_regenerated_with_the_error_only():
    w, sdk = writer([(WRONG_VERDICT, "end_turn"), (GOOD, "end_turn")])
    r = w.write_digest(Q, YES)
    assert (r.status, r.attempts) == ("regenerated", 2)
    retry = sdk.created[1]["messages"]
    assert retry[1] == {"role": "assistant", "content": PLACEHOLDER}
    assert "verdict must be 'yes'" in retry[2]["content"]
    assert WRONG_VERDICT not in json.dumps(retry, ensure_ascii=False)


def test_bad_json_then_good():
    w, _ = writer([("Here you go: {}", "end_turn"), (GOOD, "end_turn")])
    assert w.write_digest(Q, YES).status == "regenerated"


def test_two_failures_give_the_template():
    w, sdk = writer([(WRONG_VERDICT, "end_turn"), (WRONG_VERDICT, "end_turn")])
    r = w.write_digest(Q, YES)
    assert (r.status, r.attempts, r.verdict) == ("template", 2, "yes")
    assert r.text == template_answer(YES, Q) and len(r.errors) == 2 and len(sdk.created) == 2


def test_a_refusal_gives_the_template_without_retry():
    w, sdk = writer([("", "refusal")])
    r = w.write_digest(Q, YES)
    assert (r.status, r.attempts) == ("template", 1) and len(sdk.created) == 1


def test_the_spend_guard_stops_the_writer():
    w, _ = writer([(GOOD, "end_turn")], limit=0.000001)
    with pytest.raises(SpendLimitExceeded):
        w.write_digest(Q, YES)


def test_write_builds_the_digest_from_an_engine_answer(engine):
    fx = json.loads((ROOT / "tests" / "fixtures" / "train_181.json").read_text(encoding="utf-8"))
    scene = SceneGraph.model_validate(fx["scene"])
    ans = engine.answer(scene, _program.validate_python(fx["cases"][0]["program"]))
    w, _ = writer([(GOOD, "end_turn")])
    assert w.write(Q, ans, scene).status == "first_try"
