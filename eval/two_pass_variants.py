"""Two free experiments on the two-pass trial (owner, 2026-11-16). No API call; nothing in
vqa/ changes. Built from stored run files only.

- **Trial minus UNKNOWN:** the trial's scenes with every sign whose code is UNKNOWN
  dropped (and its plates with it). Stands in for a read step that may answer "not a
  sign". Counts how many dropped signs matched a real (readable) gold sign: real signs
  this would lose.
- **Hybrid:** each frozen scene, plus only the trial signs that overlap no frozen sign
  (`vqa.perception.fallback.same_region`, the tile dedup's test, on the sent image's
  boxes) and were read with a catalog code. Frozen codes are kept for signs both found.
  An added sign takes its rank by box top (`place_ranks`, the tile rule) and keeps the
  trial's side. A trial sign with the same catalog row as a frozen sign that has no box
  is not added (no box to compare).
- **Frozen scenes:** public_dev: the scenes the frozen pipeline runs H1-H3 saw (their
  perception files warmed into a temporary cache and rebuilt with the current code, so
  T4 applies). Set T: the stored scenes of `d1ff09db5bf4` (its pass-1 file keeps no raw
  replies, so T4 is not applied there; T4 only drops some alternatives).
- **Engine-only replay:** each scene variant through the rule engine with stored
  programs, and the fallback trigger. public_dev: the stored parses of the frozen T4
  runs (H1-H3, 51 questions each). Set T: the train questions on set-T images that have
  a reviewed gold program (only these have a program without a parser call).
  Grading, free only where it can be exact:
  - an answer whose engine decision (verdict and value) and route are unchanged keeps
    its stored grade (public_dev);
  - a Yes/No rules answer is graded from the verdict (the writer opens with it;
    faithfulness 100%);
  - a question that stays with the fallback is assumed to keep its stored grade
    (assumption: the fallback reads the image; the scene graph is a hint);
  - everything else (a changed Natural QA rules answer, a question moved to or from the
    fallback without a Yes/No grade) is **ungraded**: reported with bounds (all wrong,
    all right) and an estimate at the measured accuracy of where it went.

    .venv/bin/python eval/two_pass_variants.py report > <file>
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_eval as ee  # noqa: E402
from eval import gold_signs as gs  # noqa: E402
from eval import parser_eval as pev  # noqa: E402
from eval import perception_eval as pe  # noqa: E402
from eval import two_pass_trial as tp  # noqa: E402
from vqa.kb import Catalog, load_catalog  # noqa: E402
from vqa.perception.fallback import place_ranks, same_region  # noqa: E402
from vqa.perception.matching import match, row_of  # noqa: E402
from vqa.schemas import SceneGraph  # noqa: E402

RUNS = pe.RUNS
TRIAL = {"T": "T_claude-haiku-5-5_v5trial_8fa0b31b88cb.jsonl",
         "public_dev": "public_dev_claude-haiku-5-5_v5trial_37386c61f54d.jsonl"}
FROZEN_T = "T_claude-haiku-5-5_v4+fb_d1ff09db5bf4.jsonl"
# The frozen pipeline's last public_dev runs (T4) and the perception files their scenes came from.
H_RUNS = {"H1": ("public_dev_replay_T4-H1_2a108f86371b.jsonl", "public_dev_claude-haiku-5-5_v4+fb_9981d8112688.withraw.jsonl"),
          "H2": ("public_dev_replay_T4-H2_3c127f06d946.jsonl", "public_dev_claude-haiku-5-5_v4+fb_1c9ca7368074.jsonl"),
          "H3": ("public_dev_replay_T4-H3_c8880835ee4a.jsonl", "public_dev_claude-haiku-5-5_v4+fb_b490cd60479f.jsonl")}
# Measured accuracies used only for the estimate of ungraded answers (public_dev, tuned, T4).
RULES_ACC, FALLBACK_ACC = 0.888, 0.780
# Per-image perception cost as a real pipeline (DESIGN section 3; the trial's measured cost).
USD_PER_IMAGE = {"frozen": 0.0028, "trial": 0.0014, "trial_minus_unknown": 0.0014, "hybrid": 0.0028 + 0.0014}
FALLBACK_USD = 0.008          # one answer-level fallback call (Sonnet), phase 4
WRITER_USD = 0.0003

# ---------------------------------------------------------------- scenes


def _scenes_of(path: Path) -> dict[str, SceneGraph]:
    _, rows = pe.load_run(path)
    return {r["image_id"]: SceneGraph.model_validate(r["scene"]) for r in rows if r["scene"] is not None}


def frozen_scenes_public_dev(path: Path) -> dict[str, SceneGraph]:
    """The frozen pipeline's scenes for one H run: its perception file warmed into a
    temporary cache, every scene rebuilt with the current code (T4) and no call."""
    from vqa.perception.fallback import FallbackConfig
    from vqa.perception.scene import perceive

    head, rows = pe.load_run(path)
    split_of = dict(pe.set_images(head["set"]))
    out = {}
    with tempfile.TemporaryDirectory(prefix="vqa_variants_warm_") as d:
        pe.warm_run(path, Path(d))
        from vqa.perception.cache import SceneCache
        cache = SceneCache(Path(d))
        cfg = FallbackConfig(policy=head["fallback"]["policy"])
        for r in rows:
            res = perceive(gs.image_path(r["image_id"], split_of[r["image_id"]]), model=head["model"],
                           version=pe._version_of(head["prompt_id"]), client=pe._NoCalls(head["model"]),
                           cache=cache, use_cache=True, fallback=cfg)
            if res.scene is not None:
                out[r["image_id"]] = res.scene
    return out


def minus_unknown(scene: SceneGraph) -> tuple[SceneGraph, list[int]]:
    """The scene without its UNKNOWN signs; returns the dropped signs' indices."""
    drop = [k for k, s in enumerate(scene.signs) if s.code == "UNKNOWN"]
    keep = [s for k, s in enumerate(scene.signs) if k not in drop]
    return scene.model_copy(update={"signs": keep}), drop


