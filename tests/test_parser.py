"""Question parser, offline: wire schema, conversion and defaults, validator, the
retry loop (with a fake SDK), and few-shot provenance."""

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from vqa.llm.client import LLMClient
from vqa.llm.pricing import cost_usd, worst_case_usd
from vqa.llm.spend import SpendGuard, SpendLimitExceeded
from vqa.parsing import validator
from vqa.parsing.claude_parser import ClaudeParser
from vqa.parsing.prompt import examples, system_prompt
from pydantic import ValidationError

from vqa.parsing.wire import WParse, explain, from_wire, to_query
from vqa.schemas import QueryProgram, Verdict

from conftest import articles, scene, sign

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
        if isinstance(out, Exception):
            raise out
        stop = {"REFUSE": "refusal", "MAXTOK": "max_tokens"}.get(out, "end_turn") \
            if isinstance(out, str) else "end_turn"
        if stop != "end_turn":
            text = '{"program": {"inte' if stop == "max_tokens" else ""
        else:
            text = out if isinstance(out, str) else json.dumps(out)   # str = raw reply text
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

def test_no_json_schema_is_sent(engine):
    # the API caps strict schemas at 24 optional / 16 union-typed parameters in total;
    # the DSL needs far more, so the reply is plain JSON checked by the wire models
    p, sdk = parser([GOOD], engine)
    p.parse("...")
    req = sdk.created[0]
    assert "format" not in req.get("output_config", {}) and "tools" not in req


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
    assert req["output_config"] == {"effort": "medium"}
    assert req["system"][0]["text"] == system_prompt("v6")
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
    assert "output_config" not in sdk.created[0]


# ---------------------------------------------------------------- prompt and few-shots

def test_prompt_is_stable_and_has_the_catalog():
    s = system_prompt("v6")
    assert s == system_prompt.__wrapped__("v6")      # byte-identical rebuild (prompt cache)
    assert "Reply with only the JSON object" in s and "required format" not in s
    assert '"W.207" covers its variants' in s and '"W.221"' not in s
    assert "P.104 | no_motorbikes" in s and "## Examples" in s


# Released prompt versions never change: a version is part of cache keys and results.
FROZEN_PROMPTS = {
    "v1": {"spec.md": "ef44908b291ebf1df92746bd83800c26c0169df1762f9b66105785777e21f257",
           "fewshot.jsonl": "b5fdcc0aef594f7776fcf707e355c9a4e5ba5e9b3e3aa4e8249785af8bd37770"},
    "v2": {"spec.md": "ef44908b291ebf1df92746bd83800c26c0169df1762f9b66105785777e21f257",
           "fewshot.jsonl": "f644a21c024865bf4bbe55c00a44542e6ded14d84a3dfc383421856f2a1c04a5"},
    "v3": {"spec.md": "235ea70bcfe685420a145e6cf7f0bbe671137c38ec4f210a17c76644978f1583",
           "fewshot.jsonl": "f644a21c024865bf4bbe55c00a44542e6ded14d84a3dfc383421856f2a1c04a5"},
    "v4": {"spec.md": "a51cc692eb41120595183bf1ebde5dfac805bfea223e1b71326ff3ce0ab1beb1",
           "fewshot.jsonl": "f644a21c024865bf4bbe55c00a44542e6ded14d84a3dfc383421856f2a1c04a5"},
    "v5": {"spec.md": "447471827b3df0f2f9d598f0a643685c6410cee81224042ed7ab86cc6eb0f91d",
           "fewshot.jsonl": "f644a21c024865bf4bbe55c00a44542e6ded14d84a3dfc383421856f2a1c04a5"},
    "v6": {"spec.md": "c3c78d024016d9e943ec8cfa94f4edbb08a2d44ac865491f05eee308cdc61028",
           "fewshot.jsonl": "f644a21c024865bf4bbe55c00a44542e6ded14d84a3dfc383421856f2a1c04a5"},
    "v7": {"spec.md": "05c471a0bedc379480ca61305fa78413ec05be5e6f9696c843b5103157f8a16c",
           "fewshot.jsonl": "3e967613d95d4b269da63218cf43972c0ed85e6bfcd89774dc3b881bd50b9c9f"},
    "v8": {"spec.md": "1a9cebdc2ad2663af8811baa764a3dd107f6ecea08ad21fe0c1b86987793d05c",
           "fewshot.jsonl": "3e967613d95d4b269da63218cf43972c0ed85e6bfcd89774dc3b881bd50b9c9f"},
    # phase 4.6: v9 is the frozen phase-4.5 parser (eval/frozen_phase45.json)
    "v9": {"spec.md": "de1cdbbef615de101ab136902b28f567e82c072ec8e52c1b2a405a9de9799403",
           "fewshot.jsonl": "d09c2fdc36edd54373381ae7497185a9f93243a45a9507dd2eeaf80ec8ccbb7f"},
}


