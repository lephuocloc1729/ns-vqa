"""Gold-intent tooling, offline: cost estimate with a fake count, review import."""

import csv
import json
from types import SimpleNamespace

import pytest

import eval.gold_intents as gi
from vqa.llm.pricing import cost_usd, worst_case_usd
from vqa.llm.spend import SpendLimitExceeded


@pytest.fixture
def tmp_out(tmp_path, monkeypatch):
    monkeypatch.setattr(gi, "OUT", tmp_path)
    rows = [{"id": "train_9", "split": "train", "question": "Câu hỏi?"},
            {"id": "public_natural_0001", "split": "public_dev", "question": "đây là biển báo gì?"}]
    (tmp_path / "questions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return tmp_path


class CountSDK:
    def __init__(self):
        self.messages = self

    def count_tokens(self, **kw):
        assert kw["model"] == "claude-opus-5-5" and kw["output_config"]["effort"] == "medium"
        return SimpleNamespace(input_tokens=10_000)


def test_estimate_exact_and_bounds(tmp_out):
    est = gi.estimate(CountSDK())
    assert est["method"].startswith("exact") and est["requests"] == 2
    assert est["prompt_tokens_total"] == 20_000
    assert est["expected_usd_all_cache_hits"] < est["expected_usd_no_cache_hits"] < est["worst_case_usd"]


def test_estimate_without_key_is_marked_rough(tmp_out):
    assert gi.estimate(None)["method"].startswith("rough")


def write_review(path, rows):
    cols = ["id", "split", "question", "draft_status", "draft_program", "verdict",
            "corrected_program", "also_accept", "notes"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def test_import_review(tmp_out):
    draft = json.dumps({"program": {"intent": "meaning", "sign": {"only": True}}})
    fix = json.dumps({"program": {"intent": "is_sign", "sign": {"only": True}, "code": "P.125"}})
    alt = json.dumps([{"program": {"intent": "is_sign", "sign": {"only": True},
                                   "meaning": "no_overtaking"}}])
    write_review(tmp_out / "review.csv", [
        {"id": "a", "split": "train", "question": "Q1", "draft_program": draft, "verdict": "ok"},
        {"id": "b", "split": "train", "question": "Q2", "draft_program": draft, "verdict": "fix",
         "corrected_program": fix, "also_accept": alt},
        {"id": "c", "split": "public_dev", "question": "Q3", "verdict": "out_of_scope",
         "notes": "guide-sign content"},
        {"id": "d", "split": "train", "question": "Q4", "draft_program": draft, "verdict": ""},
    ])
    gold = gi.import_review()
    assert [g["id"] for g in gold] == ["a", "b", "c"]
    assert gold[1]["program"]["program"]["code"] == "P.125" and len(gold[1]["also_accept"]) == 1
    assert gold[2]["program"]["out_of_scope"] is True
    assert all("question" not in g for g in gold)      # no dataset text in the gold file


def test_import_rejects_invalid_programs(tmp_out):
    bad = json.dumps({"program": {"intent": "lanes_for", "vehicle": {"vehicle_class": "every_vehicle"}}})
    write_review(tmp_out / "review.csv", [{"id": "a", "split": "train", "question": "Q",
                                           "verdict": "fix", "corrected_program": bad}])
    with pytest.raises(SystemExit):
        gi.import_review()


def test_collect_will_not_overwrite_reviewed_csv(tmp_out):
    write_review(tmp_out / "review.csv", [
        {"id": "a", "split": "public_dev", "question": "Q", "verdict": "ok"},
        {"id": "b", "split": "public_dev", "question": "Q", "verdict": ""}])
    assert gi.reviewed_rows(tmp_out / "review.csv") == 1
    with pytest.raises(SystemExit, match="1 reviewed rows"):
        gi.collect()


def test_reviewed_rows_without_csv(tmp_out):
    assert gi.reviewed_rows(tmp_out / "review.csv") == 0


def test_spread_sample_covers_categories_and_images():
    pool = [{"id": f"train_{i}", "image_id": f"img_{i % 6}", "question": q}
            for i, q in enumerate(["Xe máy được đi làn nào?", "Biển gì?", "Chạy 50 km/h được không?",
                                   "Có vi phạm không?", "Xe tải 3 tấn được đi không?", "Đi làn nào?"] * 3)]
    picked = gi.spread_sample(pool, 5)
    assert len(picked) == 5 and len({gi.category(t["question"]) for t in picked}) == 5
    assert len({t["image_id"] for t in picked}) == 5
    assert gi.spread_sample(pool, 5) == picked          # seeded, reproducible


# --------------------------------------------------------------------------- sequential run

GOOD = json.dumps({"program": {"intent": "meaning", "sign": {"only": True}}})


class SeqSDK:
    """Fake anthropic client for run(): every call answers GOOD with the given usage."""

    def __init__(self, usages, prompt_tokens=30_000):
        self.usages, self.prompt_tokens, self.sent = list(usages), prompt_tokens, []
        self.messages = self

    def count_tokens(self, **kw):
        return SimpleNamespace(input_tokens=self.prompt_tokens)

    def create(self, **kw):
        self.sent.append(kw)
        u = self.usages.pop(0) if self.usages else {"cache_read_input_tokens": 29_990}
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=u.pop("text", GOOD))],
            stop_reason=u.pop("stop", "end_turn"), stop_details=None, _request_id="req",
            usage=SimpleNamespace(**{"input_tokens": 10, "output_tokens": 900,
                                     "cache_read_input_tokens": 0,
                                     "cache_creation_input_tokens": 0, **u}))


