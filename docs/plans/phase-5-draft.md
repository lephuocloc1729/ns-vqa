# Phase 5 plan (draft): benchmark and evaluation

DESIGN.md roadmap phase 5: "Freeze the system, then run the private test once as the benchmark: baselines, ablations, and error analysis by stage and question feature."

**Status: draft, for the owner's approval.** Nothing here is built, and no API call is made until each paid step has the owner's go-ahead on its estimate.

**Starting point:**
- phase 4 is closed (`docs/status.md`, "Phase 4: closing"). The configuration is frozen in `eval/frozen_phase4.json`, and public_holdout ran once: 83.7% overall, 89.6% on non-duplicate images (n=24, 95% CI 72–97);
- on holdout the rules scored 78.0% on their 25 answers, below the fallback's 89.6% on 24 (the reverse of public_dev, which is tuned);
- `phase-4` is not merged into `main` and not pushed (decision P10 below).

## What phase 5 delivers

1. **The private-test benchmark**, run once with the frozen phase-4 system, aggregate only.
2. **Baselines** on the same questions, with the same judge.
3. **Ablations** showing what each part contributes.
4. **Error analysis by stage and by question feature** (DESIGN section 8 table), in aggregate on private and per question on public_dev only.
5. **Human scoring** of the private Natural QA answers, with agreement against the judge (DESIGN section 9).

## The private test

- **146 questions on 104 images** (Yes/No 70, Natural QA 76).
- **Duplicates.** "Duplicate" means the image is also in train or in public (CLAUDE.md). From `data/splits/duplicates.json` (image files only): **87 of the 104 private images** are duplicates (79 with train, 26 with public). Only 17 images are non-duplicate, so the non-duplicate score will rest on few questions and have a wide CI. The question count is mapped at evaluation time.
- **Private answers.** They are never opened outside the scoring. The scoring code reads them in memory, grades each answer (Yes/No mapping, or the Opus judge for Natural QA), sums the grades and writes only the aggregate. No per-question line is printed or written, and no question, image or answer id appears in a report.
  - The exception is the human scoring (item 5), which needs the owner to read the answers (decision P6).
- **Run once.** The guards follow the holdout:
  - the git tree is clean;
  - the live configuration equals `eval/frozen_phase4.json`;
  - a committed sentinel (`eval/private_ran.json`) is written before the first call;
  - fresh perception into a temporary cache.
- **Nothing changes after the run.** The system is not tuned on private results. Labelling private gold signs and programs afterwards, for per-module scores, is allowed (DESIGN section 8, hold-out rule).

## Work items

### 1. The private benchmark run (`eval/e2e_private.py`, proposed)

- A copy of `e2e_holdout.py` for the private split, with its own sentinel, the same guards and an aggregate-only report.
- The report has:
  - the git commit, the frozen configuration and the prompt ids;
  - overall, strict, Yes/No and Natural QA scores;
  - all images and non-duplicate images (Wilson 95% CI);
  - rule coverage, the rules-only score, the fallback score and the fallback rate by trigger;
  - faithfulness and the template rate;
  - cost and seconds per question.
- **The by-feature breakdown** (claims, vehicle classes, turns, speed, lanes, time, meaning, weight, violations) uses the same keyword rules as the DESIGN section 8 table, computed in memory and reported as counts and accuracy per feature.
- **Leakage tests:** the module is the only eval code that names the private split, and it writes no per-question data.

### 2. Baselines (proposed; same judge, same questions)

| baseline | what it is | may touch |
|---|---|---|
| B1 Claude alone | image + question to Haiku 5.5, Sonnet 5.5 and Opus 5.5 (three runs), one plain prompt, no rules | public_dev (to fix the prompt), private once each |
| B2 Claude + retrieval | B1 with Sonnet 5.5, plus the top law_db articles retrieved for the question (eval-side code only; inference code still never reads law_db) | public_dev, private once |
| B3 oracle A | gold scenes + gold programs through the engine, writer and fallback | public_dev (done in phase 4); private only after private gold signs and programs exist (item 4) |

- The baseline prompts are fixed on train and public_dev before any private result, and pinned like the system's.
- Each private baseline run is aggregate only, with its own sentinel.

### 3. Ablations (proposed)

