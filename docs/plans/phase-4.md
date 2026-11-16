# Phase 4 plan: answering and the end-to-end pipeline

DESIGN.md roadmap phase 4. **Status: approved by the owner on 2026-11-16**, with the decisions and changes below (the draft `phase-4-draft.md` is replaced by this file). Changes to this plan need the owner's approval.

**Starting point:**
- phase 3 closed with the perception gate **failed**. Phase 4 uses Haiku 5.5, prompt v4 + the fallback, under policy (d) (`docs/status.md`, "Phase 3: closing");
- the parser is Sonnet 5.5 at medium effort, prompt v6. It passed its gate at 93.6%;
- the engine has not changed since phase 2;
- `phase-3` was merged into `main` at `7ec1134` (not pushed), and `phase-4` branches from there (D10).

## Decisions (owner, 2026-11-16)

| | decision |
|---|---|
| D1 | **Haiku 5.5 answer writer**, plus the guard and the template answer. |
| D2 | **The perception rule as written** (procedure step 3), fixed before any step-2 result. |
| D3 | **Sonnet 5.5 answer-level fallback.** Inputs: **image + question + scene graph only.** There is no `law_db` retrieval: inference never reads `law_db` (CLAUDE.md). Triggers: the four in item 2, **plus every engine `unknown` and `uncertain` verdict.** |
| D4 | **Opus 5.5 judge, correct / partial / wrong scored 1 / 0.5 / 0**, with the prompt pinned before any result. The **strict score** (partial = 0) is also reported. |
| D5 | **Faithfulness ≥ 99%, pooled over the 3 H development runs**, with a template answer counted as faithful. **The template answer may be used on at most 5% of answers, or the faithfulness gate fails.** The template rate is always reported. |
| D6 | End-to-end accuracy is **reported, not gated**. |
| D7 | **No sign codes go to the parser in phase 4.** It sees only the question, as it was gated. |
| D8 | **At most 5 tuning runs** on public_dev. After any tuning change, public_dev figures are labelled **tuned**. |
| D9 | **Phase-4 API ceiling: $10.** |
| D10 | Merge `phase-3` into `main` (no push), then branch `phase-4`. **Done:** `7ec1134`. |

**Also decided:**
- **Scene reuse.** Checkpoint-2 scenes reach the pipeline **only by warming the scene cache from the run files**, which hold model outputs only.
  - `answer()` stays `image_path + question`.
  - The oracle A/B runs call the parser and engine directly from `eval/`, never through `answer()`.
  - Leakage-guard tests cover both rules (item 5).
- **Rules-only score.** Every end-to-end report also gives a rules-only score: accuracy on the questions answered without the fallback. It is reported next to the overall score and rule coverage.

## What phase 4 delivers

- **`vqa/pipeline.py`:** one entry point, `answer(image_path, question) -> PipelineAnswer`. It runs these stages:
  1. perception;
  2. the parser;
  3. the engine;
  4. the answer writer and the faithfulness guard;
  5. the answer-level fallback, when one of its triggers fires.

  The result carries:
  - the Vietnamese answer text, and the verdict;
  - `basis` (`rules`, `non_standard_plate`, `fallback`, …), the citations and the proof;
  - a per-stage trace (scene id, program, engine verdict, which fallback fired and why), and the cost.
- **`vqa/answer/`:**
  - `writer.py`, the answer writer;
  - `faithfulness.py`, the guard;
  - `template.py`, deterministic Vietnamese answers built from the verdict;
  - `fallback.py`, the answer-level fallback.
- **`eval/e2e_eval.py`:** end-to-end runs on public_dev (development) and one aggregate-only run on public_holdout, with the gate and stage attribution.
- **`eval/warm_scene_cache.py`:** writes checkpoint-2 model outputs from the run files into a per-run scene cache directory (see item 3).
- **`eval/judge.py`:** the Natural-QA judge.
- **Leakage-guard extensions**, and a test for every new rule.

Not in phase 4:
- the private-test benchmark, baselines and ablations (roadmap phase 5);
- the demo UI;
- traffic lights.

