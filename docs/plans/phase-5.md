# Phase 5 plan: benchmark and evaluation

DESIGN.md roadmap phase 5: "Freeze the system, then run the private test once as the benchmark: baselines, ablations, and error analysis by stage and question feature."

**Status: approved (owner, 2026-11-16)**, with the decisions in the last section. It replaces `phase-5-draft.md`. No API call is made until each paid step has the owner's go-ahead on its estimate.

**ON HOLD (owner, 2026-11-16): the private run is held.** `eval/e2e_private.py` is not run. The requirement changed: the report counts rule-based answers only (the answer fallback is for the demo), with a target of about 80% rule coverage, where coverage is the share of questions the rules *decide* (yes / no / value; unknown, uncertain and out_of_scope count as not covered). Phase 4.5 (`docs/plans/phase-4.5.md`) is **approved** (owner, 2026-11-16); the private run is held until its new freeze. **Changes to this plan (owner, 2026-11-16, phase-4.5 Q1–Q6):**
- **P11 is replaced:** the private run uses the phase-4.5 freeze, not the phase-4 one.
- **P3:** A1 "no answer fallback" is now **the main system**: the report's headline is the rules-only figures (decided coverage, accuracy on decided, overall with non-decided counted wrong). The with-fallback figure is the demo figure, from the same private run (fallback on, Q6).
- The private run's report (item 1) adds the three rules-only figures with CIs; the guards check the phase-4.5 freeze record.
- Everything else below stands until the owner revises it.

**Starting point:**
- phase 4 is closed (`docs/status.md`, "Phase 4: closing"). The configuration is frozen in `eval/frozen_phase4.json`, and public_holdout ran once: 83.7% overall, 89.6% on non-duplicate images (n=24, 95% CI 72–97);
- on holdout the rules scored 78.0% on their 25 answers, below the fallback's 89.6% on 24 (the reverse of public_dev, which is tuned);
- `phase-4` is merged into `main` (no push) and phase 5 works on branch `phase-5` (P10).

## What phase 5 delivers

1. **The private-test benchmark**, run once with the frozen phase-4 system exactly as is (P11), aggregate only.
2. **Baselines** on the same questions, with the same judge: B1 with Haiku, Sonnet and Opus, and B2 with Sonnet (P2).
3. **Ablations** showing what each part contributes: A1, A3, A6 and A4 on private; A2 on public_dev only (P3).
4. **Error analysis by stage and by question feature** (DESIGN section 8 table), in aggregate on private and per question on public_dev only.
5. **Human scoring** of the private Natural QA answers by the owner, with agreement against the judge (DESIGN section 9; P6).
6. **Private gold labels** for per-module scores, after the benchmark, if the owner has time (P7).

## The private test

- **146 questions on 104 images** (Yes/No 70, Natural QA 76).
- **Duplicates.** "Duplicate" means the image is also in train or in public (CLAUDE.md). From `data/splits/duplicates.json` (image files only): **87 of the 104 private images** are duplicates (79 with train, 26 with public). Only 17 images are non-duplicate, so the non-duplicate score will rest on few questions and have a wide CI. The question count is mapped at evaluation time.
- **Private answers.** They are never opened outside the scoring code. The scoring code reads them in memory, grades each answer (Yes/No mapping, or the Opus judge for Natural QA), sums the grades and writes only the aggregate. No per-question line is printed or written, and no question, image or answer id appears in a report.
  - **The one exception is the owner's human scoring (item 5, P6):** only the owner reads private answers, and only after every automatic score (the benchmark, the baselines and the ablations on private) is recorded and committed. The assistant never reads the scoring sheet or the private answers.
- **Run once.** The guards follow the holdout:
  - `--confirm-frozen` is given;
  - the git tree is clean;
  - the live configuration equals `eval/frozen_phase4.json`, and the perception model is the frozen one;
  - it has never run: no committed sentinel `eval/private_ran.json` and no private aggregate file;
  - the sentinel is written before the first call, so a run that stops part way counts as the one run;
  - fresh perception into a new, empty scene cache.
