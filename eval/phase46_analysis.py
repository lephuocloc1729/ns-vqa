"""Phase 4.6 diagnosis (owner, 2026-11-17): free analyses behind docs/plans/phase-4.6.md. No API call.

    .venv/bin/python eval/phase46_analysis.py calibrate       # set T: is the first reading right when perception lists alternatives?
    .venv/bin/python eval/phase46_analysis.py uncertain [-v]  # dev replay of uncertain-reading policies
    .venv/bin/python eval/phase46_analysis.py step1           # step 1 guardrail: the engine's policy A on all dev
    .venv/bin/python eval/phase46_analysis.py step4           # step 4 replays: dev and D3 cached scenes (indicative)
    .venv/bin/python eval/phase46_analysis.py trainset        # the biased train working set and its cost estimate
    .venv/bin/python eval/phase46_analysis.py oos             # out-of-scope wording groups (dev records, train text)

Data rules (CLAUDE.md):
- dev (`data/splits/train_dev.json`) is read question by question, from the stored records
  `eval/runs/e2e/dev_candidate_7caed6170de6.jsonl` and `dev_reparse_v9_8bbb5eb01cff.jsonl`;
- set T is train (gold signs v1, owner-reviewed); public_dev runs are not used;
- the validation split file is read for its **question and image ids only**, to leave them
  out; no validation question, image, answer or result is read;
- holdout, private and gold intents are not touched.

The working set (`trainset`) is train minus dev minus validation. It is **biased**: its images
fed the few-shots, the stage-A sign list and the rules, so it is for diagnosis only, never a score.
"""

from __future__ import annotations

import argparse
import hashlib
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

E2E = ROOT / "eval" / "runs" / "e2e"
CANDIDATE_RUN = E2E / "dev_candidate_7caed6170de6.jsonl"
REPARSE_RUN = E2E / "dev_reparse_v9_8bbb5eb01cff.jsonl"
PROVISIONAL = E2E / "phase46_provisional_grades.json"      # local, assistant-graded against the dev answer
SPLITS = ROOT / "data" / "splits"
SET_T_RUNS = sorted((ROOT / "eval" / "runs" / "perception").glob("T_claude-haiku-5-5_v[45]+fb_*.jsonl"))
DECIDED = ("yes", "no", "value")
RANK = {"high": 3, "medium": 2, "low": 1}


def _jsonl(p: Path) -> tuple[dict, list[dict]]:
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[0], rows[1:]


def _ids(name: str) -> dict:
    """A split file's ids. For the validation split only the id lists are used (to exclude them)."""
    d = json.loads((SPLITS / name).read_text(encoding="utf-8"))
    return {"questions": set(d["questions"]), "images": set(d["images"])}


# ---------------------------------------------------------------- 1a. calibration on set T

def _family(code: str | None, cat) -> str | None:
    if not code or code == "UNKNOWN":
        return None
    try:
        return cat.get(code).code
    except Exception:
        return code


def calibrate(runs: list[Path] = SET_T_RUNS) -> dict[str, Any]:
    """For every predicted sign with alternatives (confidence below high), whether the first
    reading or an alternative matches a gold code on the same image (family level). A coarse
    image-level match, enough to see whether the first reading is the better bet."""
    from vqa.kb import load_catalog
    cat = load_catalog()
    gold = {g["image_id"]: g for g in (json.loads(x) for x in gs.GOLD.read_text(encoding="utf-8").splitlines() if x.strip())}
    tally: dict[str, Counter] = defaultdict(Counter)
    for p in runs:
        _, rows = _jsonl(p)
        for r in rows:
            g = gold.get(r["image_id"])
            if not g or not r.get("scene"):
                continue
            codes = {_family(s["code"], cat) for s in g["signs"] if s.get("readable", True) and "local_notice" not in s}
            codes.discard(None)
            for s in r["scene"]["signs"]:
                alts = s.get("alternatives") or []
                if not alts or s.get("confidence") == "high":
                    continue
                prim = _family(s["code"], cat)
                alt_f = [_family(a["code"], cat) for a in alts]
                unknown_alt = any(a["code"] == "UNKNOWN" for a in alts)
                p_hit, a_hit = prim in codes, any(f in codes for f in alt_f if f)
                key = f"first={s['confidence']}" + (" alt=UNKNOWN" if unknown_alt else "")
                tally[key]["signs"] += 1
                tally[key]["first_only" if p_hit and not a_hit else "alt_only" if a_hit and not p_hit
                           else "both" if p_hit else "neither"] += 1
    return {"runs": [p.name for p in runs], "by_first_confidence": {k: dict(v) for k, v in sorted(tally.items())}}


