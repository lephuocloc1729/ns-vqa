"""Rules-only figures and the causes of non-decided questions (owner, 2026-11-16). No API call.

The report counts rule-based answers only. A question is **decided** when the rules
answer it (verdict yes / no / value: the fallback trigger is None); unknown, uncertain,
out_of_scope, parse failures and programs that cannot run are not decided.

- `figures`: decided coverage, accuracy on decided answers, and overall with every
  non-decided question counted wrong, for the public_dev T4 runs (H1-H3), public_holdout
  (from its aggregate report only: no per-question data), and oracle A (gold scenes and
  gold programs through today's engine).
- `causes`: the non-decided public_dev T4 question-runs by cause (per question is allowed
  on public_dev). For uncertain answers, the sign whose alternative flips the answer and
  where that alternative came from (pass 1's own `alt`, the re-run, or a crop that
  replaced pass 1's code); for unreadable signs, the code or look; for other unknowns,
  the check that stayed unknown; for out_of_scope, the parser's reason.
- `validation_pool`: train questions on untouched images (not in set T, gold signs, gold
  intents, few-shots, prompt examples, fixtures, tests, kb or audits, and in no
  duplicate group with public, private or an excluded train image).
- `trial_effect`: decided coverage of the two-pass trial variants on the same questions.

    .venv/bin/python eval/coverage_analysis.py > <file>
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_eval as ee  # noqa: E402
from eval import gold_signs as gs  # noqa: E402
from eval import parser_eval as pev  # noqa: E402
from eval import perception_eval as pe  # noqa: E402
from eval import two_pass_variants as tv  # noqa: E402
from eval.report import DUPLICATES, score_report, wilson_ci  # noqa: E402

E2E = ROOT / "eval" / "runs" / "e2e"
HOLDOUT_AGGREGATE = E2E / "holdout_aggregate_0ec3209c0324.json"
ORACLE_A = E2E / "public_dev_oracleA_O_5f0160f4bd7c.jsonl"
DECIDED = ("yes", "no", "value")

# ---------------------------------------------------------------- figures


def decided_summary(rows: list[dict], split: str = "public") -> dict[str, Any]:
    """rows: {image_id, decided, correct (0..1, or None if not graded)}."""
    n = len(rows)
    dec = [r for r in rows if r["decided"]]
    graded = [r for r in dec if r["correct"] is not None]
    right = sum(r["correct"] for r in graded)
    as_wrong = [{"image_id": r["image_id"], "correct": (r["correct"] or 0.0) if r["decided"] else 0.0} for r in rows]
    rep = score_report(as_wrong, split)
    nd_ids = {r["image_id"] for r in rows} - _dup(split)
    nd_dec = [r for r in graded if r["image_id"] in nd_ids]
    return {"questions": n, "decided": len(dec), "coverage": len(dec) / n if n else None,
            "coverage_ci95": list(wilson_ci(len(dec), n)) if n else None,
            "accuracy_on_decided": right / len(graded) if graded else None, "decided_graded": len(graded),
            "accuracy_on_decided_ci95": list(wilson_ci(right, len(graded))) if graded else None,
            "overall_non_decided_wrong": right / n if n else None,
            "non_duplicate": {"questions": rep["non_duplicate_images"]["n"],
                              "overall_non_decided_wrong": rep["non_duplicate_images"]["accuracy"],
                              "overall_ci95": rep["non_duplicate_images"]["ci95"],
                              "decided": len([r for r in dec if r["image_id"] in nd_ids]),
                              "accuracy_on_decided": (sum(r["correct"] for r in nd_dec) / len(nd_dec)) if nd_dec else None}}


def _dup(split: str) -> set[str]:
    from eval.report import duplicated_images
    return duplicated_images(split)


def h_rows(h_file: Path) -> list[dict]:
    _, rows = ee.load(h_file)
    return [{"id": r["id"], "image_id": r["image_id"], "question_type": r["question_type"],
             "decided": r["trigger"] is None and r["engine_verdict"] in DECIDED, "correct": r["correct"],
             "trigger": r["trigger"]} for r in rows]


def holdout_figures() -> dict[str, Any]:
    """From the aggregate report only (no per-question data exists)."""
    d = json.loads(HOLDOUT_AGGREGATE.read_text(encoding="utf-8"))
    n, dec = d["questions"], d["rules_only_n"]
    right = d["rules_only_score"] * dec
    return {"questions": n, "decided": dec, "coverage": d["rule_coverage"], "coverage_ci95": list(wilson_ci(dec, n)),
            "accuracy_on_decided": d["rules_only_score"], "accuracy_on_decided_ci95": list(wilson_ci(right, dec)),
            "overall_non_decided_wrong": right / n, "overall_ci95": list(wilson_ci(right, n)),
            "not_decided_by_trigger": d["fallback_by_trigger"],
            "non_duplicate": "not available: the aggregate splits by image only for all answers, rules and fallback together",
            "fallback_failed": d.get("fallback_failed")}


def oracle_a_figures(engine) -> dict[str, Any]:
    """Gold scenes + gold programs through today's engine on every public_dev question.
    A question without a gold program is not decided. Grades: Yes/No from the verdict;
    Natural QA from the stored oracle A run when its engine verdict is the same."""
    scenes, programs = ee.gold_scenes(), ee.gold_programs()
    _, stored = ee.load(ORACLE_A)
    st = {r["id"]: r for r in stored}
    rows, c = [], Counter()
    for q in ee.load_dev():
        p = programs.get(q["id"])
        if p is None:
            rows.append({"image_id": q["image_id"], "decided": False, "correct": None})
            c["no_gold_program"] += 1
            continue
        ans, why = tv.engine_run(engine, scenes.get(q["image_id"]), p, "ok")
        decided = why is None and ans.verdict.value in DECIDED
        c[why or "decided"] += 1
        correct = None
        if decided and q["question_type"] == "Yes/No":
            correct = tv._yes_no_grade(ans.verdict.value, q["answer"])
        elif decided and (s := st.get(q["id"])) and s.get("engine_verdict") == ans.verdict.value \
                and s.get("trigger") is None:
            correct = s["correct"]
        elif decided:
            c["decided_ungraded"] += 1
        rows.append({"image_id": q["image_id"], "decided": decided, "correct": correct})
    out = decided_summary(rows)
    out["routes"] = dict(c)
    out["note"] = ("today's engine and gold (0094 decided, ea5b0a8); Natural QA grades from the stored oracle A run "
                   "(writer answer/v2) where the engine verdict is unchanged; ungraded decided answers are left out of "
                   "accuracy and counted wrong in overall")
    return out


def figures(engine) -> dict[str, Any]:
    per = {h: decided_summary(h_rows(E2E / f)) for h, (f, _) in tv.H_RUNS.items()}
    pooled = decided_summary([r for h, (f, _) in tv.H_RUNS.items() for r in h_rows(E2E / f)])
    return {"public_dev_T4": {"label": "tuned", "per_run": per, "pooled_3_runs": pooled},
            "public_holdout": holdout_figures(), "oracle_A": oracle_a_figures(engine)}


# ---------------------------------------------------------------- causes


def rebuilt(path: Path) -> dict[str, tuple[Any, list[str]]]:
    """{image: (scene, issues)} for one H run's perception file, rebuilt with T4, no call."""
    import tempfile

    from vqa.perception.cache import SceneCache
    from vqa.perception.fallback import FallbackConfig
    from vqa.perception.scene import perceive

    head, rows = pe.load_run(path)
    split_of = dict(pe.set_images(head["set"]))
    out = {}
    with tempfile.TemporaryDirectory(prefix="vqa_cov_warm_") as d:
        pe.warm_run(path, Path(d))
        cache = SceneCache(Path(d))
        cfg = FallbackConfig(policy=head["fallback"]["policy"])
        for r in rows:
            res = perceive(gs.image_path(r["image_id"], split_of[r["image_id"]]), model=head["model"],
                           version=pe._version_of(head["prompt_id"]), client=pe._NoCalls(head["model"]),
                           cache=cache, use_cache=True, fallback=cfg)
            out[r["image_id"]] = (res.scene, res.issues)
    return out


