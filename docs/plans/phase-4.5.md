# Phase 4.5 plan (proposed): rule coverage for a rules-only report

**Status: approved (owner, 2026-11-16):** Q1–Q6 yes, as proposed. **The targets in section 4 are fixed and don't move after any result: 80% decided coverage is the aim; the 70% floor is what must hold.** Every fix is built from train and public_dev only; tests use hand-made scenes modelled on train; the owner reviews new catalog rows before the new freeze. The figures below come from stored runs (`eval/coverage_analysis.py`, no API call). The private run is on hold (`docs/plans/phase-5.md`).

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

## Decisions (owner, 2026-11-16: all approved as proposed)

| | question | decision |
|---|---|---|
| Q1 | Approve this plan as phase 4.5, before the private run | yes |
| Q2 | The targets and floors in section 4 | as written |
| Q3 | The validation set: about 110 questions from the 197-question pool, Yes/No drawn first, aggregate only | yes |
| Q4 | A baseline validation run with today's frozen system (aggregate only, about $1.1) before any fix | yes |
| Q5 | Fixes 5 and 6 (perception, high risk) only if fixes 1–4 leave coverage short | yes |
| Q6 | The private run with fallback on, so the demo figure comes from the same run | yes |

## 9. Scope-expansion round (owner, 2026-11-17)

The baseline validation (`docs/status.md`) decided 30.0% (22–39), with accuracy on decided 72.7% (56–85) and overall 21.8% (15–30). Out of scope was the biggest cause: 43 of 110. This round widens what the rules can answer, and it is built on a dev set with the validation set's profile.

**Hard budget: $5 for everything in this round** (dev runs, parser v7 development and its gate rerun, the final validation). No API call is made without the owner's go-ahead on an estimate, and the owner runs paid commands.

**Dev set:** the 87 questions on 60 images left in the validation pool once the validation set is removed (`data/splits/train_dev.json`, ids only). It has the same profile as the validation set: untouched, and no duplicates with public or private. **Dev may be read question by question; the validation set stays aggregate only.**
- **One difference (found when it was built):** the dev set is **all Natural QA** (87 of 87). The validation draw took Yes/No images first, and that took every Yes/No image in the pool. So Yes/No question types come from train minus the validation set (step 3a) and from public_dev, not from dev.

**Steps:**
1. **Dev run:** the frozen system, fallback off, keeping per-question records (scenes, parses, verdicts, grades) in the gitignored `eval/runs/` folder (`eval/e2e_dev.py`).
2. **Dev analysis (free):** every undecided dev question with its cause, and for out_of_scope, the missing intent. Each is classed as either a parser wording failure (the question fits an existing intent) or a new question type. Accuracy on decided, with the wrong answers explained.
3. **Scope expansion:**
   - a. Count the question types across train minus the validation set (free). For each type the system can't answer: train and dev counts; whether it needs a new DSL intent (parser v7), a new rule over an existing intent, or only a parser wording fix; its law articles; whether perception can supply what it needs; size in days.
   - b. Propose the set to add, ranked by train questions gained per day, with a stopping point. For each: the intent schema, rules, tests and accuracy risk. Free engine, selector and KB fixes come first, checked by engine-only replay on the dev parses. Parser v7 gets few-shots from train with the exact question text, then a parser-gate rerun on public_dev gold intents, where no regression is allowed (priced). **Stop for the owner's approval before building.**
   - c. **Guardrail:** after each new type, the dev replay must keep accuracy on decided ≥ 85%. A type that can't stays out of scope (in the demo it goes to the fallback).
4. **After the fixes:** one dev replay; the new freeze record `eval/frozen_phase45.json`; then the final validation command, run once.

**Success criterion (fixed now):** the final validation's decided coverage and overall are clearly above the baseline (outside the baseline's 95% CI: above 39.1% coverage and above 30.4% overall), and accuracy on decided is ≥ 85%. The 80% / 70% targets stay as written and are reported as met or missed.

