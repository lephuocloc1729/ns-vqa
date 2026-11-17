# Phase 4.6 plan (proposed): coverage round 2

**Status: proposed (2026-11-17), awaiting the owner's approval.** Every figure below is free: it comes from stored runs through `eval/phase46_analysis.py` (no API call). Nothing in `vqa/` or `app/` has changed. Not touched: the validation set beyond its ids and aggregate, its sentinels, public_holdout, private, gold, `eval/frozen_phase4.json`, `eval/frozen_phase45.json`.

**Goal (owner, round 2):** more decided coverage before the private run, which stays on hold.

## 1. Where we stand

| | questions | decided coverage | accuracy on decided | overall (non-decided = wrong) |
|---|---|---|---|---|
| dev, v9 re-parse (`dev_reparse_v9_8bbb5eb01cff`) | 87 | 73.6% (64) | 85.2% | 62.6% |
| validation, final (`7a3dbec997f7`, aggregate only) | 110 | 47.3% (52) | 77.9% | 36.8% |

- **Budget:** $2.95 of the round's $5 spent; **$2.05 left.**
- Dev's not-decided causes: out of scope 12, uncertain 6, unknown 3, program can't run 1, unreadable sign 1. Validation's: out of scope 28, uncertain 16, unknown 7, unreadable sign 4, can't run 2, parse failed 1.

## 2. Findings

### 2.1 Uncertain readings: a free dev replay

`eval/phase46_analysis.py uncertain` narrows each low/medium-confidence sign's readings with a policy, re-runs the engine on the stored scenes of `dev_candidate_7caed6170de6` with the v9 parses, and applies the fallback trigger. Only the 6 uncertain answers can change. Newly decided answers carry **provisional grades** (assistant, against the dev answer; partial = 0.5), kept in the local `eval/runs/e2e/phase46_provisional_grades.json`.

| policy | decided | coverage | accuracy on decided | overall | newly decided (provisional grade) |
|---|---|---|---|---|---|
| current | 64 | 73.6% | 85.2% | 62.6% | — |
| **A. higher confidence** (asked): each sign keeps its highest-confidence reading; a tie keeps the first reading | 70 | **80.5%** | 82.9% | **66.7%** | 138 (1), 159 (0.5), 432 (0.5), 450 (0.5), 517 (1), 521 (0) |
| **B. first unless tied low** (variant): an UNKNOWN alternative is dropped (as single-sign questions already do); a reading stays only if its confidence is the top one, so low-against-low ties stay uncertain | 66 | 75.9% | 83.3% | 63.2% | 450 (0.5), 521 (0) |
| C. alternative when first is low (for comparison): medium keeps the first reading, low gives way to the alternative | 70 | 80.5% | 80.7% | 64.9% | 138 (0), 159 (1), 432 (0.5), 450 (0.5), 517 (0), 521 (0) |

**Set-T calibration** (`calibrate`; 5 stored Haiku v4/v5 + fallback runs on set T, gold signs v1; a coarse image-level family match). For predicted signs with alternatives:

| first reading | signs | first right only | alternative right only | both | neither |
|---|---|---|---|---|---|
| medium | 81 | 29 | 6 | 45 | 1 |
| low | 107 | 23 | 45 | 13 | 26 |
| any, with an UNKNOWN alternative | 6 | 1 | 0 | 0 | 5 |