| ablation | what changes | how it runs | may touch |
|---|---|---|---|
| A1 no answer fallback | trigger cases get the engine's own answer through the writer | replay of the private run's stored scenes and parses: no perception or parser call | private (aggregate), public_dev |
| A2 no pictograms | perception prompt without the law_db pictograms (a new scene version, perception only) | fresh perception, then the frozen pipeline | public_dev first; private once if the owner wants it |
| A3 no scene fallback | pass 1 only (no tiles, no crops) | replay of pass-1 records from the private run's cache | private (aggregate), public_dev |
| A4 Sonnet perception | Sonnet 5.5 + fallback for the scene call | fresh perception | private once (aggregate) |
| A5 gold scenes | = B3 | as B3 | as B3 |
| A6 no T4 | `drop_own_alt_on_agree` off | replay | private (aggregate), public_dev |

- **Replays** (A1, A3, A6) need the private run's scene and parse records kept for the replay, in a temporary location. This is a decision (P4), because the holdout kept nothing.
- **public_holdout is not touched again in phase 5.** It has served as phase 4's one measure.

### 4. Private gold labels for per-module scores (proposed, after the benchmark run)

- **Gold signs:** an Opus pre-fill of the 104 private images, blind to the questions and kept local; then the owner's review of every sign (DESIGN section 8).
- **Gold intents:** Opus drafts of the 146 programs, reviewed by the owner; kept local. They allow perception and parser scores on private, and B3.

### 5. Human scoring and agreement (DESIGN section 9)

- The owner scores every private Natural QA answer from the final system and from the strongest baseline, without seeing the judge's verdict.
- The report gives both scores and Cohen's kappa.
- It needs a blind scoring sheet: answers in random order, no system label.

### 6. Error analysis

- **On public_dev, per question:** stage attribution from oracle A and B, as in phase 4.
- **On private, aggregate only:** by stage, by trigger and by question feature.
- **public_holdout:** no per-question analysis.

## Cost estimate (no API calls made)

Per-question costs measured in phase 4 (`logs/api_calls.jsonl`):

| item | basis | estimate |
|---|---|---|
| 1 private benchmark run, fresh perception, 146 q | holdout $0.0127 per question | about $1.9 |
| B1 Claude alone, Haiku / Sonnet / Opus | about $0.0004 / $0.008 / $0.02 per question, plus judge $0.40 per run | about $0.5 / $1.6 / $3.3 |
| B2 Claude + retrieval (Sonnet) | B1 Sonnet plus about 3k article tokens | about $2.5 |
| B1/B2 prompt fixing on public_dev | about 2 runs each, 51 q | about $2 |
| A1, A3, A6 replays on private | writer + judge for changed answers | about $0.4 each, $1.2 |
| A2 no pictograms (public_dev, then private) | perception + pipeline | about $0.7 + $1.5 |
| A4 Sonnet perception on private | 104 × $0.023 + pipeline | about $3.6 |
| Item 4 gold pre-fill and drafts (Opus) | DESIGN estimates | about $2 + $1.5 |
| B3 on private | writer, fallback, judge | about $0.6 |
| **total** | | **about $23** (about $16 if the baselines use the Batch API at half price) |

- Of that, about $1.9 (item 1) is the benchmark itself. The rest is optional, and each part can be dropped.
- A ceiling of **$25** is proposed (P9). The benchmark run is funded first.

## Decisions needed from the owner

| | question | proposed |
|---|---|---|
| P1 | Approve this plan as phase 5, and the order: benchmark first, then baselines and ablations | yes |
| P2 | Which baselines: B1 with all three models? B2 (retrieval)? | B1 Haiku + Sonnet + Opus, B2 Sonnet |
| P3 | Which ablations run on private (A1–A6), and which only on public_dev | A1, A3, A6 on private (replays, cheap); A2 on public_dev only; A4 on private |
| P4 | May the private run keep its scene and parse records (model outputs only, local, gitignored) so the replays can run? The holdout kept none. | yes, deleted after phase 5 |
| P5 | Use the Message Batches API for the baselines (half price, asynchronous)? | yes for B1/B2; no for the system run (it is sequential) |
| P6 | Human scoring: may the owner read the private Natural QA answers for it? It is the only per-question look at private. | yes, after all automatic scores are recorded |
| P7 | Private gold labels (item 4): now, or not in phase 5 | after the benchmark run, in phase 5 |
| P8 | `0094`'s gold reading, before any oracle figure is reported | owner |
| P9 | Phase-5 API ceiling | $25 |
| P10 | Merge `phase-4` into `main` (no push), then branch `phase-5` | yes |
| P11 | Does the private run use the frozen phase-4 system exactly as is (no fix for the deferred KB items)? | yes: the benchmark measures what was frozen |