**Rules:**
- Fixes are built from dev, train and public_dev only.
- Tests use hand-made scenes modelled on train.
- Every rule cites its `law_id` + `article_id`, and Prolog rules have no cuts.
- The owner reviews new catalog rows before the freeze.
- Files are staged by name, with the list checked before each commit.
- Not touched: the validation set beyond its aggregate, public_holdout, private, and gold.

## 10. Scope round: dev findings and the proposed additions (2026-11-17; proposed, awaiting the owner's approval)

### Dev run (`13ded0d75451`, frozen system, fallback off, $0.612)

| dev (87 Natural QA) | decided coverage (95% CI) | accuracy on decided (95% CI) | overall, non-decided = wrong |
|---|---|---|---|
| frozen phase 4 | 40.2% (31–51) | 80.0% (64–90) | 32.2% |

**The 52 undecided questions, by what fixes them:**

| class | questions | ids |
|---|---|---|
| parser wording or selector failure (an existing intent fits) | 5 | 14, 99, 260, 287, 421 |
| new slot on an existing intent (sign group) | 4 | 78, 160, 520, 523 |
| perception (a misread or unreadable sign) | 4 | 316, 450, 514, 518 |
| new question type with a law basis | 31 | guide-sign content 21; driver conduct 4; STOP sign 2; placement 2; presence 1; scope of effect 1 |
| stays out: no `law_db` article, or outside v1 | 8 | speed by road type 4 (54, 55, 56, 58); speed range 2 (254, 413); traffic light 1 (341); "why" 1 (351) |

- **14** (parse failed): speed limits for two vehicles; the parser added a `sign` field `speed_limit` doesn't take.
- **99**: "Biển trong ảnh cấm hành vi gì?" with four signs: needs `select(category=prohibitory)`, not `only`.
- **260**: "Các ký hiệu trên biển cho biết đây là loại đường nào?": the meaning of IE.452, selected by code or look, not `only`.
- **287**: the selector asks for red border and red background, but the scene records P.102's look differently: selectors should also match on visual category.
- **421**: "Xe máy được đi ở những làn nào": the lane count is missing, though R.415a's board rows give it.
- **78, 160, 520, 523**: "thuộc nhóm nào": the readings or signs differ, but they all fall in the same QCVN 41 art. 11 group.
- **316, 450, 518, 514**: guide-board alternatives, a P.124c alternative, an R.420 alternative, an UNKNOWN junction sign.
- **Guide-sign content** (80, 159, 230, 231, 248, 249, 250, 258, 259, 261, 325, 327, 329, 348, 361, 397, 414, 415, 515, 521, 525): destinations, distances, directions and route names printed on I/IE boards.
- **Driver conduct** (216, 219, 222, 432): "người lái xe cần làm gì" after warning, prohibitory or mandatory signs. **STOP** (337, 375): R.122, not in the catalog, so perception reads it UNKNOWN.
- **Placement** (402, 517), **presence** (107: "biển nào không có trong ảnh"), **scope** (269: "có hiệu lực từ đâu đến đâu").
- **Out:** speeds by road type after R.420 (no `law_db` article gives them); speed ranges on expressways (no article for default expressway limits); a traffic light; an explanation question.

**Wrong or partial decided answers (7 points lost of 35):**
- **81** (wrong): the scene has IE.452 (start of expressway), but no rule bans mopeds, motorbikes and rudimentary vehicles there (Law 36 art. 25.3), so the closed world says yes.
- **145** (wrong): "Biển phụ cho biết điều gì?": the plate is S.501 "Phạm vi tác dụng của biển" (QCVN 41 F.1), which is not in the catalog; the answer described the main sign.
- **272** (partial): the police car without signals was "undetermined", but P.127 applies to every vehicle, so the vehicle's kind doesn't matter.
- **308** (partial): the group was named "biển chỉ dẫn bắt buộc"; art. 11 calls it "biển hiệu lệnh".
- **352** (wrong): an expressway choice with no speed sign in the scene. The speed options are unknown, and stopping on the expressway is not ruled out (Law 36 art. 25.2), but a `choose` with unknown options still counted as decided.
- **381** (wrong): P.127 120 and R.306 60 over lanes, with no lane asked. Each option came out unknown, although every lane gives the same verdict.
- **451** (wrong): R.411 with no lane rows in the scene: the engine called all four lane claims false instead of unknown.
- **526** (wrong): perception read I.414 for an interchange sign.