- **A medium first reading is the better bet** (right in 74 of 81). A **low** first reading is right in only 36 of 107 against 58 for its alternative. So for low-against-low ties, A's choice is a weak bet, and A's 2.5 of 4 on dev's low ties is probably luck. C follows the calibration, but it does worse on dev (1.5 of 4).
- **The 4 low-tie cases are where A and B differ.** A gains 4.1 overall points on dev. Its expected accuracy on those cases elsewhere is about one in three, but deciding them can't lower overall, because a non-decided answer already counts as wrong.
- **Recommendation: A**, the policy the owner asked for. It has the best dev overall, it meets the guardrail (accuracy on decided 82.9% ≥ 70%), and the metric rewards deciding. **B is the fallback** if the owner wants accuracy on decided protected: on validation, 16 uncertain answers decided at about 50% would pull accuracy on decided from 77.9% toward 71%. C is not recommended. Owner decision **D1**.
- **What the answer shows:** the answer names the reading it chose and lists the other readings in `uncertain_signs`, so a decision made this way is visible in the proof. The verdict `uncertain` stays for readings that are tied under B. Under A, `uncertain` is never produced by readings. That is a change to a CLAUDE.md / DESIGN.md convention ("uncertain (alternative readings disagree)"), so the wording of both changes with the owner's yes.
- **Judge:** the 6 newly decided answers are Natural QA and need the judge. At the candidate run's rates ($0.00025 writer + $0.00533 judge each), that is **$0.033 (range $0.027–0.05)**. It is folded into step 6's dev re-parse, not run on its own.

### 2.2 Yes/No gap: a biased train working set

`eval/phase46_analysis.py trainset`: **train minus dev minus validation = 333 questions (232 Natural QA, 101 Yes/No on 83 images).** The validation split is read for its question and image ids only, to leave them out.

- **Biased; for diagnosis only, never a score.** Its images fed the parser few-shots (v7–v9), the stage-A sign list and rule design. A number from it says where Yes/No answers go undecided, not how well the system does.
- **Why it matters:** validation shows Yes/No at 39.6% decided (90.5% right when decided) against Natural QA at 54.4%. The causes can't be read there, and dev has no Yes/No.
- **Scene cache:** 19 of the 83 images already have a scene v5 record (all are set-T images), covering 21 Yes/No questions. 64 images would need fresh perception.
- **Estimate (no spend):**

| part | rate (measured) | cost |
|---|---|---|
| parser v9, 101 questions | $0.00396 per question (v9 gate run + v9 dev re-parse, 51 calls) | $0.40 |
| perception v5 + fallback + guide, 64 new images | $0.0021 per image (candidate dev run) | $0.13 |
| writer on decided (about 45%) | $0.00025 | $0.01 (can be skipped: grade the engine verdict) |
| judge | none: Yes/No is graded by the yes/no mapping | $0 |
| **total** | | **$0.55 (range $0.44–0.71)** |

- **Cheaper option: the 21 Yes/No questions on the 19 cached images only, parse only: about $0.08.** It is a smaller sample, all of it set T, which is the most biased part.
- **What it needs:** a runner, `eval/e2e_trainset.py` (not built). Its header marks the run `biased: true`, it refuses any validation question or image id, it writes per-question records to the gitignored `eval/runs/`, and it uses the frozen phase-4.5 configuration with the fallback off.

### 2.3 Out of scope: what the questions ask

**Dev's 12** (from the v9 re-parse, grouped by hand by what they ask):

| group | dev ids | count |
|---|---|---|
| **guide-board content beyond today's `guide` asks** (yes/no about a board's content, road type from board symbols, a route code's meaning, the junction shape, a place beside a board) | 231, 259, 260, 361, 386 | 5 |
| **compound: two asks in one question** | 248, 414, 515 | 3 |
| **why / which vehicle is at fault** | 15, 351 | 2 |
| speed range (min and max) | 413 | 1 |
| traffic light | 341 | 1 |

