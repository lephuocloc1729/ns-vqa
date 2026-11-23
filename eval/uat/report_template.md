# UAT results (YYYY-MM-DD)

> Fill in from `score_sus.py` (form + log) and `turn_stats.py` (server). Save as `docs/results/uat-<date>.md`. Aggregates only: no names, IDs next to quotes, photos or question text.

## Setup

- **When and where:** dates; in person / video call / unmoderated (task success is then *self-reported*).
- **Participants:** n = __ (drivers __, students __, people who know traffic law __); devices: computer __, phone __.
- **System:** https://signcite.xyz, API image `____`, frozen phase52 pipeline, 10 answer slots, RAG fallback on an RTX 5090 (Qwen3.5-9B Q4_K_M, 1 slot), RAG answer cache on.
- **Tasks:** 5 fixed tasks on the owner's own street photos (`eval/uat/task_sheet.md`), then 5 questions of the tester's own, then the form (`eval/uat/form_questions.md`: SUS, CSAT, per-task ease).
- **Caveat:** the fixed tasks' photos were asked once in a dry run, so their perception came from the scene cache: T1–T4 waits are shorter than a first question on a new photo. The free questions show the cold wait.

## Headline

| Measure | Result | Target / reference |
|---|---|---|
| SUS, mean (95% CI) | __ (__–__), grade __ | 68 = average; ≥ 72.6 = B- or better |
| CSAT, share giving 4–5 (95% CI) | __% (__–__%) | — |
| Task success, all attempts (95% CI) | __% (__–__%) | — |
| In-app 👍 share | __% of __ rated answers | — |
| Seconds per answer, p50 / p95 | __ / __ | load test: p95 ≤ 2 s at the API with the fake pipeline |
| Answered by rules / fallback | __ / __ | private benchmark coverage: __% |
| Claude API cost | $__ (≈ $__ per answer) | cap $__ |

## SUS

(paste `score_sus.py`'s SUS section, with the per-group table)

## Tasks

(paste the task table: success, partial, fail, rate with CI, median time, ease)

Notes per task: what failed and why, in one line each.

## Answers during the sessions

(paste `turn_stats.py`'s output; add the session days together)

## Top 3 complaints, with a fix or an explanation

| # | Complaint (participants) | Evidence (issue tag, form quotes) | Fix done / planned, or why not |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |

## What went well

Two or three points with evidence (tags absent, high-ease tasks, quotes).

## Threats to validity

- Small sample (n = __): CIs are wide; no claim beyond this group.
- Recruited from the team's contacts, so not a random sample of drivers.
- Fixed tasks used cached photos (see Setup); free questions were cold.
- Testers judged legal correctness themselves; the 👍 share is perceived, not graded, correctness.
- Unmoderated sessions only: task success is self-reported.
