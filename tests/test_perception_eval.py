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
        "name": "perception_gate_v2",
        "fixed": "2026-11-15, before any public_dev result (v1: before any perception result)",
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
        "matching": "one-to-one; same catalog row or same visual category; then side, rank, order",
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


def test_side_comes_before_rank_when_ranks_are_shifted():
    """train_7_23's case (gate v2): the model ranked a board first, so its P.127 ranks
    are one higher; side keeps the left 100 with the left 100."""
    gold = [g("P.127", 1, "left", value=100), g("P.127", 2, "right", value=80)]
    pred = [p("P.127", 2, "left", value=100), p("P.127", 3, "right", value=80)]
    c = pe.score_image(gold, pred)
    assert (c["tp"], c["value_pairs"], c["value_ok"]) == (2, 2, 2)


def test_overhead_sides_fall_back_to_rank_already():
    """train_7_23 with Sonnet: every gantry sign 'overhead'. No pair gets side credit,
    so rank decides, the same as an 'overhead matches any side' rule would; with ranks
    shifted by one, rank alone can still pair across the road. Only real sides in the
    reply (prompt v3) fix this, so matching is left unchanged."""
    gold = [g("P.127", 1, "left", value=100), g("P.127", 2, "right", value=80)]
    pred = [p("P.127", 2, "overhead", value=100), p("P.127", 3, "overhead", value=80)]
    c = pe.score_image(gold, pred)
    assert c["tp"] == 2 and c["value_ok"] == 0                      # paired across the road
    pred_sides = [p("P.127", 2, "left", value=100), p("P.127", 3, "right", value=80)]
    assert pe.score_image(gold, pred_sides)["value_ok"] == 2         # real sides fix it


def test_rule_bearing_code_f1_is_reported_not_gated():
    from vqa.kb import load_catalog
    cat = load_catalog()
    assert pe.rule_bearing("P.127", cat) and pe.rule_bearing("DP.134", cat)
    assert not pe.rule_bearing("W.207c", cat)          # meaning-only
    assert not pe.rule_bearing("R.303", cat)           # effect_unmodelled
    assert not pe.rule_bearing("S.508a", cat) and not pe.rule_bearing("UNKNOWN", cat)
    tri = dict(shape="triangle", border="red", background="yellow")
    units = [pe.score_image([g("P.104", 1), g("W.207c", 2, **tri)],
                            [p("P.104", 1), p("W.207b", 2, **tri)]),
             pe.score_image([g("P.123a", 1)], [p("P.123b", 1)])]
    m = pe.metrics(units, with_ci=False)
    # rule-bearing: gold P.104, P.123a; predicted P.104, P.123b; 1 right -> P = R = 1/2
    assert m["sign_code_f1_rule_bearing"] == pytest.approx(0.5) and m["rule_bearing_gold_signs"] == 2
    assert "rule_bearing" not in json.dumps(pe.GATE)


def test_reverify_rebuilds_from_the_cache_without_calls(fake_set):
    out = pe.run("public_dev", "claude-haiku-5-5", 1.0, sdk=FakeSDK(2), out_dir=fake_set / "runs")
    rev = pe.reverify_run(out)
    head, rows = pe.load_run(rev)
    assert head["reverified_from"] == out.name and len(rows) == 2 and all(r["ok"] for r in rows)
    assert [r["scene"]["signs"][0]["code"] for r in rows] == ["P.104", "P.104"]
    assert pe.score([rev])["runs"][0]["all_images"]["sign_recall"] == pytest.approx(2 / 3)


def test_reverify_refuses_a_run_without_cached_replies(fake_set, monkeypatch, tmp_path):
    out = pe.run("public_dev", "claude-haiku-5-5", 1.0, sdk=FakeSDK(2), out_dir=fake_set / "runs")
    monkeypatch.setenv("VQA_SCENE_CACHE_DIR", str(tmp_path / "empty"))
    with pytest.raises(SystemExit, match="no cached reply"):
        pe.reverify_run(out)


def test_reverify_makes_no_call():
    with pytest.raises(Exception, match="no API calls"):
        pe._NoCalls("claude-haiku-5-5").json_reply(system="s", user="u")


