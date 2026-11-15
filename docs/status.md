# Project status

Last updated 2026-11-15. Branch `phase-2` (not merged), on top of `main` at `9264d55`.

## Done

### Phase 1: contracts and KB core

- `24dc356` Pydantic schemas, a 68-row sign catalog, Prolog rules with a proof-building meta-interpreter, the janus engine, and tests.
- `0eb5cda` Fixed two citation bugs: speed rules now cite art. 22, and F.4 is cited only for an actual S.504 plate.
- `3cdf18b` Integration tests for six train questions (hand-written fixtures).

### Phase 1.5: phase 1 gaps

- `71d265c` Proofs for "yes" answers (`assess` / `clears`); plates cite art. 41.
- `c32e0de` Schema 1.2: vehicle bounds, meaning selectors, time intervals with a quantifier, `Forbidden`, condition groups, `Choose`.
- `508de0f` `similar_rudimentary` (interpretation of Law 36 art. 34(2)(e)); R.301 placement rules (D.1a).
- `b3e6c5b` Fixtures rewritten in the new DSL; DESIGN.md and CLAUDE.md updated.

### Between phases

- `44d2ef1` public_dev / public_holdout split (50/50 by image, seed 20261114); coverage audit v1.
- `1af4b31` Near-duplicate image check across splits (`data/splits/duplicates.json`); parser and coverage notes.

### Phase 1.6: coverage for the private test's profile

- `a267dd5` Leakage guard: inference rule, import test, duplicate-aware eval reports with a 95% CI.
- `368be36` `is_sign` identity claims; `all_of` / `any_of` compound claims.
- `e22391b` `which_vehicles`; non-standard (`local`) plates, flagged in proofs and in `Answer.basis`.
- `60ff26c` R.415a/b lane board; lane slot in `permitted`/`forbidden`; `lane_vehicles`; `speed_limit`.
- `f6d106a` 148 meaning-only W/I/IE catalog rows, plus a review list.
- `7c86517` Public-dev audit v2: 39 A / 3 B / 9 C (76.5%, development estimate).
- `2ca5d04` Applied the meaning-row review: IE.473 renamed, IE.472 split into two rows, visual fixes, review flags.
- `9264d55` `every_vehicle` for "các loại xe"; local-plate assumptions recorded.

### Phase 2: question parser (in progress, branch `phase-2`)