## Work items

### 1. The answer writer and the faithfulness guard (DESIGN section 7)

- **Input:** the question, the engine verdict (`yes` / `no` / `unknown` / `uncertain` / a value), the proof tree (signs used, rules fired, sources) and the uncertainty flags. **No image.**
- **Output:** one plain JSON object, `{"verdict", "answer", "cited_signs", "cited_rules"}`.
  - It is checked in Python.
  - It gets one retry that sends only the error, as the scene call and the parser do.
- **Guard (code):**
  - the reply's `verdict` equals the engine's;
  - every cited sign and rule is in the proof;
  - the text contains no sign code or number missing from the proof;
  - true/false questions start with "Đúng" or "Sai".
- **On a guard failure:**
  - one regeneration, with the failure as the error;
  - if that fails too, the deterministic **template answer**: the verdict, plus the proof's main reason and citation. So the shipped answer never contradicts the engine;
  - the template rate counts toward D5's 5% limit.
- **Prompt:** `prompts/answer/v1/`, with text-only examples from train answers in the dataset's style. It is versioned and pinned like the other prompts. **v2** (owner, 2026-11-16) adds a Đúng/Sai, an `unknown` and a sign-meaning example, and it is the version used from step 2 on.

### 1b. Engine fixes from the oracle A diagnosis (owner, 2026-11-16; tuned on public_dev)

These come from the public_dev oracle A diagnosis (`docs/status.md`), so every public_dev figure after them is labelled **tuned**. Each fix has tests with hand-made scenes modelled on train questions (not on public_dev questions), is committed on its own, and keeps the full suite green with Prolog loading.

1. **Selector for single-sign questions** ("Đây là biển gì?" and similar, `only`):
   - unreadable signs are dropped from the candidates;
   - if every readable candidate has the same code, the answer is decided with it, and the unreadable signs are listed in `uncertain_signs`;
   - if the readable codes differ, the answer stays unknown.

   This is Python selector resolution; the legal conclusion stays in Prolog.
2. **Meaning questions over several signs:** answer for the readable signs and list the unreadable ones.
3. **Load → gross weight (kb/):** load > x implies gross weight > x.
   - It is recorded under `vehicle_interpretations` in the catalog and shown in the proof, with no cut.
   - It has its own `rule_source` entry marking it as an interpretation, not law text.
4. **Relevance:** an unreadable rectangle with a red background or a red border counts as prohibitory (permissions, speed, violations). CLAUDE.md's relevance list, `Engine.visual_category` and `Engine.could_matter` are updated.
5. **Deferred (not in phase 4):** the warning-sign behaviour rule, counting signs, and guide-sign content.

After the fixes, oracle A runs again engine-only (free) and is reported as **tuned**.
- **0068** is recorded as a **disputed gold answer**: the engine's Đúng is believed correct. It is scored as is.
- The owner fixes **0094**'s gold plate vehicles; the assistant doesn't touch gold.

### 2. The answer-level fallback (D3; not yet in DESIGN)