# ---------------------------------------------------------------- mean of runs and drafter split


def test_pooled_units_sum_an_images_counts_over_runs():
    a = {"x": {"gold": 2, "found": 1}, "y": {"gold": 1, "found": 1}}
    b = {"x": {"gold": 2, "found": 2}, "y": {"gold": 1, "found": 0}}
    assert pe.pooled_units([a, b], ["x", "y"]) == [{"gold": 4, "found": 3}, {"gold": 2, "found": 1}]


def test_the_mean_ci_bootstraps_pooled_images_with_the_gate_seed():
    a = {"x": pe.score_image([g("P.104", 1)], []), "y": pe.score_image([g("P.112", 1)], [g("P.112", 1)])}
    b = {"x": pe.score_image([g("P.104", 1)], [g("P.104", 1)]), "y": a["y"]}
    s = pe.summarise([a, b], ["x", "y"])
    assert s["runs"] == 2 and s["images"] == 2 and s["gold_signs"] == 2
    assert s["mean_sign_recall"] == pytest.approx((0.5 + 1.0) / 2)
    assert s["range_sign_recall"] == [0.5, 1.0]
    ci = pe.GATE["ci"]
    pooled = pe.pooled_units([a, b], ["x", "y"])
    assert s["sign_recall_ci95"] == bootstrap_ci(pooled, pe.recall, ci["resamples"], ci["seed"], ci["level"])
    assert s["sign_code_f1_ci95"] == bootstrap_ci(pooled, pe.code_f1, ci["resamples"], ci["seed"], ci["level"])


def test_score_reports_the_mean_and_the_split_by_draft_model(fake_set, monkeypatch):
    monkeypatch.setattr(pe, "gold_rows", lambda: {
        "public_test_1_1": {"signs": [g("P.104", 1)], "draft_model": "claude-opus-5-5"},
        "public_test_1_2": {"signs": [g("P.104", 1), g("P.112", 2)], "draft_model": "claude-haiku-5-5"}})
    outs = [pe.run("public_dev", "claude-haiku-5-5", 1.0, sdk=FakeSDK(2), out_dir=fake_set / "runs")
            for _ in range(3)]
    rep = pe.score(outs)
    assert rep["gate"]["verdict"] == "FAIL"                     # the gate is unchanged
    (s,) = rep["summaries"]
    assert s["model"] == "claude-haiku-5-5" and len(s["run_ids"]) == 3
    assert s["all_images"]["mean_sign_recall"] == pytest.approx(rep["gate"]["mean_sign_recall"])
    assert s["non_duplicate_images"]["images"] == 1
    d = s["by_draft_model"]
    assert set(d) == {"claude-opus-5-5", "claude-haiku-5-5"}
    assert d["claude-opus-5-5"]["mean_sign_recall"] == 1.0 and d["claude-opus-5-5"]["non_duplicate_images"] == 0
    assert d["claude-haiku-5-5"]["mean_sign_recall"] == pytest.approx(0.5)
    assert d["claude-haiku-5-5"]["gold_signs"] == 2 and d["claude-haiku-5-5"]["non_duplicate_images"] == 1


# ---------------------------------------------------------------- the gate refuses mixed configurations


def _relabel(path, out, **head):
    lines = path.read_text(encoding="utf-8").splitlines()
    h = json.loads(lines[0])
    h.update(head)
    out.write_text("\n".join([json.dumps(h)] + lines[1:]) + "\n", encoding="utf-8")
    return out


@pytest.mark.parametrize("change", [
    {"model": "claude-sonnet-5-5"},
    {"prompt_id": "scene/v3@000000000000"},
    {"fallback": {"tile": "scene/v4-tile@x", "crop": "scene/v4-crop@y"}},
    {"set": "T"},
])
def test_the_gate_refuses_runs_of_mixed_configurations(fake_set, change):
    outs = [pe.run("public_dev", "claude-haiku-5-5", 1.0, sdk=FakeSDK(2), out_dir=fake_set / "runs")
            for _ in range(3)]
    odd = _relabel(outs[2], fake_set / "odd.jsonl", run_id="odd", **change)
    with pytest.raises(SystemExit, match="one configuration; these files mix 2"):
        pe.score([outs[0], outs[1], odd])


