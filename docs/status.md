# Project status

Last updated 2026-11-16. Branch `phase-4`, from `main` at `7ec1134` (`phase-3` merged locally, not pushed; plan D10). **Phase 3 is closed** (see "Phase 3: closing"). **Phase 4 is approved** (`docs/plans/phase-4.md`, owner, 2026-11-16) and in progress.

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

### Phase 2: question parser (merged into `main` at `afe006c`)

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

### Phase 2 results in one table (tuned on public_dev)

**Every v5 and v6 score here is tuned on public_dev.** The rules came from errors on these 47 questions, and the three-run rule was added after v4 and v5 had failed. The unbiased figure comes from public_holdout, end to end.

| model | effort | prompt | gold | runs | mean accuracy | correct per run | gate rule | gate |
|---|---|---|---|---|---|---|---|---|
| Haiku 5.5 | low | v4 | v1 | 1 | 83.0% | 39 | single run | FAIL |
| Haiku 5.5 | low | v4 | v2 | 1 | 87.2% | 41 | single run | FAIL |
| Haiku 5.5 | medium | v4 | v1 | 1 | 87.2% | 41 | single run | FAIL |
| Haiku 5.5 | medium | v4 | v2 | 1 | 89.4% | 42 | single run | FAIL |
| Haiku 5.5 | medium | v5 | v1 | 2 | 87.2% | 41 / 41 | single run | FAIL / FAIL |
| Haiku 5.5 | medium | v5 | v2 | 2 | 90.4% | 42 / 43 | single run | FAIL / PASS |
| Haiku 5.5 | medium | v6 | v1 | 3 | 89.4% | 42 / 42 / 42 | mean of 3 | FAIL |
| Haiku 5.5 | medium | v6 | v2 | 3 | 92.2% | 43 / 43 / 44 | mean of 3 | PASS |
| Sonnet 5.5 | medium | v6 | v1 | 3 | 93.6% | 44 / 44 / 44 | mean of 3 | **PASS** (the official result) |
| Sonnet 5.5 | medium | v6 | v2 | 3 | 93.6% | 44 / 44 / 44 | mean of 3 | PASS |

