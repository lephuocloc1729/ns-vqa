"""Phase-4 item 4: the judge, the public_dev end-to-end eval (warm, run, next), the
oracles, scoring, and the aggregate-only holdout run. Fake SDK, hand-made images,
questions and gold; no API call and no dataset file."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

import eval.e2e_eval as ee
import eval.e2e_holdout as eh
import eval.judge as judge
import eval.perception_eval as pe
from vqa.llm.client import LLMClient
from vqa.llm.spend import SpendGuard
from vqa.schemas import SceneGraph

JUDGE_SHA = "7c500c35df277ba23e7f0cf39ab66e6bca81c84f13a4ea6316f52d2ff9426c57"

SCENE_REPLY = json.dumps({"signs": [{"code": "P.104", "shape": "circle", "border": "red", "background": "white",
                                     "rank": 1, "side": "right", "confidence": "high"}],
                          "road": {"type": "urban"}, "vehicles": []})


class RoutedSDK:
    """Replies by role (system prompt prefix); `default` replies when a role's list is empty."""

    def __init__(self, default=None, **replies):
        self.replies = {k: list(v) for k, v in replies.items()}
        self.default = default or {}
        self.created: list[str] = []
        self.messages = self

    @staticmethod
    def role(kw) -> str:
        s = kw["system"][0]["text"]
        for prefix, role in (("You write the final answer", "writer"),
                             ("You answer Vietnamese questions", "fallback"),
                             ("You grade answers", "judge"),
                             ("# Task\n\nYou turn one Vietnamese question", "parser")):
            if s.startswith(prefix):
                return role
        return "perception"

    def count_tokens(self, **kw):
        return SimpleNamespace(input_tokens=3000)

    def create(self, **kw):
        role = self.role(kw)
        self.created.append(role)
        lst = self.replies.get(role) or []
        text = lst.pop(0) if lst else self.default[role]
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
                               stop_details=None, _request_id="req_t",
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=80,
                                                     cache_read_input_tokens=2000, cache_creation_input_tokens=0))


# ---------------------------------------------------------------- judge

def test_judge_is_pinned_opus():
    assert judge.prompt_id("v1") == "judge/v1@" + JUDGE_SHA[:12], "judge prompt changed: make a new version"
    assert judge.config("v1")["model"] == "claude-opus-5-5"                 # D4
    assert (judge.SCORES["partial"], judge.STRICT["partial"]) == (0.5, 0.0)


def _judge(replies, tmp_path, monkeypatch):
    monkeypatch.setenv("VQA_LOG_DIR", str(tmp_path / "logs"))
    sdk = RoutedSDK(judge=replies)
    return judge.Judge(llm=LLMClient(model="claude-opus-5-5", sdk=sdk, guard=SpendGuard(1.0))), sdk


def test_judge_grades_and_retries(tmp_path, monkeypatch):
    j, _ = _judge([{"label": "partial", "reason": "one window missing"}], tmp_path, monkeypatch)
    v = j.grade("Khung giờ nào?", "Từ 6:30 đến 8:00 và từ 16:30 đến 18:30.", "Từ 6:30 đến 8:00.")
    assert (v.label, v.score, v.strict) == ("partial", 0.5, 0.0)
    j, sdk = _judge(["prose", {"label": "correct", "reason": "ok"}], tmp_path, monkeypatch)
    assert j.grade("q", "a", "a").label == "correct" and sdk.created == ["judge", "judge"]
    j, _ = _judge(["prose", "prose"], tmp_path, monkeypatch)
    assert j.grade("q", "a", "b").label == "error"
    j, sdk = _judge([], tmp_path, monkeypatch)
    assert j.grade("q", "a", "  ").label == "wrong" and sdk.created == []


# ---------------------------------------------------------------- helpers

