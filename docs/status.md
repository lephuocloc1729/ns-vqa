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
- `f7e9991` Parser and engine now agree on what a sign code names. This closes the two open items `39384c3` left (stems of separate rows, and string matching in selectors).
  - The wire accepts exactly what `Catalog.codes_matching` resolves, including stems of separate rows such as "W.221" and "P.124". The owner withdrew the rule that rejected them.
  - Selectors use `Catalog.code_selects`:
    - equal codes match ("W.207c" selects only W.207c);
    - a family stem or the full family row code selects the family's variants;
    - a stem of separate rows selects each of its rows;
    - UNKNOWN or uncatalogued scene codes never match.
  - v1 to v4 prompts are pinned by sha256.

- `cf5afe6` Gold intents v1: 87 reviewed programs, 47 public_dev and 40 train (ids and programs only).
- `ecadd29` `eval/parser_eval.py` (`run`, `score`; gate fixed before any Haiku result). Raw replies are now kept for every parser call and in gold drafting's `run_progress.jsonl`.

- `c909f43` Prompt `v5`: v4 plus spec rules learned from the first Haiku errors. The few-shots are unchanged, so the gate set is unchanged.

- `927fdd4` Prompt `v6` (the default): v5 with the sign-selector rules narrowed. Two spec lines changed; the few-shots are unchanged.

- `0257a71` Gate on the mean of three runs (the owner's rule, set before the v6 results).
- `9afa338` `score` counts a run once even if its file is given twice (identified by run_id).
- `7f19fd2` The parser's default is Sonnet 5.5 at medium effort (the owner's choice after the gate runs).

Full test suite: 334 passed.

### First gate result (prompt v4, 2026-11-15): FAIL

| Haiku 5.5 effort | program accuracy | 95% CI | slot F1 | OOS P / R | cost |
|---|---|---|---|---|---|
| low | 83.0% (39/47) | 69.9–91.1% | 83.3% | 100% / 100% | $0.0134 |
| medium (default) | **87.2% (41/47)** | 74.8–94.0% | 84.7% | 100% / 100% | $0.0133 |

- Medium is better at the same cost.
- Medium's six wrong rows:
  - two real parser errors that flip the answer: 0011 dropped "kể cả xe ưu tiên", and 0065 wrote `permitted` for "có bị phạm luật không";
  - three equivalent sign selectors that the strict gold does not accept: 0002, 0025, and 0043 (code P.107 instead of the meaning);
  - one DSL gap, 0005, a phase 1.7 "only for X" claim.
- Low also missed:
  - 0094: "xe thô sơ 3 bánh" became `rudimentary`;
  - 0084: `only` was missing;
  - 0025: a `category` in a selector, which failed after the retry.
- The non-duplicate / duplicate split (100% vs 80%) means nothing here: the parser never sees the image.

**Prompt v5** adds rules for these errors:
- "kể cả xe ưu tiên" means `all_of` with a `priority: true` claim;
- a named vehicle plus "có vi phạm không" means `forbidden`;
- `meaning` over `code` unless the code is written;
- selectors have no `category`, and `sign: {}` selects several signs;
- `required` has no `sign` and `which_vehicles` has no `vehicle`;
- "xe thô sơ 3 bánh" is `cyclo`.

The rules come from public_dev errors, so a v5 score on public_dev is a tuned figure. A test checks that the v5 spec quotes no gate question (no 6-word overlap). The unbiased figure comes from public_holdout, end to end.

### Prompt v5 result (2026-11-15): FAIL, two runs

| run | accuracy | slot F1 | cost | wrong |
|---|---|---|---|---|
| v5 A | 87.2% (41/47) | 92.1% | $0.0145 | 0002, 0005, 0025, 0048, 0051, 0092 |
| v5 B | 87.2% (41/47) | 92.0% | $0.0126 | 0002, 0005, 0025, 0043, 0048, 0051 |

- 0011 and 0065 were fixed in both runs, and 0043 in run A.
- v5 caused new errors:
  - 0051 and 0092: its "`sign: {}` for several signs" rule spread to `ban_times` and `which_vehicles`, where the gold leaves the sign empty;
  - 0048: the claims about a sign named in quotes lost its `meaning` selector.
- Slot F1 rose from 84.7% to 92%, so the remaining errors are smaller.
- **Run-to-run noise:** the two v5 runs differ on two questions (0043, 0092), and one question is 2.1 points. The owner decided, before any v6 result, that from v6 on the gate is decided on the mean of three runs; the mean, the range and each run's CI are reported.
- Without `also_accept` for 0002 and 0025, and with 0005 still a DSL gap, a run can reach at most 44/47 = 93.6%.

**Prompt v6** keeps `sign: {}` to `meaning` and `is_sign`. It leaves `sign` empty for other intents that are about the road or all its signs. And a sign named in words or quotes gets its `meaning` selector on every claim, inside `all_of` / `any_of` too.

### Prompt v6 result (2026-11-15): FAIL on the mean of three runs

| run | accuracy | slot F1 | OOS P / R | cost |
|---|---|---|---|---|
| v6 A | 89.4% (42/47) | 92.9% | 88.9% / 100% | $0.0143 |
| v6 B | 89.4% (42/47) | 90.8% | 100% / 100% | $0.0127 |
| v6 C | 89.4% (42/47) | 92.7% | 100% / 100% | $0.0126 |
| **mean** | **89.4%** (range 89.4–89.4%) | | | $0.040 in total |