- **Nothing changes after the run.** The system is not tuned on private results. Labelling private gold signs and programs afterwards, for per-module scores, is allowed (DESIGN section 8, hold-out rule).
- **The catalog is not reviewed before the private run**, since a catalog change would break the freeze. The report states that the catalog is mostly assistant-reviewed: in `kb/sign_catalog.yaml` 78 of 80 rows, and in `kb/sign_catalog_meaning.yaml` 110 of 149 rows, are not `reviewed_by: human`.

### Replay records (P4)

The replays (A1, A3, A6) need the private run's model outputs. The private run keeps them **locally, gitignored, under `cache/private_run/<run_id>/`, and they are deleted at the end of phase 5**:
- `scenes/`: the run's scene cache (pass 1, re-run, tiles and crops; model outputs only, keyed as usual);
- `records.jsonl`: one line per question with the question id, the image id, the question type, the pipeline's answer text, verdict, trigger and trace (the parse, the engine's answer, the writer and fallback status). It holds **no gold answer and no grade**.
- The folder is read only by the replay code, which writes aggregates only. The assistant never reads these files per question; the code checks that git ignores the folder before writing to it.

## Work items

### 1. The private benchmark run (`eval/e2e_private.py`)

- Built on `e2e_holdout.py`: the same guards, its own sentinel (`eval/private_ran.json`), an aggregate-only report.
- **The report has:**
  - the git commit, the frozen configuration and the prompt ids;
  - the catalog review state (counts of rows by `reviewed_by`);
  - overall, strict, Yes/No and Natural QA scores;
  - all images and non-duplicate images (duplicates against train and public; Wilson 95% CI);
  - rule coverage, the rules-only score, the fallback score and the fallback rate by trigger, with the score per trigger;
  - faithfulness and the template rate;
  - cost and seconds per question.
- **The by-feature breakdown** (claims, vehicle classes, turns, speed, lanes, time, meaning, weight, violations): keyword rules over the question text, computed in memory and reported as counts, score and rule coverage per feature. The rules behind the DESIGN section 8 table were not kept in the repo, so `e2e_private.FEATURES` is a new, committed set written to match the table's categories; it is tested on hand-written questions and checked on train.
- **Leakage tests:** the module is the only code that names the private question file; it prints no per-question line and writes no per-question data outside the gitignored replay folder; the records there hold no gold answer and no grade.

### 2. Baselines (same judge, same questions)

| baseline | what it is | may touch |
|---|---|---|
| B1 Claude alone | image + question to Haiku 5.5, Sonnet 5.5 and Opus 5.5 (three runs), one plain prompt, no rules | public_dev (to fix the prompt), private once each |
| B2 Claude + retrieval | B1 with Sonnet 5.5, plus the top law_db articles retrieved for the question (eval-side code only; inference code still never reads law_db) | public_dev, private once |
| B3 oracle A | gold scenes + gold programs through the engine, writer and fallback | public_dev (done in phase 4); private only if the private gold labels exist (item 6) |

- B1 and B2 run through the **Message Batches API** at half price (P5). The system run is sequential and does not.
- The baseline prompts are fixed on train and public_dev before any private result, and pinned like the system's.
- Each private baseline run is aggregate only, with its own sentinel.

### 3. Ablations

| ablation | what changes | how it runs | runs on |
|---|---|---|---|
| A1 no answer fallback | trigger cases get the engine's own answer through the writer | replay of the private run's records: no perception or parser call | private (aggregate), public_dev |
| A2 no pictograms | perception prompt without the law_db pictograms (a new scene version, perception only) | fresh perception, then the frozen pipeline | **public_dev only** |
| A3 no scene fallback | pass 1 only (no tiles, no crops) | replay of pass-1 records from the private run's cache | private (aggregate), public_dev |
| A4 Sonnet perception | Sonnet 5.5 + fallback for the scene call | fresh perception | private once (aggregate) |
| A5 gold scenes | = B3 | as B3 | as B3 |
| A6 no T4 | `drop_own_alt_on_agree` off | replay | private (aggregate), public_dev |