def hybrid(frozen: SceneGraph, trial: SceneGraph, width: int, catalog: Catalog) -> tuple[SceneGraph, dict[str, int]]:
    """The frozen scene plus trial signs with a catalog code that overlap no frozen sign."""
    boxes = [tuple(s.position.box) for s in frozen.signs if s.position.box is not None]
    no_box_rows = {row_of(s.code, catalog) for s in frozen.signs if s.position.box is None} - {None}
    added, c = [], Counter()
    for s in trial.signs:
        if s.code == "UNKNOWN" or row_of(s.code, catalog) is None:
            c["skipped_unknown"] += 1
            continue
        b = s.position.box
        if b is None:
            c["skipped_no_box"] += 1
            continue
        if any(same_region(tuple(b), p) for p in boxes):
            c["skipped_overlap"] += 1
            continue
        if row_of(s.code, catalog) in no_box_rows:
            c["skipped_same_row_as_unboxed_frozen"] += 1
            continue
        added.append(s)
        c["added"] += 1
    if not added:
        return frozen, dict(c)
    tops = [None if s.position.box is None else float(s.position.box[1]) for s in frozen.signs]
    n = len(frozen.signs)
    renamed = [s.model_copy(update={"id": f"s{n + k + 1}"}) for k, s in enumerate(added)]
    placed = place_ranks(list(frozen.signs), tops, [(s, float(s.position.box[1])) for s in renamed], width)
    sides = {s.id: s.position.side for s in renamed}
    placed = [s.model_copy(update={"position": s.position.model_copy(update={"side": sides[s.id]})})
              if s.id in sides else s for s in placed]
    return frozen.model_copy(update={"signs": placed}), dict(c)


# ---------------------------------------------------------------- perception scores


def units_of(scenes: dict[str, SceneGraph], gold: dict, catalog: Catalog) -> dict[str, dict]:
    return {i: pe.score_image(gold[i]["signs"], [s.model_dump(mode="json", by_alias=True) for s in sc.signs], catalog)
            for i, sc in scenes.items()}


