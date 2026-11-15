"""Parser eval, offline: normalization, scoring, gate, reports, and the run loop
with a mocked client. Gold, questions and predictions are hand-written here; no
dataset text."""

import json
from types import SimpleNamespace

import pytest

import eval.parser_eval as pe

# ---------------------------------------------------------------- helpers

CAR_BAN = {"program": {"intent": "forbidden", "action": "enter", "vehicle": {"vehicle_class": "car"},
                       "when": {"start": "06:00", "end": "22:00", "quantifier": "all"}}}
MEANING = {"program": {"intent": "meaning", "sign": {"only": True}}}
OOS = {"out_of_scope": True, "out_of_scope_reason": "guide-sign content"}


def gold_row(i, program, split="public_dev", also=()):
    return {"id": i, "split": split, "program": program, "also_accept": list(also), "verdict": "ok"}


def pred(i, program=None, status=None, cost=0.001, split="public_dev"):
    if program is None:
        return {"id": i, "split": split, "status": status or "invalid", "query": None,
                "cost_usd": cost, "model": "claude-haiku-5-5", "effort": "low", "prompt_version": "v4"}
    q = pe.gold_query(program)
    return {"id": i, "split": split, "status": status or ("out_of_scope" if q.out_of_scope else "ok"),
            "query": q.model_dump(mode="json"), "cost_usd": cost, "model": "claude-haiku-5-5",
            "effort": "low", "prompt_version": "v4"}


def score(preds, gold, dups=None):
    images = {g["id"]: f"img_{g['id']}" for g in gold}
    return pe.score_predictions(preds, gold, images, duplicates=dups or {"groups": []})


# ---------------------------------------------------------------- normalization

def test_forbidden_equals_verify_not_permitted_with_flipped_quantifier():
    alt = {"program": {"intent": "verify", "expect": False, "claim": {
        "intent": "permitted", "action": "enter", "vehicle": {"vehicle_class": "car"},
        "when": {"start": "06:00", "end": "22:00", "quantifier": "any"}}}}
    assert pe.canonical(pe.gold_query(CAR_BAN)) == pe.canonical(pe.gold_query(alt))


def test_verify_true_is_the_bare_claim_and_defaults_are_filled():
    bare = {"program": {"intent": "permitted", "action": "park"}}
    wrapped = {"program": {"intent": "verify", "claim": {"intent": "permitted", "action": "park",
                                                         "vehicle": {"vehicle_class": "motor_vehicle"}}}}
    assert pe.canonical(pe.gold_query(bare)) == pe.canonical(pe.gold_query(wrapped))


def test_choice_labels_are_ignored_but_order_and_expect_count():
    def choose(labels, expect=True):
        return {"program": {"intent": "choose", "options": [
            {"label": lab, "expect": expect, "claim": {"intent": "speed_ok", "speed_kmh": v}}
            for lab, v in zip(labels, (30.0, 40.0))]}}
    a, b = pe.gold_query(choose(["30 km/h", "40 km/h"])), pe.gold_query(choose(["a", "b"]))
    assert pe.canonical(a) == pe.canonical(b)
    assert pe.canonical(a) != pe.canonical(pe.gold_query(choose(["a", "b"], expect=False)))


def test_forbidden_inside_all_of_is_compiled_too():
    a = {"program": {"intent": "all_of", "claims": [CAR_BAN["program"], MEANING["program"] | {
        "intent": "is_sign", "meaning": "no_entry_one_way"}]}}
    c = pe.canonical(pe.gold_query(a))["program"]
    assert c["claims"][0]["intent"] == "verify" and c["claims"][0]["expect"] is False


# ---------------------------------------------------------------- scoring

def test_exact_match_also_accept_and_failures():
    alt = {"program": {"intent": "is_sign", "sign": {"only": True}, "code": "P.102"}}
    gold = [gold_row("q1", CAR_BAN), gold_row("q2", MEANING, also=[alt]),
            gold_row("q3", MEANING), gold_row("q4", MEANING)]
    preds = [pred("q1", CAR_BAN), pred("q2", alt), pred("q3", status="invalid")]   # q4 missing
    s = score(preds, gold)["splits"]["public_dev"]
    assert s["correct"] == 2 and s["n"] == 4 and s["failed"] == 2
    assert s["wrong"] == ["q3", "q4"]