def decisive_signs(engine, scene, program) -> list[tuple[str, str, str]]:
    """(sign id, primary code, alternative code) whose alternative alone changes the
    primary reading's answer."""
    first = engine.answer(scene.model_copy(update={"signs": [s.model_copy(update={"alternatives": []})
                                                             for s in scene.signs]}), program)
    out = []
    for s in scene.signs:
        if not s.alternatives or s.confidence.value == "high":
            continue
        for a in s.alternatives:
            sc = scene.model_copy(update={"signs": [
                (x.model_copy(update={"code": a.code, "value": a.value if a.value is not None else x.value,
                                      "alternatives": []}) if x.id == s.id else x.model_copy(update={"alternatives": []}))
                for x in scene.signs]})
            b = engine.answer(sc, program)
            if tv._decision(b) != tv._decision(first):
                out.append((s.id, s.code, a.code))
    return out


def alt_source(code: str, alt: str, issues: list[str]) -> str:
    if any(i.endswith(f"crop read {code}; replaces {alt}") or f"crop read {code}; replaces {alt}" in i for i in issues):
        return "crop (crop's code first, pass 1's reading kept as the alternative)"
    if any(f"the re-run read {alt}" in i for i in issues):
        return "re-run"
    return "pass 1's own alt"


def causes(engine) -> dict[str, Any]:
    from vqa.schemas import Verdict

    catalog = engine.catalog
    out: dict[str, Any] = {"question_runs": 0, "not_decided": 0, "by_cause": Counter(), "uncertain_source": Counter(),
                           "uncertain_pairs": Counter(), "unreadable": Counter(), "unknown_checks": Counter(),
                           "out_of_scope_reasons": Counter(), "parse_failed": Counter(), "cannot_run": Counter(),
                           "per_question": defaultdict(lambda: {"runs_not_decided": 0, "causes": Counter()})}
    for h, (hf, pf) in tv.H_RUNS.items():
        scenes = rebuilt(pe.RUNS / pf)
        for q in tv.public_dev_questions(E2E / hf):
            out["question_runs"] += 1
            sc, issues = scenes.get(q["image_id"], (None, []))
            ans, why = tv.engine_run(engine, sc, q["program"], q["parse_status"])
            if why is None and ans.verdict.value in DECIDED:
                continue
            out["not_decided"] += 1
            cause = why or "decided_but_not_yes_no_value"
            out["by_cause"][cause] += 1
            pq = out["per_question"][q["id"]]
            pq["runs_not_decided"] += 1
            pq["causes"][cause] += 1
            pq["question_type"] = q["question_type"]
            if why == "uncertain":
                dec = decisive_signs(engine, sc, q["program"])
                if not dec:
                    out["uncertain_source"]["only a combination of alternatives changes it"] += 1
                for sid, code, alt in dec[:1]:
                    out["uncertain_source"][alt_source(code, alt, issues)] += 1
                    out["uncertain_pairs"][f"{code} vs {alt}"] += 1
            elif why == "unreadable_sign":
                for sid in ans.uncertain_signs:
                    s = sc.sign(sid)
                    kind = ("UNKNOWN" if s.code == "UNKNOWN" else
                            "not in catalog" if not catalog.has(s.code) else "effect_unmodelled")
                    out["unreadable"][f"{kind}: {s.code} ({engine.visual_category(s)})"] += 1
            elif why == "unknown":
                details = [r.detail or "?" for r in ans.reasons if r.truth == "unknown"]
                out["unknown_checks"][(" | ".join(sorted(set(details))) or ans.note or "no reason given")[:160]] += 1
            elif why == "out_of_scope":
                p = q["program"]
                out["out_of_scope_reasons"][(getattr(p, "out_of_scope_reason", None) or "?")[:160]] += 1
            elif why == "parse_failed":
                out["parse_failed"][q["id"]] += 1
            elif why == "program_cannot_run":
                out["cannot_run"][(ans.note if ans else "engine error")[:160] if ans else "engine error"] += 1
    out["distinct_questions_not_decided_in_any_run"] = len(out["per_question"])
    out["distinct_questions_not_decided_in_all_3_runs"] = sum(v["runs_not_decided"] == 3 for v in out["per_question"].values())
    out["per_question"] = {k: {"runs_not_decided": v["runs_not_decided"], "question_type": v.get("question_type"),
                               "causes": dict(v["causes"])} for k, v in sorted(out["per_question"].items())}
    for k, v in list(out.items()):
        if isinstance(v, Counter):
            out[k] = dict(v.most_common())
    _ = Verdict
    return out