def test_one_configuration_still_scores_and_a_header_without_fallback_is_off(fake_set):
    outs = [pe.run("public_dev", "claude-haiku-5-5", 1.0, sdk=FakeSDK(2), out_dir=fake_set / "runs")
            for _ in range(3)]
    explicit = _relabel(outs[2], fake_set / "off.jsonl", run_id="off", fallback=None)
    rep = pe.score([outs[0], outs[1], explicit])
    assert rep["gate"]["runs"] == 3 and rep["summaries"][0]["fallback"] is False


# ---------------------------------------------------------------- the fallback command (plan item 7)


def _pass1_run(fake_set, run_id="p1run"):
    """A hand-made pass-1 run on the fake set: a dense scene (5 signs, one low) per image."""
    signs = [{"id": f"s{k}", "code": "P.104", "confidence": "low" if k == 3 else "high",
              "shape": "circle", "border": "red", "background": "white",
              "position": {"rank_top_down": k, "side": "right", "box": [10 + 50 * k, 10, 40 + 50 * k, 40]}}
             for k in range(1, 6)]
    path = fake_set / f"public_dev_claude-haiku-5-5_v4_{run_id}.jsonl"
    head = {"run_id": run_id, "set": "public_dev", "model": "claude-haiku-5-5",
            "prompt_id": "scene/v4@153536ec5975", "gate": pe.GATE["name"], "started": "x"}
    rows = [{"image_id": i, "ok": True, "error": None, "retried": False, "cost_usd": 0.002, "reran": True,
             "issues": [], "raw_codes": {}, "scene": {"scene_id": "x", "signs": signs}}
            for i in ("public_test_1_1", "public_test_1_2")]
    path.write_text("\n".join(json.dumps(x) for x in [head, *rows]) + "\n", encoding="utf-8")
    return path


def test_the_fallback_command_adds_calls_and_marks_the_run(fake_set):
    p1 = _pass1_run(fake_set)
    sdk = FakeSDK(0)
    out = pe.fallback_run(p1, 1.0, sdk=sdk, out_dir=fake_set / "runs")
    head, rows = pe.load_run(out)
    from vqa.perception.fallback import CHOSEN_POLICY
    assert head["fallback"]["pass1_run"] == "p1run" and head["fallback"]["policy"] == CHOSEN_POLICY
    assert head["fallback"]["tile"].startswith("scene/v4-tile@") and head["run_id"] != "p1run"
    assert len(sdk.created) == 2 * (4 + 1)                    # per image: 4 tiles, 1 crop
    for r in rows:
        assert r["fallback_stats"]["tiled"] and r["fallback_stats"]["crops"] == 1
        assert r["cost_usd"] == pytest.approx(r["pass1_cost_usd"] + r["fallback_cost_usd"])
        assert len(r["fallback_replies"]) == 5
    with pytest.raises(SystemExit, match="already has the fallback"):
        pe.fallback_run(out, 1.0, sdk=sdk, out_dir=fake_set / "runs")


def test_a_replay_makes_no_call_and_checks_its_source(fake_set):
    p1 = _pass1_run(fake_set)
    first = pe.fallback_run(p1, 1.0, sdk=FakeSDK(0), out_dir=fake_set / "runs")
    again = pe.fallback_run(p1, 0.0, policy="never", replay=first, out_dir=fake_set / "runs")
    (h1, r1), (h2, r2) = pe.load_run(first), pe.load_run(again)
    assert h2["fallback"]["policy"] == "never" and h2["fallback"]["replayed_from"] == first.name
    assert all(r["fallback_cost_usd"] == 0.0 for r in r2)
    other = _pass1_run(fake_set, run_id="other")
    with pytest.raises(SystemExit, match="not a fallback run of other"):
        pe.fallback_run(other, 0.0, replay=first, out_dir=fake_set / "runs")


