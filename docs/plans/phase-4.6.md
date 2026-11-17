# Phase 4.6 plan (proposed): coverage round 2

**Status: approved (owner, 2026-11-17)** with the decisions in section 7, which override sections 2–6 where they differ. **Steps 1 and 2 and the D3 runner are built** (section 8). Every figure below is free: it comes from stored runs through `eval/phase46_analysis.py` (no API call). Nothing in `vqa/` or `app/` has changed. Not touched: the validation set beyond its ids and aggregate, its sentinels, public_holdout, private, gold, `eval/frozen_phase4.json`, `eval/frozen_phase45.json`.

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

## 7. Decisions (owner, 2026-11-17)

- **D1: policy A.** Built as a switch: `Engine(reading_policy="higher_confidence")` / `PipelineConfig.reading_policy`. The default `"all"` (disagreeing readings give `uncertain`) is the frozen behaviour of both freeze records, which still match. The phase-4.6 freeze profile will set `"higher_confidence"`.
- **D2: I1–I4** (`multi`, guide-board content, `explain`, speed range).
- **D3: parse only**, all 101 train Yes/No questions with v9, no new perception, **about $0.40**. Causes are reported by question type, marked biased. This replaces section 2.2's options.
- **D4: final2 yes, run last.** Its cap is set when it runs, to what is left of the $2.05 and at most $1.05. Every step's cap is set when that step runs, so the caps never sum past $2.05.
- **D5: yes** to the doc update in CLAUDE.md and DESIGN.md: schema 1.3, the phase-4.5 and 4.6 intents, and the uncertain-verdict wording that policy A changes. `SCHEMA_VERSION` stays "1.2" for now.
- **D6:** decided after step 2's re-based estimate (section 8).

**Budget, revised ($2.05 left; each cap set when its step runs):**

| step | estimate (range) | cap when it runs |
|---|---|---|
| 3. D3 parse-only train Yes/No | $0.40 ($0.32–0.52) | $0.55 |
| 5. parser gate v10, one run | $0.21 ($0.19–0.25) | $0.30 |
| 6. dev re-parse v10, `--select all` | $0.33 ($0.27–0.43) | $0.45 |
| 7. final2 validation | $0.85 ($0.70–1.05) | what is left, at most $1.05 |
| **total** | **$1.79** | |

- **Expected left for final2: $1.11** after steps 3, 5 and 6 at their estimates, so its cap is $1.05.
- **If steps 3, 5 and 6 all land at the top of their ranges ($1.20), $0.85 is left.** That equals final2's estimate with no margin, so final2's cap would be $0.85, and a run that needs more would stop part way and still use up the label. If less than $0.90 is left by then, final2 needs the owner's decision first.

## 8. Built (2026-11-17; no API call)

**Step 1, policy A** (`43f5b10`, `8fc3d66`): `vqa/reasoning/facts.py` `top_reading`, `vqa/reasoning/engine.py` `_higher_confidence`, the switch in `vqa/pipeline.py` and `eval/freeze.py`, and the tests in `tests/test_phase46_reading_policy.py`.
- **The answer** names the reading it used in `note`, lists the signs in `uncertain_signs` and carries `basis: ["reading_choice"]`.
- **Dev replay** (`eval/phase46_analysis.py step1`, every dev question through the engine switch): **70 of 87 decided (80.5%), accuracy on decided 82.9%, overall 66.7%**, against 73.6% / 85.2% / 62.6%. Only the 6 uncertain answers changed; their grades are provisional until step 6's judge. **Guardrail met; kept.**

**Step 2, `eval/e2e_private.py`** (`c3c9f40`):
- **Rules-only figures:** `rules_only` in the report gives decided coverage, accuracy on decided and overall with non-decided counted wrong, each with its 95% CI. They come by question type and on all, non-duplicate and duplicate images (duplicate: also in train or public).
- **The re-based estimate** uses counts only (146 questions, 104 images, 76 Natural QA, from DESIGN.md), so the private file is not read. It uses the phase-4.5 stage rates, calibrated ×1.146 to the final validation's measured $0.83.
- **Still to do before the private run:** point it at the phase-4.6 freeze record once that exists (step 7).