# ---------------------------------------------------------------- the validation pool

_IMG = re.compile(r"train_\d+_\d+")
_QID = re.compile(r"train_\d+(?![_\d])")
SCAN = ["prompts", "eval/prompts", "tests", "kb", "eval/audits", "docs", "tools"]


def mentioned(paths=SCAN) -> tuple[set[str], set[str]]:
    """Train image ids and question ids named in any text file under `paths`."""
    imgs, qids = set(), set()
    for d in paths:
        for p in (ROOT / d).rglob("*"):
            if p.is_file() and p.suffix in (".py", ".md", ".json", ".jsonl", ".yaml", ".yml", ".pl", ".txt", ".csv"):
                t = p.read_text(encoding="utf-8", errors="ignore")
                imgs |= set(_IMG.findall(t))
                qids |= set(_QID.findall(t))
    return imgs, qids


def pool() -> tuple[list[str], list[dict], dict[str, set[str]]]:
    """(pool image ids, their questions as {id, image_id, question_type}, excluded images by
    reason). Reads ids and types only."""
    rows = [{k: q[k] for k in ("id", "image_id", "question_type")}
            for q in json.loads(gs.TRAIN_QA.read_text(encoding="utf-8"))]
    img_of = {q["id"]: q["image_id"] for q in rows}
    all_imgs = {q["image_id"] for q in rows}
    excluded: dict[str, set[str]] = {}
    excluded["set_T"] = set(gs.set_t_images())
    excluded["gold_signs"] = {r["image_id"] for r in pe.gold_rows().values() if r.get("split") == "train"}
    excluded["gold_intents"] = {img_of[g["id"]] for g in pev.load_gold() if g["split"] == "train" and g["id"] in img_of}
    m_imgs, m_qids = mentioned()
    named = (m_imgs & all_imgs) | {img_of[q] for q in m_qids if q in img_of}
    # The dev set is readable question by question (owner, 2026-11-17), so tests and docs may
    # name its ids. Those names don't move the pool the frozen splits were drawn from.
    dev_file = ROOT / "data" / "splits" / "train_dev.json"
    if dev_file.exists():
        named -= set(json.loads(dev_file.read_text(encoding="utf-8"))["images"])
    excluded["named_in_repo"] = named
    dup = json.loads(DUPLICATES.read_text(encoding="utf-8"))
    out_imgs = set().union(*excluded.values())
    with_test = set()
    for g in dup["groups"]:
        if {"public", "private"} & set(g["splits"]):
            with_test |= {i["image_id"] for i in g["images"] if i["split"] == "train"}
    excluded["duplicate_with_public_or_private"] = with_test
    near = set()
    for g in dup["groups"]:
        tr = {i["image_id"] for i in g["images"] if i["split"] == "train"}
        if tr & out_imgs:
            near |= tr
    excluded["duplicate_of_an_excluded_train_image"] = near - out_imgs
    bad = set().union(*excluded.values())
    pool_imgs = sorted(all_imgs - bad)
    return pool_imgs, [q for q in rows if q["image_id"] in set(pool_imgs)], excluded