def test_the_gate_does_not_mix_pass1_and_fallback_runs(fake_set):
    p1 = _pass1_run(fake_set)
    out = pe.fallback_run(p1, 1.0, sdk=FakeSDK(0), out_dir=fake_set / "runs")
    with pytest.raises(SystemExit, match="fallback off .* fallback on|fallback on .* fallback off"):
        pe.score([p1, out])
    rep = pe.score([out])
    assert rep["summaries"][0]["fallback"] is True and rep["gate"]["runs"] == 1


def test_perceive_runs_the_fallback_only_when_asked(fake_set):
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard
    from vqa.perception.fallback import FallbackConfig
    from vqa.perception.scene import perceive
    img = fake_set / "public_test_1_1.jpg"
    sdk = FakeSDK(0)
    client = LLMClient(model="claude-haiku-5-5", guard=SpendGuard(1.0), sdk=sdk, run_id="t")
    plain = perceive(img, model="claude-haiku-5-5", version="v4", client=client, use_cache=False)
    assert plain.fallback is None and len(sdk.created) == 1
    fbres = perceive(img, model="claude-haiku-5-5", version="v4", client=client, use_cache=False,
                     fallback=FallbackConfig())
    assert fbres.fallback is not None and not fbres.fallback.tiled      # one sure sign: nothing to do
    assert fbres.scene == plain.scene and len(sdk.created) == 2


def test_compare_counts_fixed_and_broken_against_pass1(fake_set):
    p1 = _pass1_run(fake_set)
    out = pe.fallback_run(p1, 1.0, sdk=FakeSDK(0), out_dir=fake_set / "runs")
    rep = pe.compare(p1, [out])
    (x,) = rep["fallback"]
    from vqa.perception.fallback import CHOSEN_POLICY
    assert x["policy"] == CHOSEN_POLICY and x["images_tiled"] == 2 and x["crops"] == 2
    assert x["fixed_by_tiles"] + x["fixed_by_crops"] >= 0 and x["broken"] >= 0
    assert rep["pass1"]["run_id"] == "p1run"
    with pytest.raises(SystemExit, match="not a fallback run"):
        pe.compare(_pass1_run(fake_set, run_id="other"), [out])


def test_gold_status_marks_tp_wrong_miss_and_excluded():
    gold = [g("P.104", 1), g("P.112", 2, side="left"), g("P.123a", 3, readable=False), g("P.130", 4)]
    pred = [g("P.104", 1), g("P.106a", 2, side="left")]
    assert pe.gold_status(gold, pred) == ["tp", "wrong", None, "miss"]


def test_a_replay_skips_failed_attempts_and_the_cache_option_is_recorded(fake_set):
    p1 = _pass1_run(fake_set)
    out = pe.fallback_run(p1, 1.0, sdk=FakeSDK(0), out_dir=fake_set / "runs", use_cache=True)
    head, rows = pe.load_run(out)
    assert head["fallback"]["use_cache"] is True
    rows[0]["fallback_replies"].insert(0, {**rows[0]["fallback_replies"][-1], "raw_text": "prose", "failed": True})
    out.write_text("\n".join(json.dumps(x) for x in [head, *rows]) + "\n", encoding="utf-8")
    again = pe.fallback_run(p1, 0.0, replay=out, out_dir=fake_set / "runs")
    assert [r["scene"] for r in pe.load_run(again)[1]] == [r["scene"] for r in rows]


@pytest.mark.parametrize("where", ["fallback", "top"])
def test_score_refuses_a_public_dev_run_made_with_the_cache(fake_set, where):
    p1 = _pass1_run(fake_set)
    out = pe.fallback_run(p1, 1.0, sdk=FakeSDK(0), out_dir=fake_set / "runs", use_cache=True)
    if where == "top":                     # a header that says so at the top level
        head, rows = pe.load_run(out)
        head = {**head, "use_cache": True, "fallback": {**head["fallback"], "use_cache": False}}
        out.write_text("\n".join(json.dumps(x) for x in [head, *rows]) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="use_cache can't be scored; gate runs must be independent"):
        pe.score([out])


