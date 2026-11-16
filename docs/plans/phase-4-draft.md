# Phase 4 plan: answering and the end-to-end pipeline (draft, not approved)

DESIGN.md roadmap phase 4. **Status: a draft for the owner's approval.** No phase-4 code, prompt or API call exists. The decisions the owner needs to make are under "Decisions for the owner" (D1–D10); each lists the recommended default first.

**Starting point:**
- phase 3 closed with the perception gate **failed**;
- perception is Haiku 5.5, prompt v4 + the fallback, by policy (d) (`docs/status.md`, "Phase 3: closing");
- the parser is Sonnet 5.5 at medium effort, prompt v6, which passed its gate at 93.6%;
- the engine is unchanged since phase 2.

## What phase 4 delivers

- **`vqa/pipeline.py`:** one entry point, `answer(image_path, question) -> PipelineAnswer`. It runs perception, then the parser, then the engine, then the answer writer and the faithfulness guard, then the answer-level fallback when one of its triggers fires. The result carries:
  - the Vietnamese answer text, and the verdict;
  - `basis` (`rules`, `non_standard_plate`, `fallback`, …), the citations and the proof;
  - a per-stage trace (scene id, program, engine verdict, which fallback fired and why), and the cost.
- **`vqa/answer/`:**
  - `writer.py`, the answer writer;
  - `faithfulness.py`, the guard;
  - `template.py`, deterministic Vietnamese answers built from the verdict;
  - `fallback.py`, the answer-level fallback.
- **`eval/e2e_eval.py`:** end-to-end runs on public_dev (development) and one aggregate-only run on public_holdout, with the gate and stage attribution.
- **`eval/judge.py`:** the Natural-QA judge.
- **Leakage-guard extensions**, and a test for every new rule.

Not in phase 4: the private-test benchmark, baselines and ablations (roadmap phase 5); the demo UI; traffic lights.

## Work items

### 1. The answer writer and the faithfulness guard (DESIGN section 7)

- **Input:** the question, the engine verdict (`yes` / `no` / `unknown` / `uncertain` / a value), the proof tree (signs used, rules fired, sources) and the uncertainty flags. **No image.**
- **Output:** one plain JSON object, `{"verdict", "answer", "cited_signs", "cited_rules"}`, checked in Python, with one retry that sends only the error (as the scene call and the parser do).
- **Guard (code):**
  - the reply's `verdict` equals the engine's;
  - every cited sign and rule is in the proof;
  - the text contains no sign code or number missing from the proof;
  - true/false questions start with "Đúng" or "Sai".