def test_out_of_scope_rows_count_and_match_only_out_of_scope():
    gold = [gold_row("a", OOS), gold_row("b", OOS), gold_row("c", MEANING), gold_row("d", MEANING)]
    preds = [pred("a", OOS), pred("b", MEANING), pred("c", OOS), pred("d", MEANING)]
    s = score(preds, gold)["splits"]["public_dev"]
    assert s["correct"] == 2                         # a and d
    assert s["oos_precision"] == 0.5 and s["oos_recall"] == 0.5


def test_slot_f1_counts_partial_programs():
    gold = [gold_row("a", CAR_BAN)]
    wrong_time = json.loads(json.dumps(CAR_BAN))
    wrong_time["program"]["when"]["end"] = "21:00"
    s = score([pred("a", wrong_time)], gold)["splits"]["public_dev"]
    assert s["correct"] == 0 and 0.5 < s["slot_f1"] < 1.0
    s0 = score([pred("a", status="invalid")], gold)["splits"]["public_dev"]
    assert s0["slot_f1"] == 0.0


def test_fewshot_ids_are_not_in_the_gate_set():
    shots = sorted(i for i in pe.fewshot_ids("v4") if i.startswith("public_natural"))
    assert shots == ["public_natural_0026", "public_natural_0082", "public_natural_0097"]
    gold = [gold_row(shots[0], MEANING), gold_row("q1", MEANING)]
    s = score([pred("q1", MEANING)], gold)["splits"]["public_dev"]
    assert s["n"] == 1 and s["accuracy"] == 1.0
    assert [g["id"] for g in pe.gate_rows(gold)] == ["q1"]


@pytest.mark.parametrize("right,passed", [(9, True), (8, False)])
def test_gate_on_the_point_estimate_with_wilson_ci(right, passed):
    gold = [gold_row(f"q{i}", MEANING) for i in range(10)]
    preds = [pred(f"q{i}", MEANING if i < right else OOS) for i in range(10)]
    s = score(preds, gold)["splits"]["public_dev"]
    assert s["gate"]["passed"] is passed
    lo, hi = s["ci95"]
    assert lo < s["accuracy"] < hi


def test_report_splits_duplicate_images():
    gold = [gold_row(f"q{i}", MEANING) for i in range(4)]
    preds = [pred("q0", MEANING), pred("q1", MEANING), pred("q2", OOS), pred("q3", MEANING)]
    dups = {"groups": [{"images": [{"split": "public", "image_id": "img_q0"},
                                   {"split": "train", "image_id": "train_1"}]}]}
    rep = score(preds, gold, dups)["splits"]["public_dev"]["report"]
    assert rep["all_images"]["n"] == 4 and rep["non_duplicate_images"]["n"] == 3
    assert "ci95" in rep["non_duplicate_images"]
    text = pe.format_scores(score(preds, gold, dups))
    assert "gate" in text and "non" in text.lower()


def test_train_rows_are_scored_only_when_predicted():
    gold = [gold_row("q1", MEANING), gold_row("t1", MEANING, split="train")]
    assert "train" not in score([pred("q1", MEANING)], gold)["splits"]
    both = score([pred("q1", MEANING), pred("t1", MEANING, split="train")], gold)["splits"]
    assert both["train"]["n"] == 1 and "gate" not in both["train"]


def test_comparison_table_and_cost():
    gold = [gold_row("q1", MEANING), gold_row("q2", MEANING)]
    a = score([pred("q1", MEANING, cost=0.002), pred("q2", MEANING, cost=0.002)], gold)
    b = score([pred("q1", MEANING), pred("q2", OOS)], gold)
    b["effort"] = "medium"
    assert a["splits"]["public_dev"]["cost_usd"] == pytest.approx(0.004)
    t = pe.comparison_table([a, b])
    assert "| low |" in t and "| medium |" in t and "100.0%" in t and "50.0%" in t


# ---------------------------------------------------------------- data access

