# Neuro-symbolic traffic sign VQA

DESIGN.md is the full design. Read it before you change architecture. We build it phase by phase, following its roadmap. **Current phase: 1, "Contracts and KB core"** (no Claude API calls).

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
- **Never open the private test answers.** The private test is the final benchmark and runs once, at the end.
- Keep `provenance.json` and `review.json` out of prompts. `train_284` has an invalid citation.

## Layout

- `vqa/schemas.py`: contracts: SceneGraph, QueryProgram (the DSL), Answer. Any vocabulary that reaches Prolog is an enum here.
- `vqa/kb.py`: loads `kb/sign_catalog.yaml` and turns it into Prolog facts.
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
  - `rules/*.pl`: one file per rule family.
  - `query.pl`: the `q_*` entry points.
- `tests/`: one file per rule family, using hand-written scene graphs and programs.

## Conventions

- **The rule engine owns every legal conclusion.** Python resolves selectors, loops over lanes and reading variants, and packages results. It never decides what is permitted.
- **Three-valued logic.** Truth values are `true`, `false` and `unknown`. A missing fact (time, weight, lane, exact vehicle subtype) makes the result `unknown`, never `false`. Verdicts: `yes`, `no`, `unknown`, `uncertain` (alternative readings disagree), or `value`.
- **Every rule and catalog row cites its source** as `law_id` + `article_id`, using the dataset's `relevant_articles` format, e.g. `QCVN 41:2024/BGTVT` + `B.25`.
  - Generic rules use `cite(r_...)` with a `rule_source/3` fact in `kb/rules/common.pl`.
  - Catalog facts are cited automatically through `catalog_sign/4`.
- **Catalog rows are drafts until a person checks them.** Each row has `reviewed: false` until then. Quote the article text in a YAML comment wherever an effect depends on a specific phrase, such as "kể cả xe được ưu tiên".
- **Prolog rules may not contain cuts.** The meta-interpreter does not implement cut, so use if-then-else or mutually exclusive clauses. Small deterministic helpers are marked `leaf(...)`: they run natively and show up as one proof node, and they may cut.
- **Vehicle classes live in two places.** They are `VehicleClass` in `vqa/schemas.py` and `is_a/2` in `kb/ontology.pl`. `tests/test_schemas.py` checks that the two stay in sync.
  - "xe khách" means `coach`, a bus that is not a city bus.
  - "xe ba bánh" / "xe lam" means `motor_tricycle`, which falls under B.11, not P.104.
- **Sign codes in Prolog** are lowercase with no dots: `P.127b` becomes `p127b`, `S.H,6` becomes `sh_6`. See `vqa.kb.code_atom`.
- **Lanes are numbered from 1**, with lane 1 the leftmost. Time windows include both ends and may run past midnight.
- Add a test with every new rule. Write test scenes by hand and model them on train questions. Do not copy them from dataset files.

## Not built yet (later phases)

- Claude parser, perception, answer writer, faithfulness guard, eval runner.
- Rules not yet covered:
  - `Required` questions and placement relative to intersections.
  - Signal-priority order.
  - Default speed limits by road type (needs a source).
  - Which vehicle is being overtaken (the B.25 exception for two-wheelers).
  - Dashed vs. solid bus-lane markings.
