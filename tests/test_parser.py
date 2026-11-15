"""Question parser, offline: wire schema, conversion and defaults, validator, the
retry loop (with a fake SDK), and few-shot provenance."""

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from vqa.llm.client import LLMClient
from vqa.llm.spend import SpendGuard
from vqa.parsing import validator
from vqa.parsing.claude_parser import ClaudeParser
from vqa.parsing.prompt import examples, system_prompt
from pydantic import ValidationError

from vqa.parsing.wire import WParse, explain, json_schema, to_query
from vqa.schemas import QueryProgram

ROOT = Path(__file__).resolve().parent.parent


class FakeSDK:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.created = []
        self.messages = self

    def count_tokens(self, **kw):
        return SimpleNamespace(input_tokens=12_000)

    def create(self, **kw):
        self.created.append(kw)
        out = self.outputs.pop(0)
        stop = "refusal" if out == "REFUSE" else "end_turn"
        text = "" if out == "REFUSE" else json.dumps(out)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)],
                               stop_reason=stop, stop_details=None, _request_id="r",
                               usage=SimpleNamespace(input_tokens=200, output_tokens=150,
                                                     cache_read_input_tokens=11_800,
                                                     cache_creation_input_tokens=0))


@pytest.fixture(autouse=True)
def tmp_log(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path))


def parser(outputs, engine, **kw):
    sdk = FakeSDK(outputs)
    llm = LLMClient(model="claude-haiku-5-5", sdk=sdk, guard=SpendGuard(1.0))
    return ClaudeParser(llm=llm, engine=engine, context_year=2026, **kw), sdk


# ---------------------------------------------------------------- schema

def test_wire_schema_is_strict_and_not_recursive():
    s = json_schema()
    defs = s["$defs"]
    refs = {k: set(re.findall(r"#/\$defs/(\w+)", json.dumps(v))) for k, v in defs.items()}

    def cyclic(start):
        stack, seen = list(refs[start]), set()
        while stack:
            r = stack.pop()
            if r == start:
                return True
            if r not in seen:
                seen.add(r)
                stack += list(refs[r])
        return False

    assert not [k for k in defs if cyclic(k)]

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "object" and "properties" in n:
                assert n["additionalProperties"] is False
                assert set(n["required"]) == set(n["properties"])
            assert "default" not in n
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(s)
    text = json.dumps(s)
    assert "every_vehicle" in text
    # codes and meanings are strings, not enums: as enums the API's grammar was too large
    assert "no_overtaking" not in text and "W.221a" not in text
    enums = re.findall(r'"enum": \[([^\]]*)\]', text)
    assert max(e.count(",") + 1 for e in enums) < 50
    assert len(text) < 20_000


def test_unknown_code_or_meaning_gives_a_short_error():
    for bad, word in ((({"intent": "is_sign", "sign": {"only": True}, "code": "P.999"}), "P.999"),
                      (({"intent": "meaning", "sign": {"meaning": "nope"}}), "nope")):
        with pytest.raises(ValidationError) as e:
            WParse.model_validate({"program": bad})
        msg = explain(e.value)
        assert word in msg and "catalog" in msg and len(msg) < 300
    WParse.model_validate({"program": {"intent": "is_sign", "sign": {"only": True}, "code": "P.102"}})


# ---------------------------------------------------------------- conversion

def test_defaults_year_and_vehicle_recorded():
    w = WParse.model_validate({"program": {"intent": "permitted", "action": "park",
                                           "when": {"day": 5, "month": 11}}})
    q = to_query(w, 2026)
    assert q.program.when.date.isoformat() == "2026-11-05"
    assert q.program.vehicle.cls.value == "motor_vehicle"
    assert q.defaults_applied == ["vehicle", "year"]


def test_no_defaults_when_given_or_not_needed():
    w = WParse.model_validate({"program": {"intent": "permitted", "action": "park",
                                           "vehicle": {"vehicle_class": "truck"},
                                           "when": {"day": 5, "month": 11, "year": 2025}}})
    assert to_query(w, 2026).defaults_applied == []
    m = WParse.model_validate({"program": {"intent": "meaning", "sign": {"only": True}}})
    assert to_query(m, 2026).defaults_applied == []


