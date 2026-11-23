# Neuro-symbolic traffic sign VQA

DESIGN.md is the full design. Read it before you change architecture. We build it phase by phase, following its roadmap. The scene graph and DSL are at schema 1.2 in code (`SCHEMA_VERSION` stays "1.2"); DESIGN.md, "Schema 1.3 and 1.4", documents the optional additions since then (1.3 guide boards, 1.4 the scene v6 fields) and the phase-4.5 to 4.7 intents and rules.

- **Where things stand and what's next:** `docs/status.md` (done work with commit hashes, next steps, open items, coverage figures).
- **The approved plan for each phase:** `docs/plans/` (e.g. `docs/plans/phase-2.md`). Follow the approved plan; ask before changing it.
- **Claude API calls are allowed only behind the spend guard,** and never without the owner's go-ahead on the estimated cost.

## Setup

You need SWI-Prolog 9.1 or later (`brew install swi-prolog`) and Python 3.11 or later.

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'     # pydantic, pyyaml, janus-swi, pytest
.venv/bin/python -m pytest -q
```

If `janus-swi` fails to build, put `SWI_HOME_DIR=/opt/homebrew/lib/swipl` in front of the pip command. Add the `eval` extra (`.[dev,eval]`) for Pillow and numpy.

Other commands:

```bash
swipl -q -g "consult('kb/load.pl'), halt"           # check the Prolog files on their own
.venv/bin/python eval/audits/public_dev_v2_checks.py # audit checks (hand-made scenes, no API)
.venv/bin/python tools/draft_catalog_rows.py         # regenerate kb/sign_catalog_meaning.yaml
.venv/bin/python eval/make_public_split.py           # regenerate the public split
.venv/bin/python eval/find_duplicates.py             # regenerate data/splits/duplicates.json
.venv/bin/python eval/gold_intents.py estimate       # gold-intent cost estimate, no spend
```

## Dataset rules

- The dataset is at `VLSP2025-MLQA-Natural/` (or set `$VQA_DATASET_DIR`). It is **read-only** and gitignored. Never copy dataset files into the repo.
  - **One exception (owner, 2026-11-15): law_db figures in the scene prompt.** `tools/build_scene_pictograms.py` may write resized copies (≤320 px) of chosen law_db figures into `prompts/scene/<version>/pictograms/`, which is gitignored. Only the manifest `prompts/scene/<version>/pictograms.yaml` is committed: per row, its code, source article, figure name, caption and the copy's sha256. The copies are never committed. `vqa/perception/prompt.py` refuses to build a version whose copies are missing or don't match the manifest. Inference reads `prompts/`, never law_db.
- Build rules, prompts and examples from the **train split and `law_db` only**. Use the public test only for tuning.
- **The public test is split 50/50 by image** into `public_dev` and `public_holdout`. Questions that share an image stay on the same side.
  - The split is saved in `data/splits/public_split.json` (seed 20261114). `eval/make_public_split.py` regenerates it and only reads question and image ids.
  - **Only `public_dev` may be looked at question by question** (images, questions, answers, error analysis).
  - `public_holdout` is for aggregate scores only. Don't read its questions, images or per-question results.
  - **Lifted (owner, 2026-11-21):** after the private benchmark, `public_holdout` may be read question by question like `public_dev`, for the Chapter 4 error analysis. It runs through `eval/e2e_public_dev52.py --split public_holdout` on the frozen phase52 system (the benchmarked one, from its pre-fix commit). It is no longer held out: no later public number is unbiased, and the earlier holdout figures (phase 4: 83.7%; the phase-4.9 paired check) stay as they were reported.
- **The phase-4.5 validation set** (`data/splits/train_validation.json`, seed 20261116, ids only; built by `eval/make_validation_split.py`) is 110 untouched train questions on 54 images. **It is aggregate only, like `public_holdout`:** don't read its questions, images, answers or per-question results, and never use them for few-shots, fixtures, gold or tuning. It runs only through `eval/e2e_validation.py` (fallback off, sentinels `eval/validation_ran_<label>.json`), once as `baseline` and once as `final`.
- **The phase-4.5 dev set** (`data/splits/train_dev.json`, ids only: the validation pool minus the validation set, 87 Natural QA questions on 60 images) **may be read question by question** (owner, 2026-11-17). It runs through `eval/e2e_dev.py`, with per-question records in the gitignored `eval/runs/`.
- **Many images repeat across splits.** `data/splits/duplicates.json` lists near-duplicate image groups, made by `eval/find_duplicates.py`. It uses perceptual hashes and reads image files only, never question files.
  - 79 of the 104 private images and 53 of the 90 public images also appear in train.
  - Earlier evaluations reported every score twice: on all questions, and without questions whose image is in `duplicated_with_train`. Since 2026-11-20 (owner) the all-questions score is enough.
  - The duplicate check finds copies and slight re-crops. It misses different photos of the same scene.
- **Never open the private test answers.** The private test is the final benchmark and runs at the end.
  - Only the scoring code reads them, in memory, and it writes aggregates only (`eval/e2e_private.py`, sentinel `eval/private_ran.json`).
  - **Three runs for the mean and spread (owner, 2026-11-21).** The private test runs 3 times on the frozen phase52 setup (`eval/frozen_phase52.json`), because perception, parsing and the writer are Claude calls whose output varies from run to run. Run 1 is `eval/private_ran.json` (`a51605785ace`); runs 2 and 3 are `e2e_private.py run --run 2` and `--run 3`, with sentinels `eval/private_ran_2.json` and `eval/private_ran_3.json`, each with its own run id, replay folder, fresh scene cache and aggregate. All 3 runs are reported (mean and spread), never the best one, and nothing is tuned between them.
  - **One exception (owner, 2026-11-16, phase-5 P6): human scoring.** The owner, and only the owner, may read private answers to score the Natural QA answers by hand, and only after every automatic score on private is recorded and committed. The assistant never reads the scoring sheet or the private answers.
  - The private run's replay records (`cache/private_run/`, P4) are model outputs only, gitignored, read only by replay code, and deleted at the end of phase 5.
  - **The owner's grading sheets (owner, 2026-11-20, P6):** `e2e_private.py` and `e2e_private_rag.py` also write `owner_grading.csv` and `owner_grading_rag.csv` into the same gitignored replay folder, one row per question with the question, gold answer, system answer and the judge's grade, for the owner's hand grading of V1, V2 and RAG alone. `records.jsonl` and the aggregates stay free of gold and grades. The assistant never reads the sheets, and nothing from them is printed.
- Keep `provenance.json` and `review.json` out of prompts. `train_284` has an invalid citation.

## Leakage guard

- **At inference, the pipeline never uses hand-made scene graphs, test fixtures, gold labels or train QA for an image.**
  - It never looks up train (or any split's) data by image hash or image similarity.
  - The only cache is the scene cache (`vqa/perception/cache.py`, `cache/scenes/`, gitignored). It holds model outputs only, keyed by image hash plus model id plus effort plus prompt version.
  - The fallback's tile and crop records (plan item 7) live in the same cache. Their key adds the region's pixel box on the original image (`region_key`).
  - **One exception (owner, 2026-11-23): the RAG answer cache** (`app/api/rag_cache.py`, `VQA_RAG_CACHE`, default off).
    - It holds the live RAG fallback's own answers to questions asked through the API: model outputs only, never gold, dataset files or evaluation outputs.
    - The key is the image hash, the exact question and the RAG's version.
    - It is used only when the RAG runs one question at a time, because only then do its answers repeat exactly.
    - Evaluation scripts call the pipeline directly and never use it.
    - It is deleted after the defense.
- **Inference code means `vqa/` and `app/`.** It must not import from `tests`, `conftest` or `eval`. It must not mention fixture, annotation, audit, split or duplicate files, or the dataset's QA files.
  - `tests/test_leakage_guard.py` enforces this.
  - Few-shot examples built from train go into versioned prompt files under `prompts/`. They are never selected per image.
- **The RAG fallback is outside this guard (owner, 2026-11-20, `docs/plans/rag-fallback.md`).** The owner's RAG service keeps its similarity-chosen train few-shots and example-guided law retrieval. `vqa/` only sends it the image and the question, and the guard above still applies to `vqa/` and `app/`.
- **Eval reports give the score on all images (owner, 2026-11-20).** Non-duplicate figures are no longer required; `eval/report.py` (`score_report`, `format_report`) still prints them, and earlier reports keep theirs.
  - For public, "duplicate" means the image is also in train. For private, it means the image is also in train or public.

## Layout

- `vqa/schemas.py`: contracts: SceneGraph, QueryProgram (the DSL), Answer. Any vocabulary that reaches Prolog is an enum here.
- `vqa/kb.py`: loads the catalog and turns it into Prolog facts.
  - `kb/sign_catalog.yaml`: rows with rule effects.
  - `kb/sign_catalog_meaning.yaml`: meaning-only W/I/IE rows drafted by `tools/draft_catalog_rows.py`. Their review list is `kb/review/meaning_rows_review.md`.
- `tools/`: offline authoring tools. They may read law_db; inference code may not.
- `docs/`: `status.md` (status and next steps) and `plans/` (approved phase plans).
- `web/`: the web UI (React + Vite + TypeScript; `web/README.md`). It talks to `app/api` only. `web/e2e/fake_api.py` runs the real API with a fake pipeline for the Playwright test.
- `eval/`: splits, duplicates, reports (`report.py`), audits, gold-intent tooling. Not inference code.
- `vqa/parsing/dsl.py`: rewrites run before the engine. `Forbidden` becomes `Verify(Permitted, expect=False)` with the quantifier flipped.
- `vqa/parsing/`, the question parser (phase 2):
  - `wire.py`: the depth-limited structured-output schema, since the API rejects recursive schemas. It converts to `QueryProgram` and applies the defaults.
  - `validator.py`: semantic checks, plus a dry run on an empty scene.
  - `prompt.py`: builds the cached system prompt from `prompts/parser/<version>/` (`spec.md`, `fewshot.jsonl`) and the catalog.
  - `claude_parser.py`: one call, with one retry that includes the error.
- `vqa/llm/`, Claude API access:
  - `client.py`: structured calls.
  - `pricing.py`.
  - `spend.py`: the spend guard (default $2, `VQA_SPEND_LIMIT` or `--max-spend`) and the usage log `logs/api_calls.jsonl` (gitignored).
  - The key comes from `ANTHROPIC_API_KEY` only and is never committed.
- `vqa/pipeline.py` (phase 4): `answer(image_path, question)`. `vqa/answer/`: the proof digest, the faithfulness guard, template answers, the writer (`prompts/answer/`), the answer-level fallback (`prompts/answer_fallback/`).
- `eval/e2e_eval.py` (public_dev, warm, run, next; oracles; scores), `eval/judge.py` (`eval/prompts/judge/`), `eval/e2e_holdout.py` (aggregate only).
- `eval/freeze.py`: write-once freeze records. The private runner now requires `eval/frozen_phase52.json` (owner, 2026-11-20): phase50 (scene v5 + guide reading, no scene re-run, parallel calls, writer v3, reading policy A, signals off; several_signs, sign_charts, one_sign_g1 and asked_only on; confusable_pairs and stated_exceptions off) with parser v18, the 65bbfbb rule and engine fixes and the 8b45e0b lane_reserved_is fixes. v18 and those fixes have no dev run yet; see docs/status.md. Historical freeze records stay unchanged.
- `vqa/reasoning/`:
  - `terms.py`: Python values to Prolog text.
  - `facts.py`: SceneGraph to scene facts, plus the variants for alternative sign readings.
  - `engine.py`: the janus bridge. `Engine().answer(scene, program) -> Answer`.
  - `explain.py`: proof dict to ProofNode, plus citations.
- `kb/`:
  - `load.pl`: loads everything.
  - `meta.pl`: meta-interpreter that builds the proof tree.
  - `scene.pl`: declarations for the fact predicates.
  - `ontology.pl`: vehicle hierarchy.
  - `rules/*.pl`: one file per rule family: `prohibitions`, `speed` (speed limits, lanes, limit values), `mandatory` (R.301 by placement) and `identity` (`is_sign`). Shared checks are in `common.pl`.
  - Later rule files: `zones` (phase 4.5: expressway and residential zones), `coverage47` (who a sign addresses), `general47` (Law 36 general rules: places, lanes, priority vehicles, Circular 38 speeds), `signals47` (scene v6 lights, markings, R.411 arrows) and `v13_47` (the officer, signal precedence, right of way, vehicle classes).
  - `v6_fields_47.yaml`: the scene v6 field switch (signals off, owner 2026-11-18). Its key is quoted, `"off":`, because a bare `off` is YAML 1.1 for false.
  - `query.pl`: the `q_*` entry points.
- `tests/`: one file per rule family, using hand-written scene graphs and programs.
  - `tests/integration/` runs train questions from `tests/fixtures/train_*.json` (format in `tests/fixtures/README.md`).

## Conventions

- **The rule engine owns every legal conclusion.** Python resolves selectors, loops over lanes and reading variants, and packages results. It never decides what is permitted.
- **Three-valued logic.** Truth values are `true`, `false` and `unknown`. A missing fact (time, weight, lane, exact vehicle subtype) makes the result `unknown`, never `false`. Verdicts: `yes`, `no`, `unknown`, `uncertain` (alternative readings disagree), or `value`. Under reading policy A (`higher_confidence`, the frozen phase-4.6 and 4.7 policy) a disagreement is answered with each sign's highest-confidence reading, with the signs in `uncertain_signs` and `basis: ["reading_choice"]`; `uncertain` remains the verdict of the policy `all`.
- **An unreadable sign makes closed-world answers unknown, but only if it could bear on the claim.** "Unreadable" means the code is UNKNOWN or not in the catalog; a sign on an `effect_unmodelled` row (effect not modelled yet, e.g. R.303) acts like an unreadable sign of its visible category.
  - **Affected verdicts:** a "yes" from `permitted`/`speed_ok`, or a "no" from `required`/`exists_violation`. The answer lists the sign in `uncertain_signs`.
  - **Relevance comes from the sign's visible category** (`Engine.visual_category`, `could_matter`):
    - red-bordered circle (prohibitory): permissions, speed, violations;
    - rectangle with a red background or red border (local ban notices, red plates): counts as prohibitory, so permissions, speed, violations;
    - blue circle (mandatory): directions, speed, `required`;
    - other rectangles (blue/green/white board): speed, or a claim about a given lane;
    - triangle (warning) and end-of-restriction signs: never;
    - nothing recorded: always.
  - **Not affected:** answers decided by a readable sign.
  - **Single-sign questions** (`only`, "Đây là biển gì?"): unreadable candidates are dropped. If every readable candidate has the same code, the answer is decided with it and the unreadable signs go in `uncertain_signs`; if the readable codes differ, the answer stays unknown (`Engine.single_sign`).
  - **In the full pipeline**, an answer that is unknown because of an unreadable sign goes to the fallback.
- **`every_vehicle` claims quantify over members, not just classes.** A class whose answer depends on unstated weight or seats is tried at the scene's thresholds. A failing member makes the class a counterexample, reported with its condition.
- **Every rule and catalog row cites its source** as `law_id` + `article_id`, using the dataset's `relevant_articles` format, e.g. `QCVN 41:2024/BGTVT` + `B.25`.
  - Generic rules use `cite(r_...)` with a `rule_source/3` fact in `kb/rules/common.pl`.
  - Catalog facts are cited automatically through `catalog_sign/4`.
  - A proof step that uses an auxiliary plate cites art. 41 next to the plate's own article (F.10, F.5, F.17, F.4).
  - **Knowledge-based rules (owner exception, 2026-11-17):** when `law_db` has an article for an effect, the rule cites it and follows its wording (quote the text in a YAML comment where the effect depends on a phrase). When `law_db` has nothing, a rule may come from knowledge of Vietnamese traffic law, but only the current versions (QCVN 41:2024/BGTVT, Law 36/2024/QH15, and Circular 38/2024/TT-BGTVT for speed limits by road type; owner, 2026-11-17). It is marked as an interpretation: `law_id: interpretation` plus a `basis` note naming the law and article it is believed to come from. It shows in proofs, is never counted as a law citation, and never contradicts a `law_db` article. Knowledge-based rules are listed separately for the owner's review; new and changed rows are `reviewed_by: assistant`.
- **Every answer has a proof and citations, "yes" included.**
  - The checks in `assess/6` return a truth value and never fail.
  - `forbids` and the other "against" rules use them to show why a sign applies.
  - `clears`, `speed_clears`, `lane_clears` and `requirement_clears` use them to name the check that failed (`vehicle_not_covered`, `outside_time_window`, ...).
  - Citations follow the verdict: clears for yes, true reasons for no, unknown reasons for unknown.
- **Catalog rows are drafts until a person checks them.**
  - `reviewed_by: human | assistant | none` says who checked a row's name, letters and citation. Only `human` counts as checked.
  - `visual_reviewed_by` tracks the visual attributes separately.
  - Quote the article text in a YAML comment wherever an effect depends on a specific phrase, such as "kể cả xe được ưu tiên".
- **Prolog rules may not contain cuts.** The meta-interpreter does not implement cut, so use if-then-else or mutually exclusive clauses. Small deterministic helpers are marked `leaf(...)`: they run natively and show up as one proof node, and they may cut.
- **Vehicle classes live in two places.** They are `VehicleClass` in `vqa/schemas.py` and `is_a/2` in `kb/ontology.pl`. `tests/test_schemas.py` checks that the two stay in sync.
  - "xe khách" means `coach`, a bus that is not a city bus.
  - "xe ba bánh" / "xe lam" means `motor_tricycle`, which falls under B.11, not P.104.
  - "xe 4 bánh thô sơ" means `similar_rudimentary`, our interpretation of Law 36 art. 34(2)(e). Interpretations like this are listed under `vehicle_interpretations` in the catalog and shown in proofs.
  - A stated load bounds the gross mass: load > x implies gross > x (`load_implies_gross`, from QCVN 41 B.15's definition of gross mass). It is a `vehicle_interpretations` entry with an `attribute_rule`, shown in proofs as `cite(r_load_implies_gross)`. Its `rule_source` has law_id `interpretation`, so it is never counted as a law citation.
- **Vehicle attributes are exact or bounded** (`seats_gt=29`), never both. In Prolog a bounded attribute is an interval `iv(Lo, LoIn, Hi, HiIn)`.
- **Time intervals need a quantifier** (`all` or `any`), which applies to what the program states. For a ban, write `Forbidden`, not `Verify(Permitted, expect=False)`.
- **A sign with several (vehicle, time) pairs uses condition groups (`Sign.rules`)**, not separate vehicle and time plates.
- **The context is `ctx(Minute, Day, Lane)`.** The lane check is part of `assess/6`. A sign over some lanes gives unknown when no lane is asked about.
- **Non-standard plates are plates of kind `local`.**
  - The text is kept verbatim.
  - Its vehicles and actions replace the sign's own (`effective_prohibits/4`).
  - Proofs show `local_plate(...)` and `cite(r_non_standard_plate_not_in_qcvn41)`, which has no law source.
  - Answers get `basis: ["non_standard_plate"]`.
  - Standalone local signs (no standard main sign) are not modelled.
  - **Assumptions to re-check against real failures:**
    - **Condition groups narrow the sign's vehicles.** A vehicle no group mentions loses the sign's ban, e.g. tractors under train_7_15's truck-only plate on P.106a. The alternative: groups qualify only the vehicles they name, and the rest keep the sign's own effect.
    - **Replacement keeps the pictogram's weight condition.** When a local plate replaces the sign's vehicles (e.g. "CẤM CÁC LOẠI XE TẢI" under a 1.25 t P.106b), the number on the pictogram still applies through `value_cond`, so only trucks above 1.25 t are banned. The alternative: the plate's wording wins and every truck is banned.
- **Catalog family rows carry their variants in QCVN notation** (`W.207(a,b,...)`). `Catalog.get("W.207c")` resolves to the family row.
- **Sign codes in Prolog** are lowercase with no dots: `P.127b` becomes `p127b`, `S.H,6` becomes `sh_6`. See `vqa.kb.code_atom`.
- **Lanes are numbered from 1**, with lane 1 the leftmost. Time windows include both ends and may run past midnight.
- Add a test with every new rule. Write test scenes by hand and model them on train questions. Do not copy them from dataset files.

## Parser rules

- **"Các loại xe" / "mọi phương tiện" (every vehicle) maps to `every_vehicle`, not `vehicle`.**
  - `every_vehicle` makes a claim hold only if it holds for every vehicle class.
  - `vehicle` means "a vehicle of unknown kind": against a motor-vehicle ban it gives unknown.
- **The parser fills in values the question leaves out, and records that it did** in `defaults_applied` (next to `missing_slots`):
  - year: the current year in the question's context;
  - vehicle: `motor_vehicle`.
- **Questions no DSL intent can express come back as `out_of_scope`,** never as a forced program. They go to the fallback.
- **Few-shot examples come from train and `public_dev` only, with the dataset's exact question text.** `tests/test_parser.py` checks this.
  - A `public_dev` question used as a few-shot is excluded from the gate score.
  - Change a prompt only by adding a new version under `prompts/parser/`. The version is part of cache keys and results.
- **Gold-intent working files hold dataset question text and stay local** (gitignored). The gold file keeps ids and programs only.
- **Rule coverage** is the share of questions the rules answer rather than the fallback.
  - Audits of `public_dev` are development estimates only.
  - The real figure is measured on `public_holdout` through the pipeline.