- Gold v1 is the official gold the gate was fixed on.
- Gold v2 (`146e4e1`, the owner's `also_accept` decisions after the gate runs) is shown for comparison.
- **Model choice:** Sonnet 5.5 at medium, chosen by the owner after the results.
  - The real-error rates are similar: Haiku 1 in 141 v6 predictions, Sonnet 0 in 141.
  - The difference on gold v1 came from rows where the gold accepted one reading only.
  - Sonnet's extra cost is negligible in absolute terms, about $0.003 per question.
- **Total API spend in phase 2: $1.06** over 582 logged calls. This covers gold drafting, all the parser runs and the three unbilled 400s.

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

### Phase 3: perception v1 (in progress, branch `phase-3`)

Plan: `docs/plans/phase-3.md`, approved with D1–D10 (`6113e00`).

- `13eb3a0` `docs/gold_signs_guide.md`: the labeller's rules (what counts as a sign, `readable: false`, fields, plates, lane boards, vehicles, the label file, the D10 check).
- `c88f928` `eval/gold_signs.py`: `select`, `estimate`, `prefill`, `sheet`, `import`.
  - `prefill` is written but not run. It goes through the spend guard before every call and logs each one. It calls the SDK directly, because `LLMClient` takes text only until item 3.
  - Private labels are written only to `data/annotations/gold_signs_private/` (gitignored), and only if git ignores that path.
  - `.gitignore` covers the gold-sign working files and the private folder.
- `7961c6f` Set T: 36 train images in `data/splits/gold_signs_set_t.json` (ids only, seed 20261115). 31 train images were excluded as duplicates of public_dev images.
- `46c095f` Tests for the tooling; `eval/gold_signs.py` added to `EVAL_QUESTION_READERS` in the leakage guard.

Full test suite: 365 passed.

**Pre-fill estimate (2026-11-15, no API call):** 81 images (45 public_dev, 36 set T), Opus 5.5 at medium, prompt `p1` (sha `42def04109fc`).
- Rough method: the system prompt at 2.04 bytes per token (measured on the parser prompt), about 10,970 tokens; images at width × height / 750 after resizing.
- Expected: **$2.85** sequential with caching, at 1,500 output tokens per image. $5.28 if outputs are twice that. $6.18 with no cache hits. Worst case (every call writes the whole prompt and uses all 8,000 output tokens): $17.65.
- Output is most of the cost (121,500 tokens, about $2.43).
- Superseded by the stage-1 measurement below.

- `10c6730` Set T excludes train images that share a duplicate group with **any** public test image (6 of the 36 shared one with a public_holdout image). Ids come from `public_split.json` only. `select` re-run with the same seed and n=36: 57 train images excluded (was 31), pool 247. 23 of the 36 images changed, since the smaller pool reshuffles the round-robin. A test checks that no set-T image shares a group with any public image.
- `047a7f7` `prefill` logs `http_error` (cost 0, status, request id, error text) when `count_tokens` or `create` fails, then re-raises.

Full test suite: 369 passed.

**Pre-fill stage 1 (2026-11-15, owner-approved, `--max-spend 0.5`, run by the owner):** the spend guard stopped it before image 9 (public_test_3_10), as intended (spent $0.2946; that call's worst case was $0.21).
- 8 images drafted, all public_dev. Status: 6 ok, 2 invalid, 0 bad_json, 0 truncated, 0 refused.
  - public_test_2_1: `UNKNOWN` on a sign marked readable.
  - public_test_3_1: `R.412`, a stem of eight separate rows, where the guide asks for the variant.

  Invalid drafts still go to the sheet; the reviewer fixes them.
- **Cost: $0.2946.** The first call wrote the cache ($0.077); the other seven averaged $0.031.
- **Output tokens:** mean 1,312, max 3,245 (public_test_2_11, 13 signs), min 553.
- **Cache:** the system prompt is 9,690 tokens (the rough estimate said 10,970). Calls 2–8 read it from the cache: 93% of their prompt tokens. 82% over all 8 calls, counting the first call's write.
- **Image and user tokens per call:** 198–1,526.
- **Projection for the other 73 images:** about $2.3 at $0.031 per image, about $2.9 if outputs run 25% longer. Add about $0.05 if the cache has expired and is written again. Stage 1 plus stage 2 comes to about $2.6–3.2, against the $2.85 estimate.

- `a3e2da2` Pre-fill drafter: Haiku 5.5 for the remaining 73 images (the owner's D2 change). `prefill --model` (default Opus), recorded per draft; prompt version p2 = p1's text drafted by Haiku. `import` records each label's `draft_model`. `estimate` now prices each call on its own: summing first priced 73 Haiku calls as one 747K-token request at the long-prompt rate ($0.31 instead of $0.067).

Full test suite: 373 passed.

**Pre-fill stage 2, Haiku 5.5 (2026-11-15, owner-approved, `--max-spend 0.25`, run by the owner, run id `1d3b02b2b076`):** all 73 remaining images drafted (37 public_dev, 36 set T); the 8 Opus drafts were not redone.
- **Cost: $0.0599** (estimate $0.067).
- **Output tokens:** mean 1,307, median 1,106, max 4,089, min 179.
- **Cache:** one cache write (9,690 tokens, call 1). Calls 2–73 read 94.6% of their prompt tokens from the cache; 93.3% over all 73.
- **Status:** 42 ok, **31 invalid (42.5%)**, 0 bad_json, 0 truncated, 0 refused. That is above the owner's 30% stop line, so `sheet` was not run.
- **Why the 31 are invalid.** An image can have several causes; the count in brackets is images with that cause alone.
  - 13 (8): an extra field on a sign, mostly a per-sign `notes` (also `notes_text`, `notes_on_sign`, `text`);
  - 8 (3): a vehicle written as a bare string (`"car"`) instead of `{class: car}`;
  - 5 (3): a bad enum value (`days: [even]` as a list, `op: lte`, colour `dark`);
  - 5 (4): a made-up code (`local`, `LOCAL`, `P.UNKNOWN`) for local or unread signs;
  - 5 (2): a family code in the wrong form (`W.201(a,b)`, `R.301(a,...,h)`, `I.444 (… family)`);
  - 4 (1): `UNKNOWN` on a sign marked readable;
  - 2 (1): a real code missing from the catalog (P.116, P.118).
- Most causes are format slips, which the reviewer would fix by hand. P.116 and P.118 are a catalog gap (P.118 / P.119 size limits are already a phase 1.7 open item).
- **Pre-fill total so far: $0.3545** (stage 1 Opus $0.2946 + stage 2 Haiku $0.0599). `logs/api_calls.jsonl`: 663 lines.

- `48a594c` `sheet` cleans up the format of each draft as it writes the label YAML, and flags what it doesn't fix. The owner chose this instead of a re-draft or a p3.
  - Two lossless fixes: a vehicle given as a bare `VehicleClass` string becomes `{class: ...}`; a sign's extra text fields (`notes`, `notes_text`, `notes_on_sign`, `text`, ...) move verbatim into a YAML comment above that sign.
  - Everything else stays as drafted, with a `# needs fix: ...` comment above the sign and a red line in `sheet.html`.
  - `drafts.jsonl` is only read (same sha256 before and after); existing YAMLs are never overwritten.

Full test suite: 385 passed.

**Review sheet (2026-11-15, no API call):** 81 label files written: `data/annotations/gold_signs_v1/work/labels/public_dev/` (45) and `.../labels/train/` (36). Page: `data/annotations/gold_signs_v1/work/sheet.html`.
- **33 drafts were invalid** (31 Haiku, 2 Opus). After the clean-up, **11 are valid** (all Haiku) and **22 still need a fix** (20 Haiku, 2 Opus). No draft became invalid. 53 draft text fields were moved into comments.
- **Still to fix, by reason.** "Images" counts label files with that reason; a file can have several.

  | images | flags | reason |
  |---|---|---|
  | 6 | 6 | family code written wrongly, or a stem of several rows (`W.201(a,b)`, `R.301(a,…,h)`, `I.444 (…)`, `R.412`) |
  | 5 | 5 | `UNKNOWN` on a sign marked readable |
  | 5 | 5 | made-up code (`local`, `LOCAL`, `P.UNKNOWN`) |
  | 2 | 2 | `days` as a list |
  | 2 | 2 | code missing from the catalog (P.116, P.118) |
  | 2 | 3 | colour `dark` (1 image); `op: lte` (1 image) |
  | 1 | 3 | extra non-text plate fields (`conditions`, `value`, `unit` on a plate; public_test_5_1) |
  | 1 | 5 | vehicles that aren't class names, left as is (public_test_8_9) |
  | 1 | 1 | condition groups together with a vehicle/time plate (public_test_6_5) |
  | 1 | 1 | plate `actions` not a list (public_test_6_8) |

- The last two were hidden behind other errors before the clean-up, so they are new in the list but not new errors.

- `90b3949` Guide: partial readings go in the label's top-level `notes`, naming the sign by its rank; the family-code example now uses the real row code (`W.207(a,b,c,d,e,f,g,h,i,k,l)`) or its stem. Pre-fill prompt hash 42def04109fc → d8fecd3b2cce.
- `9f3f96f` `import` never writes an empty or shrinking gold file without `--replace`, writes atomically, and prints done / todo / rejected counts first. The same rules apply to the private path.
- `750011a` Catalog: **P.118** "Hạn chế chiều ngang xe" (B.18), a rule row on the P.117 pattern: `width_m` gt the value, priority vehicles included. **`reviewed_by: none`, waiting for the owner's review of the row.**
- `6945a25` Catalog: **P.119** "Hạn chế chiều dài xe" (B.19), the same pattern: `length_m` gt the value. B.19 a) covers priority vehicles too, quoted in the YAML, and B.19 b)'s "đối với xe đơn chiếc" is noted. **`reviewed_by: none`, waiting for the owner's review.**
  - P.116 (axle load) is not added, and there is no axle attribute. Its only draft (public_test_8_3, Haiku, "9 m") is likely a misread P.119; the owner will check the image.
- **Prompt hashes moved with the catalog.** Both prompts below are built with the catalog in them.

  | prompt | before | after P.118 | after P.119 |
  |---|---|---|---|
  | parser v6, built system prompt | 93ba1cf3ada9 | f5ed53804834 | e08989d2b637 |
  | gold-sign pre-fill | d8fecd3b2cce | 34008e80ae62 | e9aae8315b6d |

  - The phase-2 parser gate (Sonnet 5.5, v6) was measured on 93ba1cf3ada9 and was not re-run; the change is two catalog lines.
  - Existing pre-fill drafts keep their recorded `prompt_sha` and are not re-run.

Full test suite: 394 passed. Prolog loads.

**Review sheet after P.118 / P.119 (no API call):** `sheet` re-run; all 81 label YAMLs kept unchanged (none overwritten), and `sheet.html` recomputed. Still **22 files need a fix**.
- The P.118 flag cleared. Its only file, train_8_32, still needs a fix for `UNKNOWN` on a readable sign. Its YAML keeps the old `# needs fix` comment for P.118, since `sheet` never rewrites an existing file; the flag is gone from `sheet.html`.
- What remains, by reason (files, flags, then the files):
  - 6 / 6: a family code written wrongly, or a stem of several rows: public_test_3_1, 4_6, 5_6, 6_11, 7_12, train_6_39;
  - 5 / 5: `UNKNOWN` on a readable sign: public_test_2_1, 3_8, 5_6, train_6_7, train_8_32;
  - 5 / 5: made-up code (`local`, `LOCAL`, `P.UNKNOWN`): public_test_4_4, 7_10, 8_9, train_2_10, train_5_29;
  - 2 / 2: `days` as a list: public_test_7_12, train_6_8;
  - 1 / 1 each: `op: lte` (public_test_3_6); condition groups with a vehicle/time plate (public_test_6_5); plate `actions` not a list (public_test_6_8); P.116 (public_test_8_3);
  - 1 / 2: colour `dark` (train_8_8);
  - 1 / 3: extra non-text plate fields (public_test_5_1);
  - 1 / 5: vehicles that aren't class names (public_test_8_9).

**Owner's hand review (2026-11-15): 66 of 81 label files done, 15 left as todo.** The 15 were blocked by readable QCVN 41 codes missing from the catalog and by standalone local notices.
- `9b5b9fa` Catalog: **R.403a** "Đường dành cho xe ô tô" and **R.403b** "Đường dành cho xe ô tô, xe máy" are bans on entry for every vehicle except the classes shown (D.11 l). **R.404a** ends R.403a (D.12). **R.307** ends R.306 (D.7). All `reviewed_by: none`.
  - law_db has no article D.11: its text sits at the end of D.10, so the R.403 rows cite D.10.
  - Not added: **R.302(a,b,c), R.303, R.411, R.420**. They have no effect the engine can model, and `test_catalog` allows meaning-only rows only for warning and information signs (a mandatory row with no effect would turn "unknown" into a confident "yes"). They need an owner decision.
  - Prompt hashes: parser v6 e08989d2b637 → 785ef169881f; pre-fill e9aae8315b6d → 348b93a1f952.
- `b789ad9` Gold signs: the **`local_notice`** marker. A readable standalone local notice is `code: UNKNOWN`, `readable: true`, `local_notice: "<text>"`. Plan D7 (owner-approved, before any result): such signs are scored like `readable: false` and reported apart. Pre-fill prompt hash 348b93a1f952 → cc0bf58890b4.
- **The 15 files now** (checked read-only; no label YAML was edited):
  - 5 have no errors left and need only `status: done`: public_test_3_1, public_test_6_8, train_3_25, train_6_29, train_7_23;
  - 3 need the owner to switch their notice to `local_notice`: public_test_2_1, public_test_7_10, train_6_7;
  - 7 wait on R.302a / R.303 / R.411 / R.420: public_test_5_6, 7_4, 7_12, 8_9, train_1_6, train_6_38 (which also has a notice), train_7_18.
- **Uncommitted, the owner's:** `reviewed_by: human` on P.118 and P.119, and a `tests/test_meaning_rows.py` edit that still expects 39 human-reviewed rows (there are 41 with those two). With the edit, that test fails; every committed state passes (407 tests).

- `87f894c` Catalog: **R.302(a,b,c), R.303, R.411, R.420** as `effect_unmodelled` rows (D.2, D.3, D.13, D.17). These are mandatory signs whose effects can't be modelled yet.
  - `vqa/kb.py` and `vqa/reasoning/engine.py`: the engine treats them like unreadable signs of their visible kind for closed-world claims, and lists them in `uncertain_signs` with a note. Identity and meaning claims work.
  - All `reviewed_by: none`. Tests cover the flag on each row.
  - Prompt hashes: parser v6 785ef169881f → 2d0ec50e3611; pre-fill cc0bf58890b4 → ee8106d9539c.
- **Label edits (2026-11-15, at the owner's request; the label YAMLs are gitignored, so there is no commit):**
  - the four freestanding notices now use `local_notice` with their text verbatim: public_test_2_1, public_test_7_10, train_6_7, train_6_38. public_test_2_1's plate reading (car and motorcycle, "cấm đỗ") is now only in the notice text;
  - every P.102 is `border: red, background: red`, as the catalog row has it. 8 signs changed (border none → red): public_test_5_6 s14–s18, public_test_7_12 s1, train_1_6 s14, train_8_32 s1 (a done file). The owner checks them against the images: labels record what is seen, not the catalog, so label YAMLs are not edited by the assistant again. A copy of the labels from before both edits is in `data/annotations/gold_signs_v1/work/backup_pre_p102/` (gitignored);
  - the owner's notes ("REVIEW BLOCKED …") were left as written.
- **All 81 label files now validate:** 66 `done`, and 15 `todo` with no errors left. The owner sets those 15 to `done`, then `import`.

- **Gold signs v1 (`9387764`, updated `c6fb83f`, 2026-11-15): 81 images imported, 0 rejected.** The owner reviewed every label by hand. The assistant set the last 15 files to `status: done` at the owner's request (status line only), and the owner re-checked them.

  | split | images | Opus-drafted | Haiku-drafted | readable signs | readable:false | local_notice |
  |---|---|---|---|---|---|---|
  | public_dev | 45 | 8 | 37 | 143 | 31 | 2 |
  | set T | 36 | 0 | 36 | 120 | 14 | 2 |

  14 vehicles are labelled, on 3 violation images.
- **Anchoring, per drafter.** A sign counts as kept if the final label equals a draft sign exactly, after the sheet clean-up.

  | drafter | images | draft signs | final signs | kept unchanged | changed or added |
  |---|---|---|---|---|---|
  | Opus 5.5 | 8 | 35 | 39 | 22 (56%) | 17 |
  | Haiku 5.5 | 73 | 256 | 273 | 71 (26%) | 202 |

  - `b79e0bc`: `import` now counts anchoring sign by sign against the cleaned-up draft, including drafts invalid as a whole. Each row stores `draft_signs`, `draft_signs_invalid`, `final_signs`, `kept` and `changed_or_added`. The table above is the stored figure: invalid draft signs were 2 for Opus and 24 for Haiku. The first import's field had counted 0 kept for the 33 invalid drafts (totals 19 and 53).
  - `c6fb83f`: re-imported the same 81 ids. The owner re-checked the 15 files the assistant set to done and cleared every "REVIEW BLOCKED" note; none remains in the gold file. No sign labels changed.
  - Low "kept" figures mean the owner changed most drafted signs, so the anchoring towards the drafters is weak. Exact equality also counts small edits (a side or a rank) as changes.
- **D10 visual-review list (55 rows):** the rows in the set-T gold, `tests/fixtures/train_*.json` and train question text.
  - **The list:** P.102, P.103a, P.103c, P.106a, P.106b, P.107, P.107a, P.110a, P.111a, P.111b, P.111d, P.112, P.115, P.117, P.123b, P.124c, P.125, P.130, P.131a, P.131b, P.131c, P.127, P.127b, P.127c, R.306, R.403a, R.307, R.404a, R.302(a,b,c), R.303, R.411, R.420, R.412f, R.415a, R.415b, W.201b, W.203(a,b,c), W.205(a,b,c,d,e), W.207(a,b,c,d,e,f,g,h,i,k,l), W.210, W.224, W.227, W.244, W.245a, I.407(a,b,c), I.408, I.409, I.414(a,b,c,d), I.415, I.423(a,b), IE.451b, IE.452, IE.464, IE.465, IE.466.
  - None of the 55 is `visual_reviewed_by: human` yet.
  - **Rows only in the public_dev gold (21; record-only under D10, not on the list):** P.104, P.105, P.119, P.124b, P.126, P.128, R.403b, R.301b, R.412d, W.206, W.221b, W.239b, W.240, W.245b, I.417(a,b,c), I.419a, I.434a, I.439, I.441(a,b,c), IE.467, IE.473.

- `acdeb47` `tools/draft_catalog_rows.py`: a `VISUAL_REVIEWED` set writes `visual_reviewed_by: human` (over `VISUAL_OVERRIDES`' `assistant`). With an empty set, regenerating is byte-identical.
- **D10 visual check (owner, 2026-11-15): all 55 rows `visual_reviewed_by: human`** (51 ok, 4 fixed, 0 skipped), applied exactly as the owner's list in `data/annotations/visual_review/notes.txt` (gitignored).
  - **35 rule rows** in `kb/sign_catalog.yaml`. One fix: **P.102 `border: none`** (background stays red). This settles the P.102 convention for the catalog. The 8 P.102 label signs the assistant had set to `border: red` were not changed back: labels record what is seen, and are the owner's to check.
  - **20 meaning rows** through `VISUAL_REVIEWED` and regenerated. Three fixes, as `VISUAL_OVERRIDES`: **I.415 `shape: other`**, **IE.451b `background: blue`**, **IE.464 `shape: other`**.
  - `test_review_provenance` now pins 55 human visual reviews (35 rule, 20 meaning) and the four fixed values. The 5 `assistant` rows are unchanged: W.242(a,b), W.243(a,b,c), IE.451a, IE.471, IE.473. None of them is on the D10 list.
  - **Prompt hashes:** the parser's built prompt is unchanged at 2d0ec50e3611, since its catalog table has no visuals. The gold pre-fill prompt goes from ee8106d9539c to 73022496646a; existing drafts keep their recorded hash. `prompts/scene/v1` doesn't exist yet and will be built on the reviewed catalog.

- `f9998a1` Gold: all 12 P.102 signs set to `border: none`. This was the owner's convention decision and the one label edit the owner authorized; no other label field changed. The recomputed anchoring moved on 3 images whose drafts said red: public_test_7_4, 7_12 and 8_2, 4 kept signs fewer in all, all Haiku-drafted. Opus stays at 22 of 39 kept; Haiku goes from 71 to 67 of 273.
- **Phase 3 item 3, first chunk** (no API calls):
  - `03cf04b` `vqa/perception/image.py`: EXIF orientation, RGB, native size, scale factor, sha256 of the original bytes. Pillow is now a main dependency.
  - `354138c` `json_reply` accepts image and text content blocks; the parser's string turn is unchanged.
  - `3282a94` `vqa/perception/wire.py`: the reply format to `SceneGraph`, in strict and final modes.
  - `d2b3ccd` `vqa/perception/cache.py`: the key is image sha256 + model + effort + prompt version (D5), and records hold model outputs only. `cache/scenes/` is gitignored, and CLAUDE.md is updated.
  - `8d10df4` Leakage guard: the phase-3 strings, and checks on the cache key and record fields.

- **Phase 3 item 3, second chunk** (no API calls):
  - `b86effc` `prompts/scene/v1` (spec, config, one train example: train_1_3) and `vqa/perception/prompt.py`. The prompt id is `scene/v1@d6be305ababc`; its hash covers the catalog. train_2_26 was left out of the examples: it is the same street as public_test_8_9, which the duplicate check missed.
  - `d87b65d` `perceive()`: plain JSON, one retry that sends only the error (the rejected reply is not echoed), refusal / max_tokens without retry, spend guard, scene cache.
  - `bcc636c` Verification (plan item 4) and the low-confidence re-run; `vqa/perception/matching.py` is shared with the eval.
  - `1c6dc57` `eval/perception_eval.py`: `GATE` (perception_gate_v1, pinned), matching, image-level bootstrap in `eval/report.py`, `--set T|public_dev` (a public_dev run warns that it is a recorded checkpoint).
  - Full test suite: 529 passed.
- **Estimates (2026-11-15, no API call; Haiku 5.5 at medium, scene/v1):** about 10,870 system tokens and 1,300 output tokens per image.
  - set T, 1 run (36 images): **$0.031** with no re-runs to **$0.060** if every image is re-run. Worst case $0.40 ($0.0056 per call).
  - public_dev, 3 runs (45 images): **$0.11 to $0.22**. Worst case $1.50.
  - Waiting for the owner's yes on the first paid run: Haiku, set T.

**First paid perception run (2026-11-15): Haiku 5.5, medium, `scene/v1@d6be305ababc`, set T. These are development figures, not the gate.** Run `c11b768af950`, run by the owner with `--max-spend 0.5`. The spend guard didn't stop it.

| set T, development | images | sign recall (95% CI) | code F1, catalog row (95% CI) | code F1, strict |
|---|---|---|---|---|
| all images | 36 | 86.7% (77.8–96.7%) | 60.8% (51.3–71.0%) | 59.9% |
| non-duplicates (no public or private copy) | 26 | 82.2% (72.4–94.4%) | 59.8% (49.4–72.6%) | 59.8% |

- **Counts:** 120 scored gold signs (14 readable:false and 2 local notices excluded; 1 of the 2 notices was found) and 117 predictions. 104 gold signs were found, 72 with the right code.
- **Cost:** $0.0528 in all, $0.0015 per image, over 61 calls (40 scene calls including 4 retries, plus 21 re-runs). That is within the $0.031–0.060 estimate.
  - Output tokens: mean 1,376, median 1,373, max 3,704.
  - One cache write; 92.6% of prompt tokens were read from the cache.
- **Status:** 36 ok, 4 retried, 0 bad_json, 0 refused, 0 truncated.
  - Retry causes: 3 replies put a `box` on a plate; 1 wrote `I.451b` for IE.451b.
- **Re-runs:** 21 of 36 images (58%). Of the signs paired by re-runs, 68 agreed and 20 got an alternative reading; 6 were seen in the re-run only and 3 in the first reading only.
- **Verification issues:** 11 id renumberings, 10 look mismatches, 1 lane-row renumbering, 1 missing value.
  - Of the look mismatches, 9 lowered a sign (human-reviewed rows) and 1 was recorded only.
  - The lowerings include IE.451b (seen green, catalog now blue) and IE.464 (seen rectangle, catalog now other). Both are D10 fixes that disagree with the gold labels.
- **Accuracy:** value 80% (12 of 15); shape 100%; background 100%; border 81.7%.
  - Border: 14 of the 19 mismatches are blue boards that the gold labels `border: white` and the model calls `none` (as does the catalog). This is a convention question, not a misread.
- **Errors (set T only), 16 missed gold signs and 32 wrong codes:**
  - **UNKNOWN for a readable sign (10):** train_1_6 I.409, train_2_8 W.203c, train_2_41 W.207, train_3_25 R.404a, train_6_29 R.403a, train_6_39 W.205 and W.245a, train_6_41 P.130, train_7_46 P.103a, train_8_8 P.125.
  - **Look-alike pictograms (10 wrong, 1 missed):** P.131a→P.130 (train_1_6, 7_37); P.123b→P.123a (1_6); P.111b→P.131a / P.104 / P.106a (2_11, 3_25, 6_7); P.125→P.103a (7_37); P.103c→P.124b (7_46); P.117→P.118 and P.124c→P.124a (8_32); R.307 read as P.127 (7_23, unmatched).
  - **Lane boards (4):** P.127c↔P.127b (2_11, 6_41 ×2); R.415a→I.417c (1_6).
  - **Guide and information boards (8 wrong, 4 missed):**
    - I.444 for I.414 (1_6, 6_38), W.244 (6_38) and R.403a (6_38);
    - IE.466 read as IE.454, IE.464 or I.414 (1_8, 1_19, 6_40); IE.452→I.444 (6_40);
    - four I.407c arrow boards read as I.415 with `shape: other`, copying the catalog's new look, so they can't be paired (7_25).
  - **Small, distant or dense (11 missed):** train_1_6 (collage: R.411, R.420, P.102, R.302a), train_6_38 (R.403a, I.414 ×2, P.130, R.302a), train_3_25 (I.415, R.404a).
  - **Catalog gap:** none (no uncatalogued code after the retry).
  - **Matching artefact:** train_7_23's two P.127 values (100, 80) show as swapped. The model ranked the green board first, so its ranks are off by one, and the pinned matching puts rank above side. Both values were read correctly.

**Owner decisions after the first set-T run (2026-11-15):**
- `677a87b` **Border convention:** a thin white rim on a blue sign is `border: none`, as in the catalog. The guide says so. 69 blue-background gold signs in 23 images went from white to none (the owner authorized this label edit). The gold diff is exactly those 69 values plus recomputed anchoring on 7 images.
- `6258779` **Look check (D10 refinement):** on a human-reviewed row, only a shape or background mismatch lowers a sign; a border-only mismatch is recorded. Plan updated, with tests.
- `b722247` **Matching:** same side now comes before closest rank. The gate is now `perception_gate_v2`, changed before any public_dev result; v1 is in `1c6dc57`. Plan updated, pin test updated.
- **Re-scoring run c11b768af950 (no new calls), set T, development:**

  | | gold | recall | code F1 | strict F1 | value acc. | border acc. |
  |---|---|---|---|---|---|---|
  | v1 matching | as at the run | 86.7% | 60.8% | 59.9% | 80.0% | 81.7% |
  | v1 matching | border convention applied | 86.7% | 60.8% | 59.9% | 80.0% | 96.2% |
  | **v2 matching** | border convention applied | **86.7%** | **60.8%** | 59.9% | **93.3%** | 96.2% |

  Non-duplicates under v2: recall 82.2%, code F1 59.8%, value accuracy 100%. The CIs are unchanged.
- **IE.451b, IE.464:** the owner re-checks them. I.415 stays.
- **Possible gold errors on set T (reported, not changed):**
  - **train_7_23 s4: gold R.307 (40).** The sign is a white disc with a thin blue-grey ring, outlined digits and a hatched diagonal. That matches the DP.134 "Hết tốc độ tối đa cho phép" figure (B.34, image174); R.307's figure (D.7, image308) is a blue disc with a white number and a red slash. The model read P.127 40, which is also wrong.
  - **train_7_46 s2: gold P.103a, readable: true.** It is a small distant sign; the model said UNKNOWN. Check whether it is readable.
  - **train_8_32: gold P.124c (bottom right, cut off by the frame).** The model read P.124a. The image shows too little to decide.
  - **train_7_25 s3–s6: gold I.407c ×4.** The model read I.415 for all four. These are blue rectangular arrow boards on barriers; I.407 is "Đường một chiều" and I.415 "Mũi tên chỉ hướng đi". It's the owner's reading to confirm.
  - Checked against the images and **found right**: P.117 (train_8_32), P.127b (6_41), P.127c (2_11), P.131a (7_37), P.111b (2_11), P.103c (7_46), and P.106b 2.5 t (7_37, the number is faint).
- `19bd70c` **Prompt v2** (`scene/v2@26be620fb386`): proposed changes 1–6. The pictogram notes quote catalog names only (tested). v1 is pinned by sha256. `perception_eval.py` takes `--version`.
- **Estimates for set T, 1 run, v2 (no API call), 12,148 system tokens:**
  - **Haiku 5.5: $0.031** with no re-runs to **$0.061** if every image is re-run. Worst case $0.41. v1's real cost was $0.053, at a 58% re-run rate.
  - **Sonnet 5.5: $0.58** with no re-runs to **$1.14** if every image is re-run, about $2.10 if outputs double. Worst case $8.23 ($0.114 per call); the spend guard caps it at the limit.
- Full test suite: 535 passed.

**Set-T runs with prompt v2 (2026-11-15), run by the owner. Set T, development, gate v2 matching, gold after `ddb044b` (train_7_23 s4 = DP.134):**

| set T, development | Haiku v1 (re-scored) | Haiku v2 | Sonnet v2 |
|---|---|---|---|
| run | c11b768af950 | aa8cc8952831 | f200a07b933e |
| recall, all 36 (95% CI) | 86.7% (77.8–96.7) | 89.2% (81.9–97.7) | **92.5%** (85.9–100) |
| code F1 row-level, all (CI) | 60.8% (51.3–71.0) | 64.7% (57.5–72.5) | **70.4%** (61.9–79.4) |
| code F1 strict, all | 59.9% | 64.7% | 69.5% |
| recall, 26 non-duplicates (CI) | 82.2% (72.4–94.4) | 87.8% (80.2–98.2) | 90.0% (82.8–100) |
| code F1, non-duplicates (CI) | 59.8% (49.4–72.6) | 64.0% (55.9–73.5) | 68.6% (59.3–79.0) |
| value accuracy, all / non-duplicates | 93.3% / 100% | 93.3% / 100% | 68.8% / 58.3% (artefacts, see below) |
| re-runs / retries | 21/36 · 4 | 19/36 · 0 | 17/36 · 1 |
| cost, total (per image) | $0.0528 ($0.0015) | $0.0453 ($0.0013) | $0.3242 ($0.0090) |
| output tokens, mean / max | 1,376 / 3,704 | 1,267 / 3,139 | 318 / 749 |

- **Haiku v1 → v2,** per gold sign: 9 fixed, 3 broken, 4 wrong → missed, 4 missed → wrong.
  - **Fixed:** the plate-box retries (0 now); I.414 (×2, plus 2 found that were missed); P.127c (2_11); P.131a (7_37); R.403a and P.130 (no longer UNKNOWN); R.411 found.
  - **Remain:** the vehicle-ban pictograms, P.117/P.118, P.124c, P.123b, IE.466, the dense-scene misses.
  - **v2 side effects:**
    - "always guess" turned 6 false UNKNOWNs into wrong codes;
    - the train_6_41 P.127b boards were split into P.127 and R.306 discs;
    - the I.407c boards are now found but read as I.415;
    - three new errors: IE.465→IE.464, IE.451b→IE.452, P.110a→P.104.
- **Sonnet v2 vs Haiku v2,** per gold sign: 11 that Haiku gets wrong or misses are right for Sonnet; 7 that Haiku gets right are wrong for Sonnet; 30 are wrong or missed by both.
  - **Sonnet only right:** IE.465, P.131a (1_6), R.415a, W.203c (as W.203a, row-level), P.110a, IE.452, P.127b (6_41 r1), IE.451b, DP.134, P.103c, P.117.
  - **Sonnet only wrong:** IE.464→IE.464b, P.127c→R.415a (2_11), P.127c→P.127b (3_25), P.111a→P.104, R.403a→R.412b, I.414→I.444 (6_38), P.106b→P.107.
  - **Both wrong:**
    - P.111b ×3 and P.125 ×2 (pictogram confusion);
    - P.123b, P.124c and P.103a (7_46);
    - the W.207 / W.205 / W.245a triangles;
    - IE.466 ×3, I.409, W.244, R.404a;
    - I.407c ×4 (both models say I.415).
  - **Both missed:** the 9 dense-scene signs (train_1_6 ×3, train_6_38 ×4, train_3_25 ×2).
- **Sonnet's value accuracy is a set of artefacts, all on train_7_23:**
  - Sonnet gives every gantry sign `side: overhead`, so side can't break ties and the pairing falls back to shifted ranks.
  - `merge_rerun` kept two entries for the "40" sign: the first reading said DP.134 and the re-run P.127 40, and their visual categories differ, so they weren't paired.
  - Verification dropped DP.134's 40 ("the row takes no value"), although an end-of-limit sign shows the limit it ends.

  Sonnet read every number correctly.
- **Cost:** Sonnet cost $0.009 per image, below the $0.58–1.14 estimate, because its outputs are short. That is about 7× Haiku's cost per image.

**Artefact fixes and re-verification (2026-11-15, no API calls):**
- `6771e52` Verification: end-of-limit signs (rows with `ends`) keep the limit they end; it is checked as a speed when they end a speed limit.
- `31a32e2` Re-run pairing relates same-family readings and end/limit pairs (DP.134 ↔ P.127, R.307 ↔ R.306). The gate's matching never relates.
- `935df91` Gantry sides: matching already falls back to rank for all-`overhead` predictions, so an "overhead matches any side" rule would change nothing. The fix is real sides from the model, proposed for v3. A test pins both halves.
- `1745a9e` `rescore --reverify` rebuilds scenes from the cached replies with the current code and makes no calls. A reported, ungated metric is added: code F1 on rule-bearing signs (68 of the 120 set-T gold signs).
- **Set T, development, gate v2, before → after re-verification:**

  | | recall (CI) | code F1 (CI) | strict | rule-bearing F1 | value acc. |
  |---|---|---|---|---|---|
  | Haiku v1 | 86.7% (77.8–96.7) | 60.8% (51.3–71.0) | 59.9% | 68.8% | 93.3% (unchanged) |
  | Haiku v2 | 89.2% (81.9–97.7) | 64.7% (57.5–72.5) | 64.7% | 68.1% | 93.3% (unchanged) |
  | Sonnet v2, before | 92.5% (85.9–100) | 70.4% (61.9–79.4) | 69.5% | 72.7% | 68.8% |
  | **Sonnet v2, after** | 92.5% (85.9–100) | **70.7%** (62.1–80.0) | 69.8% | **73.3%** | **75.0%** |

  - Non-duplicates, after: Haiku v1 82.2% / 59.8%, Haiku v2 87.8% / 64.0%, Sonnet v2 90.0% / 69.0% (recall / code F1). Rule-bearing F1 on non-duplicates: 72.5%, 70.8%, 73.7%.
  - Only Sonnet changes: one duplicate sign on train_7_23 is gone (113 → 112 predictions), and the DP.134 value now counts. Its remaining value misses come from the all-`overhead` gantry sides.
  - On rule-bearing signs, Haiku v2 is no better than v1 (68.1% vs 68.8%). Its gains were on guide boards.
- **Proposal, waiting for the owner:** `docs/plans/phase-3-proposal-v3-pictograms.md`. It covers scene prompt v3 with reference pictograms for 41 confused rows (43 law_db figures, about 2,500 cached image tokens). It needs a dataset-rule exception: local gitignored copies made by a `tools/` builder, pinned by a committed sha256 manifest. It also proposes three text changes (gantry sides, lane boards as one sign, a softer "always guess").

**Prompt v3 with reference pictograms (2026-11-15):**
- `ccb2648` CLAUDE.md: the dataset-rule exception for law_db figures (local gitignored copies, committed sha256 manifest).
- `a792fdc` `scene/v3@69d91ed6a300`: 53 rows over 51 figures (≤ 320 px), about 3,069 cached tokens.
  - The rows are the 41 confused rows, the owner's 7, and 5 more so no observed confusion pair is half-pictured: I.401, IE.451b, IE.474, P.115, W.246.
  - Figures chosen by hand: IE.452 → image026, R.415a → its own figure (W.244's "W.224" caption is a law_db typo).
  - Plus v3's three text changes. v1 and v2 prompt ids are unchanged (pinned).
- **Haiku v3 on set T (run f16a09d95189, $0.051, $0.0014 per image), development, gate v2:**

  | | Haiku v2 | **Haiku v3** | Sonnet v2 (after fixes) |
  |---|---|---|---|
  | recall, all (95% CI) | 89.2% (81.9–97.7) | 81.7% (72.3–92.3) | 92.5% (85.9–100) |
  | code F1 row-level (CI) | 64.7% (57.5–72.5) | **73.5%** (64.7–82.5) | 70.7% (62.1–80.0) |
  | code F1 strict | 64.7% | 71.7% | 69.8% |
  | rule-bearing F1 | 68.1% | **75.8%** | 73.3% |
  | non-duplicates: recall / code F1 | 87.8% / 64.0% | 77.8% / **74.4%** | 90.0% / 69.0% |
  | value accuracy | 93.3% | 100% | 75.0% |
  | predictions (gold 120) | 121 | 103 | 112 |
  | re-runs / retries | 19/36 · 0 | 18/36 · 1 | 17/36 · 1 |

  - **Pictograms fixed 10 signs, all pictured rows:** IE.465, IE.466 ×2, IE.452, IE.451b, P.131a (1_6), W.203c, P.110a, P.103c, P.124c.
  - **9 signs that were wrong are now missing:** I.407c ×4, W.205, W.245a, I.409, W.244, P.103a. The softer guessing rule made Haiku leave unsure signs out instead of writing UNKNOWN.
  - **6 signs that were right are now wrong or missed:**
    - R.411 and I.414 on the train_1_6 collage are missed;
    - P.127 and R.306 on 6_40 (separate discs) are missed, probably swallowed by the lane-board rule;
    - P.131a became P.130 on 7_37; W.201b became W.201a.
  - **Introduced by a pictogram:** the train_6_41 green P.127b boards are read as IE.452 (3 IE.452 predictions against 1 gold).
  - **Still wrong:** P.111b ×3, P.125 ×2, P.117→P.118, P.123b→P.123a, and the dense-scene misses.
  - **Sonnet v3** was held: its uncalibrated estimate ($0.60–1.17) was over the owner's $0.60 ceiling.

**Prompt v4, the last set-T tuning round (2026-11-15).** `4cc8717`, `scene/v4@153536ec5975`: v3 plus "list every sign", "separate discs stay separate", and P.127b vs IE.452. Runs: Haiku `4e6780670d2f` ($0.054), Sonnet `7a4f533fc335` ($0.360). Set T, development, gate v2:

| set T, development | Haiku v3 | Haiku v4 | Sonnet v2 (after fixes) | Sonnet v4 |
|---|---|---|---|---|
| recall, all (95% CI) | 81.7% (72.3–92.3) | 83.3% (73.9–94.1) | 92.5% (85.9–100) | **90.8%** (84.6–97.9) |
| code F1 row-level (CI) | **73.5%** (64.7–82.5) | 72.3% (65.1–80.6) | 70.7% (62.1–80.0) | 69.8% (60.4–79.6) |
| code F1 strict | 71.7% | 69.6% | 69.8% | 69.0% |
| rule-bearing F1 | 75.8% | 76.2% | 73.3% | **79.0%** |
| non-duplicates: recall / code F1 | 77.8% / 74.4% | 80.0% / 70.7% | 90.0% / 69.0% | 87.8% / 69.0% |
| non-duplicates: rule-bearing F1 | 77.8% | 77.8% | 73.7% | 79.1% |
| value accuracy | 100% | 100% | 75.0% | 100% |
| predictions (gold 120) | 103 | 104 | 112 | 112 |
| re-runs / retries | 18/36 · 1 | 22/36 · 0 | 17/36 · 1 | 19/36 · 2 (1 bad_json) |
| cost per image | $0.0014 | $0.0015 | $0.0090 | $0.0100 |

- **v4 vs v3 for Haiku:** within noise.
  - **Worked:** P.127b vs IE.452 (both train_6_41 boards right; IE.452 down from 3 predictions to 1).
  - **Barely worked:** "list every sign". UNKNOWN rose from 9 to 12 and predictions from 103 to 104. The I.407c ×4, W.205 and W.245a still vanish.
  - **Didn't work:** separate discs (train_6_40's P.127 and R.306 are still missed).
  - About 6 signs flipped each way (the IE.464/465/466 boards, P.124c, P.111a). That is single-run noise.
- **Sonnet v2 → v4:** 8 signs fixed and 10 broken.
  - **Fixed:** IE.466 (1_8), P.127c ×2, W.207, I.415, R.403a (6_29), P.125 (7_37), P.124c.
  - **Broken:** P.127 and R.306 (6_40) missed; I.414 (6_38, 3_25) missed or wrong; P.117→P.118; W.201b→W.201a; the train_6_41 P.127b boards → IE.452, despite the v4 note.
  - Rule-bearing F1 rose from 73.3% to 79.0% and value accuracy from 75% to 100%. Overall code F1 stayed level, because guide boards got worse.
- **Remaining errors by cause (Haiku v4 / Sonnet v4, 39 each):**

  | cause | Haiku v4 | Sonnet v4 |
  |---|---|---|
  | dense-scene misses (train_1_6, 6_38, 3_25) | 12 | 8 |
  | other misses | 8 (I.407c ×4, W.205, W.245a, P.127 and R.306 on 6_40) | 3 (I.408, P.127 and R.306) |
  | listed as UNKNOWN | 5 | 11 (I.407c ×4, W.244, W.245a, R.403a, R.404a, R.420, P.103a, P.125) |
  | prohibitory look-alikes | 9 (P.111b ×3, P.125, P.131a, P.111a, P.117, P.123b, P.124c) | 7 (P.111b ×3, P.111a, P.106b, P.117, P.123b) |
  | guide / expressway boards | 5 | 8 |
  | warning triangles | 0 | 2 |

- **What crops (plan item 7) can and can't do:**
  - Every prediction carries a box (Haiku 111/111, Sonnet 119/119).
  - **None of the misses (Haiku 20, Sonnet 11) can be recovered by box crops.** On every image with a missed gold sign, every listed sign was paired: the missed signs were never listed.
  - Box crops could re-read the code of signs listed wrong at low confidence or as UNKNOWN: 14 for Haiku (5 UNKNOWN) and 21 for Sonnet (11 UNKNOWN).
  - **Upper bounds** if every one of those were fixed: code F1 about 85% for Haiku and 88% for Sonnet. Realistically about half get fixed, so roughly 78–80%.
  - **Recall needs a region-level pass,** not box crops: tile dense scenes, or crop whole gantries and boards, then read each part. Haiku is 8 signs short of 90% recall on set T; its 12 dense-scene misses are the pool.

**public_dev checkpoint 1 (gate v2, prompt v4), 2026-11-16.** `perception_gate_v2`, `scene/v4@153536ec5975`, 45 gate images (143 gold signs; 31 `readable: false` and 2 `local_notice` excluded), 17 non-duplicates (27 gold signs; duplicate = also in train). CIs are image bootstraps from `eval/report.py` (`bootstrap_ci`, 10,000 resamples, seed 20261115); the split uses `duplicated_images`. The CI of a mean pools each image's counts over the runs. Not tuned: no prompt or trigger change came from public_dev.

- **Runs:** Haiku `e0128c462ed3`, `2dd3a6e61573`, `932c3d2b7009`; Sonnet `f19dd5bc36f6`.
- **Sonnet has one run, not three (owner's decision, 2026-11-16).** After the first run the owner chose to report without the other two. Its verdict is "not decided (1 of 3 runs)", indicative FAIL. To pass, the two missing runs would have to average about 90% code F1, against Haiku's run-to-run spread of 6 points.

| public_dev checkpoint 1 | Haiku v4, mean of 3 | Haiku runs (e012 / 2dd3 / 932c) | Sonnet v4, 1 run |
|---|---|---|---|
| recall, all (95% CI) | **79.7%** (69.1–92.5) | 79.0% (67.9–92.4) / 79.7% (69.4–92.6) / 80.4% (69.8–93.3) | **81.8%** (69.6–96.3) |
| code F1 row-level, all (CI) | **68.1%** (59.6–78.4) | 71.0% (62.6–81.9) / 64.9% (56.7–75.3) / 68.4% (58.1–80.3) | **75.1%** (67.7–84.6) |
| code F1 strict, all | 67.9% | 71.0% / 64.9% / 67.7% | 74.3% |
| rule-bearing F1, all (reported, not gated) | 70.2% | 73.1% / 66.3% / 71.2% | 77.6% |
| value accuracy, all | 88.1% | 78.6% / 92.9% / 92.9% | 76.5% |
| recall, non-duplicates (CI) | 87.7% (75.4–100) | 92.6% (84.4–100) / 85.2% (70.3–100) / 85.2% (70.3–100) | 100% (100–100) |
| code F1, non-duplicates (CI) | 71.2% (57.5–91.8) | 74.1% (56.8–100) / 64.2% (49.1–84.2) / 75.5% (60.6–95.2) | 80.7% (70.1–94.7) |
| code F1 strict / rule-bearing, non-dup | 70.0% / 67.9% | 74.1% / 64.2% / 71.7% · 66.7% / 60.9% / 76.2% | 77.2% / 78.3% |
| predictions (gold 143) | 118 | 116 / 119 / 120 | 126 |
| re-runs · retries · errors | 22.3/45 · 2.7 · 0 | 19 · 2 · 0 / 24 · 3 · 0 / 24 · 3 · 0 | 20/45 · 1 · 0 |
| UNKNOWN codes | 12 | 8 / 13 / 15 | 18 |
| cost | $0.198 ($0.0015/image) | $0.062 / $0.068 / $0.067 | $0.403 ($0.0090/image) |
| **gate verdict** (recall ≥ 90% and F1 ≥ 85%) | **FAIL** | | **not decided (1 of 3), indicative FAIL** |

- **Anchoring (plan item 6, D2).** Results by the model that drafted the gold, mean over runs, all images. The 8 Opus images are none of the non-duplicates, so this split is confounded with image difficulty.

  | drafted by | images (gold) | Haiku v4 recall / F1 | Sonnet v4 recall / F1 |
  |---|---|---|---|
  | Haiku 5.5 (p2), "anchored (Haiku pre-fill)" | 37 (111) | 77.2% (65.6–92.4) / 63.8% (55.6–76.0) | 82.9% (68.4–98.7) / 73.0% (64.9–83.8) |
  | Opus 5.5 (p1) | 8 (32) | 88.5% (79.2–100) / 82.4% (77.1–91.8) | 78.1% (60.9–100) / 82.8% (71.6–98.0) |

  There is no sign that the Haiku pre-fill helped Haiku: it does worse on the images Haiku drafted.
- **Against set T:** public_dev is a little below set T for Haiku (recall 79.7% vs 83.3%, F1 68.1% vs 72.3%). It is lower on recall for Sonnet (81.8% vs 90.8%) and higher on F1 (75.1% vs 69.8%). The recommendation expected both models to fail on F1, and they did. It did not expect Sonnet's recall result: it put Sonnet's recall near 90% on public_dev (about a coin flip against the gate), and the run gave 81.8%.
- **Spend:** checkpoint 1 cost $0.601 (Haiku $0.198, under its $0.35 ceiling; Sonnet $0.403 for one run). Phase 3 total: $1.84.
- **public_dev per-image errors were not looked at.** They are a record only, per the handoff rules, and nothing here is drawn from them.

**The two-pass fallback on set T (plan item 7), 2026-11-16. Set T, development, in-sample.**

The triggers were chosen on set T and are measured on set T, so these gains overstate what public_dev will show.

- **Commits:** the design and its approval (`7bdd290`), the implementation (`47f0335`), and the pin and `compare` command (this commit).
- **Runs on the frozen v4 pass-1 runs:**
  - Haiku: pass 1 `4e6780670d2f`; fallback "rules" `a3d4be075b54` (paid by the owner);
  - Sonnet: pass 1 `7a4f533fc335`; fallback "rules" `01f062ee69c7` (paid by the owner);
  - replays (no API calls; `logs/api_calls.jsonl` stayed at 1,439 lines):
    - crop_always: Haiku `d1ff09db5bf4`, Sonnet `d082c4d6cb96`;
    - crop_high: Haiku `adf1e6477e5d`, Sonnet `9d43a8024287`;
    - never: Haiku `5dbc44e65299`, Sonnet `7f82d17118aa`.
  - A "rules" replay reproduced both paid runs' scenes exactly.
- **Prompts:** `scene/v4-tile@a052a9fc72f7`, `scene/v4-crop@30e2d18b84d9`. The figures come from `perception_eval.py compare`.

| set T, development, in-sample | recall | code F1 | strict F1 | rule-bearing F1 | non-dup recall / F1 | predictions (gold 120) | codes fixed (tiles + crops) | codes broken |
|---|---|---|---|---|---|---|---|---|
| **Haiku pass 1** | 83.3% | 72.3% | 69.6% | 76.2% | 80.0% / 70.7% | 104 | | |
| Haiku + rules | 88.3% | 71.8% | 69.2% | 74.2% | 87.8% / 71.3% | 114 | 3 + 3 | 3 |
| Haiku + crop_always | 89.2% | **73.5%** | 70.9% | 77.3% | 88.9% / 74.7% | 114 | 3 + 7 | 5 |
| Haiku + crop_high | 87.5% | 69.5% | 67.0% | 73.4% | 86.7% / 69.4% | 113 | 2 + 0 | 2 |
| Haiku + never | 88.3% | 71.2% | 68.7% | 76.6% | 86.7% / 69.4% | 113 | 2 + 0 | 0 |
| **Sonnet pass 1** | 90.8% | 69.8% | 69.0% | 79.0% | 87.8% / 69.0% | 112 | | |
| Sonnet + rules | 95.8% | **75.4%** | 74.6% | 81.8% | 94.4% / 75.4% | 124 | 1 + 10 | 0 |
| Sonnet + crop_always | 95.8% | **75.4%** | 74.6% | 81.8% | 94.4% / 75.4% | 124 | 2 + 10 | 1 |
| Sonnet + crop_high | 95.8% | 74.6% | 73.8% | 81.8% | 94.4% / 74.3% | 124 | 1 + 9 | 0 |
| Sonnet + never | 95.8% | 67.2% | 66.4% | 78.1% | 94.4% / 65.6% | 124 | 1 + 0 | 0 |

"Fixed" means a gold sign that pass 1 missed or misread and the fallback got right. "Broken" means one pass 1 had right and the fallback got wrong.

**Triggers:**

| | images tiled | tile signs added | crops | crops with no reply | crops that changed a code |
|---|---|---|---|---|---|
| Haiku | 6 / 36 | 12 | 52 | 0 | rules 16 (30.8%), crop_always 24 (46.2%), crop_high 6 (11.5%) |
| Sonnet | 7 / 36 | 15 | 56 | **26 (46%)** | rules 16 (28.6%), crop_always 18 (32.1%), crop_high 12 (21.4%) |

**Spend against the estimate:**
- Haiku: $0.0446 ($0.0238 for 24 tiles, $0.0208 for 52 crops), against $0.041–0.050.
- Sonnet: $0.433 ($0.242 for 28 tiles, $0.191 for 56 crops), against $0.42–0.52.
- Per call, Sonnet tiles cost $0.0087 against the estimated $0.0073, and crops $0.0034 against $0.0035.
- The 26 failed Sonnet crops were billed. Phase-3 spend is now **$2.32** ($1.84 + $0.48).

**The combining rule: "rules", kept by the owner's 1-point rule.**
- Mean code F1 over both models: crop_always **74.46%**, rules 73.60%, crop_high 72.06%, never 69.23% (pass 1: 71.07%).
- rules is 0.86 points behind the best, inside the 1-point margin, so it stays.
- Frozen as `fallback.CHOSEN_POLICY = "rules"`. The v4-tile and v4-crop files are pinned by sha256 in `tests/test_perception_fallback.py`.

**What it shows:**
- **Recall rose as expected:** Haiku +5.0 points, Sonnet +5.0. Code F1 rose less than the proposal's realistic figure:
  - Haiku + rules 71.8% (proposal: 78.4%), **0.5 points below pass 1**;
  - Sonnet + rules 75.4% (proposal: 78.2%), +5.6.
- **Haiku's tiles add predictions that are mostly wrong.** 12 tile signs added, 6 more gold signs found, but only 3 with the right code, so precision falls. Haiku's crops under rules fixed 3 codes and broke 3.
  - Under (d), a configuration whose mean code F1 doesn't rise keeps pass 1 alone. If public_dev looks like set T, that would apply to Haiku.
- **Sonnet's crop pass lost almost half its replies.** 26 of 56 crop calls came back `bad_json`: the reply was not a bare JSON object (87–166 output tokens, `end_turn`). Haiku had 0 of 52.
  - The fallback skips a failed crop with no retry, and the failed replies' text was not kept.
  - So Sonnet's crop figures come from 30 readings, and its policy comparison is weaker than Haiku's.
  - This looks like phase 2's Sonnet prose-around-JSON problem.

**The crop retry and Sonnet's repair run (2026-11-16). Set T, development, in-sample.**

- **The retry** (`d7ac725`): tile and crop calls get one retry on bad JSON that sends only the error (D4), and each failed attempt's raw text is kept.
- **The repair run:** Sonnet fallback `7ea7aa8dcc8f`, run by the owner with `--use-cache`, cost **$0.1829**.
  - The 28 tiles and 30 crops came from the cache; only the 26 crops that failed before were paid.
  - 25 of the 26 were prose again on the first attempt, and **all 25 retries were usable**.
  - **No crop failed after the retry.** The first attempts reason in prose and then give the JSON. For example: "…That matches R.420 "Bắt đầu khu đông dân cư" (start of a built-up area).\n\n{"code":"R.420","confidence":"high"}".
- **Sonnet replays** (no API call; the log stayed at 1,490 lines): crop_always `a366b7c37100`, crop_high `40ba9224e784`, never `2907c1e78596`. A "rules" replay reproduced the repair run's scenes exactly. Haiku's files stand (0 failed calls).

| set T, development, in-sample, Sonnet after the retry | recall | code F1 | strict F1 | rule-bearing F1 | non-dup recall / F1 | codes fixed (tiles + crops) | broken | crops changing a code |
|---|---|---|---|---|---|---|---|---|
| pass 1 | 90.8% | 69.8% | 69.0% | 79.0% | 87.8% / 69.0% | | | |
| rules | 95.8% | 77.9% | 77.0% | 81.5% | 94.4% / 77.6% | 2 + 12 | 0 | 23 of 56 (41.1%) |
| crop_always | 95.8% | **78.7%** | 77.9% | 81.5% | 94.4% / 79.8% | 4 + 14 | 3 | 33 (58.9%) |
| crop_high | 95.8% | 74.6% | 73.8% | 81.8% | 94.4% / 74.3% | 1 + 9 | 0 | 14 (25.0%) |
| never | 95.8% | 67.2% | 66.4% | 78.1% | 94.4% / 65.6% | 1 + 0 | 0 | 0 |

**The combining rule changes to crop_always** (`086f1ee`):
- mean code F1 over both models (Haiku as before): crop_always **76.10%** (Haiku 73.50%, Sonnet 78.69%), rules 74.83%, crop_high 72.06%, never 69.23%; pass 1 71.07%;
- rules is 1.27 points behind, outside the owner's 1-point rule, so `CHOSEN_POLICY = "crop_always"`, and the fallback command defaults to it;
- under crop_always, both models' code F1 rises over pass 1 on set T: Haiku +1.2 points, Sonnet +8.9.

**Guard** (`086f1ee`): `score` refuses a public_dev run whose header has `use_cache: true`, because gate runs must be independent calls.

**Spend:** phase 3 is now **$2.50**.

**public_dev checkpoint 2 (gate v2, prompt v4 + fallback), 2026-11-16.**

- **Configuration:** `perception_gate_v2`; pass 1 `scene/v4@153536ec5975`; fallback v4-tile `a052a9fc72f7`, v4-crop `30e2d18b84d9`, `crop_always`, one retry on bad JSON.
- **Gate set:** 45 images (143 gold signs) and 17 non-duplicates (27 gold signs).
- **Statistics:** CIs are image bootstraps (`eval/report.py`); the CI of a mean pools each image's counts over the runs.
- **Not tuned:** the triggers, prompts and combining rule came from set T only. The changes after the approval were recorded before scoring (`cc06067`).
- **Runs:** pass 1 is reused from checkpoint 1.
  - Haiku fallback `b83d5dae690e`, `023c1a474288`, `9981d8112688` (on `e0128c462ed3`, `2dd3a6e61573`, `932c3d2b7009`);
  - Sonnet fallback `949418393534` (on `f19dd5bc36f6`). **Sonnet ran once, by the owner's decision on cost.**
- **Per-image errors were not looked at.**

| public_dev checkpoint 2 | Haiku pass 1, mean of 3 | **Haiku + fallback, mean of 3** | Haiku + fallback runs (b83d / 023c / 9981) | Sonnet pass 1, 1 run | **Sonnet + fallback, 1 run** |
|---|---|---|---|---|---|
| recall, all (95% CI) | 79.7% (69.1–92.5) | **90.0%** (85.3–95.7); exactly 89.98% | 90.2% / 90.2% / 89.5% | 81.8% (69.6–96.3) | **95.8%** (90.3–99.2) |
| code F1, all (CI) | 68.1% (59.6–78.4) | **75.6%** (69.2–83.0) | 77.1% / 75.4% / 74.2% | 75.1% (67.7–84.6) | **76.9%** (68.9–84.8) |
| code F1 strict | 67.9% | 74.9% | 76.4% / 74.7% / 73.5% | 74.3% | 76.3% |
| rule-bearing F1 (reported, not gated) | 70.2% | 78.8% | 81.3% / 79.1% / 75.8% | 77.6% | 81.5% |
| value accuracy | 88.1% | 86.4% | 76.5% / 88.9% / 93.8% | 76.5% | 73.7% |
| recall, non-duplicates (CI) | 87.7% (75.4–100) | 86.4% (73.0–100) | 88.9% / 85.2% / 85.2% | 100% | 100% |
| code F1, non-duplicates (CI) | 71.2% (57.5–91.8) | 74.9% (61.4–95.7) | 72.7% / 74.1% / 77.8% | 80.7% (70.1–94.7) | 66.7% (49.4–93.9) |
| predictions (gold 143) | 118.3 | 143.7 | 137 / 146 / 148 | 126 | 156 |
| **gate** (recall ≥ 90% and F1 ≥ 85%) | FAIL | **FAIL** | | not decided | **not decided (1 of 3 runs); indicative FAIL on F1** |

**The fallback's work** (paired with each pass-1 run; reported, not gated):

| | images tiled | tile signs added | crops | crops with no reply after the retry | crops that changed a code | fixed (tiles + crops) | broken | fallback cost |
|---|---|---|---|---|---|---|---|---|
| Haiku (b83d / 023c / 9981) | 8 / 7 / 8 | 27 / 32 / 30 | 67 / 81 / 80 | 0 / 0 / 0 | 38.8% / 46.9% / 43.8% | 11+8 / 11+15 / 8+12 | 3 / 2 / 2 | $0.189 in all |
| Sonnet (9494) | 9 | 35 | 77 | **4** (34 retried) | 42.9% | 16+2 | 4 | $0.647 |

- **Anchoring (D2)**, fallback mean by gold drafter:
  - Haiku: on the 37 Haiku-drafted images, recall 88.0% and F1 72.4%; on the 8 Opus-drafted images, 96.9% and 87.0%;
  - Sonnet: 98.2% / 75.1% (Haiku-drafted) and 87.5% / 83.9% (Opus-drafted).
- **Against set T** (in-sample): Haiku + fallback recall 90.0% vs 89.2% and F1 75.6% vs 73.5%. Sonnet + fallback recall 95.8% vs 95.8% and F1 76.9% vs 78.7%.
  - Haiku gained more on public_dev (+7.5 F1 points) than on set T (+1.2).
  - Sonnet's crops fixed only 2 codes here (14 on set T), while its tiles fixed 16.
  - Sonnet's non-duplicate F1 fell (80.7% to 66.7%, on 27 gold signs).
- **Spend:** checkpoint 2 cost **$0.836** (Haiku $0.189, Sonnet $0.647), within the estimates. Phase 3 is now **$3.34**.
- **Cost per image, all-in (pass 1 + fallback):** Haiku about $0.0028, Sonnet about $0.023.

**Policy (d), applied as written:**
1. **No configuration passes the gate.**
   - Haiku + fallback fails code F1 by 9.4 points. Its recall is 89.98%, 0.02 points under 90%.
   - Sonnet + fallback is not decided on one run, and its F1 (76.9%) is far under 85% even at the top of its CI (84.8%).
2. **The highest mean code F1 on all 45 images** is Sonnet + fallback at 76.9%, from 1 of 3 runs.
3. **Haiku + fallback (75.6%) is 1.3 points behind it,** within 2 points, so **Haiku** is chosen.
4. **The fallback raised Haiku's mean code F1** from 68.1% to 75.6%, so it stays.

**→ Phase 4 perception: Haiku 5.5, prompt v4 + the fallback** (v4-tile, v4-crop, `crop_always`), with the perception gate recorded as **failed**.
- **No checkpoint 3 in phase 3** (d).
- The comparison with Sonnet rests on one Sonnet run. Haiku's code F1 varies by 2.9 points across its three fallback runs, so a 1.3-point gap is within run-to-run noise.

### Phase 3: closing (2026-11-16)

**Outcome: the perception gate failed.**
- Haiku v4 + fallback, mean of 3 runs on public_dev: recall **89.98%** (below 90%) and code F1 **75.6%** (below 85%).
- Sonnet v4 + fallback ran once, by the owner's decision on cost: recall 95.8%, code F1 76.9%, not decided.
- Under policy (d), fixed before checkpoint 2, **phase 4 uses Haiku v4 + the fallback**, and the gate is recorded as failed. There is no checkpoint 3.
- DESIGN.md section 3 has the as-built design and the figures (`1986de3`).

**What was done (main commits):**
- **Plan and gold:**
  - plan `6113e00` (D1–D10);
  - gold tooling and guide `13eb3a0`, `c88f928`, set T `7961c6f` and `10c6730`;
  - gold signs v1 `9387764`: 81 images, every sign reviewed by the owner;
  - later gold changes `c6fb83f`, `f9998a1`, `677a87b`, and the last gold commit `ddb044b`;
  - the D10 visual check `4605a36` (55 rows human-reviewed).
- **Catalog:** P.118 and P.119 (`750011a`, `6945a25`, reviewed in `c308cbb`); R.403a/b, R.404a, R.307 (`9b5b9fa`); the effect_unmodelled rows (`87f894c`).
- **Perception code:**
  - image prep `03cf04b`, wire `3282a94`, cache `d2b3ccd`, leakage guard `8d10df4`;
  - prompt builder `b86effc`, scene call `d87b65d`, verification and re-run `bcc636c`;
  - `perception_eval.py` with the pinned GATE `1c6dc57`; gate v2 matching `b722247`.
- **Prompts:**
  - v2 `19bd70c`;
  - v3 with pictograms `a792fdc`, under the dataset-rule exception in CLAUDE.md `ccb2648`;
  - v4 `4cc8717`, pinned in `07aa01b`.
- **Checkpoint tooling:** mean-of-runs summaries and the drafter split `493b897`; the mixed-configuration refusal `6338059`.
- **Fallback:**
  - proposal `99140cf`, approval `7bdd290`;
  - implementation `47f0335`; pins and `compare` `c7a7bc3`;
  - the retry and `--use-cache` `d7ac725`; `crop_always` and the cached-run guard `086f1ee`;
  - checkpoint-2 decisions recorded before scoring `cc06067`.
- 644 tests pass and Prolog loads (as of `086f1ee`; no code has changed since).

**The configuration going into phase 4:**

| part | value |
|---|---|
| scene model | `claude-haiku-5-5`, effort medium (each prompt config's `effort`) |
| pass-1 prompt | `scene/v4@153536ec5975`. Pinned in `tests/test_scene_prompt_v3.py` (`V4_SHA256`: spec `4757bbb2…`, config `3c3f60ce…`, examples `def4618e…`, pictograms manifest `d4b38018…`) |
| tile prompt | `scene/v4-tile@a052a9fc72f7`. Pinned in `tests/test_perception_fallback.py` (`V4_TILE_SHA256`: spec `d9eb38db…`, config `26d51b4b…`, examples `def4618e…`, manifest `040bfd12…`) |
| crop prompt | `scene/v4-crop@30e2d18b84d9`. Pinned there too (`V4_CROP_SHA256`: spec `d2fbec72…`, config `8a58a28e…`, examples `cd6e0aa5…`, manifest `2ca9fbc2…`) |
| combining rule | `vqa.perception.fallback.CHOSEN_POLICY = "crop_always"` (pinned) |
| fallback constants | tiles at ≥ 5 signs, 2 × 2 with 20% overlap, dedup IoU 0.30; crop margins 0.5 / 0.5 / 0.5 / 1.0, minimum 128 px, upscale to 384 px (pinned) |
| gate | `perception_gate_v2` (pinned) |
| pictograms | the local copies come from `tools/build_scene_pictograms.py --version v4`, `v4-tile` and `v4-crop`; the prompts refuse to build without them |
| entry point | `perceive(image_path, model="claude-haiku-5-5", version="v4", fallback=FallbackConfig())` |

**Spend:** **$3.34** over 1,375 calls, all from the usage log:

| | cost |
|---|---|
| gold pre-fill | $0.35 |
| scene calls | $0.99 |
| re-runs | $0.50 |
| tiles | $0.69 |
| crops | $0.66 |
| crop retries | $0.14 |

**Open items:**
- **Owner reviews pending:**
  - catalog rows with `reviewed_by: none`: R.403a, R.403b, R.307, R.404a, and the effect_unmodelled rows R.302(a,b,c), R.303, R.411, R.420;
  - the IE.451b visual (catalog background blue; the train_7_23 gold says green) and IE.464 (catalog shape other; seen as a rectangle);
  - train_7_25's four arrow boards: gold I.407c, both models I.415 (the owner kept I.407c);
  - standalone local notices: labelled `local_notice` and out of the gate, still not modelled by the engine;
  - the five visual rows still `visual_reviewed_by: assistant`: W.242(a,b), W.243(a,b,c), IE.451a, IE.471, IE.473.
- **Perception limits carried into phase 4:**
  - code F1 is about 10 points short of the gate;
  - tile-added signs often get the wrong code;
  - Sonnet answers crops in prose before the JSON (34 of 77 retried, 4 still failed);
  - every gain on set T is in-sample.
- **Not done in phase 3 (proposed):**
  - the private gold labels (C2, after the benchmark run);
  - the pictogram ablation;
  - the parser-cache key including the catalog hash (open since phase 2).

### Phase 4: answering and the end-to-end pipeline (in progress, branch `phase-4`)

- `7ec1134` `phase-3` merged into `main` (local, not pushed; D10). `a5133c9` plan approved (`docs/plans/phase-4.md`).
- **Item 1, the answer writer and the faithfulness guard** (procedure step 1, no API):
  - `vqa/answer/digest.py`: the proof digest, the writer's only input (verdict, value, the signs it rests on, rules fired, reasons, citations). No raw Prolog goals.
  - `vqa/answer/faithfulness.py`: the guard. It checks the reply shape, the engine's verdict, that cited signs and rules are in the digest, that no code or number is missing from the digest or the question, and the opening word (Đúng/Sai for true/false questions; the verdict's polarity for other yes/no; never a yes/no word for unknown/uncertain).
  - `vqa/answer/template.py`: deterministic Vietnamese answers for every verdict and value shape. Each passes the guard (tested).
  - `vqa/answer/writer.py`: Haiku 5.5 (D1). At most two calls: a bad-JSON or guard failure gets one retry that sends only the error; then the template.
  - `prompts/answer/v1/` (`answer/v1@aed34f731e7f`, pinned in `tests/test_answer_writer.py`): spec, config (Haiku, effort low, 600 max tokens), 6 text-only examples from the train fixtures with the dataset's exact question text.
  - 678 tests pass (34 new) and Prolog loads.
- **Readings made while building item 1** (the owner can change them; the prompt is pinned, so a change is a v2):
  - numbers and codes the question states may appear in the answer;
  - "one retry" and "one regeneration" are the same single retry, so there are at most two writer calls;
  - writer effort `low`;
  - only 6 examples: no Đúng/Sai, `unknown` or meaning example yet, since no train fixture has one.

- **Owner decisions (2026-11-16)** on P1–P3 and writer v2 are recorded in the plan.
- **P1 tooling** (`557c5ff`):
  - `perception_eval.py run` now keeps the raw pass-1 / re-run replies in each row;
  - `backfill-raw` copies a pre-phase-4 run's replies out of the scene cache into `<run>.withraw.jsonl`, checked against the usage log's request ids;
  - `warm` rebuilds one run's cache records in a dedicated, emptied directory (`cache/warm/`, gitignored) and checks the rebuilt scenes.
  - **Done locally:** `9981d8112688` (H) and `949418393534` (S) backfilled and warmed: 45/45 scenes rebuilt exactly, from model outputs alone. `b83d5dae690e` is refused (its pass-1 replies are gone).
- **Writer prompt v2** (`c42f4cd`, `answer/v2@4887560f8b50`, the default; v1 kept): adds a Đúng/Sai (train_275), a sign-meaning (train_96) and an `unknown` (train_144) example. The hand-made scenes are in `tests/fixtures/answer_v2_scenes.json`.
- **Items 2–3** (`a74a1e2`):
  - `vqa/answer/fallback.py`: Sonnet, image + question + scene graph, prompt `answer_fallback/v1@dd75b41f09cd`, train-only style examples;
  - `vqa/pipeline.py`: `answer(image_path, question)`, with cache-only mode and P3.
- **Items 4–5** (this commit):
  - `eval/e2e_eval.py`: public_dev runs (warm, run, next), oracles A/B called directly, `score`, gate D5, rule D2, `attribution`, `estimate`;
  - `eval/judge.py`: Opus, `judge/v1@7c500c35df27`, pinned;
  - `eval/e2e_holdout.py`: aggregate only, temporary cache, refuses without `--confirm-frozen`;
  - leakage tests for scene reuse, oracles, the judge, prompts and `answer()`'s signature.
  - 747 tests pass and Prolog loads.
- **Oracle A, Yes/No part (free, gold scenes + gold programs, engine verdicts): 7 of 20 correct** (non-duplicates 3 of 7). This is far below DESIGN's "close to 100%":
  - 6 gold programs are `out_of_scope` and 4 verdicts are `unknown`. In the pipeline these 10 go to the fallback;
  - of the 10 the engine decided, 7 are right and 3 wrong:
    - `0011`: the B.25 overtaking exception, not modelled (phase 1.7);
    - `0068`: the gold scene's S.505a plate under P.123b lists trucks only, so motorbikes may turn right; the gold answer says Sai;
    - `0094`: the gold local plate "CẤM XE 3 BÁNH VÀ 4 BÁNH THÔ SƠ" has no structured `vehicles`, so P.111b's own vehicles apply.
  - The 4 public_dev few-shot questions have no gold program.
  - Gold and kb/ were not changed.
- **Readings for the owner to confirm:**
  - a `perception_failed` fallback trigger (no scene at all), which is not in D3's list;
  - gold scenes for oracles drop standalone local notices and keep unreadable gold signs as `UNKNOWN`.

### Oracle A diagnosis (development, public_dev, 2026-11-16)

Engine only, no API. Gold scenes (gold signs v1, with the accepted readings: local notices dropped, unreadable signs as `UNKNOWN`) and gold programs (gold intents v1). Nothing in kb/ or gold was changed.

**Coverage.** 47 questions have a gold program. The plan's 48 counted `0096`, which gold v1 skipped (P.118/P.119 size limits); the other 3 missing are parser few-shots.

**Verdicts:**

| yes | no | value | unknown | uncertain | out_of_scope |
|---|---|---|---|---|---|
| 9 | 6 | 14 | 10 | 0 | 8 |

So the rules decide **29 of 47 (62%)** with gold parts. The decided Yes/No answers were scored in the earlier check: 7 of 10 right. Natural-QA values need the writer and the judge, so they are not scored here.

**Each unknown and out_of_scope, with its reason:**

| id | intent | verdict | reason (from the proof or the gold program) |
|---|---|---|---|
| 0001 | meaning, `only` | unknown | expected exactly one sign: 3 × P.131c + 5 unreadable |
| 0022 | meaning, `only` | unknown | expected exactly one sign: I.423b + 1 unreadable |
| 0036 | meaning, `only` | unknown | expected exactly one sign: P.131b + 1 unreadable |
| 0044 | is_sign, `only` | unknown | expected exactly one sign: IE.465, IE.464, IE.467 + 1 unreadable |
| 0045 | meaning, `only` | unknown | expected exactly one sign: P.125 + 2 unreadable |
| 0053 | is_sign, `only` | unknown | expected exactly one sign: P.125 + 2 unreadable |
| 0080 | is_sign, `only` | unknown | expected exactly one sign: I.419a + 1 unreadable |
| 0084 | is_sign, `only` | unknown | expected exactly one sign: P.102 + R.302a (both readable) |
| 0086 | meaning, all signs | unknown | one of the 5 signs is unreadable, so `_meaning` returns unknown for the whole list |
| 0095 | permitted | unknown | `vehicle-unknown`: the program has `load_t > 10`, while P.115 limits `gross_t > 10`; the rules don't know that gross ≥ load |
| 0021 | — | out_of_scope | counting signs |
| 0055 | — | out_of_scope | guide-sign content (direction to a place) |
| 0063 | — | out_of_scope | guide-sign content (junction shape) |
| 0070 | — | out_of_scope | guide-sign content (route / exit) |
| 0067 | — | out_of_scope | driver behaviour required by a warning sign (reduce speed) |
| 0073 | — | out_of_scope | driver behaviour in response to a warning sign |
| 0087 | — | out_of_scope | what a driver should do (gold: reduce speed; warning signs) |
| 0085 | — | out_of_scope | traffic lights (turning on red) |

**Causes, with counts and fixes:**

1. **`only` selector finds several signs: 8** (0001, 0022, 0036, 0044, 0045, 0053, 0080, 0084).
   - In 7 of them the extra signs are unreadable ones (and in 0001 there are also 3 identical readable signs). 0084 has two different readable signs.
   - **Fix:** engine / DSL semantics in Python (`Engine.resolve` and `_meaning` / `_is_sign` in `vqa/reasoning/engine.py`), not kb/:
     - `only` resolves to the readable signs when they all share one catalog row;
     - for `is_sign` with several different readable candidates, a decision is needed: every candidate must match (0044 then depends on whether IE.464/465/467 all carry that meaning), or any may (0084 then becomes "yes").
   - **Owner decision:** whether an unreadable extra sign may be ignored for "đây là biển gì?". The pipeline will see the same pattern, since perception also lists UNKNOWN signs.
   - **Size:** small, about half a day with tests. It would likely decide 7–8 of the 8.
2. **Meaning over several signs, one unreadable: 1** (0086).
   - **Fix:** in `_meaning`, return the readable signs' meanings as a value and list the unreadable ones, rather than making the whole answer unknown. This is engine Python.
   - **Size:** small, about an hour. The gold answer ("biển chỉ dẫn") is a category even though R.412d is mandatory, so expect at most partial credit.
3. **Weight attribute mismatch, load vs gross: 1** (0095).
   - **Fix:** a KB rule that `load_t > x` implies `gross_t > x` (gross weight ≥ load). It would sit in the vehicle-spec matching in `kb/rules/common.pl` (`any_spec_match`) or the ontology. Alternative: a parser/gold convention that "trên 10t" under a P.115 means gross weight.
   - **Size:** small KB change plus tests, about half a day.
4. **Guide-sign content: 3** (0055, 0063, 0070).
   - Genuinely beyond the rules: the scene graph doesn't hold destinations, arrows or junction shapes. These stay with the fallback.
   - **Size if attempted:** large (a new scene-graph field and new perception prompts). Not recommended in phase 4.
5. **Warning-sign driver behaviour: 3** (0067, 0073, 0087).
   - Already listed for phase 1.7 ("phải giảm tốc độ").
   - **Fix:** a KB rule citing the QCVN 41 warning-sign article, a DSL action or claim (e.g. `required(reduce_speed)` for warning signs), parser prompt v7, and gold intents v2 for these rows.
   - **Size:** medium, 1–2 days, and it reopens the parser gate (a new prompt version and new parser runs).
6. **Counting signs: 1** (0021).
   - Phase 1.7 item.
   - **Fix:** a DSL `count` intent over a selector or category, the engine, parser v7 and gold v2.
   - **Size:** small to medium; it shares the parser-v7 cost with cause 5.
7. **Traffic lights: 1** (0085). Out of v1 scope; stays with the fallback.

**What fixing them could do to rule coverage with gold parts:** causes 1–3 are Python plus one small KB rule, with no parser change: from 29/47 (62%) to about 38/47 (81%). Adding cause 5 brings it to about 41/47 (87%), but that needs parser v7.

**Also seen (not a cause of unknowns):**
- **The B.25 overtaking exception (0011)** gives a wrong "yes" (KB, phase 1.7).
- **0094's gold local plate has no structured `vehicles`.** That is a gold-scene labelling gap, so cyclos look allowed under P.111b.
- **The relevance rule treats every rectangle as an information board.** So an unreadable red or local rectangle can never make a turn or permission answer unknown. Local notices are often red rectangles. This is a possible gap in `Engine.could_matter`; it did not change any answer here.

**public_natural_0068: which is wrong?**
- **Question and gold answer:** "Người điều khiển xe máy được rẽ phải vào đường Hồng Hà lúc 10 giờ sáng, đúng hay sai?" Gold: **Sai**.
- **Gold scene:** s2 is `P.123b` with two plates:
  - `{"kind": "vehicle", "code": "S.505a", "text": "", "vehicles": [{"class": "truck"}]}`;
  - `{"kind": "time", "code": "S.508a", "text": "6:00 - 22:00", "time_windows": [06:00–22:00]}`.

  The other signs are the overhead guide I.414 "ĐƯỜNG HỒNG HÀ" with a bent-right arrow, and two unreadable ones. The owner's gold note says the plate pictogram is a truck, not a car.
- **Engine proof:** `clears(turn_right, motorbike, 10:00, s2, plate_vehicle_not_covered)`. P.123b prohibits turning right for every vehicle (B.23, art. 22), but the S.505a plate (art. 41, F.5) narrows it to trucks: `any_spec_match([spec(truck)], motorbike) = false`. The time window holds (6:00–22:00 includes 10:00). Verdict: **yes (Đúng)**.
- **The image** (public_dev, allowed): the plate under P.123b shows a box truck and "6:00-22:00". The red strip at the right edge is a cropped roadside banner, not a sign.
- **Verdict: the gold label and the rule are right; the gold answer is very likely wrong.** Under F.5 the sign applies only to trucks, so a motorbike may turn right at 10:00. The dataset's "Sai" probably reads P.123b as a ban for every vehicle and ignores the plate. Only the dataset can be blamed here; nothing to change in kb/ or gold.

### Engine fixes 1b and oracle A rerun (tuned, development, public_dev, 2026-11-16)

**Fixes** (plan item 1b; each with tests on hand-made scenes modelled on train questions; full suite green and Prolog loads after each):
- `674641d` 1b.1: single-sign selector. Unreadable candidates are dropped; readable candidates sharing one code decide, with the unreadable ones in `uncertain_signs`; different codes stay unknown.
- `5f486fb` 1b.2: meaning over several signs answers for the readable signs and lists the unreadable ones.
- `4b07a60` 1b.3 (kb/): load > x implies gross mass > x.
  - It is a `vehicle_interpretations` entry with `attribute_rule: load_implies_gross`, sourced from QCVN 41 B.15's definition of gross mass.
  - It shows in proofs as `cite(r_load_implies_gross)`. Its `rule_source` law_id is `interpretation`, so `explain.citations` leaves it out. No cut.
- `c0d8b90` 1b.4: an unreadable rectangle with a red background or border is category `red_board`, treated as prohibitory for relevance. The perception gate's matching groups are unchanged.
- Deferred, not in phase 4: the warning-sign rule, counting signs, guide-sign content.
- 769 tests pass.

**Oracle A, engine only, tuned** (gold scenes + gold programs; 47 questions with a gold program):

| | yes | no | value | unknown | uncertain | out_of_scope | decided |
|---|---|---|---|---|---|---|---|
| before 1b | 9 | 6 | 14 | 10 | 0 | 8 | 29 (62%) |
| **after 1b (tuned)** | 11 | 7 | 19 | 2 | 0 | 8 | **37 (79%)** |

- **Yes/No accuracy (tuned): 9 of 20 = 45%** (before: 7 of 20).
  - Non-duplicate images: 4 of 7 = 57% (95% CI 25–84%).
  - Duplicates of train: 5 of 13.
- **Of the 12 decided Yes/No answers, 9 are right.** The 3 wrong:
  - `0011`: the B.25 overtaking exception (deferred KB);
  - `0068`: a disputed gold answer, below;
  - `0094`: the gold plate has no vehicles; the owner fixes it.
- **The 8 undecided Yes/No:**
  - 6 out_of_scope: guide content 3, warning behaviour 2, traffic lights 1;
  - 2 unknown: `0044` (IE.465 / IE.464 / IE.467: different readable codes) and `0084` (P.102 + R.302a). Both stay unknown under the 1b.1 rule.
- **The remaining unknowns are those 2.** The out_of_scope 8 are unchanged: counting 1, guide content 3, warning behaviour 3, traffic lights 1.

**Disputed gold answer: public_natural_0068.**
- The gold answer is **Sai**. The engine answers **Đúng**: P.123b's S.505a plate shows a truck, so under F.5 only trucks may not turn right 6:00–22:00.
- The engine's Đúng is believed correct. The image shows the truck plate, and the owner's gold note agrees.
- It is **scored as is** (counted wrong) in every report.

### Step 2 results (public_dev, tuned, 2026-11-16)

Runs (owner, 2026-11-16): fresh Haiku pass-1 runs `04d55157f9ce` and `63128b1c2fd6` with fallbacks `1c9ca7368074` and `b490cd60479f`; pipeline runs H1 `e3a07fadeb7a` (scenes `9981d8112688`), H2 `fd6c15ef8d69`, H3 `d052db954849`, S `4ac8ae832b37` (scenes `949418393534`); oracle A `5f0160f4bd7c`; oracle B on H1 only, `71f861f94792` (owner decision: no oracle B for H2 and H3). Writer `answer/v2@4887560f8b50`, fallback `answer_fallback/v1@dd75b41f09cd`, parser v6, judge `judge/v1@7c500c35df27`. Outputs (local, gitignored): `eval/runs/e2e/score_tuned.json`, `eval/runs/e2e/attribution_H1.json`.

**Spend for step 2: $2.20** (perception $0.25, pipeline runs and oracles $1.95). Phase 4 so far: $2.20 of the $10 ceiling.

| run | questions | overall | strict | Yes/No | Natural QA | non-dup (95% CI) | rule coverage | rules-only | fallback rate | template rate |
|---|---|---|---|---|---|---|---|---|---|---|
| H1 | 51 | 81.4% | 78.4% | 20/24 | 79.6% | 92.1% (72–98) | 56.9% | 86.2% (29) | 43.1% | 2/30 |
| H2 | 51 | 82.4% | 78.4% | 21/24 | 77.8% | 84.2% (62–94) | 49.0% | 86.0% (25) | 51.0% | 2/28 |
| H3 | 51 | 78.4% | 74.5% | 19/24 | 77.8% | 78.9% (57–91) | 58.8% | 88.3% (30) | 41.2% | 3/32 |
| **H pooled** | 153 | **80.7%** | 77.1% | 83.3% | 78.4% | **85.1% (74–92)** | 54.9% | 86.9% (84) | 45.1% | **7/90 = 7.8%** |
| S | 51 | 80.4% | 78.4% | 18/24 | 85.2% | 86.8% (65–96) | 66.7% | 80.9% (34) | 33.3% | 1/34 |
| oracle A | 47 | 86.2% | 83.0% | 16/20 | 90.7% | 94.1% (73–99) | 78.7% | 86.5% (37) | 21.3% | 4/37 |
| oracle B (H1) | 47 | 79.8% | 74.5% | 16/20 | 79.6% | 94.1% (73–99) | 57.4% | 83.3% (27) | 42.6% | 3/28 |

- Non-duplicate subsets: 19 questions per pipeline run (57 pooled), 17 for the oracles. "Duplicate" means the image is also in train.
- **Gate (D5): FAIL.** Faithfulness 100% (90 of 90 writer-path answers), but the template rate is 7.8% (7 of 90), above the 5% cap.
- **Perception rule (D2): Haiku + fallback goes to holdout.** S 80.4% is below the H mean 80.7% + 5 points and below the best H run 82.4%.
- **Fallback triggers, H pooled:** uncertain 34, out_of_scope 24, unreadable_sign 7, unknown 2, parse_failed 2. Fallback failures (P3): 6.
- **Stage attribution, H1 only** (11 answers not fully correct): perception 3 (`0002`, `0036`, `0051`), parser 1 (`0065`), rules, writer or fallback 7.

### Step 2 diagnosis (public_dev, tuned, 2026-11-16; no API calls, nothing changed)

**1. The 7 template answers (D5) all come from the writer reply being cut off at `max_tokens=600`.**
- Cases: `0026` in H1, H2 and H3; `0094` in H1, H2 and H3; `0065` in H3. Each has one attempt with the error "the reply was cut off at max_tokens=600". By design, the writer does not retry after a cut-off.
- No template case comes from a guard rule: the guard never rejected a complete writer reply in step 2.
- **Cause: the writer config (`prompts/answer/v2/config.yaml`, `max_tokens: 600`), not the guard or the digest.**
  - The three questions have large digests: a local plate and two or more applying signs (`0026`, `0094`), or five signs (`0065`).
  - Complete writer replies reach 582 output tokens (median 188, 90th percentile 462). 15 of the 189 writer calls in the log hit 600.
  - The raw cut-off replies are not kept in the run files, so it is not known whether the length is answer text or reasoning.
- The template answers themselves were right in 4 of 7 cases (`0026` ×3, `0065`). `0094` is wrong in all three, for the reason in part 4.

**2. The 34 "uncertain" triggers.** Each was replayed with the engine only, on the run's warmed scene and parsed program, removing one source of alternative readings at a time. Sources:
- pass 1's own `alt` field: the model gives a second reading, usually the sibling variant, e.g. P.131b vs P.131c;
- re-run disagreement (`verify.merge`);
- `crop_always` keeping pass 1's reading as an alternative after the crop replaced it.

Results:

| alternative that causes "uncertain" | cases | rules answer if dropped | likely right | wrong | needs the judge | still unknown |
|---|---|---|---|---|---|---|
| pass 1's own `alt` only | 21 | 20 | 15 | 3 | 2 | 1 |
| re-run disagreement only | 4 | 2 | 1 | 2 | 0 | 2 |
| `crop_always`'s kept pass-1 reading only | 4 | 4 | 4 | 0 | 0 | 0 |
| several sources (all include crop_always) | 5 | 4 | 1 | 2 | 1 | 1 |

- **So 25 of the 34 come from readings that disagree within pass 1 itself** (its own `alt`, or the re-run). 4 come from crop_always alone, and 5 mix crop_always with pass-1 sources.
- How "right" was judged:
  - Yes/No: against the gold answer.
  - Natural QA: against oracle A's engine value, where the judge marked oracle A correct. Sign ids and catalog-variant names with the same meaning count as the same.
  - "Needs the judge": `0086` (a guide-sign list).
- **Net against the fallback answers the runs actually shipped:**
  - dropping pass 1's own `alt`: **about +6 to +7 correct over 153 pooled H answers** (+1 `0036`, +0.5 ×2 `0036`, +1 ×3 `0038`/`0037`, +1 ×2 `0083`, −0.5 `0092`, and `0086` ±0.5 ×2);
  - dropping re-run alternatives: −1.5;
  - dropping crop_always's alternative: +1, and that +1 is `0068`, the disputed gold answer;
  - dropping all alternatives in the mixed cases: −1.5.
- 19 of the 20 pass-1-`alt` cases that the rules would answer are on signs whose crop **agreed** with pass 1's main code (confidence raised to medium).
- The 3 wrong ones: `0002` ×2 (pass 1 and the crop agree on P.130; gold P.131a) and `0092` (part 4).

**3. The 6 fallback failures (P3): all are Sonnet replying with prose around the JSON, on both attempts.** The errors are "must be only a JSON object" 11 times and "Extra data" once.
- Cases: `0068` (H1), `0036`, `0038`, `0049` (H2), `0037`, `0038` (H3). Five came from uncertain triggers and one (`0049`) from an unknown trigger.
- The shipped writer answers scored 0.5 once and 0 five times.
- **The same error drives the retries:** 32 of the 69 H fallback calls (46%) failed the first attempt this way. S had 2 of 17. Failed fallback replies run 97–332 output tokens, against a median of 87 for good ones.
- **Cause: the fallback reply format.** The client accepts only a bare or fenced JSON object, and the fallback prompt doesn't hold Sonnet to it on image questions. It is not a trigger or guard problem.

**4. The 7 H1 errors in "rules, writer or fallback":**
- `0011` (rules): P.125 with "kể cả xe được ưu tiên". The B.25 exception is not modelled (deferred). All three runs wrong.
- `0043` (rules or gold reading, 0.5): `ban_times` returns both condition groups' windows (6:00–22:00 for heavy vehicles, plus the three short windows). The gold answer lists only the short windows. Same in oracles A and B.
- `0063` (fallback, out_of_scope guide content): Sonnet reads the Đại Lộc guide sign as a plain crossroads (Sai; gold Đúng). Same in all three.
- `0068` (fallback failure plus disputed gold): H1's scene is uncertain, the fallback failed (part 3), and the shipped answer is "Chưa chắc chắn". Oracle A gives Đúng against gold Sai (disputed).
- `0087` (fallback, 0.5): the answer "giảm tốc độ" is right, but Sonnet adds a 5.0 m height-limit claim the judge calls unsupported. Same in all three.
- `0092` (writer or template phrasing plus vehicle mapping):
  - `which_vehicles banned` gives `banned: []`, with P.111b/d conditional on the plate's time windows, and the answer opens "Không có loại xe nào", which the judge reads as contradicting the gold answer;
  - oracle A also returns motor_tricycle (the gold plate mapping) where gold names rudimentary three-wheelers.
- `0094` (vehicle mapping, not the gold-fix timing):
  - **Oracle A ran after the gold fix** (it started 13:11 +07; `8b588c5` is 11:52 +07). An engine-only rerun now (free) gives the same Đúng.
  - The question's "xe thô sơ 3 bánh" parses to `cyclo`. The fixed gold plate "CẤM XE 3 BÁNH VÀ 4 BÁNH THÔ SƠ" maps to `motor_tricycle` + `similar_rudimentary`.
  - So the plate does not cover `cyclo` (`vehicle_not_covered`), and Đúng follows.
  - For Sai, the plate's "3 bánh ... thô sơ" would have to cover rudimentary three-wheelers (cyclo and the like). This is the owner's gold reading to decide.

## Next steps, in order

**Next (2026-11-16): phase 4, procedure step 4 (tuning, D8: at most 5 runs).** Step 2 is done (above). The D5 gate failed on the template rate (7.8% > 5%). Tuning approved (owner, 2026-11-16; plan section "Tuning on public_dev"): T1 + T3, then T2, then T4, each its own run (D8: 3 of 5). Built: the replay tool `eval/e2e_replay.py`, writer prompt `answer/v3@7d0f2b8ddf1f` (T1, now the default; v2 stays), the conditional `which_vehicles` wording (T3). The T1 + T3 replay (about $0.36) waits for the owner. Then step 5 (freeze) and step 6 (holdout once, Haiku + fallback, about $0.67).

All public_dev figures are labelled **tuned**.

### Handoff (2026-11-15): where phase 3 stands, and what comes next (kept as a record)

**Where things stand** (branch `phase-3`, not pushed):
- **Gold signs v1:** 81 images (45 public_dev, 36 set T), hand-reviewed by the owner, in `data/annotations/gold_signs_v1/gold_signs_v1.jsonl`. Last gold commit `ddb044b` (train_7_23 s4 = DP.134).
- **Set-T results** (development, gate v2):

  | | recall | code F1 | rule-bearing F1 |
  |---|---|---|---|
  | Haiku v4 | 83.3% | 72.3% | 76.2% |
  | Sonnet v4 | 90.8% | 69.8% | 79.0% |
  | Haiku v3 (best Haiku F1) | 81.7% | 73.5% | 75.8% |

  No configuration is near 85% code F1; the 95% CIs top out around 80–83%. The full tables are in the entries below.
- **Prompt:** `scene/v4@153536ec5975`, pinned by sha256 at `07aa01b` (v1–v4 are all pinned). The v3/v4 pictograms are local, gitignored copies; rebuild them with `tools/build_scene_pictograms.py --version v4` if they are missing (the prompt refuses to build otherwise).
- **Gate:** `perception_gate_v2` in `eval/perception_eval.py`, pinned by a test: recall ≥ 0.90 and code F1 ≥ 0.85 on the mean of 3 runs; readable:false and local_notice gold excluded; side before rank in matching.
- **Phase-3 API spend so far: $1.24** over 421 calls. That is the gold pre-fill ($0.29 Opus + $0.06 Haiku) and six set-T runs ($0.89: Haiku v1–v4 $0.20, Sonnet v2 and v4 $0.68). There has been no public_dev run.
- `ANTHROPIC_API_KEY` is not set in the assistant's shell: the owner runs the paid commands.

**Fallback on set T: done (2026-11-16).** "rules" frozen. v4-tile and v4-crop are pinned. Spend is $2.32. See the entry above.

**Checkpoint 2: done (2026-11-16).** Haiku + fallback FAIL: recall 89.98%, code F1 75.6% (mean of 3). Sonnet + fallback: 1 run, not decided, recall 95.8%, F1 76.9%. The results entry is above.

- **Policy (d):** phase 4 uses **Haiku v4 + fallback** (`crop_always`). The perception gate is recorded as failed. No checkpoint 3.
- **Spend:** phase 3 is $3.34.
- **Left in phase 3:**
  - plan item 9's DESIGN.md updates: the plain-JSON scene call, the gold-label decision, the gate on public_dev, matching and CI, the model choice, and the fallback;
  - the open catalog reviews.

**Checkpoint 1: done (2026-11-16).** Haiku v4 FAIL (recall 79.7%, code F1 68.1%, mean of 3). Sonnet v4 was run once (owner's decision): recall 81.8%, F1 75.1%, not decided, indicative FAIL. The results entry is above. Phase-3 spend is now $1.84. Next: the owner's decision on plan item 7 (the fallback, built on set T; see "Open owner decisions"), then checkpoint 2.

**Checkpoint 1 procedure** (approved by the owner; kept as a record; Sonnet stopped after 1 of 3 runs):
1. **Haiku v4 × 3 on public_dev**, each run with `--max-spend 0.5`; ceiling **$0.35** for the three runs (estimate $0.20 calibrated, range $0.13–0.25):
   `.venv/bin/python eval/perception_eval.py run --set public_dev --model claude-haiku-5-5 --version v4 --max-spend 0.5` (three times)
2. Score with the gate (mean of 3): `.venv/bin/python eval/perception_eval.py score <the three run files>`.
3. **If Haiku fails: Sonnet v4 × 3**, each run with `--max-spend 1.0`; ceiling **$1.80** (estimate $1.28 calibrated, range $0.88–1.64):
   `.venv/bin/python eval/perception_eval.py run --set public_dev --model claude-sonnet-5-5 --version v4 --max-spend 1.0` (three times), then score.
   Opus is skipped (owner's decision).
4. **Report** via `eval/report.py`, labelled **"public_dev checkpoint 1 (gate v2, prompt v4)"**:
   - both scores, on all 45 images and on the 17 non-duplicates, with 95% CIs, per run and the mean;
   - recall, code F1 (row and strict), rule-bearing F1 (reported, not gated), value accuracy, cost;
   - the gate verdict for each model.

   Then one status commit and stop.

**Rules:**
- public_dev per-image errors are a record only. They are never used to design the fallback or any prompt. The fallback trigger is chosen from set-T errors only.
- No new prompt versions without the owner's decision.
- No push.

**Open owner decisions:**
- **The plan-item-7 change:** box crops that re-read low-confidence / UNKNOWN codes, plus a region pass (tiles or whole-board crops) on dense scenes. Box crops can't recover a missed sign: on set T every missed sign was never listed.
- **What happens if the gate still fails after the fallback.**

**Other open items:**
- Catalog rows waiting for the owner's review (`reviewed_by: none`): R.403a, R.403b, R.307, R.404a, and the effect_unmodelled rows R.302(a,b,c), R.303, R.411, R.420.
- IE.451b (catalog background blue; the train_7_23 gold says green) and IE.464 (catalog shape other; seen as a rectangle): the owner re-checks them.
- train_7_25's four arrow boards: gold I.407c, while both models say I.415 (the owner kept I.407c).
- Standalone local notices: labelled `local_notice` and excluded from scoring; still not modelled by the engine.


0. **Recommendation for the public_dev checkpoint** (owner's decision; no more set-T prompt versions):
   - **Prompt v4 for both models, in plan item 6's order:** Haiku v4 × 3, then Sonnet v4 × 3, since Haiku will very likely fail.
     - Expected cost about $0.20 for Haiku (45 images × $0.0015 × 3) and $1.35 for Sonnet (45 × $0.0100 × 3), about $1.55 in all. Spend limits $0.5 and $2.5.
   - **Expected result: both FAIL** on code F1 ≥ 85%. Set T gives 70–74% with 95% CIs topping out near 80–83%.
     - Sonnet's recall (90.8% on set T, CI 84.6–97.9%) is about a coin flip against 90%.
     - Haiku's recall (83%) very likely fails.
     - public_dev is not the tuning set, so expect at or below set T.
   - **Then the fallback (plan item 7), built on set T:** box crops that re-read low / UNKNOWN codes, plus a region pass (tiles or board crops) on dense scenes for never-listed signs. Then the plan's second public_dev checkpoint.
   - **The model to carry forward: Sonnet v4.** It has recall near the gate, the best rule-bearing F1 (79%) and 100% value accuracy, at about $0.01 per image.

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

- **The parser's version key should include the catalog hash,** as the phase-3 scene prompt does. The parser prompt is built from `prompts/parser/<version>/` plus the catalog table, but only the spec and few-shot files are pinned. So a catalog change (P.118 and P.119 here) changes the prompt the parser actually sends, under the same version name.
- **P.118 and P.119 rows wait for the owner's review** (`reviewed_by: none` in git; the owner has marked them `human` locally, not committed).
- **R.302(a,b,c), R.303, R.411, R.420** are in the catalog with `effect_unmodelled` (`87f894c`). Their effects are still to be modelled; until then they make closed-world answers unknown where they could matter.
- **R.403a, R.403b, R.404a, R.307, R.302(a,b,c), R.303, R.411, R.420 wait for the owner's review** (`reviewed_by: none`).
- **Sonnet's bad_json first replies.** 16 of 141 first replies (11%) across the three v6 runs had prose around the JSON and needed the retry; Haiku had 0 of 141. One retry, on 0005 in run f20993f4ac4e, was refused with category `reasoning_extraction`.
  - The likely cause is the retry wording. `ClaudeParser.parse` sends the rejected reply back as the assistant turn, prose included, followed by "That answer is not valid: …. Reply with only the corrected JSON object."
  - Candidates for a v7: don't echo the prose back (send a placeholder or only the error); tell the model more firmly to reply with nothing but the object; or accept "prose, then one ```json fence".
  - Any of these needs a new prompt version and new runs.
- **Visual corrections.** Five catalog rows are still `visual_reviewed_by: assistant`: W.242(a,b), W.243(a,b,c), IE.451a, IE.471 and IE.473.

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