def test_out_of_scope_has_no_program():
    q = to_query(WParse.model_validate({"out_of_scope": True, "out_of_scope_reason": "traffic lights"}))
    assert q.out_of_scope and q.program is None and q.out_of_scope_reason == "traffic lights"
    with pytest.raises(ValueError):
        QueryProgram(out_of_scope=False)


def test_validator_rejects_every_vehicle_outside_claims(engine):
    w = WParse.model_validate({"program": {"intent": "lanes_for",
                                           "vehicle": {"vehicle_class": "every_vehicle"}}})
    errs = validator.check(to_query(w, 2026), engine)
    assert errs and "every_vehicle" in errs[0]


# ---------------------------------------------------------------- parser loop

GOOD = {"out_of_scope": False, "out_of_scope_reason": None, "missing_slots": [],
        "program": {"intent": "forbidden", "action": "enter",
                    "vehicle": {"vehicle_class": "car"},
                    "when": {"start": "06:00", "end": "22:00", "quantifier": "all"}}}
BAD = {"program": {"intent": "lanes_for", "vehicle": {"vehicle_class": "every_vehicle"}}}
OOS = {"out_of_scope": True, "out_of_scope_reason": "road markings", "program": None}


def test_parse_ok(engine):
    p, sdk = parser([GOOD], engine)
    r = p.parse("Xe ô tô không được phép di chuyển trong khung giờ từ 6:00 đến 22:00, đúng hay sai?")
    assert r.status == "ok" and r.attempts == 1 and r.query.program.intent == "forbidden"
    req = sdk.created[0]
    assert req["output_config"]["effort"] == "low"
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert req["system"][0]["text"] == system_prompt("v2")
    assert r.cost_usd > 0


def test_parse_out_of_scope(engine):
    p, _ = parser([OOS], engine)
    r = p.parse("Vạch kẻ đường liền nét là vạch gì?")
    assert r.status == "out_of_scope" and r.query.out_of_scope


def test_retry_once_with_the_error(engine):
    p, sdk = parser([BAD, GOOD], engine)
    r = p.parse("...")
    assert r.status == "ok" and r.attempts == 2
    retry_msgs = sdk.created[1]["messages"]
    assert retry_msgs[1]["role"] == "assistant"
    assert "every_vehicle" in retry_msgs[2]["content"]


def test_invalid_twice(engine):
    p, _ = parser([BAD, BAD], engine)
    r = p.parse("...")
    assert r.status == "invalid" and r.attempts == 2 and r.errors


def test_refusal_is_an_error(engine):
    p, _ = parser(["REFUSE"], engine)
    assert p.parse("...").status == "error"


def test_effort_is_configurable(engine):
    p, sdk = parser([GOOD], engine, effort=None)
    p.parse("...")
    assert "effort" not in sdk.created[0]["output_config"]


# ---------------------------------------------------------------- prompt and few-shots

def test_prompt_is_stable_and_has_the_catalog():
    s = system_prompt("v2")
    assert s == system_prompt.__wrapped__("v2")      # byte-identical rebuild (prompt cache)
    assert "P.104 | no_motorbikes" in s and "## Examples" in s


def test_fewshots_are_valid_programs(engine):
    for ex in examples("v2"):
        q = to_query(WParse.model_validate(ex["output"]), 2026)
        assert validator.check(q, engine) == [], ex["id"]


def test_fewshots_come_from_train_or_public_dev_only():
    split = json.loads((ROOT / "data" / "splits" / "public_split.json").read_text())
    holdout = set(split["public_holdout"]["questions"])
    dev = set(split["public_dev"]["questions"])
    ids = [ex["id"] for ex in examples("v2")]
    assert len(ids) == len(set(ids))
    for ex in examples("v2"):
        assert ex["split"] in ("train", "public_dev"), ex["id"]
        assert ex["id"] not in holdout and not ex["id"].startswith("private"), ex["id"]
        if ex["split"] == "public_dev":
            assert ex["id"] in dev, ex["id"]
    train = (Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural"))
             / "dataset" / "train data" / "vlsp_2025_train.json")
    if train.exists():
        rows = {t["id"]: t for t in json.loads(train.read_text(encoding="utf-8"))}
        for ex in examples("v2"):
            if ex["split"] == "train":
                assert ex["id"] in rows and rows[ex["id"]]["question"] == ex["question"], ex["id"]