def test_yes_no_mapping():
    assert [ee.yes_no(t) for t in ("Đúng.", "ĐÚNG", "Có", "Được đi.", "Sai", "SAI.", "Không", "Không được phép.",
                                   "Làn 1.", "")] == [True, True, True, True, False, False, False, False, None, None]


def test_gold_scene_keeps_unreadable_signs_as_unknown_and_drops_local_notices():
    row = {"image_id": "x", "signs": [
        {"id": "s1", "code": "P.104", "readable": True, "shape": "circle", "border": "red", "background": "white",
         "position": {"rank_top_down": 1, "side": "right"}},
        {"id": "s2", "code": "P.127", "readable": False, "shape": "circle", "border": "red", "background": "white",
         "position": {"rank_top_down": 2, "side": "right"}},
        {"id": "s3", "code": "UNKNOWN", "readable": True, "local_notice": "KHU VỰC CẤM ĐỖ", "shape": "rectangle",
         "border": "none", "background": "blue", "position": {"rank_top_down": 3, "side": "right"}}]}
    sc = ee.gold_scene(row)
    assert [(s.id, s.code) for s in sc.signs] == [("s1", "P.104"), ("s2", "UNKNOWN")]


def test_load_dev_reads_public_dev_only(tmp_path):
    split = {"public_dev": {"questions": ["q1"], "images": ["i1"]}, "public_holdout": {"questions": ["q2"], "images": ["i2"]}}
    pub = [{"id": "q1", "question": "a?", "image_id": "i1", "question_type": "Yes/No", "answer": "Có", "relevant_articles": []},
           {"id": "q2", "question": "b?", "image_id": "i2", "question_type": "Yes/No", "answer": "Có", "relevant_articles": []}]
    (tmp_path / "s.json").write_text(json.dumps(split))
    (tmp_path / "p.json").write_text(json.dumps(pub))
    assert [q["id"] for q in ee.load_dev(tmp_path / "p.json", tmp_path / "s.json")] == ["q1"]


# ---------------------------------------------------------------- summarize, gate, rules

def rec(i, qt="Yes/No", correct=1.0, trigger=None, writer="first_try", verdict="yes", engine="yes", **kw):
    return {"id": f"q{i}", "image_id": f"public_test_9_{i}", "question_type": qt, "correct": correct,
            "strict": correct if correct != 0.5 else 0.0, "trigger": trigger,
            "writer_status": writer, "verdict": verdict, "engine_verdict": engine, "cost_usd": 0.01,
            "seconds": 1.0, **kw}


def test_summarize_reports_coverage_rules_only_faithfulness_and_templates():
    rs = [rec(1), rec(2, correct=0.0, writer="template"),
          rec(3, qt="Natural QA", correct=0.5, verdict="value", engine="value", judge_label="partial"),
          rec(4, trigger="unknown", writer=None, verdict="no", engine="unknown", fallback_status="ok")]
    s = ee.summarize(rs)
    assert s["rule_coverage"] == 0.75 and s["rules_only_score"] == pytest.approx(1.5 / 3)
    assert s["overall"] == pytest.approx(2.5 / 4) and s["overall_strict"] == pytest.approx(2 / 4)
    assert s["natural_qa_score"] == 0.5 and s["natural_qa_strict"] == 0.0
    assert s["fallback_by_trigger"] == {"unknown": 1} and s["writer_answers"] == 3
    assert s["template_rate"] == pytest.approx(1 / 3) and s["faithfulness"] == 1.0
    assert "ci95" in s["by_images"]["non_duplicate_images"]


def test_gate_needs_faithfulness_and_at_most_5_percent_templates():
    ok = [rec(i) for i in range(40)]
    assert ee.gate(ok)["pass"]
    many_templates = ok[:-3] + [rec(100 + i, writer="template") for i in range(3)]   # 7.5%
    assert not ee.gate(many_templates)["pass"]
    unfaithful = ok[:-1] + [rec(200, verdict="no", engine="yes")]
    assert not ee.gate(unfaithful)["pass"]


