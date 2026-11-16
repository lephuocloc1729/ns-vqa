# Phase 4.5 plan (proposed): rule coverage for a rules-only report

**Status: proposed, for the owner's approval (2026-11-16).** Nothing is built. No API calls were made for this proposal; every figure comes from stored runs (`eval/coverage_analysis.py`). The private run is on hold (`docs/plans/phase-5.md`).

**The change of requirement (owner, 2026-11-16):** the report counts rule-based answers only; the answer fallback is for the demo. A question is **decided** when the rules answer it with yes, no or a value. Unknown, uncertain, out_of_scope, parse failures and programs that can't run are not decided. The report gives three figures:
- **decided coverage**;
- **accuracy on decided answers**;
- **overall**, counting every non-decided question as wrong.

## 1. Where we stand

| | questions | decided coverage (95% CI) | accuracy on decided (95% CI) | overall, non-decided = wrong (95% CI) |
|---|---|---|---|---|
| public_dev T4, H1-H3 pooled (tuned) | 153 (51 × 3) | **61.4%** (54–69) | 88.8% (81–94) | 54.6% |
| per run: H1 / H2 / H3 | 51 each | 62.7% / 56.9% / 64.7% | 89.1% / 87.9% / 89.4% | 55.9% / 50.0% / 57.8% |
| public_dev non-duplicate images (pooled) | 57 | 63.2% (36 of 57) | 100% | 63.2% (50–74) |
| **public_holdout** (once, frozen; aggregate only) | 49 | **51.0%** (37–64) | **78.0%** (59–90) | **39.8%** (27–54) |
| oracle A (gold scenes + gold programs, today's engine) | 51 | 72.5% (59–83) | 89.2% (75–96) | 64.7% |

- **The honest starting point is public_holdout:** 51% decided, 78% right when decided, so 40% overall under the new rule. The holdout aggregate doesn't split the rules' answers by image, so it has no non-duplicate figure.
- **Even perfect perception and parsing decide only 72.5%** (oracle A). The other 27.5% are gaps in the DSL and the rules, not in perception. So 80% needs both engine/DSL work and better perception.

## 2. Why public_dev questions are not decided (T4, 153 question-runs, 59 not decided)

| cause | question-runs | questions | what it is |
|---|---|---|---|
| **uncertain** | 24 | 13 | Two readings of a sign lead to different answers. The alternative came from pass 1's own `alt` in 11, a crop that replaced pass 1's code in 9, and the re-run in 4. Pairs: P.130/P.131a, P.131b/c, R.301b/d, R.301/R.302, P.111a/b, P.103b/P.123b and others. |
| **out_of_scope** | 24 | 8 | The parser finds no DSL intent: guide-sign content (directions, junction shape; 3 questions), driver behaviour after a warning sign ("must slow down"; 2), counting signs (1), traffic lights (1), open "what should the driver do" (1). All 8 are out of scope in gold too. |
| **unreadable sign** | 7 | 3 | The sign the question is about is UNKNOWN (6 boards, 5 red circles, 1 unknown look, over 12 sign mentions). Leaving it out doesn't help: single-sign programs then have no sign (6 can't run, 1 uncertain). |
| **unknown** | 2 | 1 | The scene doesn't say how many lanes there are (a lane question). |
| **parse failed** | 2 | 2 | The parser's reply failed twice (the retry-echo problem in the open items). |

13 questions are not decided in all three runs and 13 more in one or two.

**Two what-ifs, measured free:**
- **Decide uncertain answers on the primary reading:** 21 of 24 become decided, but only **4 of 7 Yes/No are right** (57%). For Natural QA, 6 of 14 match oracle A's decision. That trades coverage for accuracy, so it is not proposed.
- **Ignore unreadable signs:** none of the 7 become decided.

**The two-pass trial's effect on coverage** (same 153 question-runs, engine-only replay):

| | decided | uncertain | unreadable sign | can't run |
|---|---|---|---|---|
| frozen | 94 (61.4%) | 24 | 7 | 0 |
| trial | 89 (58.2%) | 21 | 17 | 0 |
| trial minus UNKNOWN | 97 (63.4%) | 21 | 3 | 6 |
| hybrid | 92 (60.1%) | 25 | 7 | 1 |

