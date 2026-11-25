"""Score the UAT: SUS, CSAT and task success (plan item 3.3; materials in eval/uat/).

Inputs (both stay local: put them in eval/runs/uat/, which is gitignored):
- the form's responses, exported as CSV (Google Forms › Responses › Download). Columns are found
  by the code in square brackets at the start of each question title ([ID], [GROUP], [DEVICE],
  [SUS1] … [SUS10], [CSAT], [T1] … [T5] for ease, [OK1] … [OK5] for self-reported completion,
  [PHOTO] for the free questions' photo), so the order and the rest of the title do not matter
  (eval/uat/form_questions.md).
- optionally, the moderator's observation log (observation_log_template.csv): one row per
  participant and task, outcome success | partial | fail, the time in seconds, and issue tags.
  Without it, task success comes from the form's [OK1] … [OK5] answers and is labelled self-reported.

    .venv/bin/python eval/uat/score_sus.py eval/runs/uat/responses.csv \\
        --observations eval/runs/uat/observations.csv --json eval/runs/uat/summary.json

Prints a Markdown report with aggregates only. Nothing here calls an API.

SUS (Brooke 1996): odd items score (answer - 1), even items (5 - answer); the sum times 2.5 gives
0-100. The grade is the Sauro-Lewis curved scale (A+ 84.1 and up ... F below 51.7; mean 68 = C).
The mean has a t-based 95% CI. Rates (CSAT 4-5, task success) have Wilson 95% CIs.
The acceptance targets (TARGETS, fixed by the owner before the sessions) are printed with pass/fail.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

N_SUS = 10
TASKS = [f"T{i}" for i in range(1, 6)]
OUTCOMES = ("success", "partial", "fail")
# the form's [OKn] options (Có / Một phần / Không), matched on their first words, accents optional
_SELF = [("mot phan", "partial"), ("một phần", "partial"), ("partial", "partial"),
         ("co", "success"), ("có", "success"), ("yes", "success"),
         ("khong", "fail"), ("không", "fail"), ("no", "fail")]

# the form's [GROUP] options, matched on their first words; anything else (the "Khác" option's
# free text) is reported as "Khác", so no tester's own words reach the report
GROUPS = ("Người lái xe", "Sinh viên", "Người am hiểu luật giao thông", "Khác")
# the observation tags (eval/uat/moderator_notes.md, section 4); a tag outside this list is printed
# as a warning, since it is usually a typo (a new tag is allowed when none fits)
KNOWN_TAGS = {"waiting_too_long", "upload_hard", "voice_failed", "answer_wrong", "answer_unclear",
              "evidence_hard_to_find", "proof_confusing", "boxes_hard_to_find", "followup_unclear",
              "followup_misread", "history_hard_to_find", "feedback_hard_to_find", "fallback_confusing",
              "fallback_off", "mobile_layout", "error_message"}

# Acceptance targets (owner, 2026-11-23; eval/uat/moderator_notes.md): (key, label, threshold)
TARGETS = [
    ("sus_mean", "Mean SUS ≥ 68", 68.0),
    ("task_success", "Task success ≥ 80% (full successes, all attempts)", 0.80),
    ("csat_4_5", "CSAT 4–5 ≥ 70% of testers", 0.70),
    ("every_task", "Every task ≥ 60%", 0.60),
]

# Sauro & Lewis (2016), curved grading scale: (lowest score of the grade, grade)
SUS_GRADES = [(84.1, "A+"), (80.8, "A"), (78.9, "A-"), (77.2, "B+"), (74.1, "B"), (72.6, "B-"),
              (71.1, "C+"), (65.0, "C"), (62.7, "C-"), (51.7, "D"), (0.0, "F")]

# two-sided 95% t critical values by degrees of freedom
_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
         10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110,
         18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
         26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}


def t975(df: int) -> float:
    if df in _T975:
        return _T975[df]
    keys = sorted(k for k in _T975 if k <= df)
    return _T975[keys[-1]] if keys else _T975[1]   # conservative: the next lower tabulated df


def mean_ci(xs: list[float]) -> tuple[float, float, float]:
    m = statistics.fmean(xs)
    if len(xs) < 2:
        return m, float("nan"), float("nan")
    h = t975(len(xs) - 1) * statistics.stdev(xs) / math.sqrt(len(xs))
    return m, m - h, m + h


def wilson(k: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def sus_grade(score: float) -> str:
    return next(g for lo, g in SUS_GRADES if score >= lo)


def sus_score(answers: list[int]) -> float:
    """answers: the 10 items in order, each 1-5."""
    if len(answers) != N_SUS or any(a not in (1, 2, 3, 4, 5) for a in answers):
        raise ValueError(f"SUS needs 10 answers from 1 to 5, got {answers}")
    total = sum((a - 1) if i % 2 == 0 else (5 - a) for i, a in enumerate(answers))
    return total * 2.5


def _code(title: str) -> str | None:
    m = re.match(r"\s*\[([A-Za-z]+\d*)\]", title)
    return m.group(1).upper() if m else None


def _int(v: str) -> int | None:
    m = re.match(r"\s*(\d+)", v or "")
    return int(m.group(1)) if m else None


def _nfc(v: str) -> str:
    return unicodedata.normalize("NFC", v or "")


def _pid(v: str) -> str | None:
    """A participant ID as typed on the form or in the log ("p7", "P 07", " P07 ") -> "P07"."""
    v = re.sub(r"\s+", "", _nfc(v)).upper()
    m = re.fullmatch(r"P0*(\d+)", v)
    return f"P{int(m.group(1)):02d}" if m else (v or None)


def _group(v: str) -> str | None:
    v = _nfc(v).strip()
    if not v:
        return None
    return next((g for g in GROUPS if v.lower().startswith(g.lower())), "Khác")


def _seconds(v: str | None, where: str) -> float | None:
    """time_s as seconds, or m:ss if the cell was typed as a time."""
    v = (v or "").strip()
    if not v:
        return None
    m = re.fullmatch(r"(\d+):(\d{1,2})", v)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    try:
        return float(v.replace(",", "."))
    except ValueError:
        raise SystemExit(f"{where}: time_s must be seconds (e.g. 95) or m:ss, got {v!r}") from None


def _self_outcome(v: str) -> str | None:
    v = _nfc(v).strip().lower()
    return next((o for prefix, o in _SELF if v == prefix or v.startswith(prefix + " ")), None)


def read_responses(path: Path) -> list[dict]:
    """One dict per response: id, group, sus (10 ints or None), csat, ease {T1: 1-5},
    done {T1: success | partial | fail} from the [OKn] questions."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        return []
    cols: dict[str, int] = {}
    for i, title in enumerate(rows[0]):
        c = _code(title)
        if c and c not in cols:
            cols[c] = i
    missing = [f"SUS{i}" for i in range(1, N_SUS + 1) if f"SUS{i}" not in cols]
    if missing:
        raise SystemExit(f"{path}: no column for {', '.join(missing)} (titles must start with [SUS1] ...)")
    out = []
    for r in rows[1:]:
        if not any(x.strip() for x in r):
            continue
        get = lambda c: r[cols[c]] if c in cols and cols[c] < len(r) else ""  # noqa: E731
        sus = [_int(get(f"SUS{i}")) for i in range(1, N_SUS + 1)]
        out.append({
            "id": _pid(get("ID")),
            "group": _group(get("GROUP")),
            "device": _nfc(get("DEVICE")).strip() or None,
            "photo": _nfc(get("PHOTO")).strip() or None,
            "sus": sus if all(a is not None for a in sus) else None,
            "csat": _int(get("CSAT")),
            "ease": {t: _int(get(t)) for t in TASKS if t in cols},
            "done": {t: o for t in TASKS if (o := _self_outcome(get(f"OK{t[1:]}")))},
        })
    return dedupe(out)