- **On a guard failure:** one regeneration with the failure as the error. If that fails too, the deterministic **template answer** (verdict plus the proof's main reason and citation), so the shipped answer never contradicts the engine.
- **Prompt:** `prompts/answer/v1/`, with text-only examples from train answers in the dataset's style. It is versioned and pinned like the other prompts.

### 2. The answer-level fallback (proposed; not yet in DESIGN)

CLAUDE.md sends some questions to "the fallback", but it is not designed yet. Proposed:

- **Triggers** (D3 fixes the list):
  - the parser returns `out_of_scope`;
  - the parser fails after its retry;
  - the engine answers `unknown` because of an unreadable sign (`uncertain_signs` non-empty; CLAUDE.md's rule);
  - the program can't run on the scene (a selector finds no sign).
- **The call:** one Claude vision call with the image, the question and the pass-1 scene graph as context. It replies in plain JSON (`{"answer", "verdict"}`) with one retry on bad JSON.
- **Marking:** the answer carries `basis: ["fallback"]` and no rule citation, so it is never shown as a rule-engine conclusion.
- **Rule coverage** = the share of questions answered without the fallback, measured on public_holdout through the pipeline (CLAUDE.md).

### 3. The pipeline (`vqa/pipeline.py`)

- The scene cache is reused across questions on the same image, so one image costs one perception run.
- The parser sees only the question, plus the list of sign codes in the scene if D7 says so (phase-2 D2 deferred this to phase 4).
- `answer()` takes an image path and a question string only: never an image id, split, gold or fixture.

### 4. End-to-end eval (`eval/e2e_eval.py`) and the judge (`eval/judge.py`)

- **Yes/No:** map both the prediction and the gold to true / false (Đúng, ĐÚNG, đúng, Có, Được → true; Sai, SAI, Không, Không được phép → false), then exact match.
- **Natural QA:** the judge (D4) compares the prediction with the gold answer on the key facts (code, number, lane, time, vehicle). It returns correct / partly correct / wrong, scored 1 / 0.5 / 0. Its prompt and model are fixed and pinned before the first phase-4 result.
- **Reported every time** via `eval/report.py`:
  - Yes/No accuracy and the Natural-QA score, on all questions and on questions whose image is not in train, with a 95% CI;
  - rule coverage; the fallback rate by trigger; faithfulness (guard passes on the first try, regenerations, template answers);
  - cost and seconds per question.
- **Stage attribution, on public_dev only.** Each wrong answer is assigned to a stage by re-running with gold parts, all eval-side (inference never sees gold):
  - **oracle A:** gold scenes (gold signs v1) + gold programs (gold intents v1) + the writer. This covers 48 of the 51 questions: the 3 used as parser few-shots have no gold program;
  - **oracle B:** pipeline scenes + gold programs.

  A wrong answer that oracle A gets right is a perception or parser error; oracle B separates the two. Oracle runs are eval-only and never part of inference.
- **Holdout mode:** aggregate scores only. No per-question line is printed or written: the judge's verdicts are summed in memory and the per-question records are dropped. A test checks that holdout mode writes no per-question file.

### 5. Leakage guard

- `vqa/pipeline.py` and `vqa/answer/` are inference code: they never import `eval` or `tests`, and never mention gold, splits, fixtures or QA files.
- The answer and fallback prompts hold train examples only.
- `answer()`'s signature is pinned by a test (image path + question).
- The judge lives in `eval/`, never in `vqa/`.

## Procedure, with the Sonnet-vs-Haiku rule fixed before any result

1. **No API.** Build items 1–5 with hand-made tests. Run oracle A's **Yes/No part** on public_dev with the engine only (verdicts, no writer). That checks DESIGN's "rule engine with gold scenes and programs ≈ 100%" for free.
2. **Development runs on public_dev, reusing the checkpoint-2 scenes** (no new perception spend; the scenes are model outputs from the checkpoint-2 run files, passed in by the eval runner):
   - **H:** Haiku + fallback scenes, the 3 runs (`b83d5dae690e`, `023c1a474288`, `9981d8112688`);
   - **S:** Sonnet + fallback scenes, the 1 run (`949418393534`);
   - **O:** oracle A (gold scenes and programs).

   Each gets the parser, writer, fallback and judge.
3. **The perception rule** (D2, fixed now). Holdout uses Sonnet + fallback instead of Haiku + fallback **only if**:
   - S's end-to-end score (Yes/No and Natural QA pooled into one accuracy over the 51 questions) is **at least 5 points above** the mean of H's three runs, **and**
   - S is also above the best single H run.

   Otherwise Haiku + fallback. Rationale: Sonnet costs about 8× as much per image (about $0.023 against $0.0028), S is one run, and Haiku's perception F1 varied by 2.9 points across runs.
4. **Tuning on public_dev:** at most **5 more** development runs to fix the writer, fallback and guard prompts, using public_dev per-question error analysis (allowed: it is the tuning set). After any such change, public_dev figures are labelled **tuned**.
5. **Freeze:** pin the answer and fallback prompts, the judge prompt, and the chosen perception configuration by sha256. Record the frozen configuration in `docs/status.md` before step 6.
6. **public_holdout, once:**
   - fresh perception with the frozen configuration (no cache: independent calls), parser, engine, writer, fallback and judge on its 49 questions / 45 images;
   - aggregate figures only, on all questions and on questions whose image is not in train (25 of its 45 images are also in train), with CIs;
   - this is phase 4's real measure. It is reported whatever it shows, and the system is not changed after it.
7. **Gate (roadmap phase 4):** faithfulness ≥ 99% (D5). End-to-end accuracy is reported, not gated (D6).

## Cost estimate (no API calls made)

Per-question costs, from phase-2 and phase-3 logs where measured:

| part | model | per call | notes |
|---|---|---|---|
| parser | Sonnet 5.5, prompt v6 | $0.0028 (measured) | about 10% retried for prose around the JSON |
| answer writer | Haiku 5.5 (D1) | about $0.0003 | about 2k cached + 1k input, 250 out; Sonnet would be about $0.005 |
| answer fallback | Sonnet 5.5 (D3) | about $0.008 | image about 600 tokens + 2k prompt + 300 out; on about 25–35% of questions (the public_dev audit gave 76.5% rule coverage) |
| judge | Opus 5.5 | about $0.007 | Natural-QA questions only, about 63% of public |
| perception | Haiku + fallback | $0.0028 per image (measured) | holdout only; development reuses the checkpoint-2 scenes |

**About $0.010 per question** before perception.

| step | estimate |
|---|---|
| 2: H × 3, S × 1, O × 1 on public_dev (51 questions) | about $2.6 (O has no parser call) |
| 4: up to 5 tuning runs | about $2.6 |
| 6: holdout once, Haiku + fallback | about $0.63 ($0.13 perception + $0.50); about $1.55 if D2 picks Sonnet |
| **total** | **about $5.8–6.8**, range about $3.5–10 at ±50% |

Every paid step shows its estimate and waits for the owner's go-ahead, under the spend guard. Proposed phase ceiling: **$10** (D9).

## Decisions for the owner

- **D1, answer-writer model.**
  - (a) **Haiku 5.5** with the guard and the template answer (recommended: the writer only verbalises a fixed verdict, and the guard catches its errors);
  - (b) Sonnet 5.5, about 15× the cost.
- **D2, the perception rule** in procedure step 3.
  - (a) **as written** (S must beat H's mean by ≥ 5 points and its best run);
  - (b) another margin;
  - (c) no Sonnet test: Haiku + fallback goes to holdout.

  It must be fixed before step 2's results.
- **D3, the answer-level fallback.**
  - Model: (a) **Sonnet 5.5** (recommended: these are the hardest questions) or (b) Haiku 5.5.
  - Inputs: image + question + scene graph (recommended), or also law articles retrieved from `law_db` (closer to DESIGN's "Claude + retrieval" baseline; it needs retrieval code).
  - Triggers: the four in item 2. Also decide whether `uncertain` verdicts (readings disagree) and other `unknown` verdicts (a missing time or lane) go to the fallback or are answered as "depends on …". The dataset's gold answers are definite, so an `unknown` answer usually scores as wrong.
- **D4, the judge.**
  - (a) **Opus 5.5, correct / partial / wrong scored 1 / 0.5 / 0**, prompt pinned before any result (recommended; DESIGN section 9);
  - (b) also report a strict score with partial = 0.
- **D5, the faithfulness gate.** Public_dev has 51 questions, so 99% means no failure in a run.
  - (a) **≥ 99% pooled over the 3 H development runs** (153 answers, so at most 1 failure), counting a template answer as faithful but reporting the template rate;
  - (b) per run.
- **D6, end-to-end accuracy:** (a) **reported, not gated** (recommended; DESIGN gates phase 4 on faithfulness only), or (b) a minimum the owner sets now, before any result.
- **D7, sign codes to the parser** (phase-2 D2, deferred to phase 4).
  - (a) **not in phase 4**: the parser sees only the question, as it was gated (recommended);
  - (b) pass the scene's codes. That is a parser prompt v7 and new parser runs.
- **D8, tuning budget on public_dev:** (a) **at most 5 runs, figures labelled tuned** (recommended), or (b) a different number.
- **D9, phase-4 API ceiling:** (a) **$10** (recommended; estimate about $6–7), or (b) another figure.
- **D10, branches.** (a) **merge `phase-3` into `main` first, then branch `phase-4` from it** (recommended), or (b) branch `phase-4` from `phase-3`.
