"""eval/perception_eval.py: the GATE constant (pinned), matching and scoring per
image, the image-level bootstrap, run files, and the public_dev checkpoint warning.
Gold and predictions are hand-written."""

import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

import eval.perception_eval as pe
from eval.report import bootstrap_ci


def test_gate_is_pinned():
    assert pe.GATE == {
        "name": "perception_gate_v1",
        "fixed": "2026-11-15, before any perception result",
        "gate_set": "public_dev",
        "excluded_images": [],
        "sign_recall_min": 0.90,
        "sign_code_f1_min": 0.85,
        "runs": 3,
        "aggregate": "mean",
        "pass_rule": "both point estimates (mean of runs) reach their minimum on all gate images",
        "excluded_gold": ["readable_false", "local_notice"],
        "code_level": "catalog_row",
        "unknown_prediction": "counts as found for recall, never a code true positive",
        "matching": "one-to-one; same catalog row or same visual category; then rank, side, order",
        "ci": {"method": "bootstrap", "unit": "image", "resamples": 10_000, "seed": 20261115, "level": 0.95},
        "reported_on": ["all_images", "non_duplicate_images"],
    }


def g(code, rank, side="right", shape="circle", border="red", background="white", **kw):
    return {"code": code, "readable": kw.pop("readable", True), "shape": shape, "border": border,
            "background": background, "position": {"rank_top_down": rank, "side": side}, **kw}


p = g   # predictions use the same shape of dict


# ---------------------------------------------------------------- matching cases (plan item 5)

def test_two_signs_with_the_same_code():
    gold = [g("P.123a", 1, "left"), g("P.123a", 2, "right")]
    c = pe.score_image(gold, [p("P.123a", 2, "right")])
    assert (c["gold"], c["found"], c["tp"], c["pred"]) == (2, 1, 1, 1)
    c = pe.score_image(gold, [p("P.123a", 1, "left"), p("P.123a", 2, "right")])
    assert (c["found"], c["tp"], c["pred"]) == (2, 2, 2)


def test_a_plate_listed_as_its_own_sign():
    gold = [g("P.104", 1, plates=[{"kind": "time", "time_windows": [{"start": "06:00", "end": "22:00"}]}])]
    pred = [p("P.104", 1), p("S.508a", 2, shape="rectangle", border="black", background="white")]
    c = pe.score_image(gold, pred)
    assert (c["found"], c["tp"], c["pred"]) == (1, 1, 2)          # the plate costs precision only


def test_an_unknown_prediction_counts_for_recall_not_for_codes():
    c = pe.score_image([g("P.104", 1)], [p("UNKNOWN", 1)])
    assert (c["found"], c["tp"], c["pred"]) == (1, 0, 1)


def test_a_readable_false_gold_sign_is_neutral():
    gold = [g("P.104", 1), g("UNKNOWN", 2, readable=False)]
    c = pe.score_image(gold, [p("P.104", 1), p("P.127", 2)])
    assert (c["gold"], c["found"], c["tp"], c["pred"], c["readable_false"]) == (1, 1, 1, 1, 1)
    assert pe.score_image(gold, [p("P.104", 1)])["pred"] == 1     # missing it costs nothing


def test_a_local_notice_gold_sign_is_neutral_and_counted_apart():
    notice = g("UNKNOWN", 2, shape="rectangle", border="none", background="blue", local_notice="ĐÈN ĐỎ ĐƯỢC PHÉP ĐI THẲNG")
    c = pe.score_image([g("P.104", 1), notice], [p("P.104", 1), p("UNKNOWN", 2, shape="rectangle", border="none", background="blue")])
    assert (c["gold"], c["pred"], c["local_notice"], c["local_notice_found"]) == (1, 1, 1, 1)


def test_a_variant_code_is_right_at_row_level_and_wrong_strictly():
    tri = dict(shape="triangle", border="red", background="yellow")
    c = pe.score_image([g("W.207c", 1, **tri)], [p("W.207b", 1, **tri)])
    assert (c["tp"], c["tp_strict"]) == (1, 0)
    c = pe.score_image([g("W.207c", 1, **tri)], [p("W.207(a,b,c,d,e,f,g,h,i,k,l)", 1, **tri)])
    assert (c["tp"], c["tp_strict"]) == (1, 1)


def test_a_pair_with_a_different_row_and_category_stays_unmatched():
    c = pe.score_image([g("P.104", 1)], [p("W.207c", 1, shape="triangle", border="red", background="yellow")])
    assert (c["found"], c["tp"], c["pred"]) == (0, 0, 1)