# ---------------------------------------------------------------- 1b. uncertain policies on dev

def _pick(scene, policy: str):
    """The scene with each low/medium-confidence sign's readings narrowed by the policy.
    - `higher_confidence`: keep only the highest-confidence reading; a tie keeps the first
      (perception's own choice). Every sign ends with one reading, so nothing stays uncertain.
    - `first_unless_tied_low` (the variant): readable over UNKNOWN (an UNKNOWN alternative is
      dropped, as single-sign questions already drop unreadable candidates); then a reading
      is kept only if it has the top confidence. Readings tied at the top stay, so the engine
      still reports uncertain when tied readings disagree (low against low).
    - `alternative_when_first_low` (for comparison): readable over UNKNOWN; a medium first
      reading is kept, a low one gives way to its first alternative (set T's calibration).
    """
    sc = scene.model_copy(deep=True)
    for s in sc.signs:
        if not s.alternatives or s.confidence.value == "high":
            continue
        opts = [(s.code, s.value, s.confidence.value, None)] + [(a.code, a.value, a.confidence.value, a) for a in s.alternatives]
        if policy == "first_unless_tied_low":
            readable = [o for o in opts if o[0] != "UNKNOWN"]
            opts = readable or opts
        if policy == "alternative_when_first_low":
            # set T: a low first reading loses to its alternative (see `calibrate`); medium keeps it
            readable = [o for o in opts if o[0] != "UNKNOWN"] or opts
            win = readable[0] if RANK[readable[0][2]] >= 2 or len(readable) == 1 else readable[1]
            if win[3] is not None:
                s.code, s.value = win[0], win[1] if win[1] is not None else s.value
                s.confidence = win[3].confidence
            s.alternatives = []
            continue
        top = max(RANK[o[2]] for o in opts)
        keep = [o for o in opts if RANK[o[2]] == top]
        if policy == "higher_confidence":
            keep = keep[:1]
        first = keep[0]
        if first[3] is not None:                         # an alternative wins: it becomes the reading
            s.code, s.value = first[0], first[1] if first[1] is not None else s.value
            s.confidence = first[3].confidence
        s.alternatives = [o[3] for o in keep[1:] if o[3] is not None]
    return sc