- `f89b1be` `every_vehicle`: members on both sides of a threshold are counterexamples, reported with their condition.
- `aa85801` Catalog `reviewed_by` / `visual_reviewed_by` (human | assistant | none).
- `6193e85` Unreadable signs make an answer unknown only if their visible category could bear on the claim.
- `ab2baf3` API layer: `anthropic` SDK 2.x client, pricing, usage log, spend guard (default $2).
- `49169db` Parser: depth-limited wire schema, validator, Claude parser with one retry, `prompts/parser/v1` (spec plus 16 train few-shots).
- `b7e648c` Gold-intent tool: select, estimate, submit, collect, import.
- `c38b922` Prompt `v2` (the owner's rewritten train text, plus three public_dev "đúng hay sai" few-shots). Gold sample: 48 public_dev and 40 train questions.
- `3b368ce` Gold drafting `run`: sequential calls with caching, a cache check after call 2, and resume.
- `734135e` Wire schema: sign codes and meanings as strings checked in Python (first try at the grammar-size 400).
- `7ff868d` Wire schema flattened to one object per nesting level (second try; still rejected).
- `c1addf3` Parser replies in plain JSON, with no JSON schema (the owner's plan change of 2026-11-15). Prompt `v3`. Every API call is logged with a status.
- `39384c3` Sign codes in programs can also be a variant code ("W.207c") or the stem of a family row ("W.207"), kept as written.
  - A stem shared by separate rows ("W.221" for W.221a and W.221b) is rejected, and the error lists the closest valid codes.
  - Prompt `v4` (the default): v3 with the wrong "W.221" family example replaced by "W.207". v1, v2 and v3 are frozen by sha256 in the tests.

Full test suite: 273 passed. Three API requests have been sent (gold drafting, 2026-11-15). All three were rejected with a 400 before the model ran, so nothing was billed.

## Next steps, in order

1. **Visual corrections.** Five rows are still `visual_reviewed_by: assistant`, waiting for the owner's check: W.242(a,b), W.243(a,b,c), IE.451a, IE.471, IE.473. Set each confirmed row to `human` in `tools/draft_catalog_rows.py` and regenerate.
2. **Gold drafting: 48 public_dev and 40 train questions** (the owner's change of 2026-11-15). `select` has already written the 88 questions. The three public_dev few-shots are not drafted. Drafting uses prompt `v4`, Opus 5.5 at medium effort, sequential calls with caching. The owner chose sequential over batch because a batch's caching is best effort. With `ANTHROPIC_API_KEY` set:
   1. Run `eval/gold_intents.py estimate` in the owner's terminal. It is free and gives the exact count for `v4`. The offline rough figure is 18.4k prompt tokens per request: about $1.94 sequential, or $3.45 if outputs run twice as long. The owner decides the `--max-spend` from the exact figure.
   2. Run `eval/gold_intents.py run --max-spend N`.
      - The spend guard checks every call before it is sent.
      - After call 2, at least 90% of the prompt must have been read from the cache, or the run stops.
      - The run resumes where it stopped (`run_progress.jsonl`). It rewrites `review.csv` after every call, and refuses to touch one that already has verdicts.
      - A reply that is not a single JSON object becomes an `invalid` row with the reason. Gold drafting does not retry.
   3. If the cache check fails, use the batch path instead: `submit`, then `collect --wait`.
   - **Why there is no schema.** Three requests on 2026-11-15 were rejected with "The compiled grammar is too large", and none was billed. Two attempts to shrink the schema failed first: strings for codes and meanings (`734135e`), then a flat schema (`7ff868d`). The documented limits explain why: at most 24 optional parameters and 16 union-typed parameters (`anyOf` or nullable) across all strict schemas in a request. The DSL has about 60 optional fields. Since `c1addf3`, the reply is plain JSON checked by the typed wire models.
3. **Build `eval/parser_eval.py`.** It reports:
   - program exact match, after normalization, against the gold or any `also_accept` program;
   - slot F1;
   - out-of-scope precision and recall;
   - the gate score with a 95% CI, computed per split.

   Few-shot questions are excluded from scoring.
4. **After the owner's review of `review.csv`:**
   1. Run `eval/gold_intents.py import`.
   2. Run Haiku 5.5 on public_dev at `low` and at the default effort, and report accuracy and cost for each.
   3. Check the gate: ≥ 90% program accuracy on reviewed public_dev intents, with a 95% CI.

## Open items

- **Stems of separate rows.** The wire rejects "P.124", "P.106", "W.221" and the other 32 stems whose signs are separate catalog rows; this was the owner's rule in `39384c3`. The engine's `Catalog.codes_matching`, though, accepts such a stem as "any of its rows", and `tests/test_claims.py::test_family_code_matches_variants` relies on that ("P.124" against a P.124c scene gives yes). So the parser cannot produce a program the engine supports. To be decided: allow these stems in `is_sign`, or keep them out.
- **Codes in selectors are compared as strings.** `Engine.resolve` compares `sign.code` with the scene sign's code exactly. A variant or stem in a selector matches only a scene sign recorded the same way; "W.207" in a selector matches no "W.207c" sign. `is_sign` targets are not affected, because they resolve through the catalog.

- **Train questions were rewritten by the owner (2026-11-15).** The rewrite made them shorter and more conversational. There are still 530 questions and the few-shot ids still exist. Whether any answers changed can't be checked, because there is no copy of the old file. The rewrite still differs from public_dev in style:
  - public_dev ends a stated claim with "đúng hay sai" (or "đúng không") in 33% of questions; train never uses "đúng hay sai" and ends with "đúng không" / "phải không" in about 7%;
  - public_dev has quoted claims, lowercase starts, a space before "?" and typos; train has almost none;
  - train says "trong ảnh" in 44% of questions; public_dev never does and says "trong hình" or "phía trước" instead.

  The rewrite removed every "đúng hay sai" form from the seed examples. To make up for it, v2 adds three public_dev few-shots: public_natural_0026 (a quoted claim), 0097 (sign identity) and 0082 (a stated claim, then ". Đúng hay sai?"). They are excluded from drafting and from the gate score, so the gate set is 48 questions.

- **Phase 1.7:**
  - warning-sign behaviour ("phải giảm tốc độ");
  - a sign's time windows without a vehicle;
  - counting signs by category;
  - the B.25 overtaking exception (two-wheelers);
  - expressway rules (Law 36);
  - P.118 / P.119 size limits.

  The target is ≥ 80% rule coverage after phase 1.7.
- **Local-plate assumptions** (CLAUDE.md, to re-check against real failures):
  - condition groups narrow the sign's vehicles;
  - replacing a sign's vehicles keeps the pictogram's weight condition.
- **Left to the fallback:** guide-sign content (directions, destinations, distances) and traffic lights. Unknowns caused by unreadable signs also go to the fallback.
- **Not modelled yet:**
  - QCVN 41 art. 26 (where and how far prohibitory signs take effect; `Required` covers only the R.301 family);
  - standalone local signs;
  - the signal-priority order;
  - default speed limits by road type;
  - dashed vs. solid bus-lane markings;
  - time intervals for intents other than `permitted`/`forbidden` (these answer unknown).
- **Rule coverage:** measured as the share of questions the rules answer rather than the fallback.
  - The target was ≥ 70% after phase 1.6; the public_dev audit (a development estimate) gives 76.5%.
  - The real figure comes later from public_holdout through the pipeline, together with accuracy on the rule-answered questions.