def dedupe(responses: list[dict]) -> list[dict]:
    """The form allows more than one response (testers may lack a Google account), so a tester who
    submits twice would count twice. Keep each ID's last response (the export is in submission
    order); responses without an ID are all kept. The kept list's first item carries the number
    dropped, for the report."""
    last = {r["id"]: i for i, r in enumerate(responses) if r["id"]}
    kept = [r for i, r in enumerate(responses) if not r["id"] or last[r["id"]] == i]
    dropped = len(responses) - len(kept)
    if dropped:
        ids = sorted(i for i, n in Counter(r["id"] for r in responses if r["id"]).items() if n > 1)
        print(f"warning: {dropped} earlier duplicate response(s) dropped, keeping the last for "
              f"{', '.join(ids)}", file=sys.stderr)
    for r in kept:
        r["duplicates_dropped"] = 0
    if kept:
        kept[0]["duplicates_dropped"] = dropped
    return kept


def read_observations(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("participant") or "").strip()]
    out = []
    for r in rows:
        outcome = (r.get("outcome") or "").strip().lower()
        if not outcome:
            # the shared log has a row ready for every participant and task: an untouched row is
            # skipped, but a row with a time, tags or notes and no outcome is a mistake to fix
            if any((r.get(k) or "").strip() for k in ("time_s", "issues", "notes")):
                raise SystemExit(f"{path}: {r.get('participant')} {r.get('task')} has notes or a time "
                                 "but no outcome")
            continue
        if outcome not in OUTCOMES:
            raise SystemExit(f"{path}: outcome must be one of {OUTCOMES}, got {outcome!r} "
                             f"({r.get('participant')}, {r.get('task')})")
        where = f"{path}: {r.get('participant')} {r.get('task')}"
        task = (r.get("task") or "").strip().upper()
        if task not in TASKS:
            raise SystemExit(f"{where}: task must be one of {TASKS}")
        out.append({
            "participant": _pid(r["participant"]),
            "task": task,
            "outcome": outcome,
            "time_s": _seconds(r.get("time_s"), where),
            # tags are separated by ";", but a "," typed by mistake is accepted too
            "issues": [x.strip().lower() for x in re.split(r"[;,]", r.get("issues") or "") if x.strip()],
        })
    seen = Counter((o["participant"], o["task"]) for o in out)
    twice = sorted(f"{p} {t}" for (p, t), n in seen.items() if n > 1)
    if twice:
        raise SystemExit(f"{path}: more than one row for {', '.join(twice)}")
    unknown = sorted({tag for o in out for tag in o["issues"]} - KNOWN_TAGS)
    if unknown:
        print(f"warning: tags not in the list (typo?): {', '.join(unknown)}", file=sys.stderr)
    return out