def table(set_name: str, per_run: list[dict[str, dict]]) -> dict[str, Any]:
    ids = list(per_run[0])
    nd = pe.non_duplicate(set_name, ids)
    pick = lambda m: {k: m.get(k) for k in ("runs", "images", "mean_sign_recall", "sign_recall_ci95",  # noqa: E731
                                           "mean_sign_code_f1", "sign_code_f1_ci95", "mean_sign_code_f1_strict",
                                           "mean_sign_code_f1_rule_bearing", "mean_value_accuracy", "mean_predicted")}
    return {"all_images": pick(pe.summarise(per_run, ids)),
            "non_duplicate_images": pick(pe.summarise(per_run, [i for i in ids if i in nd]))}


def error_counts(scenes: dict[str, SceneGraph], gold: dict, catalog: Catalog) -> dict[str, int]:
    c: Counter = Counter()
    for i, sc in scenes.items():
        pred = [s.model_dump(mode="json", by_alias=True) for s in sc.signs]
        for st in tp.classify(gold[i]["signs"], pred, catalog):
            if st is not None:
                c[st["status"]] += 1
        matched = {j for _, j in match([pe._view(g) for g in gold[i]["signs"]], [pe._view(p) for p in pred], catalog)}
        c["false_positive"] += sum(j not in matched for j in range(len(pred)))
    return dict(c)


def lost_real_signs(trial: dict[str, SceneGraph], gold: dict, catalog: Catalog) -> dict[str, int]:
    """Of the UNKNOWN signs dropped, how many the gate's matching pairs with a readable
    gold sign (real signs lost), with an excluded gold sign (unreadable or a local notice:
    neutral), or with nothing (false positives removed)."""
    c: Counter = Counter()
    for i, sc in trial.items():
        g = gold[i]["signs"]
        pred = [s.model_dump(mode="json", by_alias=True) for s in sc.signs]
        by_pred = {j: k for k, j in match([pe._view(x) for x in g], [pe._view(p) for p in pred], catalog)}
        for j, p in enumerate(pred):
            if p["code"] != "UNKNOWN":
                continue
            c["dropped"] += 1
            if j not in by_pred:
                c["false_positive_removed"] += 1
            elif pe.excluded(g[by_pred[j]]):
                c["matched_excluded_gold"] += 1
            else:
                c["matched_real_gold_sign"] += 1
    return dict(c)


# ---------------------------------------------------------------- engine-only replay


def _decision(a) -> tuple:
    return (a.verdict.value, json.dumps(a.value, sort_keys=True, default=str, ensure_ascii=False))


def engine_run(engine, scene: SceneGraph | None, program, parse_status: str | None):
    from vqa.answer.fallback import trigger
    from vqa.reasoning.engine import EngineError

    ans, err = None, False
    if scene is not None and parse_status == "ok":
        try:
            ans = engine.answer(scene, program)
        except EngineError:
            err = True
    why = trigger(scene_ok=scene is not None, parse_status=parse_status, answer=ans, engine_error=err)
    return ans, why


def _yes_no_grade(verdict: str, gold_text: str) -> float:
    g = ee.yes_no(gold_text)
    pred = {"yes": True, "no": False}.get(verdict)
    return float(pred is not None and pred == g)


