"""Score the UAT: SUS, CSAT and task success (plan item 3.3; materials in eval/uat/).

Inputs (both stay local: put them in eval/runs/uat/, which is gitignored):
- the form's responses, exported as CSV (Google Forms › Responses › Download). Columns are found
  by the code in square brackets at the start of each question title ([ID], [GROUP], [SUS1] …
  [SUS10], [CSAT], [T1] … [T5] for ease, [OK1] … [OK5] for self-reported completion), so the order
  and the rest of the title do not matter (eval/uat/form_questions.md).
- optionally, the moderator's observation log (observation_log_template.csv): one row per
  participant and task, outcome success | partial | fail, the time in seconds, and issue tags.
  Without it, task success comes from the form's [OK1] … [OK5] answers and is labelled self-reported.

    .venv/bin/python eval/uat/score_sus.py eval/runs/uat/responses.csv \\
        --observations eval/runs/uat/observations.csv --json eval/runs/uat/summary.json

Prints a Markdown report with aggregates only. Nothing here calls an API.

SUS (Brooke 1996): odd items score (answer - 1), even items (5 - answer); the sum times 2.5 gives
0-100. The grade is the Sauro-Lewis curved scale (A+ 84.1 and up ... F below 51.7; mean 68 = C).
The mean has a t-based 95% CI. Rates (CSAT 4-5, task success) have Wilson 95% CIs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

N_SUS = 10
TASKS = [f"T{i}" for i in range(1, 6)]
OUTCOMES = ("success", "partial", "fail")
# the form's [OKn] options (Có / Một phần / Không), matched on their first words, accents optional
_SELF = [("mot phan", "partial"), ("một phần", "partial"), ("partial", "partial"),
         ("co", "success"), ("có", "success"), ("yes", "success"),
         ("khong", "fail"), ("không", "fail"), ("no", "fail")]

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


def _self_outcome(v: str) -> str | None:
    v = (v or "").strip().lower()
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
            "id": get("ID").strip().upper() or None,
            "group": get("GROUP").strip() or None,
            "sus": sus if all(a is not None for a in sus) else None,
            "csat": _int(get("CSAT")),
            "ease": {t: _int(get(t)) for t in TASKS if t in cols},
            "done": {t: o for t in TASKS if (o := _self_outcome(get(f"OK{t[1:]}")))},
        })
    return out


def read_observations(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("participant") or "").strip()]
    out = []
    for r in rows:
        outcome = (r.get("outcome") or "").strip().lower()
        if outcome not in OUTCOMES:
            raise SystemExit(f"{path}: outcome must be one of {OUTCOMES}, got {outcome!r} "
                             f"({r.get('participant')}, {r.get('task')})")
        t = (r.get("time_s") or "").strip()
        out.append({
            "participant": r["participant"].strip().upper(),
            "task": (r.get("task") or "").strip().upper(),
            "outcome": outcome,
            "time_s": float(t) if t else None,
            "issues": [x.strip().lower() for x in (r.get("issues") or "").split(";") if x.strip()],
        })
    return out


def summarize(responses: list[dict], observations: list[dict] | None = None) -> dict:
    scored = [(r["id"], sus_score(r["sus"])) for r in responses if r["sus"]]
    s: dict = {"responses": len(responses), "sus_n": len(scored)}
    if scored:
        xs = [x for _, x in scored]
        m, lo, hi = mean_ci(xs)
        s["sus"] = {"mean": m, "ci95": [lo, hi], "sd": statistics.stdev(xs) if len(xs) > 1 else 0.0,
                    "median": statistics.median(xs), "min": min(xs), "max": max(xs),
                    "grade": sus_grade(m), "above_68": sum(x > 68 for x in xs)}
        groups: dict[str, list[float]] = defaultdict(list)
        for r in responses:
            if r["sus"] and r.get("group"):
                groups[r["group"]].append(sus_score(r["sus"]))
        if groups:
            s["sus_by_group"] = {g: {"n": len(v), "mean": statistics.fmean(v)} for g, v in sorted(groups.items())}
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
        issues = Counter()
        for p, tags in _issues_by_participant(observations).items():
            issues.update(tags)         # each participant counts a tag once
        s["issues"] = issues.most_common()
    return s


def _issues_by_participant(observations: list[dict]) -> dict[str, set[str]]:
    d: dict[str, set[str]] = defaultdict(set)
    for o in observations:
        d[o["participant"]].update(o["issues"])
    return d


def _pct(x: float) -> str:
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.0f}%"


def format_report(s: dict) -> str:
    out = ["# UAT results", "", f"Form responses: {s['responses']} (SUS complete: {s['sus_n']})", ""]
    if "sus" in s:
        u = s["sus"]
        out += ["## SUS", "",
                f"- **Mean {u['mean']:.1f}** (95% CI {u['ci95'][0]:.1f}–{u['ci95'][1]:.1f}), "
                f"grade **{u['grade']}** on the Sauro-Lewis scale (68 = average).",
                f"- SD {u['sd']:.1f}, median {u['median']:.1f}, range {u['min']:.1f}–{u['max']:.1f}; "
                f"{u['above_68']} of {s['sus_n']} above 68.", ""]
        if "sus_by_group" in s:
            out += ["| Group | n | mean SUS |", "|---|---:|---:|"]
            out += [f"| {g} | {r['n']} | {r['mean']:.1f} |" for g, r in s["sus_by_group"].items()]
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
        if s["issues"]:
            out += ["## Issues (participants reporting each tag)", ""]
            out += [f"- `{tag}`: {n}" for tag, n in s["issues"][:10]]
            out.append("")
    elif "task_ease" in s:
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
