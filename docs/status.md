# Project status

Last updated 2026-11-15. Branch `phase-3`, on top of `main` at `afe006c` (phase 2 merged in PR #1).

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

## Next steps, in order

0. **Phase 3 item 3, the scene call:** the D10 visual check is done, so `prompts/scene/v1` can be written on the reviewed catalog.

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