- **Triggers:**
  - the parser returns `out_of_scope`;
  - the parser fails after its retry;
  - the engine answers `unknown` because of an unreadable sign (`uncertain_signs` is non-empty; CLAUDE.md's rule);
  - the program can't run on the scene (a selector finds no sign);
  - **every other engine `unknown` verdict** (a missing time, lane or attribute, …);
  - **every engine `uncertain` verdict** (alternative readings disagree).

  The trace records which trigger fired. Reports give the fallback rate by trigger.
- **The call:**
  - one Sonnet 5.5 vision call with the image, the question and the pass-1 scene graph as context. Nothing else: no `law_db`, no retrieval, no train QA;
  - it replies in plain JSON (`{"answer", "verdict"}`), with one retry on bad JSON.
- **Marking:** the answer carries `basis: ["fallback"]` and no rule citation, so it is never shown as a rule-engine conclusion.
- **Prompt:** `prompts/answer_fallback/v1/`, versioned and pinned, with train examples only.
- **Rule coverage** = the share of questions answered without the fallback. It is measured on public_holdout through the pipeline (CLAUDE.md).

### 3. The pipeline (`vqa/pipeline.py`) and scene reuse

- The scene cache is reused across questions on the same image, so one image costs one perception run.
- The parser sees only the question (D7).
- `answer()` takes an image path and a question string only. It never takes an image id, split, gold or fixture, and it never takes a scene or a run file.
- **Settings** (perception model and fallback settings, the scene cache directory, the spend guard) are fixed when the pipeline is set up for a run, never per question.
- **Warming the cache from checkpoint-2 runs** (`eval/warm_scene_cache.py`):
  - it copies only model outputs (raw reply text, usage, cost, request id) into cache records, in the format `vqa/perception/cache.py` already checks;
  - it uses one cache directory per run (`$VQA_SCENE_CACHE_DIR`). The three H runs share cache keys (same image, model, effort and prompt), so they can't share one directory;
  - **cache-only mode:** a development run on a warmed cache treats a cache miss as an error and makes no perception call;
  - **reproduction check (no API):** the scene each image's warmed cache rebuilds must equal the scene stored in the run file. A run that fails this check is not used.
  - **P1 (decided below):** H is `9981d8112688` plus two fresh Haiku runs whose run files keep their raw replies. H is warmed and run one run at a time.

### 4. End-to-end eval (`eval/e2e_eval.py`) and the judge (`eval/judge.py`)

- **Yes/No:** map both the prediction and the gold to true / false, then exact match.
  - Đúng, ĐÚNG, đúng, Có and Được map to true.
  - Sai, SAI, Không and Không được phép map to false.
- **Natural QA:**
  - the Opus 5.5 judge (D4) compares the prediction with the gold answer on the key facts (code, number, lane, time, vehicle);
  - it returns correct, partly correct or wrong, scored 1 / 0.5 / 0. The strict score counts partial as 0;
  - its prompt and model are fixed and pinned before the first phase-4 result.
- **Reported every time** via `eval/report.py`:
  - Yes/No accuracy and the Natural-QA score (and its strict score), on all questions and on questions whose image is not in train, with a 95% CI;
  - **rule coverage, and the rules-only score** (accuracy on the questions answered without the fallback), next to the overall score;
  - the fallback rate by trigger;
  - faithfulness: guard passes on the first try, regenerations, template answers, and **the template rate**;
  - cost and seconds per question.
- **Stage attribution, on public_dev only.** Each wrong answer is assigned to a stage by re-running with gold parts. This is all eval-side: inference never sees gold.
  - **Oracle A:** gold scenes (gold signs v1) + gold programs (gold intents v1) + the writer. It covers 48 of the 51 questions, since the 3 questions used as parser few-shots have no gold program.
  - **Oracle B:** pipeline scenes + gold programs.
  - A wrong answer that oracle A gets right is a perception or parser error; oracle B separates the two.
  - Oracle runs call the parser and the engine directly from `eval/`, never through `answer()`, and they are never part of inference.
- **Holdout mode:** aggregate scores only.
  - No per-question line is printed or written: the judge's verdicts are summed in memory and the per-question records are dropped.
  - A test checks that holdout mode writes no per-question file.

### 5. Leakage guard

- `vqa/pipeline.py` and `vqa/answer/` are inference code. They never import `eval` or `tests`, and never mention gold, splits, fixtures, run files or QA files.
- The answer and fallback prompts hold train examples only. Neither reads `law_db`.
- `answer()`'s signature is pinned by a test: image path + question.
- **Scene reuse:** a test checks that inference code never reads run files (`eval/runs/`) and that the only way a stored scene reaches `answer()` is the scene cache. Another test checks that the warmed records hold model outputs only.
- **Oracles:** a test checks that the oracle code in `eval/` never calls `answer()`, and that `vqa/` never imports the oracle code.
- The judge lives in `eval/`, never in `vqa/`.

## Procedure, with the Sonnet-vs-Haiku rule fixed before any result

1. **No API.**
   - Build items 1–5 with hand-made tests.
   - Run oracle A's **Yes/No part** on public_dev with the engine only (verdicts, no writer). That checks DESIGN's claim that the rule engine is close to 100% with gold scenes and programs, at no cost.
   - Run the cache warming and its reproduction check.
2. **Development runs on public_dev, reusing the checkpoint-2 scenes** through warmed caches (no new perception spend):
   - **H:** Haiku + fallback scenes: `9981d8112688` plus two fresh Haiku pass-1 + fallback runs made by the owner (P1);
   - **S:** Sonnet + fallback scenes, the 1 run `949418393534`;
   - **O:** oracle A (gold scenes and programs), plus oracle B on each H run.

   Each gets the parser (except O), the writer, the fallback and the judge.
3. **The perception rule (D2, fixed now).** Holdout uses Sonnet + fallback instead of Haiku + fallback **only if** both of these hold:
   - S's end-to-end score (Yes/No and Natural QA pooled into one accuracy over the 51 questions) is **at least 5 points above** the mean of H's three runs;
   - S is also above the best single H run.

   Otherwise Haiku + fallback goes to holdout.
4. **Tuning on public_dev:** at most **5 more** development runs (D8) to fix the writer, fallback and guard prompts.
   - They may use public_dev per-question error analysis: it is the tuning set.
   - After any such change, public_dev figures are labelled **tuned**.
5. **Freeze:**
   - pin the answer and fallback prompts, the judge prompt, and the chosen perception configuration by sha256;
   - record the frozen configuration in `docs/status.md` before step 6.
6. **public_holdout, once:**
   - fresh perception with the frozen configuration (no cache, so the calls are independent), then the parser, engine, writer, fallback and judge on its 49 questions / 45 images;
   - aggregate figures only, on all questions and on questions whose image is not in train (25 of its 45 images are also in train), with CIs;
   - this is phase 4's real measure. It is reported whatever it shows, and the system is not changed after it.
7. **Gate (roadmap phase 4):**
   - faithfulness ≥ 99%, pooled over the 3 H runs;
   - and a template rate ≤ 5% (D5).

   End-to-end accuracy is reported, not gated (D6).

## Cost estimate (no API calls made)

Per-question costs, from phase-2 and phase-3 logs where measured:

| part | model | per call | notes |
|---|---|---|---|
| parser | Sonnet 5.5, prompt v6 | $0.0028 (measured) | about 10% retried for prose around the JSON |
| answer writer | Haiku 5.5 (D1) | about $0.0003 | about 2k cached + 1k input, 250 out |
| answer fallback | Sonnet 5.5 (D3) | about $0.008 | image about 600 tokens + 2k prompt + 300 out. With every `unknown` and `uncertain` verdict a trigger, assume about 35–55% of questions (the public_dev audit gave 76.5% rule coverage on gold scenes; real scenes give more unknowns) |
| judge | Opus 5.5 | about $0.007 | Natural-QA questions only, about 63% of public |
| perception | Haiku + fallback | $0.0028 per image (measured) | holdout only; development reuses the checkpoint-2 scenes |

**About $0.011 per question** before perception, at a 45% fallback rate.

| step | estimate |
|---|---|
| 2: H × 3 and S × 1 on public_dev (51 questions) | about $2.3 |
| 2: O (oracle A) and oracle B × 3 (writer, fallback, judge; no parser) | about $0.7 |
| 4: up to 5 tuning runs | about $2.8 |
| 6: holdout once, Haiku + fallback | about $0.67 ($0.13 perception + $0.54); about $1.6 if D2 picks Sonnet |
| **total** | **about $6.5–7.4**; about $3.5–11 at ±50% |

Every paid step shows its estimate and waits for the owner's go-ahead, under the spend guard. **The phase ceiling is $10 (D9).** If spend nears it, tuning runs stop first, so the holdout run stays funded.

## Decisions on the open points (owner, 2026-11-16)

- **P1, decided: neither (b) nor (c).** Fresh Haiku runs would overwrite `9981d8112688`'s cache record too, since the three runs share keys. So:
  1. `perception_eval.py run` (and `fallback`) store the pass-1 and re-run raw replies in the run file. This is eval-only, with no scoring change, and it is tested.
  2. An eval-side **`warm`** step rebuilds the cache records of one run from its run file. It checks that the rebuilt verified scenes equal the file's scenes.
  3. **The H set = `9981d8112688` + two fresh Haiku pass-1 runs, each followed by the fallback.** The owner runs them. `9981d8112688`'s pass-1 replies are copied from the scene cache into a copy of its run file before any fresh run. They are checked against the usage log's request ids for pass-1 run `932c3d2b7009`.
  4. **The pipeline runs H one run at a time:** warm, run, next. A test checks that warming run k leaves no record of any run j ≠ k behind.
- **P2, accepted as proposed.** Faithfulness and the template rate are both counted over the answers that go through the writer path (writer, regeneration or template), pooled over the 3 H runs. Fallback answers are left out and reported separately.
- **P3, accepted as proposed.** When the fallback call fails after its retry, the engine's own answer ships through the writer path, counted as a fallback failure.
- **Writer prompt v2, before any step-2 result:** `prompts/answer/v2` adds examples for a Đúng/Sai answer, an `unknown` answer and a sign-meaning answer.
  - They use train questions with their exact text, and hand-made scenes modelled on them (no dataset files are copied).
  - v2 is pinned and v1 stays.
  - The other writer readings are accepted: question numbers and codes may appear in the answer; at most two writer calls; effort `low`.

- **Two readings accepted (owner, 2026-11-16):**
  - a **`perception_failed`** fallback trigger: no scene at all goes to the fallback, with the scene graph sent as `null`;
  - **oracle gold scenes** drop standalone local notices (the engine does not model them) and keep unreadable gold signs as `UNKNOWN`.

- **Oracle B on H1 only (owner, 2026-11-16).** Step 2 skips oracle B for H2 and H3, so procedure step 2's "oracle B on each H run" becomes oracle B on H1. Stage attribution uses H1 only (H1 pipeline, oracle A, oracle B H1).

## Open points as first written (kept as a record)

These came up while writing the plan. None of them changes step 1.

- **P1, two H runs can't be warmed from model outputs.** The checkpoint-2 run files keep each image's tile and crop replies (`fallback_replies`) and the final scene, but **not the pass-1 / re-run raw replies**. Those lived only in the scene cache, and each later run overwrote them, since the three Haiku runs share cache keys.
  - The cache still holds the pass-1 replies of Haiku pass-1 run `932c3d2b7009` (under fallback run **`9981d8112688`**) and Sonnet `f19dd5bc36f6` (under **`949418393534`**). Those two runs can be warmed exactly.
  - For **`b83d5dae690e`** (pass 1 `e0128c462ed3`) and **`023c1a474288`** (pass 1 `2dd3a6e61573`), only the verified scene survives.
  - Options:
    - (a) two fresh Haiku v4 + fallback runs on public_dev (about $0.25), whose raw replies are kept, so H is 3 fully warmed runs. They are not the checkpoint-2 scenes;
    - (b) a separate eval-side record kind that stores the run file's verified scene, which is derived from model outputs by code with no gold. That changes the cache contract, which now holds raw replies only;
    - (c) H = 1 run (`9981d8112688`). That changes D2 (the mean of 3) and D5 (pooled over 3).
  - Whichever option is chosen, the perception run code should keep the raw pass-1 replies in the run file from now on.
- **P2, D5's denominator.** Proposed reading: faithfulness and the template rate are both counted over the answers that go through the writer path (writer, regeneration or template), pooled over the 3 H runs. Fallback answers have no engine verdict to be faithful to, so they are left out and reported separately.
- **P3, when the fallback call itself fails** after its retry. Proposed: ship the engine's own answer through the writer path (e.g. `unknown`, with its reason), and count it as a fallback failure in the report.