def compare_answers(questions: list[dict], base: dict[str, SceneGraph], variant: dict[str, SceneGraph],
                    engine) -> dict[str, Any]:
    """questions: {id, image_id, question_type, answer, program, parse_status, stored: {trigger,
    decision, correct} or None}. The baseline's route and decision come from running the
    engine on `base`; its grade is the stored one when given."""
    c: Counter = Counter()
    moved: Counter = Counter()
    graded_delta, ungraded, est = 0.0, [], 0.0
    for q in questions:
        b_ans, b_why = engine_run(engine, base.get(q["image_id"]), q["program"], q["parse_status"])
        v_ans, v_why = engine_run(engine, variant.get(q["image_id"]), q["program"], q["parse_status"])
        stored = q.get("stored")
        b_grade = stored["correct"] if stored else None
        if b_grade is None and q["question_type"] == "Yes/No" and b_why is None:
            b_grade = _yes_no_grade(b_ans.verdict.value, q["answer"])
        same_route = (b_why is None) == (v_why is None)
        same = same_route and (b_why is not None or _decision(b_ans) == _decision(v_ans))
        c["questions"] += 1
        if same:
            c["unchanged"] += 1
            continue
        c["changed"] += 1
        if b_why is None and v_why is not None:
            c["to_fallback"] += 1
            moved[v_why] += 1
        elif b_why is not None and v_why is None:
            c["to_rules"] += 1
        else:
            c["rules_decision_changed"] += 1
        # the variant's grade, where free and exact
        v_grade = None
        if v_why is None and q["question_type"] == "Yes/No":
            v_grade = _yes_no_grade(v_ans.verdict.value, q["answer"])
        if v_grade is not None and b_grade is not None:
            graded_delta += v_grade - b_grade
            c["graded"] += 1
        else:
            ungraded.append((b_grade, v_why))
            acc = FALLBACK_ACC if v_why is not None else RULES_ACC
            est += acc - (b_grade if b_grade is not None else acc)
    lo = graded_delta + sum(-(b if b is not None else 1.0) for b, _ in ungraded)
    hi = graded_delta + sum(1.0 - (b if b is not None else 0.0) for b, _ in ungraded)
    return {**dict(c), "to_fallback_by_trigger": dict(moved), "ungraded": len(ungraded),
            "net_correct_graded": graded_delta, "net_correct_bounds": [lo, hi],
            "net_correct_estimate": graded_delta + est}


def public_dev_questions(h_file: Path) -> list[dict]:
    """The frozen run's 51 public_dev questions with their stored parses and grades."""
    from vqa.schemas import QueryProgram

    dev = {q["id"]: q for q in ee.load_dev()}
    _, rows = ee.load(h_file)
    out = []
    for r in rows:
        p = r["trace"].get("parser") or {}
        out.append({"id": r["id"], "image_id": r["image_id"], "question_type": r["question_type"],
                    "answer": dev[r["id"]]["answer"], "parse_status": p.get("status"),
                    "program": QueryProgram.model_validate(p["program"]) if p.get("program") else None,
                    "stored": {"correct": r["correct"], "trigger": r["trigger"], "engine_verdict": r["engine_verdict"]}})
    return out


def set_t_questions() -> list[dict]:
    """Train questions on set-T images that have a reviewed gold program."""
    gold = {g["id"]: g for g in pev.load_gold() if g["split"] == "train"}
    t = set(gs.set_t_images())
    rows = json.loads(gs.TRAIN_QA.read_text(encoding="utf-8"))
    return [{"id": q["id"], "image_id": q["image_id"], "question_type": q["question_type"], "answer": q["answer"],
             "parse_status": "ok", "program": pev.gold_query(gold[q["id"]]["program"]), "stored": None}
            for q in rows if q["image_id"] in t and q["id"] in gold]


def check_baseline(questions: list[dict], scenes: dict[str, SceneGraph], engine) -> dict[str, int]:
    """The engine on the rebuilt frozen scenes reproduces the stored route and verdict."""
    c: Counter = Counter()
    for q in questions:
        ans, why = engine_run(engine, scenes.get(q["image_id"]), q["program"], q["parse_status"])
        s = q["stored"]
        c["same"] += (why == s["trigger"]) and ((ans.verdict.value if ans else None) == s["engine_verdict"] or why in
                                                ("out_of_scope", "parse_failed"))
        c["n"] += 1
    return dict(c)


def _sum_dicts(ds: list[dict]) -> dict:
    keys = {k for d in ds for k in d}
    out = {}
    for k in keys:
        vals = [d.get(k, 0) for d in ds]
        if all(isinstance(v, dict) for v in vals):
            out[k] = dict(sum((Counter(v) for v in vals), Counter()))
        elif all(isinstance(v, list) for v in vals):
            out[k] = [sum(v[0] for v in vals), sum(v[1] for v in vals)]
        else:
            out[k] = sum(vals)
    return out


# ---------------------------------------------------------------- the report