### Question types across train minus the validation set (420 questions; keyword counts, checked by eye)

| type the system can't answer today | train (minus validation) | dev | needs | law articles | can perception supply it? | size |
|---|---|---|---|---|---|---|
| guide-sign content (destination, direction, distance, route) | about 36 | 21 | new intents (parser v7) + scene schema 1.3 (`guide` entries on I/IE boards) + scene prompt v5 | QCVN 41 art. 39, 45, 47; the board's own article (E.x, P.x) | partly: Haiku must read place names and distances; untested, no gold | 3–4 days |
| sign group ("thuộc nhóm nào") | 30 (dev: 9 of 13 already decided) | 4 | a `meaning` aspect slot (parser v7) + an engine rule | QCVN 41 art. 11 | yes (category from the code, or shared by every reading) | 1 day |
| driver conduct after signs | 9 | 4 | new intent `conduct` (parser v7) + rules per sign group | QCVN 41 art. 27 (warning), 32 (mandatory), 26 (prohibitory) | yes | 1 day |
| STOP sign R.122 | 2 | 2 | a catalog row (owner review) + `conduct` / `required` rule; the catalog change makes a new scene prompt version | QCVN 41 D.1 | yes once the row exists | 0.5 day |
| presence ("biển nào không có trong ảnh") | 10 | 1 | new claim `present(code or meaning)`, used inside `choose` (parser v7) | the signs' own articles (closed world over the scene) | yes, but it rests on recall and false positives | 1 day |
| expressway rules (entry ban, no stopping) | about 6 of 26 expressway questions | 1 wrong answer (81) | a rule over existing intents: IE.452 in the scene means an expressway | Law 36 art. 25.2, 25.3 | yes (IE.452 is read reliably) | 0.5 day |
| scope of effect | 3 | 1 | new intent `scope` (parser v7), and the S.501 plate row (owner review) | QCVN 41 art. 26, 30, 34; F.1 | yes | 0.5–1 day |
| placement ("đặt ở đâu") | 2 | 2 | new intent `placement` (parser v7) | QCVN 41 art. 16, 26, 30, 34, 39 | yes | 1 day |
| speed by road type, speed ranges, traffic lights, "why" | 5, 3, 2, 6 | 8 | — | none in `law_db` for the first two; outside v1 for the rest | — | not proposed |

### The proposed set, ranked by train questions gained per day

Free engine, selector and KB fixes come first. Each is checked by an engine-only replay on the stored dev parses (no call), and each is kept only if dev accuracy on decided stays ≥ 85% (3c).