def summarize(responses: list[dict], observations: list[dict] | None = None) -> dict:
    scored = [(r["id"], sus_score(r["sus"])) for r in responses if r["sus"]]
    s: dict = {"responses": len(responses), "sus_n": len(scored),
               "duplicates_dropped": sum(r.get("duplicates_dropped", 0) for r in responses)}
    if scored:
        xs = [x for _, x in scored]
        m, lo, hi = mean_ci(xs)
        s["sus"] = {"mean": m, "ci95": [lo, hi], "sd": statistics.stdev(xs) if len(xs) > 1 else 0.0,
                    "median": statistics.median(xs), "min": min(xs), "max": max(xs),
                    "grade": sus_grade(m), "above_68": sum(x > 68 for x in xs)}
        for key in ("group", "device"):
            groups: dict[str, list[float]] = defaultdict(list)
            for r in responses:
                if r["sus"] and r.get(key):
                    groups[r[key]].append(sus_score(r["sus"]))
            if groups:
                s[f"sus_by_{key}"] = {g: {"n": len(v), "mean": statistics.fmean(v)}
                                      for g, v in sorted(groups.items())}
    photos = Counter(r["photo"] for r in responses if r.get("photo"))
    if photos:
        s["free_question_photo"] = dict(photos.most_common())
    cs = [r["csat"] for r in responses if r["csat"] in (1, 2, 3, 4, 5)]
    if cs:
        k = sum(c >= 4 for c in cs)
        s["csat"] = {"n": len(cs), "mean": statistics.fmean(cs), "share_4_5": k / len(cs),
                     "share_4_5_ci95": list(wilson(k, len(cs))),
                     "counts": {str(i): cs.count(i) for i in range(1, 6)}}
    ease = {t: [r["ease"][t] for r in responses if r["ease"].get(t) in (1, 2, 3, 4, 5)] for t in TASKS}
    if any(ease.values()):
        s["task_ease"] = {t: {"n": len(v), "mean": statistics.fmean(v)} for t, v in ease.items() if v}
    if not observations:
        # no moderator's log: task success from the form's [OKn] answers, labelled self-reported
        observations = [{"participant": r["id"] or f"R{i}", "task": t, "outcome": o, "time_s": None, "issues": []}
                        for i, r in enumerate(responses, 1) for t, o in r.get("done", {}).items()]
        if observations:
            s["task_source"] = "self-reported"
    else:
        s["task_source"] = "observed"
        logged = {o["participant"] for o in observations}
        formed = {r["id"] for r in responses if r["id"]}
        s["unmatched"] = {"log_only": sorted(logged - formed), "form_only": sorted(formed - logged)}
        if logged ^ formed:
            print(f"warning: in the log but not on the form: {', '.join(s['unmatched']['log_only']) or '-'}; "
                  f"on the form but not in the log: {', '.join(s['unmatched']['form_only']) or '-'}",
                  file=sys.stderr)
    if observations:
        by_task: dict[str, list[dict]] = defaultdict(list)
        for o in observations:
            by_task[o["task"]].append(o)
        tasks = {}
        for t in sorted(by_task):
            os_ = by_task[t]
            c = Counter(o["outcome"] for o in os_)
            times = [o["time_s"] for o in os_ if o["time_s"] is not None and o["outcome"] != "fail"]
            tasks[t] = {"n": len(os_), **{o: c[o] for o in OUTCOMES},
                        "success_rate": c["success"] / len(os_),
                        "success_ci95": list(wilson(c["success"], len(os_))),
                        "median_time_s": statistics.median(times) if times else None}
        n = len(observations)
        k = sum(o["outcome"] == "success" for o in observations)
        kp = sum(o["outcome"] == "partial" for o in observations)
        s["tasks"] = tasks
        s["task_success"] = {"attempts": n, "success": k, "partial": kp, "rate": k / n,
                             "ci95": list(wilson(k, n)), "rate_with_partial_half": (k + kp / 2) / n,
                             "participants": len({o["participant"] for o in observations})}
        device = {r["id"]: r["device"] for r in responses if r.get("id") and r.get("device")}
        by_dev: dict[str, list[dict]] = defaultdict(list)
        for o in observations:
            if o["participant"] in device:
                by_dev[device[o["participant"]]].append(o)
        if by_dev:
            s["task_success_by_device"] = {
                d: {"attempts": len(v), "rate": sum(o["outcome"] == "success" for o in v) / len(v)}
                for d, v in sorted(by_dev.items())}
        issues = Counter()
        for p, tags in _issues_by_participant(observations).items():
            issues.update(tags)         # each participant counts a tag once
        s["issues"] = issues.most_common()
    s["targets"] = check_targets(s)
    return s