def validation_pool() -> dict[str, Any]:
    pool_imgs, pool_qs, excluded = pool()
    rows = json.loads(gs.TRAIN_QA.read_text(encoding="utf-8"))
    all_imgs = {q["image_id"] for q in rows}
    bad = set().union(*excluded.values())
    return {"train_images": len(all_imgs), "train_questions": len(rows),
            "excluded_images": {k: len(v) for k, v in excluded.items()}, "excluded_total": len(bad),
            "pool_images": len(pool_imgs), "pool_questions": len(pool_qs),
            "pool_question_types": dict(Counter(q["question_type"] for q in pool_qs)),
            "note": "train_284 (invalid citation) is not special here: citations are not scored"}


# ---------------------------------------------------------------- the two-pass trial's effect


def trial_effect(engine) -> dict[str, Any]:
    from eval.two_pass_variants import _scenes_of, frozen_scenes_public_dev, hybrid, minus_unknown

    catalog = engine.catalog
    _, trows = pe.load_run(pe.RUNS / tv.TRIAL["public_dev"])
    trial = _scenes_of(pe.RUNS / tv.TRIAL["public_dev"])
    width = {r["image_id"]: r["sent_size"][0] for r in trows}
    minus = {i: minus_unknown(s)[0] for i, s in trial.items()}
    res: dict[str, Counter] = defaultdict(Counter)
    for h, (hf, pf) in tv.H_RUNS.items():
        frozen = frozen_scenes_public_dev(pe.RUNS / pf)
        hyb = {i: hybrid(s, trial[i], width[i], catalog)[0] if i in trial else s for i, s in frozen.items()}
        for q in tv.public_dev_questions(E2E / hf):
            for name, scenes in (("frozen", frozen), ("trial", trial), ("trial_minus_unknown", minus), ("hybrid", hyb)):
                ans, why = tv.engine_run(engine, scenes.get(q["image_id"]), q["program"], q["parse_status"])
                res[name]["question_runs"] += 1
                res[name]["decided" if why is None else why] += 1
    return {k: {**dict(v), "coverage": v["decided"] / v["question_runs"]} for k, v in res.items()}