- **public_holdout is not touched again in phase 5.** It has served as phase 4's one measure.

### 4. Error analysis

- **On public_dev, per question:** stage attribution from oracle A and B, as in phase 4.
- **On private, aggregate only:** by stage, by trigger and by question feature.
- **public_holdout:** no per-question analysis.

### 5. Human scoring and agreement (DESIGN section 9; P6)

- **When:** only after every automatic score on private is recorded and committed.
- The owner scores every private Natural QA answer from the final system and from the strongest baseline, without seeing the judge's verdict.
- A blind scoring sheet (answers in random order, no system label) is written by code to a gitignored folder. **Only the owner opens it; the assistant never reads it or the private answers.** The owner's scores are read back by code, which reports both scores and Cohen's kappa in aggregate.

### 6. Private gold labels (P7: after the benchmark, if the owner has time)

- **Gold signs:** an Opus pre-fill of the 104 private images, blind to the questions and kept local; then the owner's review of every sign (DESIGN section 8).
- **Gold intents:** Opus drafts of the 146 programs, reviewed by the owner; kept local. They allow perception and parser scores on private, and B3.

## Cost estimate (no API calls made)

Per-question costs measured in phase 4 (`logs/api_calls.jsonl`):

| item | basis | estimate |
|---|---|---|
| 1 private benchmark run, fresh perception, 146 q | holdout $0.0127 per question | about $1.9 |
| B1 Claude alone, Haiku / Sonnet / Opus (batch) | about $0.0004 / $0.008 / $0.02 per question at full price, plus judge $0.40 per run | about $0.4 / $1.0 / $1.9 |
| B2 Claude + retrieval (Sonnet, batch) | B1 Sonnet plus about 3k article tokens | about $1.4 |
| B1/B2 prompt fixing on public_dev | about 2 runs each, 51 q | about $2 |
| A1, A3, A6 replays on private | writer + judge for changed answers | about $0.4 each, $1.2 |
| A2 no pictograms (public_dev only) | perception + pipeline | about $0.7 |
| A4 Sonnet perception on private | 104 × $0.023 + pipeline | about $3.6 |
| Item 6 gold pre-fill and drafts (Opus), if done | DESIGN estimates | about $2 + $1.5 |
| B3 on private, if item 6 is done | writer, fallback, judge | about $0.6 |
| **total** | | **about $18** |

- **Ceiling: $25 for phase 5 (P9).** The benchmark run is funded first.
- Each paid step still needs the owner's go-ahead on its own estimate.

## Decisions (owner, 2026-11-16)

| | question | decision |
|---|---|---|
| P1 | Approve this plan as phase 5, and the order: benchmark first, then baselines and ablations | **yes** |
| P2 | Which baselines | **B1 Haiku + Sonnet + Opus, and B2 Sonnet** |
| P3 | Which ablations run on private | **A1, A3, A6, A4 on private; A2 on public_dev only** |
| P4 | May the private run keep its records for the replays? | **yes: local, gitignored, deleted at the end of phase 5** |
| P5 | Message Batches API | **yes for B1/B2**; not for the system run (it is sequential) |
| P6 | Human scoring: may the owner read the private Natural QA answers? | **yes, but only the owner, and only after every automatic score is recorded and committed.** The assistant never reads the scoring sheet or private answers. Added to CLAUDE.md's dataset rules. |
| P7 | Private gold labels | **after the benchmark, if the owner has time** |
| P8 | `0094`'s gold reading | **decided and committed** (`ea5b0a8`) |
| P9 | Phase-5 API ceiling | **$25** |
| P10 | Merge `phase-4` into `main` (no push), then branch `phase-5` | **yes** (done: merge `5e1664c`) |
| P11 | Does the private run use the frozen phase-4 system exactly as is? | **yes**: the benchmark measures what was frozen |
| — | Catalog review before the private run | **no**, it would break the freeze; the report states the catalog is mostly assistant-reviewed |