| rank | addition | kind | dev gain (decided / right) | train questions | days | per day | accuracy risk |
|---|---|---|---|---|---|---|---|
| 1 | **accuracy fixes:** a `choose` / `which` answer with an unknown option needed for the answer is unknown, not decided (352); R.411 without lane rows gives unknown (451); P.127 applies to every vehicle, whatever its kind (272); group names from art. 11 (308) | engine, writer digest | −2 decided, +2 right (accuracy, not coverage) | — | 1 | — | lowers wrong answers |
| 2 | **expressway rules:** IE.452 in the scene means an expressway; entry banned for mopeds, motorbikes, rudimentary vehicles, four-wheel motor vehicles and pedestrians (art. 25.3); stopping and parking only where permitted (art. 25.2) | KB rule, `cite(r_expressway_*)` | +1 right (81) | about 6 | 0.5 | 12 | low (the article lists the classes) |
| 3 | **selector and lane-count fixes:** selectors also match on visual category (287); lane count from lane-board rows (421); lane-split speed signs that agree decide (381) | engine | +2 decided, +1 right | about 4 | 1 | 4 | low |
| 4 | **parser v7** (one prompt version for everything below): retry sends only the error; selectors by category and code (99, 260); `speed_limit` over a vehicle list (14); the new intents and slots of ranks 5–8; few-shots from train with exact text (not from the validation set) | parser | +3 decided (wording) | about 8 | 1 | 8 | low; gated on public_dev gold intents (no regression) |
| 5 | **sign group:** `meaning(..., aspect=category)`; decided when every reading, or every selected sign, falls in one art. 11 group | DSL slot + engine | +4 decided | about 9 | 1 | 9 | low |
| 6 | **driver conduct + STOP:** `conduct(select)` returns what the signs require: warning (art. 27: slow down, observe, be ready), mandatory (art. 32: obey), prohibitory (art. 26 + the sign's effect), R.122 (D.1: every vehicle stops, priority vehicles included) | new intent + rules + R.122 row | +6 decided | 11 | 1.5 | 7 | medium (the judge compares wording) |
| 7 | **presence:** `present(code or meaning)` inside `choose`; closed world over the scene, unknown when an unreadable sign of the same group could be it | new claim | +1 decided | 10 | 1 | 10 | medium (false positives in the scene) |
| 8 | **scope and placement:** `scope(select)` (art. 26, 30, 34; plates S.501 F.1); `placement(select)` (art. 16, 26, 30, 34, 39) | new intents + S.501 row | +3 decided, +1 right (145) | 5 | 1.5 | 3 | medium |
| 9 | **guide-sign content:** scene schema 1.3 `guide` entries (destination, direction, distance, route) on I/IE boards; scene prompt v5; `direction_to`, `distance_to`, `guide_text` | perception + schema + DSL + engine | up to +21 decided | about 36 | 3.5 | 10 | **high**: untested reading of place names and distances, no gold, judged on exact names |

**Stopping point:** build ranks 1–8 in order, replaying dev after each. Rank 9 is built only if three things hold: dev coverage after ranks 1–8 is below 70%, the round has at least $2.50 left, and the owner says go after seeing the replay. If any rank fails the 85% guardrail, it stays out of scope.

**Projected dev coverage:** 40.2% now; about 58% after ranks 1–8 (about +16 decided, −2 for the accuracy fixes); 70–80% if rank 9 reads boards well. Accuracy on decided after rank 1–3 fixes: about 90% on dev (2 wrong left: 352 if still decided, 526).

**Catalog changes** (owner review before the freeze): R.122 "Dừng lại" (D.1) and S.501 "Phạm vi tác dụng của biển" (F.1). A new row changes the scene prompt's catalog listing, so perception becomes `scene/v5`. A set-T perception check then confirms code F1 doesn't drop, and dev is re-perceived once.

**Tests:** hand-made scenes modelled on train questions outside the validation set, one or more per rank. Examples: a P.127 scene with a police car without signals (rank 1); an IE.452 scene with a moped (rank 2); an R.415a board with three rows and no road lane count (rank 3); two P.131 readings asked for their group (rank 5); W.227 with a conduct question (rank 6); a `choose` over four signs with one absent (rank 7); a P.128 + S.501 plate (rank 8). Every new rule cites `law_id` + `article_id` through `rule_source/3`, and Prolog rules have no cuts.

### Cost (round budget $5; $0.61 spent)

| item | estimate |
|---|---|
| parser v7: dev re-parse, two iterations (87 × 2) | about $0.50 |
| parser gate rerun on public_dev gold intents (3 runs × 47 programs) | about $0.45 |
| scene v5 (new catalog rows): set-T perception check + dev re-perception | about $0.25 |
| dev replays with judging of changed decided answers (about 3) | about $0.60 |
| final validation run, once | about $0.75 |
| **ranks 1–8 total** | **about $2.55** (with the $0.61 spent: $3.16 of $5) |
| rank 9, if it goes ahead: scene v5 guide runs on set T and dev, 2 iterations | about $0.80 more ($3.96 of $5) |

**Time:** ranks 1–8 about 8.5 days; rank 9 about 3.5 more.
