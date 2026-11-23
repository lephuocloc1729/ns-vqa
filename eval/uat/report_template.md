# UAT results (YYYY-MM-DD)

> Fill in from `score_sus.py` (form + log) and `turn_stats.py` (server). Save as `docs/results/uat-<date>.md`. Aggregates only: no names, IDs next to quotes, photos or question text.

## Setup

- **When and where:** dates; in person / video call / unmoderated (task success is then *self-reported*).
- **Participants:** n = __ (drivers __, students __, people who know traffic law __); devices: computer __, phone __, tablet __.
- **System:** https://signcite.xyz, API image `____`, frozen phase52 pipeline, 10 answer slots, RAG fallback on an RTX 5090 (Qwen3.5-9B Q4_K_M, 1 slot), RAG answer cache on.
- **Tasks:**
  1. 5 fixed tasks, written as situations, on 3 of the owner's street photos (`eval/uat/task_sheet.md`), handed out one at a time.
  2. 2 free questions on one new photo: the tester's own (__), taken in the app (__), or one of the owner's 15 spare photos never asked about before (__).
  3. The form (`eval/uat/form_questions.md`): SUS, CSAT, and per-task completion and ease.
- **Caching:** the fixed photos were asked once in a dry run, so their scenes came from the cache. Waits are therefore reported separately: the first question on a photo (the real wait) and a photo seen before.

## Acceptance targets (fixed before the sessions)

| Target | Result (95% CI) | Pass |
|---|---|---|
| Mean SUS ≥ 68 | __ (__–__), grade __ | |
| Task success ≥ 80% | __% (__–__%) | |
| CSAT 4–5 ≥ 70% | __% (__–__%) | |
| Every task ≥ 60% | lowest: T_ at __% | |

Task success is **observed** (moderator's log) / **self-reported** (form): pick one.

## Other measures

| Measure | Result | Reference |
|---|---|---|
| SUS on computer / phone | __ / __ | — |
| Task success on computer / phone | __% / __% | — |
| In-app 👍 share | __% of __ rated answers | — |
| Seconds, first question on a photo: p50 / p90 | __ / __ | the real wait |
| Seconds, photo seen before: p50 / p90 | __ / __ | cached scene |
| Answered by rules / fallback | __ / __ | private benchmark coverage: __% |
| Claude API cost | $__ (≈ $__ per answer) | cap $__ |

## SUS

(paste `score_sus.py`'s SUS section, with the per-group table)

## Tasks

(paste the task table: success, partial, fail, rate with CI, median time, ease; and task success by device)

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
- Fixed tasks used cached photos (see Setup). Only the first question on each new photo shows the real wait, so that figure rests on about one question per tester.
- The SUS wording is our Vietnamese translation, not a validated one; each item keeps the original's direction.
- Testers judged legal correctness themselves; the 👍 share is perceived, not graded, correctness.
- If any session was unmoderated, its task success is self-reported.