def test_perception_rule_d2():
    assert ee.perception_rule([0.60, 0.62, 0.61], 0.67)["step6_perception"] == "claude-sonnet-5-5"
    assert ee.perception_rule([0.60, 0.62, 0.61], 0.65)["step6_perception"] == "claude-haiku-5-5"   # < mean + 5
    assert ee.perception_rule([0.55, 0.70, 0.55], 0.69)["step6_perception"] == "claude-haiku-5-5"   # not > best


def test_attribution(tmp_path):
    def write(name, rows):
        p = tmp_path / name
        p.write_text("\n".join(json.dumps(x) for x in [{"label": name, "kind": name}, *rows]) + "\n")
        return p
    pipe = write("p", [rec(1, correct=0.0), rec(2, correct=0.0), rec(3, correct=0.0), rec(4), rec(5, correct=0.0)])
    a = write("a", [rec(1), rec(2), rec(3, correct=0.0), rec(4)])
    b = write("b", [rec(1), rec(2, correct=0.0), rec(3, correct=0.0), rec(4)])
    out = ee.attribution(pipe, a, b)
    assert out["per_question"] == {"q1": "parser", "q2": "perception", "q3": "rules_writer_or_fallback",
                                   "q5": "no_gold_program"}


# ---------------------------------------------------------------- warm, run, next (fake set)

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
    return tmp_path


QS = [{"id": "q1", "image_id": "public_test_1_1", "question_type": "Yes/No",
       "question": "Xe máy có bị cấm đi vào đường này không?", "answer": "Có"},
      {"id": "q2", "image_id": "public_test_1_2", "question_type": "Natural QA",
       "question": "Biển trong ảnh có ý nghĩa gì?", "answer": "Cấm xe máy."}]


def _perception_run(fake_set):
    sdk = RoutedSDK(default={"perception": SCENE_REPLY})
    p1 = pe.run("public_dev", "claude-haiku-5-5", 1.0, sdk=sdk, out_dir=fake_set / "runs", version="v4")
    return pe.fallback_run(p1, 1.0, sdk=sdk, out_dir=fake_set / "runs")


def _e2e_sdk():
    return RoutedSDK(parser=[{"program": {"intent": "forbidden", "action": "enter",
                                          "vehicle": {"vehicle_class": "motorbike"}}},
                             {"program": {"intent": "meaning", "sign": {"only": True}}}],
                     writer=[{"verdict": "yes", "answer": "Có. Biển P.104 (Cấm xe máy).", "cited_signs": ["s1"],
                              "cited_rules": ["r_prohibition"]},
                             {"verdict": "value", "answer": "Cấm xe máy.", "cited_signs": ["s1"], "cited_rules": []}],
                     judge=[{"label": "correct", "reason": "same meaning"}])


def test_run_warms_then_runs_the_pipeline_cache_only(fake_set):
    fb = _perception_run(fake_set)
    sdk = _e2e_sdk()
    out = ee.run_pipeline(fb, "H1", 1.0, sdk=sdk, warm_dir=fake_set / "warm", out_dir=fake_set / "e2e", questions=QS)
    head, rows = ee.load(out)
    assert head["kind"] == "pipeline" and head["scenes_from"] == pe.load_run(fb)[0]["run_id"]
    assert head["writer"].startswith("answer/v3@") and head["judge"].startswith("judge/v1@")
    assert "perception" not in sdk.created                               # cache-only: no perception call
    assert [(r["answered_by"], r["verdict"], r["correct"]) for r in rows] == [("rules", "yes", 1.0),
                                                                           ("rules", "value", 1.0)]
    assert rows[1]["judge_label"] == "correct"
    s = ee.summarize(rows)
    assert s["rule_coverage"] == 1.0 and s["overall"] == 1.0