At best the two-pass design adds 2 points of coverage (trial minus UNKNOWN), and it loses answers (`phase-4.5-option-perception.md`). It's not a route to 80%.

## 3. Fixes, ranked by coverage gained per day

Gains are in points of public_dev decided coverage (1 question = 2.0 points), and they are estimates. Each fix must also keep its answers right.

| rank | fix | kind | cause it targets | expected gain | accuracy risk | size | gain per day |
|---|---|---|---|---|---|---|---|
| 1 | **Parser v7: the retry sends only the error** (no echoed prose), and the parser version key includes the catalog hash | parser (prompt v7) | parse failed | +1.3 | low | 0.5 day | 2.6 |
| 2 | **Lane count from the lane board** when the road's lane count is missing (number of board rows) | engine | unknown | +1.3 | low | 0.5 day | 2.6 |
| 3 | **Warning-sign behaviour:** a warning sign requires the driver to slow down and take care (QCVN 41's warning-sign article, cited), as a `required` claim the DSL can state | KB + DSL + parser v7 | out_of_scope | +3.9 (2 questions); +5.9 if open "what should the driver do" questions map to it | medium (the gold answers' wording) | 1.5 days | 2.6–3.9 |
| 4 | **Counting signs** (`count(select(...))`, with category and look) | DSL + engine + parser v7 | out_of_scope | +2.0 | medium (counts depend on perception recall and false positives) | 1 day | 2.0 |
| 5 | **Confusable pairs at crop time:** for the pairs that make most uncertain answers (P.130/P.131a, P.131b/c, R.301b/d, R.301/R.302, P.111a/b), a second crop read with only that pair's two figures, and the winner decides when it is high | perception (crop prompt v5, set-T tuned) | uncertain, unreadable | +3 to +8 (of the 15.7 + 4.6 points lost to perception) | **high**: phase 3's perception gate failed, and every newly decided answer rests on a corrected reading | 2–3 days + paid set-T runs | 1.5–2.5 |
| 6 | **Guide-sign content:** destinations, arrows and junction shape read into the scene graph (schema 1.3), plus a `direction_to` / `junction` intent | perception + schema + DSL + parser v7 | out_of_scope | +5.9 (3 questions) | high (reading guide boards is perception the gate never measured) | 3–4 days | 1.5–2.0 |
| — | traffic lights | out of v1 scope | out_of_scope | +2.0 | | not proposed | |
| — | uncertain decided on the primary reading | engine | uncertain | +13.7 | **too high** (Yes/No 4 of 7) | | rejected |