def test_a_set_t_run_made_with_the_cache_still_scores(fake_set):
    p1 = _pass1_run(fake_set)
    out = pe.fallback_run(p1, 1.0, sdk=FakeSDK(0), out_dir=fake_set / "runs", use_cache=True)
    head, rows = pe.load_run(out)
    t = fake_set / "t.jsonl"
    t.write_text("\n".join(json.dumps(x) for x in [{**head, "set": "T"}, *rows]) + "\n", encoding="utf-8")
    rep = pe.score([t])
    assert rep["runs"][0]["set"] == "T" and "gate" not in rep


def test_fallback_calibration_takes_shares_and_first_attempts_from_fresh_runs(fake_set, monkeypatch):
    log = fake_set / "api_calls.jsonl"
    fresh = {"run_id": "fresh", "fallback": {"use_cache": False}}
    rerun = {"run_id": "rerun", "fallback": {"use_cache": True}}
    for h in (fresh, rerun):
        (fake_set / f"{h['run_id']}.jsonl").write_text(json.dumps(h) + "\n", encoding="utf-8")
    lines = ([{"run_id": "fresh", "purpose": "scene tile", "status": "ok", "cost_usd": 0.01}] * 2
             + [{"run_id": "fresh", "purpose": "scene crop", "status": s, "cost_usd": 0.004}
                for s in ("ok", "bad_json", "ok", "bad_json")]
             + [{"run_id": "rerun", "purpose": "scene crop", "status": "bad_json", "cost_usd": 0.009}] * 2
             + [{"run_id": "rerun", "purpose": "scene crop retry", "status": "ok", "cost_usd": 0.002}] * 2)
    log.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(pe, "LOG", log)
    cal = pe.fallback_calibration([fake_set / "fresh.jsonl", fake_set / "rerun.jsonl"])
    assert cal["crop_retry_share"] == 0.5 and cal["crop_usd"] == pytest.approx(0.004)
    assert cal["crop_retry_usd"] == pytest.approx(0.002)
    assert cal["tile_retry_share"] == 0.0 and cal["tile_usd"] == pytest.approx(0.01)


# ---------------------------------------------------------------- raw replies in run files, warm (phase 4, P1)

def _dense(tag):
    """A dense pass-1 reply (5 signs, one low) so the re-run, tiles and a crop all run.
    `tag` moves the boxes, so two runs have different region keys."""
    return json.dumps({"signs": [{"code": "P.104", "shape": "circle", "border": "red", "background": "white",
                                  "rank": k, "side": "right", "confidence": "low" if k == 3 else "high",
                                  "box": [10 + 50 * k + tag, 10, 40 + 50 * k + tag, 40]}
                                 for k in range(1, 6)]})


class ReplySDK(FakeSDK):
    """Pass-1 calls (no "scene tile"/"crop" text) get `first`; tiles and crops get GOOD."""

    def __init__(self, first):
        super().__init__(0)
        self.first = first

    def create(self, **kw):
        r = super().create(**kw)
        r.content[0].text = self.first if len(self.created) <= 2 * 2 and _is_pass1(kw) else GOOD
        return r


def _is_pass1(kw):
    return "tile" not in json.dumps(kw["messages"][-1]["content"], ensure_ascii=False)[-400:].lower() \
        and "crop" not in json.dumps(kw["messages"][-1]["content"], ensure_ascii=False)[-400:].lower()


def _fb_run(fake_set, tag, sdk_first=None):
    from vqa.perception.fallback import FallbackConfig  # noqa: F401
    p1 = pe.run("public_dev", "claude-haiku-5-5", 1.0, sdk=ReplySDK(sdk_first or _dense(tag)),
                out_dir=fake_set / "runs", version="v4")
    return p1, pe.fallback_run(p1, 1.0, sdk=FakeSDK(0), out_dir=fake_set / "runs")


def test_a_run_keeps_its_raw_pass1_replies_and_the_fallback_carries_them(fake_set):
    p1, fb = _fb_run(fake_set, 0)
    for path in (p1, fb):
        head, rows = pe.load_run(path)
        for r in rows:
            assert r["replies"] and {x["pass"] for x in r["replies"]} <= {"first", "retry", "rerun"}
            assert set().union(*map(set, r["replies"])) <= {"pass", "raw_text", "stop_reason", "usage",
                                                            "cost_usd", "request_id"}
            assert "effort" in r
    # the score is unchanged by the new fields
    assert pe.score([fb])["summaries"][0]["fallback"] is True