def test_one_run_at_a_time(fake_set):
    fb1, fb2 = _perception_run(fake_set), _perception_run(fake_set)
    warm = fake_set / "warm"
    rep1, _ = ee._warm(fb1, warm)
    ee._check_still_warm(rep1)
    ee._warm(fb2, warm)                                                  # someone warmed another run
    with pytest.raises(SystemExit, match="one at a time"):
        ee._check_still_warm(rep1)


def test_oracles_never_go_through_answer(fake_set, monkeypatch):
    import vqa.pipeline as pl

    def boom(*a, **k):
        raise AssertionError("oracle called the pipeline")
    monkeypatch.setattr(pl.Pipeline, "answer", boom)
    monkeypatch.setattr(pl, "answer", boom)
    scene = SceneGraph.model_validate({"scene_id": "g", "signs": [
        {"id": "s1", "code": "P.104", "shape": "circle", "border": "red", "background": "white",
         "position": {"rank_top_down": 1, "side": "right"}}]})
    monkeypatch.setattr(ee, "gold_scenes", lambda: {"public_test_1_1": scene, "public_test_1_2": scene})
    from eval.parser_eval import gold_query
    monkeypatch.setattr(ee, "gold_programs", lambda: {
        "q1": gold_query({"program": {"intent": "forbidden", "action": "enter", "vehicle": {"vehicle_class": "motorbike"}}})})
    sdk = RoutedSDK(writer=[{"verdict": "yes", "answer": "Có.", "cited_signs": ["s1"], "cited_rules": []}])
    out = ee.run_oracle("A", "O", 1.0, sdk=sdk, out_dir=fake_set / "e2e", questions=QS)
    head, rows = ee.load(out)
    assert head["kind"] == "oracleA" and [r["id"] for r in rows] == ["q1"]        # q2: no gold program
    assert rows[0]["correct"] == 1.0 and "parser" not in sdk.created
    fb = _perception_run(fake_set)
    sdk = RoutedSDK(writer=[{"verdict": "yes", "answer": "Có.", "cited_signs": ["s1"], "cited_rules": []}])
    out = ee.run_oracle("B", "H1", 1.0, warm_file=fb, warm_dir=fake_set / "warm", sdk=sdk,
                        out_dir=fake_set / "e2e", questions=QS)
    assert ee.load(out)[1][0]["correct"] == 1.0 and "perception" not in sdk.created


# ---------------------------------------------------------------- holdout (aggregate only)

def CLEAN():
    return {"commit": "c0ffee", "clean": True, "dirty": []}


def test_holdout_refuses_without_the_freeze(tmp_path):
    with pytest.raises(SystemExit, match="confirm-frozen"):
        eh.run_holdout(1.0, perception_model="claude-haiku-5-5")


def test_holdout_writes_only_an_aggregate_file(fake_set, capsys):
    qs = [dict(q, id=f"secret_q_{i}", image_id=q["image_id"]) for i, q in enumerate(QS)]
    sdk = _e2e_sdk()
    sdk.replies["perception"] = [SCENE_REPLY, SCENE_REPLY]
    out_dir = fake_set / "holdout_out"
    out = eh.run_holdout(1.0, perception_model="claude-haiku-5-5", confirm_frozen=True, sdk=sdk, questions=qs,
                         out_dir=out_dir, image_path=lambda i: fake_set / f"{i}.jpg",
                         sentinel=fake_set / "sentinel.json", git=CLEAN)
    assert [p.name for p in out_dir.iterdir()] == [out.name]
    text = out.read_text()
    printed = capsys.readouterr().out
    for q in qs:
        for field in ("id", "question", "answer"):
            assert q[field] not in text and q[field] not in printed
        assert q["image_id"] not in text and q["image_id"] not in printed
    rep = json.loads(text)
    assert rep["questions"] == 2 and rep["overall"] == 1.0 and "ci95" in rep["by_images"]["non_duplicate_images"]
    assert "perception" in sdk.created                                   # fresh perception, no warm cache