def check_targets(s: dict) -> list[dict]:
    """Each target: its value (None when there is no data yet) and whether it passes."""
    values = {
        "sus_mean": s.get("sus", {}).get("mean"),
        "task_success": s.get("task_success", {}).get("rate"),
        "csat_4_5": s.get("csat", {}).get("share_4_5"),
        "every_task": min((t["success_rate"] for t in s["tasks"].values()), default=None) if "tasks" in s else None,
    }
    return [{"key": k, "label": label, "threshold": th, "value": values[k],
             "pass": None if values[k] is None else values[k] >= th} for k, label, th in TARGETS]


def _issues_by_participant(observations: list[dict]) -> dict[str, set[str]]:
    d: dict[str, set[str]] = defaultdict(set)
    for o in observations:
        d[o["participant"]].update(o["issues"])
    return d


def _pct(x: float) -> str:
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.0f}%"


def format_report(s: dict) -> str:
    dup = f"; {s['duplicates_dropped']} earlier duplicate(s) dropped" if s.get("duplicates_dropped") else ""
    out = ["# UAT results", "", f"Form responses: {s['responses']} (SUS complete: {s['sus_n']}{dup})", ""]
    um = s.get("unmatched") or {}
    if um.get("log_only") or um.get("form_only"):
        out += [f"Not matched between the log and the form: {len(um['log_only'])} only in the log, "
                f"{len(um['form_only'])} only on the form (their tasks still count; the device split misses them).",
                ""]
    if s.get("targets"):
        out += ["## Acceptance targets", "", "| Target | Result | Pass |", "|---|---:|---|"]
        for t in s["targets"]:
            v = t["value"]
            shown = "–" if v is None else (f"{v:.1f}" if t["key"] == "sus_mean" else _pct(v))
            if t["key"] == "every_task" and v is not None:
                worst = min(s["tasks"], key=lambda k: s["tasks"][k]["success_rate"])
                shown += f" (lowest: {worst})"
            ok = "no data" if t["pass"] is None else ("✅ pass" if t["pass"] else "❌ fail")
            out.append(f"| {t['label']} | {shown} | {ok} |")
        out.append("")
    if "sus" in s:
        u = s["sus"]
        out += ["## SUS", "",
                f"- **Mean {u['mean']:.1f}** (95% CI {u['ci95'][0]:.1f}–{u['ci95'][1]:.1f}), "
                f"grade **{u['grade']}** on the Sauro-Lewis scale (68 = average).",
                f"- SD {u['sd']:.1f}, median {u['median']:.1f}, range {u['min']:.1f}–{u['max']:.1f}; "
                f"{u['above_68']} of {s['sus_n']} above 68.", ""]
        for key, head in (("group", "Group"), ("device", "Device")):
            if f"sus_by_{key}" in s:
                out += [f"| {head} | n | mean SUS |", "|---|---:|---:|"]
                out += [f"| {g} | {r['n']} | {r['mean']:.1f} |" for g, r in s[f"sus_by_{key}"].items()]
                out.append("")
    if "csat" in s:
        c = s["csat"]
        lo, hi = c["share_4_5_ci95"]
        out += ["## CSAT (1–5)", "",
                f"- **{_pct(c['share_4_5'])} gave 4 or 5** (95% CI {_pct(lo)}–{_pct(hi)}), mean {c['mean']:.2f}, n = {c['n']}.",
                "- Counts: " + ", ".join(f"{k}: {v}" for k, v in c["counts"].items()), ""]
    if "tasks" in s:
        t = s["task_success"]
        lo, hi = t["ci95"]
        src = "moderator's log" if s.get("task_source") == "observed" else "self-reported on the form"
        out += [f"## Task success ({src})", "",
                f"- **{_pct(t['rate'])} of {t['attempts']} attempts succeeded** (95% CI {_pct(lo)}–{_pct(hi)}); "
                f"{t['partial']} partial; {_pct(t['rate_with_partial_half'])} counting a partial as half; "
                f"{t['participants']} participants.", "",
                "| Task | n | success | partial | fail | success rate (95% CI) | median time (succeeded/partial) | ease 1–5 |",
                "|---|---:|---:|---:|---:|---|---:|---:|"]
        ease = s.get("task_ease", {})
        for name, r in s["tasks"].items():
            lo, hi = r["success_ci95"]
            tm = f"{r['median_time_s']:.0f} s" if r["median_time_s"] is not None else "–"
            e = f"{ease[name]['mean']:.1f}" if name in ease else "–"
            out.append(f"| {name} | {r['n']} | {r['success']} | {r['partial']} | {r['fail']} | "
                       f"{_pct(r['success_rate'])} ({_pct(lo)}–{_pct(hi)}) | {tm} | {e} |")
        out.append("")
        if "task_success_by_device" in s:
            out += ["Task success by device: " + "; ".join(
                f"{d} {_pct(r['rate'])} of {r['attempts']}" for d, r in s["task_success_by_device"].items()), ""]
        if s["issues"]:
            out += ["## Issues (participants reporting each tag)", ""]
            out += [f"- `{tag}`: {n}" for tag, n in s["issues"][:10]]
            out.append("")
    if "free_question_photo" in s:
        out += ["## Free questions: whose photo", ""]
        out += [f"- {p}: {n}" for p, n in s["free_question_photo"].items()]
        out.append("")
    if "task_ease" in s and "tasks" not in s:
        out += ["## Task ease (self-reported, 1–5)", ""]
        out += [f"- {t}: {r['mean']:.1f} (n = {r['n']})" for t, r in s["task_ease"].items()]
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("responses", type=Path, help="the form's CSV export")
    ap.add_argument("--observations", type=Path, help="the moderator's observation log (CSV)")
    ap.add_argument("--json", type=Path, help="also write the summary as JSON here")
    a = ap.parse_args(argv)
    s = summarize(read_responses(a.responses), read_observations(a.observations) if a.observations else None)
    print(format_report(s))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