def test_warm_rebuilds_the_runs_scenes_from_its_file_alone(fake_set):
    _, fb = _fb_run(fake_set, 0)
    import shutil
    shutil.rmtree(fake_set / "cache")                       # nothing left from the run itself
    rep = pe.warm_run(fb, fake_set / "warm")
    assert rep["ok"] and rep["mismatches"] == [] and rep["records"] > 2
    from vqa.perception.cache import RECORD_FIELDS, REPLY_FIELDS
    for f in (fake_set / "warm").glob("*/*.json"):            # warmed records: model outputs only
        data = json.loads(f.read_text())
        assert set(data) <= RECORD_FIELDS | {"box"}
        assert all(set(r) <= REPLY_FIELDS for r in data["replies"])
    assert json.loads((fake_set / "warm" / pe.WARM_MARKER).read_text())["run_id"] == rep["run_id"]


def _run_keys(fb):
    """Every cache key a run's file gives: pass-1 records and region records."""
    from vqa.perception import prompt as sp
    from vqa.perception.cache import region_key, scene_key
    head, rows = pe.load_run(fb)
    keys = set()
    for r in rows:
        sha = pe._sha256_file(pe.gs.image_path(r["image_id"], "public_dev"))
        keys.add(scene_key(sha, head["model"], r["effort"], head["prompt_id"]))
        for x in r["fallback_replies"]:
            v = pe._version_of(x["prompt_id"])
            keys.add(region_key(sha, head["model"], sp.effort_for(head["model"], v), x["prompt_id"], x["box"]))
    return keys


def test_warming_run_k_leaves_no_record_of_run_j(fake_set):
    _, fb_j = _fb_run(fake_set, 0)
    _, fb_k = _fb_run(fake_set, 7)                          # other boxes: other crop keys
    warm = fake_set / "warm"
    kj, kk = _run_keys(fb_j), _run_keys(fb_k)
    assert kj - kk                                          # some records only run j has
    pe.warm_run(fb_j, warm)
    on_disk = lambda: {f.stem for f in warm.glob("*/*.json")}
    assert on_disk() == kj
    assert pe.warm_run(fb_k, warm)["ok"]
    assert on_disk() == kk and not (on_disk() & (kj - kk))  # exactly run k's records


def test_warm_refuses_a_run_without_raw_replies_and_the_main_cache(fake_set, monkeypatch):
    p1 = _pass1_run(fake_set)                               # hand-made, pre-phase-4 shape
    with pytest.raises(SystemExit, match="keeps no raw pass-1 replies"):
        pe.warm_run(p1, fake_set / "warm")
    _, fb = _fb_run(fake_set, 0)
    import vqa.perception.cache as c
    monkeypatch.setattr(c, "CACHE_DIR", fake_set / "main")
    with pytest.raises(SystemExit, match="never writes into the main scene cache"):
        pe.warm_run(fb, fake_set / "main")


def test_backfill_copies_only_the_pass1_runs_own_replies(fake_set):
    p1, fb = _fb_run(fake_set, 0)
    head, rows = pe.load_run(fb)
    old = fake_set / "old_fb.jsonl"                          # the pre-phase-4 shape: no raw replies
    old.write_text("\n".join(json.dumps(x) for x in
                             [head, *[{k: v for k, v in r.items() if k not in ("replies", "effort")}
                                      for r in rows]]) + "\n")
    p1_id = head["fallback"]["pass1_run"]
    log = fake_set / "log.jsonl"
    log.write_text(json.dumps({"run_id": p1_id, "request_id": "r"}) + "\n")
    out = pe.backfill_raw(old, cache_dir=fake_set / "cache", log=log)
    _, back = pe.load_run(out)
    assert [r["replies"] for r in back] == [r["replies"] for r in rows]
    log.write_text(json.dumps({"run_id": "someone_else", "request_id": "r"}) + "\n")
    with pytest.raises(SystemExit, match="does not hold pass-1 run"):
        pe.backfill_raw(old, cache_dir=fake_set / "cache", log=log)