| private run estimate (D6) | at validation's decided share (47.3%) | at dev's decided share after step 1 (80.5%) |
|---|---|---|
| fallback off (rules only) | **$1.15** ($0.92–1.50) | $1.32 ($1.06–1.72) |
| fallback on (the run's default; a fallback answer per non-decided question) | **$2.10** ($1.68–2.73) | $1.67 ($1.34–2.17) |

The fallback-answer rate is still phase 4's ($0.008 per call); no later run measured it.

**D3 runner, `eval/e2e_trainset.py`** (`08630ce`):
- **What it refuses:** any dev or validation question or image id (ids only from the split files), a dirty tree, and a configuration that differs from `frozen_phase45.json`.
- **What it does:** parses with v9, makes no perception call, and rebuilds cached scenes cache-only with every call refused. The engine runs with policy A. Records are marked biased.
- **Command:** `.venv/bin/python eval/e2e_trainset.py estimate` gives 101 questions on 83 images, **$0.40 ($0.32–0.52)**. Run: `.venv/bin/python eval/e2e_trainset.py run --max-spend 0.55`, then `summary <file>`.

## 9. D3 result: parse-only train Yes/No (run `821164d62679`, $0.4184; a biased set, diagnosis only)

**101 Yes/No questions, parser v9:** 82 ok, **17 out of scope, 2 invalid.** Intents among the ok parses: permitted 25, forbidden 14, all_of 12, is_sign 12, speed_ok 7, required 3, verify 3, exists_violation 3, present 2, any_of 1.

**The 17 out-of-scope questions, grouped by what they ask (read by hand):**

| group | ids | count | covered by |
|---|---|---|---|
| **a yes/no claim about a guide board** (a place and its distance, a road type, an exit ahead, a route, which lane to take for a turn) | 104, 105, 124, 267, 301, 358, 390, 424 | 8 | **I2** (`guide` claims) |
| what lies ahead: a Y junction, a tunnel | 378, 389 | 2 | I2 or `is_sign` / `meaning` (W-sign pictograms) |
| road markings (solid line, double solid line) | 94, 113 | 2 | not planned (QCVN 41 G.*) |
| a speed range claim (max 120 and min 60) | 359 | 1 | **I4** |
| who a sign applies to, or "every vehicle except trucks" | 312, 256 | 2 | not planned |
| a set of lanes ("one of the two left lanes") | 433 | 1 | not planned |
| counting signs | 332 | 1 | not planned |

- **Guide-board claims are the largest Yes/No gap: 10 of 101,** counting the two "what lies ahead" questions. I2 must therefore include a **claim form** that checks a stated place, distance, direction or road type against the board data, not only lookups. That is within D2's I2.
- **Invalid parses (2), both parser v10 items:**
  - 84 put `day_parity` inside `when`, which the schema doesn't allow ("cấm đỗ xe vào ngày chẵn");
  - 235 used a vehicle class outside the enum ("xe nặng hơn 3 tấn").

**Engine on the 21 questions with a cached scene** (cache-only; 8 refused region or board calls; indicative): 11 decided, 9 of 11 right. Not decided: out of scope 5, program can't run 3, unreadable sign 2.
- **Can't run, 3:**
  - 274 and 498 ask `is_sign` with `only` over a scene with several signs ("Đây có phải là biển cấm ... không?" with two or three signs);
  - 183's colour selector matches no listed sign.
- **Wrong, 2:**
  - **276:** "Trong ảnh không có biển nào chỉ hướng rẽ, đúng không?" was answered yes although two signs are unreadable. **A negative presence claim should be unknown when an unreadable sign could be the one asked about** (the CLAUDE.md closed-world rule). This is an accuracy bug.
  - 338: a violation question; the scene lists no vehicle, which is a perception gap.

**Proposed for step 4 (free; beyond D2, so the owner's OK is needed):**
- **F1:** `is_sign` with `only` over several signs: yes if every readable sign matches, no if none does, unknown otherwise (274 → no, 498 → yes).
- **F2:** a negative `present` claim is unknown when an unreadable sign could match it (276).
- **Parser v10 items from D3:** `day_parity` in claims, and weight phrases without a class ("xe nặng hơn 3 tấn" → `vehicle` with `gross_gt`).

**Budget after D3:** $2.95 + $0.42 = **$3.37 of $5; $1.63 left.** Next come the gate ($0.21, cap $0.30) and the dev re-parse ($0.33, cap $0.45); that leaves about $1.09 at the estimates, so final2's cap would be $1.05.

## 10. Step 4 built (2026-11-17, `bd16777`; no API call)

**Owner decisions for step 4 (2026-11-17):**
- F1 and F2 approved;
- I2 must check stated board claims, with D3's 10 as the target;
- v10 fixes the two invalid parses, using weight bounds, not a new class;
- road markings, "who a sign applies to" and lane sets stay out of scope;
- if v10 fails the no-regression rule, one fix as v11 is allowed;
- final2 runs only if at least $0.90 of the round is left, otherwise the owner decides.

**Engine (`vqa/reasoning/engine.py`):**
- **F1:** `is_sign` with `only` over several signs follows the single-sign rule: unreadable signs are dropped; yes if every readable sign is the named one, no if none is, unknown if mixed or if none is left.
- **F2, with a corrected diagnosis.** On 276 the parse asked for R.301 (blue discs), and the two unread signs are red boards, so the existing look rule already excluded them correctly; the rule was not mis-applied.
  - What was missing: a red board is a local notice in free text, so its look rules nothing out.
  - The fix: an unread red board now keeps a negative presence claim, and an "ahead" claim, unknown. 276 is now undecided instead of wrong.
- **`when.day_parity`** ("vào ngày chẵn / lẻ", no date): the engine takes a day of that parity, which is all P.131b / P.131c depend on.
- **I1, `multi`** (2–3 parts): decided when every part is. Plus the `meaning` aspect `article`: the group's listing article (22.1 P, 28.1 W, 32.1 R, 36.1 I, 47 IE, 41 S) and the appendix article the row cites.
- **I2, `guide_claim`** (`distance`, `direction`, `listed`, `road_type`, `ahead`), plus `guide` asks `road_type` and `destinations` by arrow `direction`. Board data and sign codes only.
  - Road type comes from IE codes (art. 45; art. 36.1: "I" is for roads that are not expressways), the scene's road type, and "QL" route plates (art. 46).
  - "Ahead" features use sign codes whose catalog rows cite their article (W.240 C.40, W.238 C.38, W.205 C.5, W.206 / R.303, IE.454 / IE.455 / IE.464b / IE.474 art. 47), and whole words on the boards.
- **I3, `explain`:** the inner claim or choice answered with the signs that decide it. Fine amounts stay out.
- **I4, `speed_limit` `kind: range`, and the claim `speed_limit_is`.**
- **No catalog change,** so the scene and parser prompts frozen in phase 4.5 are unchanged; `freeze.py check` matches both records.

**Parser v10** (`prompts/parser/v10/`):
- **Spec:** v9 plus the I1–I4 lines, `day_parity`, weight-only vehicles (`motor_vehicle` + `gross_gt`), and board claims moved from out of scope to `guide_claim`.
- **Few-shots:** v9's two board-claim shots marked out of scope (train_124, train_424) now show `guide_claim`. Six new shots come from the train working set (exact text; no dev or validation question or image): 76, 422, 104, 340, 21, 490. The prompt is 11% longer.
- **Gate compare:** `eval/parser_eval.py` gives back v10's new forms as design changes, like v7's (`DESIGN_FEATURES`).
- **Validation split test:** `test_the_committed_split_is_what_the_builder_makes` now also ignores the report count `duplicate_of_an_excluded_train_image` (7 → 6, because one image moved to "named in repo" with v10's shots). The pool (114 images, 197 questions) and the draw are unchanged, and the split file is untouched.

**D3's 10 board claims under v10:**
- covered: 104, 105, 124, 267, 301, 389, 424, and 390 (approximated as a direction claim; the order of the turns is not modelled);
- not covered: 358 (which lane to take, a lane set: out of scope) and 378 (a Y junction: the shape is not readable from W.205's family code);
- **three of the covered ones are v10 few-shots (104, 124, 424),** so on those three the parse is not a test.

**Free replays (`eval/phase46_analysis.py step4`; policy A, F1, F2; hand-written v10-style programs for the out-of-scope questions, the stored parse for every other question; indicative):**

| | decided | accuracy on decided | overall |
|---|---|---|---|
| dev after step 1 | 70 / 87 (80.5%) | 82.9% | 66.7% |
| **dev after step 4** | **75 / 87 (86.2%)** | **80.0%** | **69.0%** |
| D3 cached scenes, before (biased, 21 questions) | 11 | 9 right | |
| D3 cached scenes, after | 15 | 13 right | |

- **Dev newly decided** (provisional grades, assistant): 231 (0: claims the board names Đông Hà; the dataset says it gives no distance), 260 (0.5), 351 (0: a priority vehicle on duty the scene can't show), 413 (1), 414 (0.5). **The guardrail holds.**
- **Still not decided on dev:**
  - 15: the truck's limit depends on a condition;
  - 248: the disc was read as R.306, a minimum, and the board has no arrows;
  - 515: R.411 is unmodelled;
  - 259, 341, 361, 386: stay out of scope.
- **D3 changes:**
  - F1 decides 274 and 498, both right;
  - F2 takes 276 out of the wrong answers;
  - 424 is right (a few-shot);
  - 359 is wrong (the stated 120 / 60 against the scene's limits);
  - 136 is now decided and right, by policy A.

## 11. Step 5: the parser gate, v10 (paid; the owner's go-ahead)

- **Estimate $0.21 (range $0.19–0.25):** v9's measured $0.1915 on 47 questions, scaled to v10's longer cached prompt (about 20,850 against 18,705 tokens).
- **Cap $0.40.** The runner refuses up front when its own conservative expected cost exceeds the cap, and that figure is $0.37 for v10 (it was $0.35 for v9), so $0.30 would be refused. The spend guard keeps one call's worst case ($0.093) free, so a run stops by $0.31 at the latest.
- **The rule, set before the run:** no old gold intent type may lose pooled accuracy against v6's three runs, after giving back rows that use a v7 or v10 feature (`regressed_types_without_design` empty). The gate (≥ 90%) is reported. If v10 fails the rule, one fix as v11 is allowed.
- **Budget:** $3.37 of $5 spent, **$1.63 left.**
  - After the gate ($0.21) and the dev re-parse ($0.33, cap $0.45), about **$1.09** is expected to be left.
  - final2 needs at least $0.90 left.
  - If both runs hit their caps, $0.78 is left and final2 goes to the owner.

## 12. Step 5 result: v10 fails the no-regression rule; v11 built (the one allowed fix)

**v10 gate run** (`pred_claude-sonnet-5-5_medium_v10_20261117-184429.jsonl`, **$0.1895**, 47 public_dev questions):
- **Program accuracy 76.6% (36/47),** against v9's 91.5%. The gate (≥ 90%) fails; the gold is v6-era, so design rows count as wrong here.
- **Against v6's three runs, by type:** `regressed_types_without_design` = **`permitted`** (8/10) and **`which_vehicles`** (1/2). **v10 fails the rule.**
- **New misses against v9, read question by question (public_dev is readable):**
  - 0014 and 0095, `permitted`: a truck's stated weight ("xe tải trên 4T / 10t") parsed as `gross_gt` instead of `load_gt`. **Caused by v10's new weight-only vehicle line,** which was too broad.
  - 0058, `which_vehicles`: `sign: {only: true}` dropped. v10 changed nothing there, so it is probably run noise.
  - 0055 and 0063: v6 gold says out of scope; v10 writes `guide_claim`. Design, given back.
  - 0084: `forbidden` + `every_vehicle` instead of `is_sign`. 0086: `aspect: group` where v9's spec says `name` for "loại biển nào", a real miss given back as design because `group` is a v7 feature.

**v11** (`prompts/parser/v11/`) = v10 with two spec lines changed and v10's few-shots:
- the weight-only line applies only when no kind of vehicle is named, and a weight given with a kind keeps `load_gt` ("xe tải trên 5 tấn" = truck, `load_gt: 5`);
- `which_vehicles` keeps the sign selector the question gives.

Neither line quotes a gate question (checked by the spec tests).

**Next: the v11 gate run, then the same compare.** Estimate **$0.19** (v10 measured $0.1895; same prompt length), cap **$0.40**.
- **If v11 fails the rule, stop:** no further fix is allowed, and the owner decides.
- **Budget:** $3.37 + $0.19 = **$3.56 spent, $1.44 left.** After the v11 gate ($0.19) and the dev re-parse ($0.33), about **$0.92** would be left: just above final2's $0.90 floor, with no margin. A dev re-parse above $0.35 puts final2 below the floor.

## 13. v11 passes the no-regression rule; step 6 prepared

**v11 gate run** (`pred_claude-sonnet-5-5_medium_v11_20261117-184930.jsonl`, **$0.1861**):
- **Program accuracy 85.1% (40/47),** slot F1 91.9%. The ≥ 90% gate figure fails on the point estimate and is reported only; the rule decides.
- **`regressed_types_without_design` is empty: v11 passes.** `permitted` 10/10 and `which_vehicles` 2/2.
- **The 4 lost rows are all given back as design:** 0055 and 0063 (now `guide_claim`), 0086 and 0087.
  - **0086 is a real miss:** `aspect: group` where the spec says `name` for "loại biển nào". It counts as design only because `group` is a v7 feature.
  - 0084 (an `is_sign` claim parsed as `forbidden`) is still wrong, as with v6's accuracy for that type.
- **v11 is the parser for the rest of phase 4.6.**

**Step 6: dev re-parse with v11.**
- **What it runs:** every dev question, from the v9 re-parse (the current dev record), with the engine's policy A. `eval/e2e_dev.py reparse` gained `--reading-policy`: with it, the engine also re-runs on unchanged parses, and an answer whose decision changes is written and judged again.
- **Estimate $0.37 (range $0.33–0.45):** 87 parses at v11's measured rate ($0.052 for the first, cache-writing call, then $0.0029 each: $0.30), plus the writer and the judge on about 10–16 changed decided answers ($0.0056 each).
- **Cap $0.50,** because the spend guard keeps one call's worst case ($0.093) free, so a $0.45 cap could stop near the end.
- **Budget:** $3.56 + $0.19 = **$3.75 spent, $1.25 left.** After step 6 at its estimate, **$0.88** would be left, below final2's $0.90 floor, so **final2 goes to the owner (the rule set before the gate).** At the bottom of the range ($0.33), $0.92 is left.