def test_metrics_follow_the_counts():
    units = [pe.score_image([g("P.104", 1), g("P.127", 2, value=50)], [p("P.104", 1), p("P.127", 2, value=60)]),
             pe.score_image([g("P.112", 1)], [])]
    m = pe.metrics(units, with_ci=False)
    assert m["sign_recall"] == pytest.approx(2 / 3)
    assert m["sign_code_f1"] == pytest.approx(2 * 1.0 * (2 / 3) / (1 + 2 / 3))
    assert m["value_accuracy"] == 0.0 and m["shape_accuracy"] == 1.0


# ---------------------------------------------------------------- bootstrap

def test_bootstrap_is_image_level_and_reproducible():
    units = [{"gold": 1, "found": 1}] * 8 + [{"gold": 4, "found": 0}] * 2
    a = bootstrap_ci(units, pe.recall, resamples=500, seed=7)
    assert a == bootstrap_ci(units, pe.recall, resamples=500, seed=7)
    assert a[0] < 8 / 16 < a[1] or a[0] <= 0.5 <= a[1]
    assert bootstrap_ci([], pe.recall) == (None, None)


# ---------------------------------------------------------------- run and score

GOOD = json.dumps({"signs": [{"code": "P.104", "shape": "circle", "border": "red", "background": "white",
                              "rank": 1, "side": "right", "confidence": "high"}]})


class FakeSDK:
    def __init__(self, n):
        self.messages, self.created, self.n = self, [], n

    def count_tokens(self, **kw):
        return SimpleNamespace(input_tokens=11_000)

    def create(self, **kw):
        self.created.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=GOOD)], stop_reason="end_turn",
                               stop_details=None, _request_id="r",
                               usage=SimpleNamespace(input_tokens=700, output_tokens=300,
                                                     cache_read_input_tokens=10_000, cache_creation_input_tokens=0))


@pytest.fixture
def fake_set(tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("VQA_SCENE_CACHE_DIR", str(tmp_path / "cache"))
    ids = ["public_test_1_1", "public_test_1_2"]
    for k, i in enumerate(ids):
        buf = io.BytesIO()
        Image.new("RGB", (320, 240), (k * 80, 50, 50)).save(buf, format="JPEG")
        (tmp_path / f"{i}.jpg").write_bytes(buf.getvalue())
    monkeypatch.setattr(pe, "set_images", lambda name: [(i, "public_dev") for i in ids])
    monkeypatch.setattr(pe.gs, "image_path", lambda i, s: tmp_path / f"{i}.jpg")
    monkeypatch.setattr(pe, "gold_rows", lambda: {
        "public_test_1_1": {"signs": [g("P.104", 1)]},
        "public_test_1_2": {"signs": [g("P.104", 1), g("P.112", 2)]}})
    monkeypatch.setattr(pe, "non_duplicate", lambda name, ids: {"public_test_1_2"})
    return tmp_path


def test_a_public_dev_run_warns_scores_and_needs_three_runs(fake_set, capsys):
    out = pe.run("public_dev", "claude-haiku-5-5", 1.0, sdk=FakeSDK(2), out_dir=fake_set / "runs")
    assert "recorded checkpoint" in capsys.readouterr().out
    head, rows = pe.load_run(out)
    assert head["set"] == "public_dev" and len(rows) == 2 and all(r["ok"] for r in rows)
    rep = pe.score([out, out])                          # the same run twice counts once
    assert len(rep["runs"]) == 1 and rep["gate"]["verdict"] == "not decided: 1 of 3 runs"
    r = rep["runs"][0]
    assert r["all_images"]["sign_recall"] == pytest.approx(2 / 3)
    assert r["non_duplicate_images"]["images"] == 1
    assert len(r["all_images"]["sign_recall_ci95"]) == 2


def test_three_runs_decide_the_gate(fake_set):
    outs = [pe.run("public_dev", "claude-haiku-5-5", 1.0, sdk=FakeSDK(2), out_dir=fake_set / "runs")
            for _ in range(3)]
    gate = pe.score(outs)["gate"]
    assert gate["runs"] == 3 and gate["verdict"] == "FAIL"     # recall 2/3 < 0.90


def test_runs_do_not_read_the_cache(fake_set):
    sdk = FakeSDK(4)
    pe.run("public_dev", "claude-haiku-5-5", 1.0, sdk=sdk, out_dir=fake_set / "runs")
    pe.run("public_dev", "claude-haiku-5-5", 1.0, sdk=sdk, out_dir=fake_set / "runs")
    assert len(sdk.created) == 4


def test_estimate_makes_no_call(fake_set):
    est = pe.estimate("public_dev", "claude-haiku-5-5", runs=3)
    assert est["images"] == 2 and est["runs"] == 3 and est["total_usd_range"][0] < est["total_usd_range"][1]
    assert est["prompt_id"].startswith("scene/v1@")