**Train working set, by wording only** (the parser never ran on them; checked by eye from `oos`'s patterns, so these are likely out-of-scope questions, not measured ones):
- compound (two asks) about 8: 41, 76, 77, 132, 343, 373, 422, 493;
- why / at fault 4: 21, 270, 347, 392;
- board content about 4: 198, 301, 340, 363;
- speed range 4: 385, 466, 486, 490;
- counting signs 4: 172, 243, 458, 469;
- road markings 2: 94, 113;
- traffic lights 0 (282 is about priority vehicles' lights, not a signal).

**Proposed new intents, the three largest groups:**

| | intent | sources (law_db first) | dev gain | train working-set gain (wording) |
|---|---|---|---|---|
| **I1** | **`multi`:** 2–3 sub-programs in one question. Each part is answered on its own, and the question is decided only when every part is. Also a small `meaning` aspect, `article` ("quy định ở điều nào", 76 / 77), read from the catalog citation | no new rule: each part cites its own rule; `article` uses the catalog's `law_id` + `article_id` (QCVN 41:2024/BGTVT) | +2 (248, 515), +3 with I2 (414) | about +6 of 8 |
| **I2** | **guide-board content:** new `guide` asks: `road_type` (expressway / national road from the board's colour and route code); `has` (yes/no: does the board name X, or give a distance to X); `destinations` filtered by arrow direction (414's slanted-arrow lane). Read from the board data only; any legal conclusion still comes from the engine | QCVN 41 art. 45 (45.1.6 expressway guidance), art. 47 (the expressway start board carries the expressway's name and code and its max / min speeds), appendix N (expressway codes, "mã hiệu đường cao tốc"), I.4 (a green background means an expressway, blue other roads), E.40 (I.437) | +3 (231, 259, 260); 361 and 386 stay out | about +2–3 (301, 340; 363 counts services, so out) |
| **I3** | **`explain`:** wraps a claim and answers it with the proof's deciding reasons ("vì sao"). "Xe nào bị phạt" is read as "which vehicle breaks the rule". Fine amounts stay out of scope: Decree 168/2024 is not an allowed source | no new rule: the wrapped claim's rules (e.g. P.127 B.27, P.130 B.30) | +1 (15); 351 needs a stopping exception the scene can't show, so likely unknown | about +2 (21, 392; 347 also chooses among options) |
| *I4, optional* | *`speed_limit` with `kind: range`* (min and max together) | P.127 (B.27), R.306 (D.6), board speeds (art. 47), Circular 38 expressway 120 / 60 defaults (already `r_c38_*`, interpretation) | +1 (413) | about +4 |

- **Estimated gain on dev: about +6 decided from I1–I3** (+7 with I4), i.e. 64 → about 70 before the uncertain policy and about 76 after it (**87% coverage if all hold**). That assumes the parser maps each question as hoped; accuracy is untested.
- **On validation it can't be measured** (aggregate only). On dev, the three groups are 10 of 12 out-of-scope questions; in the train wording they are about 16 of 30.
- I4 is small and could ride in the same parser version. It is listed so the owner can choose (**D2**).

## 3. Steps

**Guardrail (every step):** a change is kept only if dev overall (non-decided = wrong) doesn't drop below the last kept step's (starting at 62.6%), and dev accuracy on decided stays **≥ 70%**. Accuracy on decided is reported every time. Provisional grades are marked as such until the judge confirms them.

1. **Uncertain policy (free).** In `Engine.answer`: the chosen policy (D1; A recommended) picks the reading, the answer names it, and the other readings go in `uncertain_signs`. Tests on hand-made scenes modelled on train. A free engine-only dev replay against the guardrail.
2. **`eval/e2e_private.py` fix (free; required before the private run).**
   - Add the rules-only figures, as `eval/e2e_validation.py`'s `aggregate` does: decided coverage, accuracy on decided, overall with non-decided counted wrong, and their 95% CIs, on all images and on non-duplicate images.
   - Re-base the estimate on phase-4.5 measured rates: $0.0076 per question with the fallback off (final validation), plus the fallback's share if it stays on. Replace `HOLDOUT` and the `ee.COST` phase-4 rates.
   - It must check the phase-4.6 freeze record once there is one (it checks `frozen_phase45.json` today). Tests with a fake SDK; no call.
3. **Train Yes/No diagnosis (paid, optional, D3).** Build `eval/e2e_trainset.py` (section 2.2), then one run on the owner's go-ahead: the cached-only option ($0.08, cap $0.15) or the full option ($0.55, cap $0.75). It reports causes by question type, marked biased. Any Yes/No fix it suggests goes into step 4's parser version, with few-shots from the working set.
4. **I1–I3 (+ I4 if chosen) and parser v10 (free to build).**
   - DSL in `vqa/schemas.py` and `vqa/parsing/wire.py`, engine handlers, template answers, validator dry runs, and tests per intent.
   - `prompts/parser/v10/`: few-shots from the train working set with the exact question text, never dev or validation.
   - A free engine-only replay with hand-written v10-style programs (indicative only).
5. **Parser gate, v10 (paid): one run** on public_dev gold intents. Estimate **$0.21 (range $0.19–0.25)**; v9's run was $0.192 and v10's prompt is longer. `--max-spend 0.30`. The rule is set before the run: no old gold intent type may lose pooled accuracy against v6, after giving back rows that use a v10 feature (`compare`). The gate (mean ≥ 90%) is reported.
6. **Dev re-parse with v10, `--select all` (paid).** 87 parses at about $0.0030 each, plus the writer and the judge on changed decided answers (about 12, the 6 uncertain ones included, at $0.0056 each). **$0.33 (range $0.27–0.43)**, `--max-spend 0.45`. The guardrail on judged figures; this run also confirms the provisional grades.
7. **Freeze and "final2" validation (owner decision D4; see section 4).**
8. **Schema 1.2 → 1.3 in CLAUDE.md and DESIGN.md (doc-only; owner's yes, D5).**
   - Write up the 1.3 boards, the phase-4.5 intents and slots (sign group, conduct, presence, scope, placement, divided road, several vehicles), negative lanes, the guide call, and this phase's intents and uncertain policy.
   - `vqa/schemas.py`'s `SCHEMA_VERSION` constant is still "1.2" (scenes without boards dump as 1.2 did; `GUIDE_SCHEMA_VERSION` is "1.3"). The doc-only step leaves the code alone; whether to change the constant is a separate question for the owner, because it changes stored scene dumps.

Each step ends with a status entry and a commit (files staged by name). The owner runs every paid command.

## 4. Open owner decision: a "final2" validation run

- **What it would be:** a new label `final2` in `eval/e2e_validation.py` (`LABELS["final2"] = eval/frozen_phase46.json`), with its own freeze record written once through `eval/freeze.py write --profile phase46`, its own sentinel `eval/validation_ran_final2.json`, aggregate only, run once. `final` and `baseline` stay blocked by their sentinels; `frozen_phase45.json` stays as is.
- **Cost:** **$0.85 (range $0.70–1.05)**, `--max-spend 1.05` (final measured $0.83; v10's prompt is a little longer).
- **The trade-off:** each use of the validation set spends some of its independence, and round 2's changes are tuned on dev. Without final2, round 2 is measured only on dev (readable, tuned on, optimistic: dev 73.6% against validation 47.3% in phase 4.5) before the private run.

## 5. Budget ($2.05 left)

| step | estimate | cap |
|---|---|---|
| 3. train Yes/No diagnosis | $0.08 cached-only, or $0.55 full | $0.15 / $0.75 |
| 5. parser gate v10, one run | $0.21 | $0.30 |
| 6. dev re-parse v10 (includes the uncertain-policy judging) | $0.33 | $0.45 |
| 7. final2 validation (if D4 yes) | $0.85 | $1.05 |

- **Profile 1, with final2 (recommended):** cached-only diagnosis + gate + re-parse + final2 = **$1.47 estimated**, caps $1.95, within $2.05.
- **Profile 2, without final2:** full diagnosis + gate + re-parse = **$1.09 estimated**, caps $1.50; about $0.96 left.
- **Full diagnosis and final2 together** come to $1.94 estimated, but their caps sum to $2.55, over the $2.05 left, so they are not proposed together.
- **The private run is not in this budget.** Its cost is re-based in step 2, and it needs its own go-ahead and money (D6).

## 6. Decisions for the owner

- **D1** uncertain policy: A (recommended) or B.
- **D2** intents: I1–I3 as proposed; I4 too?
- **D3** train Yes/No diagnosis: cached-only, full or skip.
- **D4** final2 validation: yes or no.
- **D5** the schema 1.3 doc update in CLAUDE.md and DESIGN.md: yes or no (and whether `SCHEMA_VERSION` changes).
- **D6** the private run's budget, outside the round's $2.05.