- v6 fixed the v5 regressions (0048, 0051, 0092) and kept 0011 and 0065 fixed.
- The same five rows were wrong in all three runs:
  - **0002 and 0025:** equivalent selectors. Haiku's choice was stable: blue background (plus `only`) for 0002; triangle, red border and `only` for 0025.
  - **0043:** vehicle `coach` in every run, where the gold has no vehicle. P.107's windows are the same for coaches and trucks.
  - **0084:** a different program in each run:
    - out of scope ("wrong-way driving is not a modelled action"), a real error;
    - `forbidden` enter for `every_vehicle` under the no_entry_one_way sign;
    - `is_sign` with `sign: {}`.

    The last two are reasonable readings that the strict gold doesn't accept.
  - **0005:** the DSL gap.
- That makes one real parser error in 141 predictions (0084 in run A). Every other miss is a strict-gold mismatch or the DSL gap.

### Sonnet 5.5 result (prompt v6, medium, 2026-11-15): PASS on the mean of three runs

| run | run_id | accuracy | slot F1 | cost |
|---|---|---|---|---|
| A | a00bf0a63e3b | 93.6% (44/47) | 93.6% | $0.1569 |
| B | f20993f4ac4e | 93.6% (44/47) | 94.9% | $0.1587 |
| C | a42d6be03e11 | 93.6% (44/47) | 93.6% | $0.1196 |
| **mean** | | **93.6%** (range 93.6–93.6%) | | $0.435 in total, about $0.003 per question |

- **The gate passes for Sonnet** (≥ 90% on the mean of three runs); Haiku failed at 89.4%.
- The same three rows were wrong in every run:
  - 0005: the DSL gap;
  - 0025: `only: true` instead of triangle;
  - 0084: `is_sign` with `sign: {}`.
- Sonnet's lead over Haiku comes from 0002 and 0043, where it matches the selectors Opus chose when it drafted the gold. It is not a fix of real errors: Haiku's v6 runs made one real error in 141 predictions.
- **Sonnet often writes prose around the JSON.** In run B, 6 of 47 first replies were rejected as `bad_json` and retried. One retry (0005) was refused with category `reasoning_extraction`. This costs retries; a v7 instruction or an accepted "prose, then a fenced JSON" form could reduce it.
- **A first score showed three identical Sonnet files.** They were byte-identical copies of run A (same sha256 and run_id; the API log had only that run's 52 calls). It is not a result. `score` now counts a run once per run_id. The two real runs, B and C, replaced the copies.
- **Owner's decision (after the results):** the parser's default is Sonnet 5.5 at medium effort. Plan item 2 named Haiku. It costs about 11 times as much per question (about $0.003 against $0.0003).

Still open: `also_accept` for the equivalent selectors (0002, 0025, 0043). This is the owner's decision, row by row, made after the results. If adopted, it goes into a new gold version. API use so far (gold drafting, 2026-11-15):
- Three requests were rejected with a 400 before the model ran, so nothing was billed.
- The sequential gold run then made 88 calls with Opus 5.5 at medium effort on prompt v4. It cost **$0.53**, against an estimate of $1.86.
  - Every call after the first read the whole prompt from the cache.
  - Outputs averaged 104 tokens, with a maximum of 503.
  - Results: 63 ok, 19 out of scope, 6 invalid. Four of the six were `meaning` or `is_sign` with no `sign`.
- The owner's review covered 87 rows: 80 ok, 7 fix and 1 skip (public_natural_0096). Rows marked ok include the 18 out-of-scope drafts that were kept.

## Next steps, in order

1. **Visual corrections.** Five rows are still `visual_reviewed_by: assistant`, waiting for the owner's check: W.242(a,b), W.243(a,b,c), IE.451a, IE.471, IE.473. Set each confirmed row to `human` in `tools/draft_catalog_rows.py` and regenerate.
2. **Done: the parser gate.** It passed for Sonnet 5.5 at medium on prompt v6; see the results above. The rest of this step is kept as a record. **Haiku on prompt v6, medium effort, three runs:**
   - `eval/parser_eval.py run --model claude-haiku-5-5 --effort medium --max-spend 0.5`, three times
   - `eval/parser_eval.py score <the v5 medium files> <the v6 medium file>`
   - If it still misses 90%, run `claude-sonnet-5-5` once for comparison (about $0.20–0.30).

   Previous runs on v4: Prompt v4, 47 questions. The estimate is about $0.012 per run if outputs match Opus's (~104 tokens), $0.035 at ten times that, and at most about $0.37 in the worst case. With `ANTHROPIC_API_KEY` set:
   1. `eval/parser_eval.py run --model claude-haiku-5-5 --effort low --max-spend 0.5`
   2. `eval/parser_eval.py run --model claude-haiku-5-5 --effort medium --max-spend 0.5` (medium is Haiku 5.5's default)
   3. `eval/parser_eval.py score <both prediction files>`. It gives the per-run scores, the gate, all and non-duplicate images, and the effort table.
3. **After the Haiku results: a v5 spec, if the errors call for it.** The gold drafts point to three rules to add:
   - use `sign: {}` when a question covers several signs ("các biển", "hai biển");
   - `required` and `which_vehicles` take no `sign` or `vehicle` filter;
   - pick the final few-shots from the reviewed gold (D3).

   A v5 means a new prompt version and new Haiku runs, scored against the same gold. Any few-shots taken from public_dev leave the gate set.

## Open items

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
  - P.118 / P.119 size limits (public_natural_0096 was skipped in gold v1 until then);
  - an "only for X" claim, e.g. "làn bên trái chỉ dành cho xe ô tô" (public_natural_0005; gold v1 keeps the car-and-motorbike approximation);
  - `ban_times` without a vehicle (public_natural_0043; gold v1 keeps the draft with no vehicle).

  When these land, re-label the affected rows in a new gold version (`gold_intents_v2.jsonl`), not in v1.

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