@pytest.fixture
def seq_out(tmp_out, tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    rows = [{"id": f"q{i}", "split": "public_dev", "question": f"Câu {i}?"} for i in range(4)]
    (tmp_out / "questions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return tmp_out


def test_run_drafts_everything_when_the_cache_works(seq_out, engine):
    sdk = SeqSDK([{"cache_creation_input_tokens": 29_990}])        # then cache reads
    drafts = gi.run(5.0, sdk=sdk, engine=engine)
    assert len(sdk.sent) == 4 and all(d["draft_status"] == "ok" for d in drafts.values())
    req = sdk.sent[0]
    assert req["model"] == "claude-opus-5-5" and req["output_config"]["effort"] == "medium"
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    with open(seq_out / "review.csv", encoding="utf-8") as f:
        assert [r["draft_status"] for r in csv.DictReader(f)] == ["ok"] * 4
    log = (seq_out / "logs" / "api_calls.jsonl").read_text().splitlines()
    assert len(log) == 4


def test_run_stops_when_the_prompt_is_not_cached(seq_out, engine):
    sdk = SeqSDK([{"cache_creation_input_tokens": 15_000, "input_tokens": 15_000},
                  {"cache_read_input_tokens": 15_000, "input_tokens": 15_000}])
    with pytest.raises(gi.CacheMiss, match="50%"):
        gi.run(5.0, sdk=sdk, engine=engine)
    assert len(sdk.sent) == 2
    assert len((seq_out / "run_progress.jsonl").read_text().splitlines()) == 2


def test_run_resumes_and_records_failures(seq_out, engine):
    sdk = SeqSDK([{"cache_creation_input_tokens": 29_990}, {"stop": "max_tokens",
                                                             "cache_read_input_tokens": 29_990}])
    # a limit that lets call 2 through and stops call 3 before it is sent
    first = cost_usd(gi.MODEL, input_tokens=10, output_tokens=900, cache_write_tokens=29_990)
    second = cost_usd(gi.MODEL, input_tokens=10, output_tokens=900, cache_read_tokens=29_990)
    limit = first + worst_case_usd(gi.MODEL, 30_000, gi.MAX_TOKENS) + second / 2
    with pytest.raises(SpendLimitExceeded):
        gi.run(limit, sdk=sdk, engine=engine)
    done = [json.loads(l) for l in (seq_out / "run_progress.jsonl").read_text().splitlines()]
    assert [d["draft_status"] for d in done] == ["ok", "invalid"]
    assert "max_tokens" in done[1]["errors"][0]
    sdk2 = SeqSDK([{"cache_creation_input_tokens": 29_990}])
    drafts = gi.run(5.0, sdk=sdk2, engine=engine)
    assert len(sdk2.sent) == 2 and len(drafts) == 4      # only the two left were sent


def test_run_refuses_a_reviewed_csv(seq_out, engine):
    write_review(seq_out / "review.csv", [{"id": "q0", "split": "public_dev", "question": "Q",
                                          "verdict": "ok"}])
    with pytest.raises(SystemExit, match="reviewed rows"):
        gi.run(5.0, sdk=SeqSDK([]), engine=engine)


def test_estimate_reports_sequential_cost(tmp_out):
    est = gi.estimate(CountSDK())
    assert est["expected_usd_all_cache_hits"] < est["sequential_expected_usd"] \
        < est["sequential_expected_usd_double_output"]


def test_run_marks_a_non_json_reply_invalid(seq_out, engine):
    sdk = SeqSDK([{"cache_creation_input_tokens": 29_990, "text": "Program: " + GOOD}])
    drafts = gi.run(5.0, sdk=sdk, engine=engine)
    assert drafts["q0"]["draft_status"] == "invalid" and "JSON" in drafts["q0"]["errors"][0]
    assert all(drafts[f"q{i}"]["draft_status"] == "ok" for i in (1, 2, 3))


def test_requests_carry_no_schema(seq_out, engine):
    sdk = SeqSDK([{"cache_creation_input_tokens": 29_990}])
    gi.run(5.0, sdk=sdk, engine=engine)
    assert all(r["output_config"] == {"effort": "medium"} for r in sdk.sent)


def test_run_progress_keeps_the_raw_reply(seq_out, engine):
    sdk = SeqSDK([{"cache_creation_input_tokens": 29_990, "text": "Program: " + GOOD}])
    gi.run(5.0, sdk=sdk, engine=engine)
    done = [json.loads(l) for l in (seq_out / "run_progress.jsonl").read_text().splitlines()]
    assert done[0]["raw_reply"] == "Program: " + GOOD and done[0]["draft_status"] == "invalid"
    assert all(d["raw_reply"] == GOOD for d in done[1:])