**Projected coverage on public_dev:** fixes 1–4 bring it to about 70%. Adding 6 gives about 76%, and adding 5 gives 79–84%. **80% needs every fix, including the two high-risk perception items.** On a fresh set the starting point is lower (holdout: 51% against public_dev's 61%), so 80% there is a stretch.

## 4. Targets (fixed now, before any fix)

Measured once, on the validation set (section 5), after the phase-4.5 freeze:

| | target | floor (below it the fix set is not adopted) |
|---|---|---|
| decided coverage | **≥ 80%** (the owner's target) | ≥ 70% |
| accuracy on decided (judge, 1 / 0.5 / 0) | ≥ 88% | ≥ 85% |
| overall, non-decided = wrong | ≥ 70% | ≥ 60% |

- Each fix is also checked on development data (public_dev, tuned, and train outside the validation pool). A fix whose newly decided answers are below 85% right there is dropped.
- If the floors pass but the targets don't, the report gives the measured figures as they are.

## 5. Validation set: untouched train questions

**The pool** (computed from ids and image files only; no question was read):
- train has 304 images and 530 questions;
- excluded images:
  - set T (36);
  - gold signs (36);
  - gold intents (40);
  - any image or question named anywhere in `prompts/`, `eval/prompts/`, `tests/`, `kb/`, `eval/audits/`, `docs/` or `tools/` (51: few-shots, prompt examples, fixtures, catalog comments);
  - any image in a duplicate group with public or private (120);
  - any image in a duplicate group with an excluded train image (7);
  - 190 in all (the groups overlap);
- **what's left: 197 questions on 114 images** (144 Natural QA, 53 Yes/No).

**The validation set:**
- About 110 questions, drawn by image with seed 20261116 (all questions of a drawn image, images drawn until about 110 questions). Yes/No images are drawn first, so the Yes/No share is as close to the private test's 48% as the pool allows (the pool is only 27% Yes/No).
- Ids only go in `data/splits/train_validation.json`. A guard keeps these questions out of few-shots, fixtures and gold.
- **Aggregate only, like public_holdout.** No question, answer or per-question result is read during phase 4.5, so it stays a measure, not a development set.
- **Run end to end with the fallback off** (a `PipelineConfig` switch; questions it would send to the fallback come back unanswered), scored with the same judge (`judge/v1`), with 95% CIs (Wilson for coverage and accuracy) and the duplicate split. "Duplicate" here means another train image in the same duplicate group, which the pool's rules already exclude, so every pool image counts as non-duplicate.
- **Runs:** one **baseline** with today's frozen system (aggregate only: the three figures and the counts by cause), so the phase has an honest starting point. Then one **final** run after the phase-4.5 freeze.
- **Caveat:** the owner rewrote the train questions (2026-11-15), and their style differs from public and private. The validation figure is a fresh measure, but not the same style as private.

## 6. Order of work

1. Validation set and guard; the `PipelineConfig` fallback switch; `e2e_private.py` and the reports extended with the three rules-only figures. Baseline validation run (aggregate only, on the owner's go-ahead).
2. Fixes 1–4 (parser v7, lane count, warning-sign behaviour, counting), each with tests modelled on train questions outside the pool, checked on public_dev (tuned).
3. Fix 6 (guide-sign content), then fix 5 (confusable-pair crops), each only if the earlier ones leave coverage short of the target. Perception changes are tuned on set T, as in phase 3.
4. Catalog rows used by new rules get the owner's review.
5. **The phase-4.5 freeze** (`eval/frozen_phase45.json`), then the final validation run, once.
6. **The private run, once**, with the new freeze. Fallback on, so the demo figure comes from the same run: **rules-only figures are the main result**, and the with-fallback figure is the demo figure.

## 7. Cost and time

| item | estimate |
|---|---|
| baseline validation run (about 110 questions on about 64 images, fallback off) | about $1.1 |
| parser v7 development: 3 public_dev parser runs | about $0.5 |
| perception development on set T (fixes 5, 6): about 4 runs with crops | about $1.5 |
| public_dev end-to-end checks of the fixed system: 2 runs, fallback off | about $1.0 |
| final validation run | about $1.1 |
| private run, once (fallback on, for the demo figure) | about $1.9 |
| **total** | **about $7**; with a 50% margin, about $10 |

- **Time:** about 8–10 working days, plus the owner's reviews (new catalog rows, the warning-sign rule's article text).
- Phase 5's $25 ceiling has $24.89 left. After phase 4.5, about $15 remains for the baselines and ablations.

## 8. What this changes in phase 5

- **P11 ("run the frozen phase-4 system") is replaced:** the private run uses the phase-4.5 freeze. `e2e_private.py` gets the new freeze record and reports the three rules-only figures, with the decided-coverage CI, as its headline.
- **P3:** A1 "no answer fallback" becomes the **main system**. The fallback becomes the ablation, or the demo, reported from the same private run, since it is the same run with fallback answers counted. A3, A4 and A6 are reported on the rules-only figures; A2 stays on public_dev only.
- **Baselines (P2)** don't change. Claude-alone and Claude + retrieval answer everything, so the report sets their accuracy beside the rules' overall (non-decided = wrong) and their accuracy on decided.
- **Human scoring (P6)** scores the rules' decided Natural QA answers.
- **public_holdout** stays used: it is not run again. The validation set takes its role for phase 4.5.
- The two-pass perception option (`phase-4.5-option-perception.md`) stays not adopted. It adds at most 2 points of coverage.

## Decisions for the owner

| | question | proposed |
|---|---|---|
| Q1 | Approve this plan as phase 4.5, before the private run | yes |
| Q2 | The targets and floors in section 4 | as written |
| Q3 | The validation set: about 110 questions from the 197-question pool, Yes/No drawn first, aggregate only | yes |
| Q4 | A baseline validation run with today's frozen system (aggregate only, about $1.1) before any fix | yes |
| Q5 | Fixes 5 and 6 (perception, high risk) only if fixes 1–4 leave coverage short | yes |
| Q6 | The private run with fallback on, so the demo figure comes from the same run | yes |
