"""Gold-intent tooling, offline: cost estimate with a fake count, review import."""

import csv
import json
from types import SimpleNamespace

import pytest

import eval.gold_intents as gi


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