def _decision(ans) -> str:
    v = {"verdict": ans.verdict.value, "value": ans.value} if ans is not None else None
    return hashlib.sha256(json.dumps(v, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()[:12]


def uncertain(policies=("higher_confidence", "first_unless_tied_low", "alternative_when_first_low"), run: Path = REPARSE_RUN,
              verbose: bool = False) -> dict[str, Any]:
    from vqa.answer.fallback import trigger
    from vqa.reasoning.engine import Engine, EngineError
    from vqa.schemas import QueryProgram, SceneGraph
    eng = Engine()
    _, rows = _jsonl(run)
    prov = json.loads(PROVISIONAL.read_text(encoding="utf-8")) if PROVISIONAL.exists() else {}
    qa = {q["id"]: q for q in json.loads(gs.TRAIN_QA.read_text(encoding="utf-8"))}
    n = len(rows)
    base_dec = [r for r in rows if r["decided"]]
    base_right = sum(r["correct"] or 0 for r in base_dec)
    out = {"run": run.name, "questions": n,
           "current": {"decided": len(base_dec), "coverage": len(base_dec) / n,
                       "accuracy_on_decided": base_right / len(base_dec), "overall": base_right / n}}
    for pol in policies:
        dec, right, newly, lost = 0, 0.0, [], []
        for r in rows:
            p = r["trace"].get("parser") or {}
            if r["trigger"] != "uncertain":              # only answers the readings left uncertain can change
                if r["decided"]:
                    dec += 1
                    right += r["correct"] or 0
                continue
            scene = _pick(SceneGraph.model_validate(r["scene"]), pol)
            prog = QueryProgram.model_validate(p["program"])
            try:
                ans, err = eng.answer(scene, prog), False
            except EngineError:
                ans, err = None, True
            why = trigger(scene_ok=True, parse_status=p.get("status"), answer=ans, engine_error=err)
            d = _decision(ans)
            if why is None and ans.verdict.value in DECIDED:
                g = (prov.get(r["id"]) or {}).get(d)
                dec += 1
                right += g["grade"] if g else 0
                newly.append({"id": r["id"], "decision": d, "provisional_grade": g["grade"] if g else None,
                              "why": g["why"] if g else None,
                              **({"question": qa[r["id"]]["question"], "answer": qa[r["id"]]["answer"],
                                  "value": ans.value} if verbose else {})})
            else:
                lost.append({"id": r["id"], "still": why})
        ungraded = [x["id"] for x in newly if x["provisional_grade"] is None]
        out[pol] = {"decided": dec, "coverage": dec / n,
                    "accuracy_on_decided": right / dec if dec else None, "overall": right / n,
                    "newly_decided": newly, "still_not_decided": lost, "ungraded": ungraded}
    out["judge_estimate"] = judge_estimate(max(len(out[p]["newly_decided"]) for p in policies))
    return out


def judge_estimate(k: int, run: Path = CANDIDATE_RUN) -> dict[str, Any]:
    """Writer + judge per newly decided Natural QA answer, at the candidate dev run's measured rates."""
    _, rows = _jsonl(run)
    dec = [r for r in rows if r["decided"]]
    w = sum(((r["trace"].get("writer") or {}).get("cost_usd") or 0) for r in dec) / len(dec)
    j = sum((r.get("judge_cost_usd") or 0) for r in dec) / len(dec)
    return {"answers": k, "writer_per_answer": round(w, 5), "judge_per_answer": round(j, 5),
            "total_usd": round(k * (w + j), 3), "range_usd": [round(0.8 * k * (w + j), 3), round(1.5 * k * (w + j), 3)]}


def step1(run: Path = REPARSE_RUN) -> dict[str, Any]:
    """Step 1's guardrail replay: every dev question through `Engine(reading_policy="higher_confidence")`
    on the stored scenes and v9 parses. An answer whose decision is unchanged keeps its stored grade;
    a changed one takes its provisional grade (or is listed as ungraded and counted wrong)."""
    from vqa.answer.fallback import trigger
    from vqa.reasoning.engine import Engine, EngineError
    from vqa.schemas import QueryProgram, SceneGraph
    eng = Engine(reading_policy="higher_confidence")
    _, rows = _jsonl(run)
    prov = json.loads(PROVISIONAL.read_text(encoding="utf-8")) if PROVISIONAL.exists() else {}
    dec, right, changed, ungraded, causes = 0, 0.0, [], [], Counter()
    for r in rows:
        p = r["trace"].get("parser") or {}
        scene = SceneGraph.model_validate(r["scene"]) if r.get("scene") else None
        ans, err = None, False
        if scene is not None and p.get("status") == "ok":
            try:
                ans = eng.answer(scene, QueryProgram.model_validate(p["program"]))
            except EngineError:
                err = True
        why = trigger(scene_ok=scene is not None, parse_status=p.get("status"), answer=ans, engine_error=err)
        decided = why is None and ans is not None and ans.verdict.value in DECIDED
        old = r.get("engine_answer")
        same = decided == r["decided"] and (not decided or _decision(ans) == hashlib.sha256(json.dumps(
            {"verdict": old["verdict"], "value": old.get("value")}, sort_keys=True, default=str,
            ensure_ascii=False).encode()).hexdigest()[:12])
        if not decided:
            causes[why] += 1
            if not same:
                changed.append({"id": r["id"], "was": "decided", "now": why})
            continue
        dec += 1
        g = r["correct"] if same else ((prov.get(r["id"]) or {}).get(_decision(ans)) or {}).get("grade")
        if not same:
            changed.append({"id": r["id"], "was": r["trigger"] or "decided", "now": "decided",
                            "provisional_grade": g, "basis": ans.basis})
        if g is None:
            ungraded.append(r["id"])
        else:
            right += g
    n = len(rows)
    return {"run": run.name, "policy": "higher_confidence", "questions": n, "decided": dec,
            "coverage": dec / n, "accuracy_on_decided": right / dec if dec else None,
            "overall_non_decided_wrong": right / n, "not_decided_by_cause": dict(causes),
            "changed": changed, "ungraded": ungraded,
            "guardrail": {"overall_floor": 0.6264367816091954, "accuracy_floor": 0.70,
                          "kept": right / n >= 0.6264367816091954 and (right / dec if dec else 0) >= 0.70}}


def _hand(path: Path) -> dict[str, Any]:
    """Hand-written programs in wire format, converted and validated as the parser would."""
    from vqa.parsing.wire import from_wire, to_query
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: to_query(from_wire(v), 2025) for k, v in d.items() if not k.startswith("_")}


def _run_one(eng, scene, q, trigger):
    from vqa.reasoning.engine import EngineError
    if q.out_of_scope:
        return None, "out_of_scope"
    try:
        ans, err = eng.answer(scene, q), False
    except EngineError:
        ans, err = None, True
    return ans, trigger(scene_ok=True, parse_status="ok", answer=ans, engine_error=err)


def step4(dev_programs: Path = E2E / "dev_v10_handprograms.json",
          d3_programs: Path = ROOT / "eval" / "runs" / "trainset" / "d3_v10_handprograms.json",
          d3_run: Path = ROOT / "eval" / "runs" / "trainset" / "trainset_yesno_821164d62679.jsonl") -> dict[str, Any]:
    """Step 4's free engine-only replays (indicative): policy A, F1, F2, I1-I4 with hand-written
    v10-style programs for the out-of-scope questions; every other question keeps its stored parse.
    Dev: grades are stored ones, or provisional ones for changed answers (PROVISIONAL, by id and
    decision). D3 (biased): its cached-scene questions, graded by the yes/no mapping."""
    from vqa.answer.fallback import trigger
    from vqa.reasoning.engine import Engine
    from vqa.schemas import QueryProgram, SceneGraph
    eng = Engine(reading_policy="higher_confidence")
    prov = json.loads(PROVISIONAL.read_text(encoding="utf-8")) if PROVISIONAL.exists() else {}
    qa = {q["id"]: q for q in json.loads(gs.TRAIN_QA.read_text(encoding="utf-8"))}
    # dev
    hand = _hand(dev_programs)
    _, rows = _jsonl(REPARSE_RUN)
    dec, right, changed, ungraded, causes = 0, 0.0, [], [], Counter()
    for r in rows:
        p = r["trace"].get("parser") or {}
        q = hand.get(r["id"]) or (QueryProgram.model_validate(p["program"]) if p.get("program") else None)
        scene = SceneGraph.model_validate(r["scene"])
        if q is None:
            ans, why = None, r["trigger"]
        else:
            ans, why = _run_one(eng, scene, q, trigger)
        decided = why is None and ans is not None and ans.verdict.value in DECIDED
        d = _decision(ans) if ans is not None else None
        old = r.get("engine_answer")
        old_d = hashlib.sha256(json.dumps({"verdict": old["verdict"], "value": old.get("value")}, sort_keys=True,
                                          default=str, ensure_ascii=False).encode()).hexdigest()[:12] if old else None
        same = decided == r["decided"] and (not decided or d == old_d)
        if not decided:
            causes[why] += 1
            if r["decided"]:
                changed.append({"id": r["id"], "was": "decided", "now": why})
            continue
        dec += 1
        g = r["correct"] if same else ((prov.get(r["id"]) or {}).get(d) or {}).get("grade")
        if not same:
            changed.append({"id": r["id"], "was": r["trigger"] or "decided", "now": "decided", "decision": d,
                            "provisional_grade": g, "value": ans.value})
        if g is None:
            ungraded.append(r["id"])
        else:
            right += g
    n = len(rows)
    dev = {"questions": n, "decided": dec, "coverage": dec / n, "accuracy_on_decided": right / dec if dec else None,
           "overall_non_decided_wrong": right / n, "not_decided_by_cause": dict(causes), "changed": changed,
           "ungraded": ungraded, "guardrail": {"overall_floor": 0.6666666666666666, "accuracy_floor": 0.70}}
    dev["guardrail"]["kept"] = (dev["overall_non_decided_wrong"] >= dev["guardrail"]["overall_floor"]
                                and (dev["accuracy_on_decided"] or 0) >= 0.70)
    # D3 cached-scene questions
    from eval import e2e_trainset as et
    from eval import freeze
    from vqa.pipeline import Pipeline
    hand3 = _hand(d3_programs)
    pipe = Pipeline(freeze.pipeline_config("phase45", "claude-haiku-5-5", cache_only=True, answer_fallback=False,
                                           reading_policy="higher_confidence"))
    _, rows3 = _jsonl(d3_run)
    out3 = []
    for r in rows3:
        if not (r.get("scene") or {}).get("cached"):
            continue
        scene, _ = et._scene(pipe, gs.image_path(r["image_id"], "train"))
        q = hand3.get(r["id"]) or (QueryProgram.model_validate(r["program"]) if r.get("program") else None)
        if scene is None or q is None:
            out3.append({"id": r["id"], "decided": False, "trigger": r.get("trigger") or "parse_failed"})
            continue
        ans, why = _run_one(eng, scene, q, trigger)
        decided = why is None and ans is not None and ans.verdict.value in ("yes", "no")
        correct = (float((ans.verdict.value == "yes") == ee.yes_no(qa[r["id"]]["answer"])) if decided else None)
        out3.append({"id": r["id"], "decided": decided, "trigger": why, "correct": correct,
                     "was": {"decided": r.get("decided"), "trigger": r.get("trigger"), "correct": r.get("correct")},
                     "hand_program": r["id"] in hand3, "v10_fewshot": r["id"] in ("train_424", "train_104", "train_124")})
    d3dec = [x for x in out3 if x["decided"]]
    d3 = {"biased": True, "questions": len(out3), "decided": len(d3dec),
          "right": sum(x["correct"] for x in d3dec), "not_decided_by_cause": dict(Counter(x["trigger"] for x in out3
                                                                                          if not x["decided"])),
          "was": {"decided": sum(bool(x["was"]["decided"]) for x in out3),
                  "right": sum(x["was"]["correct"] or 0 for x in out3)},
          "changed": [x for x in out3 if x["decided"] != bool(x["was"]["decided"]) or x["correct"] != x["was"]["correct"]]}
    return {"dev": dev, "d3_cached": d3}


# ---------------------------------------------------------------- 2. the biased train working set

def working_set() -> list[dict]:
    """Train minus dev minus validation (ids only from the two split files)."""
    dev, val = _ids("train_dev.json"), _ids("train_validation.json")
    qs = json.loads(gs.TRAIN_QA.read_text(encoding="utf-8"))
    return [q for q in qs if q["id"] not in dev["questions"] and q["id"] not in val["questions"]
            and q["image_id"] not in val["images"]]


def _cache_dirs() -> list[Path]:
    from vqa.perception.cache import cache_dir
    return [cache_dir()] + sorted(E2E.glob("dev_cache_*"))


def _parser_rate() -> dict[str, float]:
    """Parser v9 cost per question, from the v9 dev re-parse and the v9 gate run."""
    costs = []
    _, rows = _jsonl(REPARSE_RUN)
    costs += [r["trace"]["parser"]["cost_usd"] for r in rows if r.get("reparsed")
              and (r["trace"].get("parser") or {}).get("cost_usd")]
    for g in sorted((ROOT / "logs" / "parser_eval").glob("pred_claude-sonnet-5-5_medium_v9_*.jsonl")):
        costs += [rec["cost_usd"] for rec in map(json.loads, g.read_text(encoding="utf-8").splitlines())
                  if isinstance(rec.get("cost_usd"), (int, float))]
    return {"per_question": sum(costs) / len(costs) if costs else 0.0041, "samples": len(costs)}


def trainset() -> dict[str, Any]:
    from vqa.perception import prompt as sp
    from vqa.perception.cache import SceneCache
    from vqa.perception.image import prepare_file
    ws = working_set()
    yn = [q for q in ws if q["question_type"] == "Yes/No"]
    imgs = sorted({q["image_id"] for q in yn})
    pid = sp.prompt_id("v5")
    caches = [SceneCache(d) for d in _cache_dirs()]
    cached, missing = [], []
    for i in imgs:
        sha = prepare_file(gs.image_path(i, "train")).sha256
        hit = any(c.get(sha, "claude-haiku-5-5", "medium", pid) is not None for c in caches)
        (cached if hit else missing).append(i)
    # Rates measured in phase 4.5: perception v5 + fallback + guide per image from the candidate dev run;
    # the final validation's all-in $0.0076 per question with the fallback off (perception + parser + writer).
    _, cand = _jsonl(CANDIDATE_RUN)
    seen, per_img = set(), []
    for r in cand:
        if r["image_id"] in seen:
            continue
        seen.add(r["image_id"])
        t = r["trace"]
        pe = t.get("perception") or {}
        per_img.append((pe.get("cost_usd") or 0) + ((pe.get("guide") or {}).get("cost_usd") or 0))   # guide added in case it is not in the total (conservative)
    img_rate = sum(per_img) / len(per_img)
    pr = _parser_rate()
    writer = judge_estimate(1)["writer_per_answer"]
    parse = len(yn) * pr["per_question"]
    perceive = len(missing) * img_rate
    write = 0.45 * len(yn) * writer      # Yes/No decided share on validation was 39.6%; writer only on decided
    total = parse + perceive + write
    return {"biased": True,
            "why_biased": "its images fed parser few-shots (v7-v9), the stage-A sign list and rule design; "
                          "diagnosis only, never a score",
            "working_set_questions": len(ws), "by_type": dict(Counter(q["question_type"] for q in ws)),
            "yesno_questions": len(yn), "yesno_images": len(imgs),
            "scene_v5_cached_images": len(cached), "scene_v5_missing_images": len(missing),
            "rates_usd": {"parser_v9_per_question": round(pr["per_question"], 5), "parser_samples": pr["samples"],
                          "perception_v5_fb_guide_per_image": round(img_rate, 5), "writer_per_decided": writer},
            "estimate_usd": {"parse_v9": round(parse, 3), "perceive_missing": round(perceive, 3),
                             "writer_on_decided (45%)": round(write, 3), "judge": 0.0,
                             "total": round(total, 3), "range": [round(0.8 * total, 3), round(1.3 * total, 3)]},
            "note": "Yes/No is graded by the yes/no mapping, so no judge call is needed; the writer can be "
                    "skipped too (grade the engine verdict), which leaves parse + perception."}


# ---------------------------------------------------------------- 3. out-of-scope groups

# Wording groups for what a question asks, checked by eye on dev's 12 out-of-scope questions.
# Order matters: the first match wins.
GROUPS = [
    ("compound", r"\bvà\b.*\b(không|nào|gì|bao nhiêu)\b.*\b(và|còn)\b|;|, (còn|và) (xe|làn|biển)"),
    ("speed_range", r"(khoảng|tối thiểu và tối đa|từ .* đến .* km|trong khoảng tốc độ)"),
    ("board_symbols", r"(ký hiệu|biểu tượng|hình vẽ|hình ảnh trên biển|trên biển có (những )?(gì|hình))"),
    ("traffic_light", r"(đèn tín hiệu|đèn giao thông|đèn (đỏ|vàng|xanh))"),
    ("why", r"(tại sao|vì sao|lý do)"),
    ("lane_arrows", r"(mũi tên|vạch kẻ|vạch sơn|mặt đường)"),
    ("how_many", r"(bao nhiêu (biển|làn|loại)|mấy (biển|làn|loại)|có bao nhiêu)"),
    ("board_yesno", r"(biển chỉ dẫn|bảng chỉ dẫn|biển (xanh|màu xanh)).*(đúng|phải|không)"),
    ("penalty", r"(phạt|xử phạt|mức phạt|tiền phạt|bị phạt)"),
    ("distance", r"(bao xa|cách .* (bao nhiêu|mấy)|khoảng cách)"),
    ("time_of_day", r"(giờ nào|khung giờ|thời gian nào|lúc mấy giờ)"),
]


def group_of(text: str) -> str:
    t = text.lower()
    for name, pat in GROUPS:
        if re.search(pat, t):
            return name
    return "other"


def oos() -> dict[str, Any]:
    _, rows = _jsonl(REPARSE_RUN)
    qa = {q["id"]: q for q in json.loads(gs.TRAIN_QA.read_text(encoding="utf-8"))}
    dev_oos = [{"id": r["id"], "group": group_of(qa[r["id"]]["question"]), "question": qa[r["id"]]["question"],
                "reason": ((r["trace"].get("parser") or {}).get("program") or {}).get("out_of_scope_reason")}
               for r in rows if r["trigger"] == "out_of_scope"]
    ws = working_set()
    by = defaultdict(list)
    for q in ws:
        g = group_of(q["question"])
        if g != "other":
            by[g].append(q["id"])
    return {"dev_out_of_scope": dev_oos, "dev_groups": dict(Counter(x["group"] for x in dev_oos)),
            "train_working_set_wording_groups": {g: {"questions": len(v), "yesno": sum(
                1 for i in v if qa[i]["question_type"] == "Yes/No")} for g, v in sorted(by.items(), key=lambda x: -len(x[1]))},
            "note": "train groups are by wording only (the parser never ran on them); a wording match is not "
                    "proof the parser would call it out of scope"}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("calibrate")
    sub.add_parser("step1")
    sub.add_parser("step4")
    u = sub.add_parser("uncertain")
    u.add_argument("-v", "--verbose", action="store_true")
    sub.add_parser("trainset")
    sub.add_parser("oos")
    a = ap.parse_args()
    res = {"calibrate": calibrate, "step1": step1, "step4": step4, "trainset": trainset, "oos": oos}.get(a.cmd)
    out = uncertain(verbose=a.verbose) if a.cmd == "uncertain" else res()
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
