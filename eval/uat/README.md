# UAT pack (plan item 3.3)

| File | For | What |
|---|---|---|
| `task_sheet.md` | testers (Vietnamese), one task at a time | 5 fixed tasks written as situations, 2 questions on one new photo, then the form |
| `form_questions.md` | the owner, to build the Google Form | every question with its `[CODE]`, scales and options; SUS in Vietnamese |
| `moderator_notes.md` | the moderator | acceptance targets, photos (3 fixed + 2 backups, 15 spare), dry run, server checklist per day, session script, observation tags, scoring |
| `observation_log_template.csv` | the moderator | one row per participant and task |
| `score_sus.py` | after the sessions | the targets with pass/fail; SUS (mean, 95% CI, grade, by group and device), CSAT, task success (observed or self-reported, by device), photo sources, issue tags |
| `turn_stats.py` | after each session day, on the server | answers in a time window: routes, latency (first question on a photo vs photo seen before), cost, in-app feedback; aggregates only |
| `report_template.md` | the write-up | becomes `docs/results/uat-<date>.md` |

Raw responses, logs and notes go in `eval/runs/uat/` (gitignored) and are deleted after the defense.
Tests: `tests/test_uat_score.py`, `tests/test_uat_turn_stats.py`.