@pytest.mark.parametrize("version", sorted(FROZEN_PROMPTS))
def test_released_prompt_versions_are_byte_identical(version):
    import hashlib
    for name, digest in FROZEN_PROMPTS[version].items():
        data = (ROOT / "prompts" / "parser" / version / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, f"{version}/{name} changed"


V5_RULES = ["`required` has no `sign` field", "does a vehicle seen in the photo break a rule",
            "It has no `vehicle` field", "xe thô sơ 3 bánh = cyclo", "kể cả xe ưu tiên",
            "no `category`", "use `sign: {}`", "a sign named in words, even in quotes, is `meaning`"]


def test_v5_is_v4_plus_spec_rules_with_the_same_fewshots():
    d4, d5 = (ROOT / "prompts" / "parser" / v for v in ("v4", "v5"))
    assert (d4 / "fewshot.jsonl").read_bytes() == (d5 / "fewshot.jsonl").read_bytes()
    spec = (d5 / "spec.md").read_text()
    assert all(r in spec for r in V5_RULES)
    old = (d4 / "spec.md").read_text().splitlines()
    assert sum(line not in old for line in spec.splitlines()) == 7   # 6 lines changed, 1 added


def test_v6_is_v5_with_the_sign_rules_narrowed():
    d5, d6 = (ROOT / "prompts" / "parser" / v for v in ("v5", "v6"))
    assert (d5 / "fewshot.jsonl").read_bytes() == (d6 / "fewshot.jsonl").read_bytes()
    a, b = ((d / "spec.md").read_text().splitlines() for d in (d5, d6))
    diff = [y for x, y in zip(a, b) if x != y]
    assert len(a) == len(b) and len(diff) == 2
    assert "except `meaning` and `is_sign`" in diff[0]
    assert "put that selector on every claim about the sign" in diff[1]


@pytest.mark.parametrize("version", ["v5", "v6", "v7", "v8", "v9", "v10"])
def test_spec_does_not_quote_gate_questions(version):
    # rules learned from public_dev errors must not carry a gate question's wording,
    # or it would act as an unexcluded few-shot
    public = (Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural"))
              / "dataset" / "public_test data" / "vlsp_2025_public_test.json")
    if not public.exists():
        pytest.skip("dataset not available")
    import eval.parser_eval as pe
    gate = {g["id"] for g in pe.gate_rows(pe.load_gold(), version)}
    spec = (ROOT / "prompts" / "parser" / version / "spec.md").read_text().lower()
    for q in json.loads(public.read_text(encoding="utf-8")):
        if q["id"] in gate:
            words = q["question"].lower().split()
            for i in range(len(words) - 5):
                assert " ".join(words[i:i + 6]) not in spec, q["id"]


@pytest.mark.parametrize("old,new,changed", [
    ("v2", "v3", "Reply with only the JSON object"),
    ("v3", "v4", '"W.207" covers its variants'),
])
def test_each_version_changes_one_spec_line(old, new, changed):
    d0, d1 = (ROOT / "prompts" / "parser" / v for v in (old, new))
    assert (d0 / "fewshot.jsonl").read_bytes() == (d1 / "fewshot.jsonl").read_bytes()
    a, b = ((d / "spec.md").read_text().splitlines() for d in (d0, d1))
    diff = [y for x, y in zip(a, b) if x != y]
    assert len(a) == len(b) and len(diff) == 1 and changed in diff[0]


@pytest.mark.parametrize("version", ["v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10"])
def test_fewshots_are_valid_programs(engine, version):
    for ex in examples(version):
        q = to_query(WParse.model_validate(ex["output"]), 2026)
        assert validator.check(q, engine) == [], ex["id"]


@pytest.mark.parametrize("version", ["v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10"])
def test_fewshots_come_from_train_or_public_dev_only(version):
    split = json.loads((ROOT / "data" / "splits" / "public_split.json").read_text())
    holdout = set(split["public_holdout"]["questions"])
    dev = set(split["public_dev"]["questions"])
    ids = [ex["id"] for ex in examples(version)]
    assert len(ids) == len(set(ids))
    for ex in examples(version):
        assert ex["split"] in ("train", "public_dev"), ex["id"]
        assert ex["id"] not in holdout and not ex["id"].startswith("private"), ex["id"]
        if ex["split"] == "public_dev":
            assert ex["id"] in dev, ex["id"]
    train = (Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural"))
             / "dataset" / "train data" / "vlsp_2025_train.json")
    if train.exists():
        rows = {t["id"]: t for t in json.loads(train.read_text(encoding="utf-8"))}
        for ex in examples(version):
            if ex["split"] == "train":
                assert ex["id"] in rows and rows[ex["id"]]["question"] == ex["question"], ex["id"]


@pytest.mark.parametrize("code", ["P.125", "W.207(a,b,c,d,e,f,g,h,i,k,l)",   # row codes
                                  "W.207c", "W.207l",                       # variants
                                  "W.207", "W.201",                          # family stems
                                  "W.221", "P.124", "P.106"])                # stems of separate rows
def test_sign_code_forms_accepted(code):
    w = WParse.model_validate({"program": {"intent": "is_sign", "sign": {"only": True},
                                           "code": code}})
    assert w.program.code == code                  # kept as written


@pytest.mark.parametrize("code,closest", [
    ("W.207j", ["W.207"]),                    # QCVN skips j in this family
    ("P.999", []),
    ("UNKNOWN", []),
])
def test_sign_code_rejected_with_closest_valid_codes(code, closest):
    with pytest.raises(ValidationError) as e:
        WParse.model_validate({"program": {"intent": "is_sign", "sign": {"only": True},
                                           "code": code}})
    msg = explain(e.value)
    assert code in msg and len(msg) < 300
    for c in closest:
        assert c in msg


@pytest.mark.parametrize("code", ["P.125", "W.207c", "W.207", "W.221", "P.124", "P.106",
                                  "W.207j", "P.999", "UNKNOWN", "P.107"])
def test_wire_accepts_exactly_what_the_catalog_resolves(engine, code):
    try:
        engine.catalog.codes_matching(code)
        resolves = True
    except KeyError:
        resolves = False
    try:
        WParse.model_validate({"program": {"intent": "is_sign", "sign": {"only": True},
                                           "code": code}})
        accepted = True
    except ValidationError:
        accepted = False
    assert accepted == resolves, code


def test_selector_stem_gives_the_same_verdict_as_the_exact_code(engine):
    sc = scene(sign("s1", "P.124c"), sign("s2", "P.127", value=50))
    answers = []
    for code in ("P.124", "P.124c"):
        w = WParse.model_validate({"program": {"intent": "forbidden", "action": "u_turn",
                                               "vehicle": {"vehicle_class": "car"},
                                               "sign": {"code": code}}})
        answers.append(engine.answer(sc, to_query(w, 2026)))
    a, b = answers
    assert a.verdict == b.verdict == Verdict.yes
    assert articles(a) == articles(b) and "B.24" in articles(a)


def test_parsed_variant_and_stem_reach_the_engine(engine):
    sc = scene(sign("s1", "W.207c"))
    for code in ("W.207c", "W.207"):
        w = WParse.model_validate({"program": {"intent": "is_sign", "sign": {"only": True},
                                               "code": code}})
        a = engine.answer(sc, to_query(w, 2026))
        assert a.verdict == Verdict.yes and "C.7" in articles(a), code


def test_reply_with_a_field_its_intent_lacks_is_rejected():
    reply = {"program": {"intent": "meaning", "sign": {"only": True}, "speed_kmh": 50.0}}
    with pytest.raises(ValidationError) as e:
        from_wire(reply)
    assert "speed_kmh" in explain(e.value)


def test_null_fields_take_their_defaults():
    reply = {"out_of_scope": False, "out_of_scope_reason": None, "missing_slots": [],
             "program": {"intent": "meaning", "sign": {"only": True, "code": None}}}
    assert from_wire(reply) == WParse.model_validate({"program": {"intent": "meaning",
                                                                  "sign": {"only": True}}})


# ---------------------------------------------------------------- reply text

FENCED = "```json\n" + json.dumps(GOOD) + "\n```"


def test_bare_and_fenced_json_are_accepted(engine):
    for reply in (json.dumps(GOOD), "  " + json.dumps(GOOD, indent=2) + "\n", FENCED):
        p, _ = parser([reply], engine)
        r = p.parse("...")
        assert r.status == "ok" and r.attempts == 1, reply


def test_prose_around_json_gets_one_retry(engine):
    p, sdk = parser(["Here is the program:\n" + json.dumps(GOOD), GOOD], engine)
    r = p.parse("...")
    assert r.status == "ok" and r.attempts == 2
    assert "only a JSON object" in sdk.created[1]["messages"][2]["content"]


def test_broken_json_retry_then_success(engine):
    p, sdk = parser(['{"program": {"intent": "meaning",', GOOD], engine)
    r = p.parse("...")
    assert r.status == "ok" and r.attempts == 2
    assert "not valid JSON" in sdk.created[1]["messages"][2]["content"]
    assert r.cost_usd > 0 and len(r.raw) == 2


def test_broken_json_twice_is_invalid(engine):
    p, sdk = parser(["{oops", "still not json"], engine)
    r = p.parse("...")
    assert r.status == "invalid" and r.attempts == 2 and len(sdk.created) == 2
    assert "JSON" in r.errors[0]


def test_max_tokens_is_an_error_without_retry(engine):
    p, sdk = parser(["MAXTOK"], engine)
    r = p.parse("...")
    assert r.status == "error" and len(sdk.created) == 1
    assert "cut off at max_tokens" in r.errors[0]


def test_retry_goes_through_the_spend_guard(engine):
    sdk = FakeSDK(["{oops", GOOD])
    worst = worst_case_usd("claude-haiku-5-5", 12_000, 4096)
    first = cost_usd("claude-haiku-5-5", input_tokens=200, output_tokens=150, cache_read_tokens=11_800)
    llm = LLMClient(model="claude-haiku-5-5", sdk=sdk, guard=SpendGuard(worst + first / 2))
    p = ClaudeParser(llm=llm, engine=engine, context_year=2026)
    with pytest.raises(SpendLimitExceeded):
        p.parse("...")
    assert len(sdk.created) == 1


def test_failed_calls_are_logged(engine, tmp_path):
    class HTTP400(Exception):
        status_code = 400
    p, _ = parser([HTTP400("compiled grammar too large")], engine)
    with pytest.raises(HTTP400):
        p.parse("...")
    p2, _ = parser(["MAXTOK"], engine)
    p2.parse("...")
    log = [json.loads(l) for l in (tmp_path / "api_calls.jsonl").read_text().splitlines()]
    assert log[0]["status"] == "http_error" and log[0]["cost_usd"] == 0.0
    assert log[0]["http_status"] == 400 and "grammar" in log[0]["error"]
    assert log[1]["status"] == "max_tokens" and log[1]["cost_usd"] > 0


def test_raw_replies_and_usage_kept_for_every_attempt(engine):
    p, _ = parser(["{oops", GOOD], engine)
    r = p.parse("...")
    assert r.raw == ["{oops", json.dumps(GOOD)] and len(r.usage) == 2
    p2, _ = parser(["MAXTOK"], engine)
    r2 = p2.parse("...")
    assert r2.status == "error" and r2.raw == ['{"program": {"inte'] and len(r2.usage) == 1


def test_default_parser_is_sonnet_at_medium():
    from vqa.parsing import claude_parser as cp
    assert (cp.DEFAULT_MODEL, cp.DEFAULT_EFFORT) == ("claude-sonnet-5-5", "medium")


# ---------------------------------------------------------------- v7 (phase 4.5 B2)

def test_v7_keeps_v6_fewshots_and_adds_train_ones_outside_dev_and_validation():
    """Owner, 2026-11-17: v7's new few-shots come from train, outside the phase-4.5 dev and
    validation sets and their images, with the exact question text. Only ids and image ids
    of those sets are read here."""
    v6, v7 = examples("v6"), examples("v7")
    ids6 = [e["id"] for e in v6]
    assert [e["id"] for e in v7][:len(v6)] == ids6
    changed = [e["id"] for a, e in zip(v6, v7) if a != e]
    assert changed == ["train_215"]                     # guide content is in scope now
    new = v7[len(v6):]
    assert new and all(e["split"] == "train" for e in new)
    dev = json.loads((ROOT / "data" / "splits" / "train_dev.json").read_text())
    val = json.loads((ROOT / "data" / "splits" / "train_validation.json").read_text())
    banned_q = set(dev["questions"]) | set(val["questions"])
    banned_img = set(dev["images"]) | set(val["images"])
    assert not {e["id"] for e in v7} & banned_q
    train = (Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural"))
             / "dataset" / "train data" / "vlsp_2025_train.json")
    if train.exists():
        img = {t["id"]: t["image_id"] for t in json.loads(train.read_text(encoding="utf-8"))}
        assert not {img[e["id"]] for e in v7 if e["split"] == "train"} & banned_img


@pytest.mark.parametrize("version", ["v7", "v8", "v9", "v10"])
def test_v7_covers_the_new_intents_and_slots(version):
    progs = json.dumps([e["output"] for e in examples(version)])
    for needle in ('"aspect": "group"', '"aspect": "conduct"', '"aspect": "scope"', '"intent": "present"',
                   '"intent": "guide"', '"lane": -1'):
        assert needle in progs, needle
    spec = (ROOT / "prompts" / "parser" / version / "spec.md").read_text()
    for rule in ("`road_divided`", "`vehicles`", "xe cảnh sát", "`category`", "is negative", "`placement`"):
        assert rule in spec, rule


@pytest.mark.parametrize("version", ["v7", "v8", "v9", "v10"])
def test_v7_spec_does_not_quote_dev_questions(version):
    """Dev is the tuning set: its wording must not sit in the spec as an unlisted few-shot."""
    train = (Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural"))
             / "dataset" / "train data" / "vlsp_2025_train.json")
    if not train.exists():
        pytest.skip("dataset not available")
    dev = set(json.loads((ROOT / "data" / "splits" / "train_dev.json").read_text())["questions"])
    spec = (ROOT / "prompts" / "parser" / version / "spec.md").read_text().lower()
    for q in json.loads(train.read_text(encoding="utf-8")):
        if q["id"] in dev:
            words = q["question"].lower().split()
            for i in range(len(words) - 5):
                assert " ".join(words[i:i + 6]) not in spec, q["id"]


def test_v7_prompt_lists_the_phase45_rows_and_v6_does_not():
    assert "R.122 |" in system_prompt("v7") and "R.122 |" not in system_prompt("v6")


def test_v7_retry_sends_only_the_error(engine):
    from vqa.perception.wire import PLACEHOLDER
    p, sdk = parser([BAD, GOOD], engine, prompt_version="v7")
    assert p.parse("...").status == "ok"
    msgs = sdk.created[1]["messages"]
    assert msgs[1] == {"role": "assistant", "content": PLACEHOLDER} and "every_vehicle" in msgs[2]["content"]
    p6, sdk6 = parser([BAD, GOOD], engine)
    p6.parse("...")
    assert sdk6.created[1]["messages"][1]["content"] != PLACEHOLDER          # v6 keeps its echo


def test_v8_is_v7_with_three_spec_fixes_and_the_same_fewshots():
    """Phase 4.5 B4 (v7 gate run 1, public_dev): v8 keeps v7's few-shots and changes three
    things: "loại biển gì" is `name`; value-only intents never answer a stated claim; `only`
    is not added to a selector that describes the sign."""
    d7, d8 = (ROOT / "prompts" / "parser" / v for v in ("v7", "v8"))
    assert (d7 / "fewshot.jsonl").read_bytes() == (d8 / "fewshot.jsonl").read_bytes()
    a, b = ((d / "spec.md").read_text().splitlines() for d in (d7, d8))
    added = [y for y in b if y not in a]
    assert len(b) == len(a) + 1 and len(added) == 4
    spec = "\n".join(b)
    assert "never a truth value" in spec and "loại biển gì" in spec and "without `only`" in spec


def test_v9_is_v8_with_the_general_yes_no_rule():
    """Owner, 2026-11-17 (B4 accepted): one yes/no wording rule for every intent, built from
    train outside dev and validation. v9 = v8 with that line replacing v8's narrower one,
    plus five few-shots appended (exact text, checked by the provenance tests)."""
    d8, d9 = (ROOT / "prompts" / "parser" / v for v in ("v8", "v9"))
    a, b = ((d / "spec.md").read_text().splitlines() for d in (d8, d9))
    diff = [y for x, y in zip(a, b) if x != y]
    assert len(a) == len(b) and len(diff) == 1
    for w in ('"có ... không?"', '"có phải ... không?"', '"... được không?"', '"..., đúng hay sai?"',
              "never a value program", "`is_sign` with `category`", "`present`"):
        assert w in diff[0], w
    e8, e9 = examples("v8"), examples("v9")
    assert e9[:len(e8)] == e8
    assert [e["id"] for e in e9[len(e8):]] == ["train_136", "train_127", "train_124", "train_424", "train_19"]
    kinds = [json.dumps(e["output"]) for e in e9[len(e8):]]
    assert '"intent": "is_sign"' in kinds[0] and '"intent": "present"' in kinds[1]
    assert all('"out_of_scope": true' in k for k in kinds[2:4])


def test_v10_adds_the_phase46_intents_with_train_fewshots_outside_dev_and_validation():
    """Phase 4.6 step 4 (owner, 2026-11-17): v10 = v9 plus the I1-I4 lines and the D3 slot
    fixes; v9's two board claims marked out of scope become guide claims (train_124, train_424);
    six few-shots are appended, from the train working set (outside dev and validation and
    their images), exact text (checked by the provenance tests)."""
    e9, e10 = examples("v9"), examples("v10")
    assert [e["id"] for e in e10][:len(e9)] == [e["id"] for e in e9]
    changed = [e["id"] for a, e in zip(e9, e10) if a != e]
    assert changed == ["train_124", "train_424"]
    new = e10[len(e9):]
    assert [e["id"] for e in new] == ["train_76", "train_422", "train_104", "train_340", "train_21", "train_490"]
    dev = json.loads((ROOT / "data" / "splits" / "train_dev.json").read_text())
    val = json.loads((ROOT / "data" / "splits" / "train_validation.json").read_text())
    assert not {e["id"] for e in e10} & (set(dev["questions"]) | set(val["questions"]))
    train = (Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural"))
             / "dataset" / "train data" / "vlsp_2025_train.json")
    if train.exists():
        img = {t["id"]: t["image_id"] for t in json.loads(train.read_text(encoding="utf-8"))}
        assert not {img[e["id"]] for e in e10 if e["split"] == "train"} & (set(dev["images"]) | set(val["images"]))
    progs = json.dumps([e["output"] for e in e10])
    for needle in ('"intent": "multi"', '"intent": "guide_claim"', '"intent": "explain"', '"kind": "range"',
                   '"aspect": "article"', '"ask": "road_type"'):
        assert needle in progs, needle
    spec = (ROOT / "prompts" / "parser" / "v10" / "spec.md").read_text()
    for rule in ("`guide_claim`", "`speed_limit_is`", "`multi`", "`explain`", "`kind: range`", "`day_parity",
                 "`gross_gt`", "`article`"):
        assert rule in spec, rule