def main() -> None:
    from vqa.reasoning.engine import Engine

    engine = Engine()
    out = {"note": "No API call. public_dev is tuned; public_holdout from its aggregate only.",
           "figures": figures(engine), "causes": causes(engine), "validation_pool": validation_pool(),
           "trial_effect_public_dev_153_question_runs": trial_effect(engine),
           "what_if": what_if(engine), "oracle_A_gaps": oracle_a_gaps(engine)}
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))



# ---------------------------------------------------------------- what-ifs (engine-side levers, measured free)


def _strip_alts(scene):
    return scene.model_copy(update={"signs": [s.model_copy(update={"alternatives": []}) for s in scene.signs]})


def _drop_unreadable(scene, catalog):
    return scene.model_copy(update={"signs": [s for s in scene.signs if catalog.has(s.code)
                                              and not catalog.get(s.code).effect_unmodelled]})


def what_if(engine) -> dict[str, Any]:
    """On the public_dev T4 question-runs not decided because of perception:
    - uncertain -> decide on the primary reading (alternatives ignored);
    - unreadable_sign -> decide with unreadable / unmodelled signs left out (closed world).
    Graded exactly for Yes/No (from the verdict); for Natural QA, a proxy: the decision
    equals oracle A's (gold scene, gold program) and oracle A's answer was graded right."""
    catalog = engine.catalog
    gscenes, gprog = ee.gold_scenes(), ee.gold_programs()
    _, stored = ee.load(ORACLE_A)
    ograde = {r["id"]: r["correct"] for r in stored}
    out: dict[str, Counter] = defaultdict(Counter)
    for h, (hf, pf) in tv.H_RUNS.items():
        scenes = rebuilt(pe.RUNS / pf)
        for q in tv.public_dev_questions(E2E / hf):
            sc, _ = scenes.get(q["image_id"], (None, []))
            _, why = tv.engine_run(engine, sc, q["program"], q["parse_status"])
            if why not in ("uncertain", "unreadable_sign"):
                continue
            alt = _strip_alts(sc) if why == "uncertain" else _drop_unreadable(sc, catalog)
            ans, why2 = tv.engine_run(engine, alt, q["program"], q["parse_status"])
            c = out[why]
            c["question_runs"] += 1
            if why2 is not None or ans.verdict.value not in DECIDED:
                c[f"still_not_decided ({why2})"] += 1
                continue
            c["decided"] += 1
            if q["question_type"] == "Yes/No":
                c["yes_no"] += 1
                c["yes_no_right"] += tv._yes_no_grade(ans.verdict.value, q["answer"])
            else:
                c["natural_qa"] += 1
                if q["id"] in gprog and q["image_id"] in gscenes:
                    oa, ow = tv.engine_run(engine, gscenes[q["image_id"]], gprog[q["id"]], "ok")
                    if ow is None and tv._decision(oa) == tv._decision(ans):
                        c["natural_qa_same_as_oracle_A"] += 1
                        c["natural_qa_same_as_oracle_A_and_graded_right"] += (ograde.get(q["id"]) or 0) >= 1.0
                else:
                    c["natural_qa_no_oracle"] += 1
    return {k: dict(v) for k, v in out.items()}


def oracle_a_gaps(engine) -> dict[str, Any]:
    """Oracle A's non-decided public_dev questions: why, with gold scene and gold program."""
    scenes, programs = ee.gold_scenes(), ee.gold_programs()
    out = {}
    for q in ee.load_dev():
        p = programs.get(q["id"])
        if p is None:
            out[q["id"]] = "no gold program (the gold file skips it)"
            continue
        ans, why = tv.engine_run(engine, scenes.get(q["image_id"]), p, "ok")
        if why is None and ans.verdict.value in DECIDED:
            continue
        det = sorted({r.detail for r in ans.reasons if r.truth == "unknown" and r.detail}) if ans else []
        intent = getattr(getattr(p, "program", None), "intent", None) or type(getattr(p, "program", p)).__name__
        out[q["id"]] = f"{why}; intent {intent}; " + ("; ".join(det)[:200] or (ans.note or "")[:200] if ans else "")
    return out


if __name__ == "__main__":
    main()