@pytest.fixture
def fake_data(tmp_path):
    """A made-up split and public file: two dev questions, one holdout."""
    split = {"public_dev": {"questions": ["d1", "d2"], "images": ["i1", "i2"]},
             "public_holdout": {"questions": ["h1"], "images": ["i3"]}}
    public = [{"id": "d1", "image_id": "i1", "question": "Câu một?"},
              {"id": "d2", "image_id": "i2", "question": "Câu hai?"},
              {"id": "h1", "image_id": "i3", "question": "HOLDOUT SENTINEL"}]
    (tmp_path / "split.json").write_text(json.dumps(split))
    (tmp_path / "public.json").write_text(json.dumps(public, ensure_ascii=False))
    gold = [gold_row("d1", MEANING), gold_row("d2", OOS)]
    (tmp_path / "gold.jsonl").write_text("".join(json.dumps(g) + "\n" for g in gold))
    return tmp_path


def test_only_public_dev_questions_are_loaded(fake_data):
    qs = pe.load_dev_questions({"d1", "d2"}, fake_data / "public.json", fake_data / "split.json")
    assert set(qs) == {"d1", "d2"} and qs["d1"]["image_id"] == "i1"
    with pytest.raises(SystemExit, match="not public_dev"):
        pe.load_dev_questions({"d1", "h1"}, fake_data / "public.json", fake_data / "split.json")
    with pytest.raises(SystemExit, match="not public_dev"):
        pe.load_dev_questions({"private_natural_0001"}, fake_data / "public.json",
                              fake_data / "split.json")


# ---------------------------------------------------------------- run (mocked client)

class FakeSDK:
    def __init__(self, replies, prompt_tokens=15_000):
        self.replies, self.prompt_tokens, self.created, self.counted = list(replies), prompt_tokens, [], 0
        self.messages = self

    def count_tokens(self, **kw):
        self.counted += 1
        return SimpleNamespace(input_tokens=self.prompt_tokens)

    def create(self, **kw):
        self.created.append(kw)
        text = self.replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
                               stop_details=None, _request_id="r",
                               usage=SimpleNamespace(input_tokens=20, output_tokens=80,
                                                     cache_read_input_tokens=14_980,
                                                     cache_creation_input_tokens=0))


def test_run_writes_predictions_with_raw_replies(fake_data, engine, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(fake_data / "logs"))
    sdk = FakeSDK(["not json", json.dumps(MEANING), json.dumps(OOS)])   # d1 retried once
    path = pe.run("claude-haiku-5-5", "low", 0.5, sdk=sdk, engine=engine,
                  gold_path=fake_data / "gold.jsonl", public_file=fake_data / "public.json",
                  split_file=fake_data / "split.json", out_dir=fake_data / "out")
    recs = [json.loads(line) for line in path.read_text().splitlines()]
    assert [r["id"] for r in recs] == ["d1", "d2"] and [r["status"] for r in recs] == ["ok", "out_of_scope"]
    r1 = recs[0]
    assert r1["raw"] == ["not json", json.dumps(MEANING)] and r1["attempts"] == 2
    assert len(r1["usage"]) == 2 and r1["cost_usd"] > 0
    assert (r1["model"], r1["effort"], r1["prompt_version"]) == ("claude-haiku-5-5", "low", "v5")
    assert all(c["output_config"] == {"effort": "low"} and "format" not in c["output_config"]
               for c in sdk.created)
    text = path.read_text(encoding="utf-8")
    assert "Câu" not in text and "SENTINEL" not in text          # no question text written
    s = pe.score_predictions(recs, pe.load_gold(fake_data / "gold.jsonl"), {"d1": "i1", "d2": "i2"},
                             duplicates={"groups": []})
    assert s["splits"]["public_dev"]["accuracy"] == 1.0


def test_run_refuses_when_the_worst_case_exceeds_the_limit(fake_data, engine):
    sdk = FakeSDK([])
    with pytest.raises(SystemExit, match="exceeds --max-spend"):
        pe.run("claude-opus-5-5", "medium", 0.05, sdk=sdk, engine=engine,
               gold_path=fake_data / "gold.jsonl", public_file=fake_data / "public.json",
               split_file=fake_data / "split.json", out_dir=fake_data / "out")
    assert sdk.created == [] and sdk.counted == 2       # counted (free), nothing sent


def test_estimate_expected_below_worst():
    est = pe.estimate("claude-haiku-5-5", [15_000] * 47)
    assert 0 < est["expected_usd"] < est["worst_case_usd"] < 0.5
