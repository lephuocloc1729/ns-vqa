# Neuro-symbolic traffic sign VQA

DESIGN.md is the full design. Read it before you change architecture. We build it phase by phase, following its roadmap. **Current phase: 1.5, closing the phase 1 gaps before phase 2** (no Claude API calls). The scene graph and DSL are at schema 1.2.

## Setup

You need SWI-Prolog 9.1 or later (`brew install swi-prolog`) and Python 3.11 or later.

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'     # pydantic, pyyaml, janus-swi, pytest
.venv/bin/python -m pytest -q
```

If `janus-swi` fails to build, put `SWI_HOME_DIR=/opt/homebrew/lib/swipl` in front of the pip command. To check the Prolog files on their own:

```bash
swipl -q -g "consult('kb/load.pl'), halt"
```

## Dataset rules

- The dataset is at `VLSP2025-MLQA-Natural/` (or set `$VQA_DATASET_DIR`). It is **read-only** and gitignored. Never copy dataset files into the repo.
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
  - The only cache is the scene cache. It holds model outputs only, keyed by image hash plus model id plus prompt version.
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
- `vqa/parsing/dsl.py`: rewrites run before the engine. `Forbidden` becomes `Verify(Permitted, expect=False)` with the quantifier flipped.
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
- **Every rule and catalog row cites its source** as `law_id` + `article_id`, using the dataset's `relevant_articles` format, e.g. `QCVN 41:2024/BGTVT` + `B.25`.
  - Generic rules use `cite(r_...)` with a `rule_source/3` fact in `kb/rules/common.pl`.
  - Catalog facts are cited automatically through `catalog_sign/4`.
  - A proof step that uses an auxiliary plate cites art. 41 next to the plate's own article (F.10, F.5, F.17, F.4).
- **Every answer has a proof and citations, "yes" included.**
  - The checks in `assess/6` return a truth value and never fail.
  - `forbids` and the other "against" rules use them to show why a sign applies.
  - `clears`, `speed_clears`, `lane_clears` and `requirement_clears` use them to name the check that failed (`vehicle_not_covered`, `outside_time_window`, ...).
  - Citations follow the verdict: clears for yes, true reasons for no, unknown reasons for unknown.
- **Catalog rows are drafts until a person checks them.** Each row has `reviewed: false` until then. Quote the article text in a YAML comment wherever an effect depends on a specific phrase, such as "kể cả xe được ưu tiên".
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
- **Catalog family rows carry their variants in QCVN notation** (`W.207(a,b,...)`). `Catalog.get("W.207c")` resolves to the family row.
- **Sign codes in Prolog** are lowercase with no dots: `P.127b` becomes `p127b`, `S.H,6` becomes `sh_6`. See `vqa.kb.code_atom`.
- **Lanes are numbered from 1**, with lane 1 the leftmost. Time windows include both ends and may run past midnight.
- Add a test with every new rule. Write test scenes by hand and model them on train questions. Do not copy them from dataset files.

## Phase 2 notes (parser)

- **"Các loại xe" / "mọi phương tiện" (every vehicle) is not `vehicle`.** The class `vehicle` means "a vehicle of unknown kind": against a motor-vehicle ban it gives unknown.
  - The parser should write a universal claim over classes instead, e.g. `all_of` over the classes in question, or `which_vehicles`.
  - A dedicated "for every vehicle" form may be worth adding.

- **The parser fills in values the question leaves out, and records that it did** (e.g. `defaults_applied: ["year", "vehicle"]` next to `missing_slots`):
  - year: the current year in the question's context;
  - vehicle: `motor_vehicle`.

## Coverage targets

- Rule coverage is the share of questions the rules answer, rather than the fallback.
- **Targets:** at least 70% after phase 1.6 and at least 80% after phase 1.7.
  - Phase 1.7: warning-sign behaviour, a sign's time windows without a vehicle, counting signs by category, the B.25 overtaking exception, expressway rules, P.118/P.119 size limits.
  - Guide-sign content and traffic lights stay with the fallback.
- **Audits of `public_dev` are development estimates only.** The real coverage figure is measured later on `public_holdout`, through the pipeline, together with accuracy on the rule-answered questions.

## Coverage audit

- `eval/audits/public_dev_audit_v2.tsv` (after phase 1.6) puts public-dev at **39 A / 3 B / 9 C**, i.e. 76.5% rules-covered. This is a development estimate.
  - `eval/audits/public_dev_v2_checks.py` runs the 20 questions that changed against the engine with hand-made scenes. These are audit material, not inference inputs.
- Still open:
  - phase 1.7: warning-sign behaviour (3), the overtaking exception, P.118/P.119, expressway rules, sign windows without a vehicle, counting signs;
  - fallback: guide-sign content (3), traffic lights (1).

## Not built yet (later phases)

- Claude parser, perception, answer writer, faithfulness guard, eval runner.
- Rules not yet covered:
  - Signal-priority order.
  - Default speed limits by road type (needs a source).
  - Which vehicle is being overtaken (the B.25 exception for two-wheelers).
  - Dashed vs. solid bus-lane markings.
  - Time intervals for intents other than `permitted` / `forbidden`. They answer `unknown` for now.

## TODO

- QCVN 41 art. 26: where and how far prohibitory signs take effect.
  - 26.6: P.123 applies in the area of the sign.
  - 26.7: P.124 applies at the intersection.
  - 26.8: P.125–P.131 apply up to the next intersection or the end sign.

  `Required` with placement covers only the R.301 family (D.1a).
- Plates that do not follow the standard form (e.g. the red "CẤM XE 3 BÁNH VÀ 4 BÁNH THÔ SƠ" plate on train_2_26) are not modelled. Decide how to represent the vehicles they list.
