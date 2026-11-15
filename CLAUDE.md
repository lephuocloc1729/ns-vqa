# Neuro-symbolic traffic sign VQA

DESIGN.md is the full design. Read it before you change architecture. We build it phase by phase, following its roadmap. The scene graph and DSL are at schema 1.2.

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
- **Many images repeat across splits.** `data/splits/duplicates.json` lists near-duplicate image groups, made by `eval/find_duplicates.py`. It uses perceptual hashes and reads image files only, never question files.
  - 79 of the 104 private images and 53 of the 90 public images also appear in train.
  - Evaluations report every score twice: on all questions, and without questions whose image is in `duplicated_with_train`. Map image ids to questions at evaluation time.
  - The duplicate check finds copies and slight re-crops. It misses different photos of the same scene.
- **Never open the private test answers.** The private test is the final benchmark and runs once, at the end.
- Keep `provenance.json` and `review.json` out of prompts. `train_284` has an invalid citation.

## Leakage guard

- **At inference, the pipeline never uses hand-made scene graphs, test fixtures, gold labels or train QA for an image.**
  - It never looks up train (or any split's) data by image hash or image similarity.
  - The only cache is the scene cache (`vqa/perception/cache.py`, `cache/scenes/`, gitignored). It holds model outputs only, keyed by image hash plus model id plus effort plus prompt version.
- **Inference code means `vqa/` and `app/`.** It must not import from `tests`, `conftest` or `eval`. It must not mention fixture, annotation, audit, split or duplicate files, or the dataset's QA files.
  - `tests/test_leakage_guard.py` enforces this.
  - Few-shot examples built from train go into versioned prompt files under `prompts/`. They are never selected per image.
- **Every eval report gives two scores:** one on all images, and one on non-duplicate images only, with a 95% confidence interval for the non-duplicate subset.
  - Use `eval/report.py` (`score_report`, `format_report`).
  - For public, "duplicate" means the image is also in train. For private, it means the image is also in train or public.

## Layout

- `vqa/schemas.py`: contracts: SceneGraph, QueryProgram (the DSL), Answer. Any vocabulary that reaches Prolog is an enum here.
- `vqa/kb.py`: loads the catalog and turns it into Prolog facts.
  - `kb/sign_catalog.yaml`: rows with rule effects.
  - `kb/sign_catalog_meaning.yaml`: meaning-only W/I/IE rows drafted by `tools/draft_catalog_rows.py`. Their review list is `kb/review/meaning_rows_review.md`.
- `tools/`: offline authoring tools. They may read law_db; inference code may not.
- `docs/`: `status.md` (status and next steps) and `plans/` (approved phase plans).
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
  - `query.pl`: the `q_*` entry points.
- `tests/`: one file per rule family, using hand-written scene graphs and programs.
  - `tests/integration/` runs train questions from `tests/fixtures/train_*.json` (format in `tests/fixtures/README.md`).

## Conventions

- **The rule engine owns every legal conclusion.** Python resolves selectors, loops over lanes and reading variants, and packages results. It never decides what is permitted.
- **Three-valued logic.** Truth values are `true`, `false` and `unknown`. A missing fact (time, weight, lane, exact vehicle subtype) makes the result `unknown`, never `false`. Verdicts: `yes`, `no`, `unknown`, `uncertain` (alternative readings disagree), or `value`.
- **An unreadable sign makes closed-world answers unknown, but only if it could bear on the claim.** "Unreadable" means the code is UNKNOWN or not in the catalog; a sign on an `effect_unmodelled` row (effect not modelled yet, e.g. R.303) acts like an unreadable sign of its visible category.
  - **Affected verdicts:** a "yes" from `permitted`/`speed_ok`, or a "no" from `required`/`exists_violation`. The answer lists the sign in `uncertain_signs`.
  - **Relevance comes from the sign's visible category** (`Engine.visual_category`, `could_matter`):
    - red-bordered circle (prohibitory): permissions, speed, violations;
    - blue circle (mandatory): directions, speed, `required`;
    - blue/green/white rectangle (board): speed, or a claim about a given lane;
    - triangle (warning) and end-of-restriction signs: never;
    - nothing recorded: always.
  - **Not affected:** answers decided by a readable sign.
  - **In the full pipeline**, an answer that is unknown because of an unreadable sign goes to the fallback.
- **`every_vehicle` claims quantify over members, not just classes.** A class whose answer depends on unstated weight or seats is tried at the scene's thresholds. A failing member makes the class a counterexample, reported with its condition.
- **Every rule and catalog row cites its source** as `law_id` + `article_id`, using the dataset's `relevant_articles` format, e.g. `QCVN 41:2024/BGTVT` + `B.25`.
  - Generic rules use `cite(r_...)` with a `rule_source/3` fact in `kb/rules/common.pl`.
  - Catalog facts are cited automatically through `catalog_sign/4`.
  - A proof step that uses an auxiliary plate cites art. 41 next to the plate's own article (F.10, F.5, F.17, F.4).
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