def report() -> dict[str, Any]:
    from vqa.reasoning.engine import Engine

    gold, catalog = pe.gold_rows(), load_catalog()
    engine = Engine()
    out: dict[str, Any] = {"note": ("No API call. One trial run per set; Haiku's code F1 varies about 2.9 points "
                                    "between runs. Set T is the main evidence for perception; public_dev is tuned.")}
    for s in ("T", "public_dev"):
        _, trows = pe.load_run(RUNS / TRIAL[s])
        trial = _scenes_of(RUNS / TRIAL[s])
        width = {r["image_id"]: r["sent_size"][0] for r in trows}
        if s == "T":
            frozen_runs = {"frozen": _scenes_of(RUNS / FROZEN_T)}
        else:
            frozen_runs = {h: frozen_scenes_public_dev(RUNS / p) for h, (_, p) in H_RUNS.items()}
        minus, hybrids, hstats = {}, {}, Counter()
        for i, sc in trial.items():
            minus[i] = minus_unknown(sc)[0]
        for h, fz in frozen_runs.items():
            hybrids[h] = {}
            for i, sc in fz.items():
                hybrids[h][i], st = hybrid(sc, trial[i], width[i], catalog) if i in trial else (sc, {})
                hstats.update(st)
        n_runs = len(frozen_runs)
        variants = {
            "frozen": [units_of(v, gold, catalog) for v in frozen_runs.values()],
            "trial": [units_of(trial, gold, catalog)],
            "trial_minus_unknown": [units_of(minus, gold, catalog)],
            "hybrid": [units_of(v, gold, catalog) for v in hybrids.values()],
        }
        rep: dict[str, Any] = {"label": "tuned" if s == "public_dev" else "development",
                               "frozen_scenes": (FROZEN_T + " (stored, pre-T4)") if s == "T"
                               else {h: p for h, (_, p) in H_RUNS.items()}}
        rep["perception"] = {k: table(s, v) for k, v in variants.items()}
        rep["errors"] = {"frozen": _mean_counts([error_counts(v, gold, catalog) for v in frozen_runs.values()]),
                         "trial": error_counts(trial, gold, catalog),
                         "trial_minus_unknown": error_counts(minus, gold, catalog),
                         "hybrid": _mean_counts([error_counts(v, gold, catalog) for v in hybrids.values()])}
        rep["minus_unknown_dropped"] = lost_real_signs(trial, gold, catalog)
        rep["hybrid_signs"] = {k: v / n_runs for k, v in hstats.items()}
        # engine-only replay
        if s == "T":
            qs = set_t_questions()
            base = frozen_runs["frozen"]
            ans = {k: compare_answers(qs, base, v, engine) for k, v in
                   (("trial", trial), ("trial_minus_unknown", minus), ("hybrid", hybrids["frozen"]))}
            rep["answers"] = {"questions": len(qs), "programs": "reviewed gold programs (train)",
                              "frozen_rules_yes_no": _route(qs, base, engine), **ans}
        else:
            per_h = {}
            for h, (hf, _) in H_RUNS.items():
                qs = public_dev_questions(RUNS.parent / "e2e" / hf)
                base = frozen_runs[h]
                per_h[h] = {"baseline_check": check_baseline(qs, base, engine),
                            "trial": compare_answers(qs, base, trial, engine),
                            "trial_minus_unknown": compare_answers(qs, base, minus, engine),
                            "hybrid": compare_answers(qs, base, hybrids[h], engine)}
            rep["answers"] = {"questions_per_run": 51, "runs": list(per_h), "programs": "stored parses of the frozen runs",
                              "baseline_check": _sum_dicts([p["baseline_check"] for p in per_h.values()]),
                              **{k: _sum_dicts([p[k] for p in per_h.values()])
                                 for k in ("trial", "trial_minus_unknown", "hybrid")}}
        rep["cost_per_image_usd"] = USD_PER_IMAGE
        out[s] = rep
    return out


def _route(qs, scenes, engine) -> dict[str, int]:
    c: Counter = Counter()
    for q in qs:
        a, why = engine_run(engine, scenes.get(q["image_id"]), q["program"], q["parse_status"])
        c[why or "rules"] += 1
        if why is None and q["question_type"] == "Yes/No":
            c["rules_yes_no_correct"] += _yes_no_grade(a.verdict.value, q["answer"])
    return dict(c)


def _mean_counts(ds: list[dict]) -> dict[str, float]:
    keys = {k for d in ds for k in d}
    return {k: statistics.mean(d.get(k, 0) for d in ds) for k in sorted(keys)}


def main() -> None:
    print(json.dumps(report(), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
