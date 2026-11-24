# Project status

## Where things stand (2026-11-23)

**The evaluation is complete** (branch `phase-5`). On the private test, three runs on the frozen phase52 system, hand-graded by the owner:

| System | Private, mean (sd) |
|---|---|
| **V2, rules + live RAG fallback** | **82.2% (1.8)** |
| V1, rules only | decides 66.9% of questions at 82.3% |
| RAG alone | 79.2% (judge-graded) |
| Baselines LowCost / LexiSignVQA | ~78% (owner's hand grades) |

- On the public test (public_dev + public_holdout, 100 questions), V2 scores 84.5%.
- The error analysis is done: mostly perception misreads, 3 small rules gaps, and a routing signal for future work.
- The lane-sign payload fix (QCVN 41 D.14, `05e4b3b`) is post-benchmark and never scored on private.
- Details are in the entries below.

### Task 3 (Review 3 checklist): Review 3 on 2026-11-30, the thesis defense on 2026-12-19

The dates were corrected by the owner on 2026-11-22; an earlier note had the defense on 11-30.

#### Day 1: done on 2026-11-21

Plan: `docs/plans/task-3-review-3.md` (proposed; 9-day schedule). All work goes through PRs to `main`, with CI on every push.

| PR | What | Merge |
|---|---|---|
| — | `phase-5` fast-forwarded into `main`; tag `v1.0-benchmark` (`4e71a18`, the code of the 3 private runs); GitHub Actions CI (lint, KB load, leakage guard, tests; tests needing local data skip via `tests/needs_local_data.txt`) | `ab315f1`, `e6cd2ca` |
| #1 | The RAG imported as code only under `services/rag/` (history kept, rewritten to author/committer `stfutien`; `services/rag/ORIGIN.md` maps old hashes, e.g. `db75c4b` → `f177426`) | `d965265` |
| #2 | RAG runtime assets: gitignored copies plus `assets_manifest.json` (1,596 files, sha256), `verify_assets.py`, `fetch_assets.sh`; retrieval from `services/rag/` identical to the saved runs (100 public + 146 private) | `ba5df83` |
| #3 | Backend API `app/api/` (FastAPI): `/v1/ask`, `/v1/ask/stream` (stage events), sessions, history, feedback, images, `/metrics`, Swagger; runs the phase52 profile (held equal to `eval/frozen_phase52.json` by a test) | `560e6b7` |
| #4 | Answer text streams token by token (`token`, `token_reset`; the final `answer` event stays authoritative); answers unchanged | `6f51736` |
| #5 | RAG service (`services/rag/src/text_based_rag/service.py`, `service_api.py`) and the RAG fallback client `vqa/answer/rag_fallback.py`; API mode `VQA_ANSWER_FALLBACK=rag` + `VQA_RAG_URL` | `37acdf0` |
| #6 | Fast GPU setup: bundle on the private HF dataset `lephuocloc/ns-vqa-rag-assets` (109 MB, no private-test files), `fetch.py`, `gpu_setup.sh`, GPU image `ghcr.io/lephuocloc1729/ns-vqa-rag` (public; code only) built by `.github/workflows/rag-image.yml`, runbook `docs/runbooks/gpu-session.md` | `0009e0f` |
| #7 | GPU-session fixes (UTF-8 streaming, in-place downloads), results `docs/results/gpu-session-2026-11-21.md`, and setup without an interactive HF login (`HF_TOKEN` from the container, `scripts/onstart.sh`) | `7ebae48` |

**Day 3 (2026-11-22), branch `task3/web-ui`:** the web UI in `web/` (React + Vite + TypeScript; `web/README.md`).
- Ask screen: photo by picker, drag and drop, paste or phone camera; streamed stages and answer; numbered sign boxes; notes, rule citations, proof tree, the RAG badge and its laws; feedback; history.
- Tests: Vitest for the SSE parser and turn reducer (20); Playwright on the real API with a fake pipeline, desktop and phone (3 tests each). CI jobs `web` and `web-e2e`.
- Live check on 2026-11-22: the phase52 API with fallback off, the owner's key, 3 questions on public_dev image `public_test_3_6`, **$0.084** in total.
  - The first question was sent by curl: cold cache, 12.8 s, $0.073.
  - Two follow-ups went through the UI. The scene cache was hit (`đã lưu`): one was `out_of_scope` (not decided, $0.008); the other was answered by the rules with the writer's text streaming live ($0.004).
  - Boxes line up on the real photo, feedback is stored, and the `#turn=` link works.
  - Fixed from this check: the spinner label (perception and parsing arrive in either order) and links followed while the page is open.
- Not done: the RAG fallback live behind the UI (needs the GPU box); the day-4 items (microphone, video frame, dashboard, RAG progress events).

**Measured** (details in `docs/results/gpu-session-2026-11-21.md`):

- **Live API test on the Mac, 3 public_dev questions, cold cache:** $0.1019; 1 correct, 1 sign misread, 1 undecided with the fallback off.
- **GPU (RTX 5090):**
  - a fresh machine is ready in about 2–3 minutes;
  - service vs batch runner: identical at every stage except the query-embedding batch size;
  - service latency 8.7 s mean, 6.8 s p50; peak VRAM 18.4 GB;
  - Q4_K_M vs BF16: 9.3 vs 19.6 GB, 203 vs 91 tokens/s, 4.8 vs 6.5 s per answer (accuracy not measured);
  - end to end through the API with the RAG fallback: 3/3 correct, $0.0855.

#### Days 3–4 (2026-11-22 and 2026-11-23): PRs #8–#27

| PR | What | Merge |
|---|---|---|
| #8 | This file: Task 3 day 1 | `f96a11c` |
| #9, #10 | The web UI (`web/`): ask screen, streamed stages and answer, sign boxes, proof, citations, RAG badge, feedback, history; chat-style layout; voice questions (browser speech-to-text, vi-VN) | `f49a031`, `e3b6672` |
| #11 | Docker Compose stack: web (nginx), api, postgres, prometheus, node-exporter, grafana (dashboard "SignCite – hệ thống"), rag (GPU profile); fake pipeline by default | `5f248fb` |
| #12 | Product name **SignCite** | `f2914bd` |
| #13 | HTTPS with Caddy for **signcite.xyz** (`docker-compose.https.yml`) | `f85cfab` |
| #14 | Web UI: the phone layout of the mockup, the desktop at 80%, no example questions; greeting "Hỏi biển báo trong ảnh của bạn" in the brand's serif | `6ba7058` |
| #15, #16, #17 | **CD** (`.github/workflows/cd.yml`, `docker/deploy.sh`): after CI on `main`, build and push to GHCR, deploy over SSH, check, automatic rollback of images and files; tests recorded in `docs/deploy.md` | `221028f`, `5673682`, `cb80846` |
| #18, #20, #21 | **Load test** (Locust, `eval/load/`, workflow `load-test.yml`); results in `docs/results/load-test-2026-11-22.md` and `load-test-slots-2026-11-23.md` | `ef5ec1c`, `7535be1`, `c8cea1e` |
| #19 | **Several questions at once:** `VQA_ANSWER_SLOTS` (threads sharing the pipeline, one Prolog lock); plan `docs/plans/concurrent-answers.md` (approved) | `fbf1f8d` |
| #22 | RAG settings for several questions at once (defaults unchanged) and `eval/rag_bench.py`; GPU results `docs/results/rag-concurrency-2026-11-23.md` | `ef8e6d6` |
| #23, #27 | **RAG answer cache** (`app/api/rag_cache.py`, on by default for the RAG fallback; owner exception in CLAUDE.md); cache hits recorded in stored turns and `/metrics` (#27 carries a fix that missed #23) | `62c1cd2`, `54c90dd` |
| #24 | `httpx` in the API image (the RAG client needed it); CI imports every real-mode module inside the image; CI runs on `main` no longer cancelled | `00dd01c` |
| #25 | No test-split file in what a GPU session downloads: `rag_bundle` (1,647 files) and `rag_eval_bundle` (195 public-test files, only with `--eval`); the service's caption settings beside its code; answers unchanged | `8f6e41f` |
| #26 | The demo server reaches a rented GPU's RAG: the `rag-tunnel` service and `docker/rag-session.sh key/on/off/status` | `964ac17` |

**The demo server** (`docs/deploy.md`):
- A CloudNest VPS (2 vCPU, 4 GB) at **https://signcite.xyz**, with a testers' password.
- The real phase52 pipeline, 10 answer slots, a spend cap of $5 per API restart.
- The RAG fallback is off unless a GPU session is on.
- Every merge to `main` deploys itself.
- **Tested:** CD rollback, an unreachable registry and a server reboot (back in 25 s, data and certificates kept).

**Measured:**
- **Load** (fake pipeline, 4-vCPU runners): 0 failures up to 1000 users.
  - 1 API slot: 1.05 answers/s; p95 passes 10 s at ~25 users.
  - **10 slots: 10.33 answers/s; p95 at most 2 s up to 200 users, 4.6 s at 300;** API memory 163 MB.
  - 4 processes × 1 slot: 3.58 answers/s.
  - On the real system (~20 s per answer, mostly Claude), 10 slots give about 30 answers a minute.
  - The account's rate limits (evaluation tier) cover 10 slots at full load: about 54% of Haiku's input-token limit.
- **The RAG on one RTX 5090:**
  - 1 slot: 6.8 answers/min, 8.6 s mean (12.1 s on another machine), 18.7 GB;
  - 2 slots: 11.6/min; 4 slots: 13.0/min at 26.8 GB; 8 slots: out of memory.
  - **Batching changes the answers** (5–6/24 identical), so the evaluated setup keeps 1 slot.
  - 1 slot repeats exactly: 24/24, on two days and two machines.
- **Live on signcite.xyz with the RAG** (2026-11-23):
  - an undecided question (a fine) was answered by the RAG;
  - the repeat came from the cache in 1.6–4.3 s, identical, recorded as `cache_hit: true`.
  - Fines are not in the RAG's law corpus, so it says it cannot determine them.
- **Spend** this session (owner's go-ahead): about $0.10 on 2026-11-22 and $0.15 on 2026-11-23, plus two short GPU rentals.
- **Red-team test** (2026-11-24, owner's go-ahead, $0.35; `docs/results/redteam-2026-11-24.md`): 30 attacks (injection, jailbreak, harmful, off-topic, text on the photo, false premise) and 40 normal questions on the frozen phase52 system, fallback off. 30 of 30 attacks blocked, 0 of 40 normal questions refused. The RAG's side (refused questions on the live site) is still to run on a GPU session (`redteam.py rag`).

**Next, before Review 3 (2026-11-30):**
1. **UAT**: the pack is ready in `eval/uat/` (`README.md`: task sheet, form questions with SUS in Vietnamese, moderator notes, observation log, `score_sus.py`, `turn_stats.py` for the server's aggregates, report template).
   - Owner (2026-11-23): at least 15 testers by video call, 5 fixed tasks + 2 free questions, 20 street photos (3 fixed + 2 backups, 15 spare); targets SUS ≥ 68, task success ≥ 80%, CSAT 4–5 ≥ 70%, every task ≥ 60%.
   - Each tester gets an account on the admin site, so their questions are stored with it.
   - Sessions around 26–28/11, with a GPU rented for their hours (`rag-session.sh on`/`off`); the RAG cache was cleared on 2026-11-23.
2. **The admin site** (`docs/plans/admin-page.md`, PR 1): admin.signcite.xyz with its own login; overview charts (the 1.3 dashboard page), feedback inbox, questions, tester accounts, live settings. Owner: the DNS record and `ADMIN_PASSWORD`. PR 2 after the UAT: GPU connect/disconnect from the page.
3. **A 3–5 minute backup demo video.**
4. **Thesis Chapter 5 material** (UI, deployment, tests) from the results docs above.

**Owner, 2026-11-24: everything is due before Review 3,** including the slides. The red-team set is done (above); the Q4 vs BF16 accuracy was measured earlier by the owner (figure to add to the W6 table).

**Open:**
- The thesis's location, format and status (D1, owner).
- The repo's `.venv` pip script points at `NewNeuroSymbolic/.venv`: use `.venv/bin/python -m pip`.
- After the defense, delete the RAG answer cache and the demo server's data.

---

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

### Phase 4: answering and the end-to-end pipeline (closed 2026-11-16, branch `phase-4`, not merged or pushed)

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

### Tuning T1 + T3 (public_dev, tuned, T1; 2026-11-16)

Changes: writer prompt `answer/v3@7d0f2b8ddf1f` (T1: `max_tokens` 1200, at most two sentences; the raw writer and fallback replies kept in the trace) and the conditional `which_vehicles` wording (T3), commit `1b0b0d7`. Replays of H1–H3 with `eval/e2e_replay.py` (stored scenes and parsed programs; the fallback was reused everywhere, since its inputs did not change): `9fb18833c8e5`, `fef1a7788379`, `70f1bb045848`. Score output (local): `eval/runs/e2e/score_tuned_T1.json`. **Spend $0.20.** D8 count: 1 of 5.

| pooled over H1–H3 | step 2 | T1 |
|---|---|---|
| overall | 80.7% | **81.0%** |
| strict | 77.1% | 77.8% |
| Yes/No | 83.3% | 83.3% |
| Natural QA | 78.4% | 79.0% |
| non-duplicate (n=57; 95% CI) | 85.1% (74–92) | 85.1% (74–92) |
| rule coverage | 54.9% | 54.9% |
| rules-only (n=84) | 86.9% | 87.5% |
| writer status | 83 first try, 7 template | 89 first try, 1 regenerated |
| **template rate** | 7.8% | **0.0%** |
| faithfulness | 100% | 100% |
| fallback failures | 6 | 6 (unchanged until T2) |

- **Gate (D5): PASS.** Faithfulness 100% (90 of 90), template rate 0% (≤ 5%).
- Per run, overall: T1-H1 82.4% (from 81.4%), T1-H2 82.4% (82.4%), T1-H3 78.4% (78.4%).
- **The one score change:** `0092` in H1, 0.5 → 1.0 (T3): "Xe ba bánh và bốn bánh thô sơ bị cấm trong khung giờ 05:00 - 13:00 và 16:00 - 22:00 ghi trên biển phụ." In H2 and H3, `0092` goes to the fallback.
- The 7 former template cases (`0026` ×3, `0094` ×3, `0065`) now pass on the writer's reply. Their scores are unchanged; `0094` stays wrong (the gold plate reading, the owner's decision).
- The one regeneration: `0026` in H2. The first reply opened a true/false answer without "Đúng"; the second passed.

### Tuning T2 (public_dev, tuned, T2; 2026-11-16)

Change: fallback prompt `answer_fallback/v2@8678a19681a9` (a structured-output schema for {verdict, answer} on the fallback call only, plus "claim nothing about a sign that is not in the scene graph"), commit `905f717`. Replays of the T1 runs (writer v3 kept; every fallback question asked again): `361287ed6b2f`, `34822ca744ea`, `1ce1a8d55ffd`. Score output (local): `eval/runs/e2e/score_tuned_T2.json`. **Spend $0.59.** D8 count: 2 of 5.

| pooled over H1–H3 | T1 | T2 |
|---|---|---|
| overall | 81.0% | **81.7%** |
| strict | 77.8% | 79.1% |
| Yes/No | 83.3% | 83.3% |
| Natural QA | 79.0% | 80.2% |
| non-duplicate (n=57; 95% CI) | 85.1% (74–92) | 86.8% (76–93) |
| rule coverage | 54.9% | 54.9% |
| rules-only (n=84) | 87.5% | 87.5% |
| fallback answers correct (69) | 50.5 (73.2%) | 51.5 (74.6%) |
| fallback first-try JSON | 37 of 69 | **68 of 69** |
| fallback failures (P3) | 6 | **1** |
| template rate, faithfulness | 0%, 100% | 0%, 100% (85 writer answers) |

- **Gate (D5): PASS** (template 0 of 85, faithfulness 100%).
- Per run, overall: T2-H1 84.3% (from 82.4%), T2-H2 78.4% (82.4%), T2-H3 82.4% (78.4%).
- **The format problem is gone, the answers barely move.** 17 question scores changed, all on fallback answers: +6.5 and −5.5, net +1 over 153. Most changes are Sonnet answering the same inputs differently, not the prompt; e.g. `0068` flips Sai/Đúng between runs, and `0087`'s near-identical height-limit answer is graded 0.5 or 1.
- **The one failure is new:** `0038` in H2 stopped at `max_tokens=1500` while the kept reply is a short complete JSON object, so the budget almost certainly went to the model's reasoning. Raising it would be a new prompt version (not done; owner's call).
- The new scene-graph line may make the fallback more cautious: `0038` in H1 answered "Chưa xác định được" (1 → 0), but `0038` in H3 went 0 → 1.

### Tuning T4: perception replay (tuned, after the gate; 2026-11-16; no API calls)

Change: in `vqa/perception/fallback.py`, after `combine`, when a crop agrees with pass 1's main code, pass 1's own alternative for that sign (from its reply's `alt` field, not the re-run's) is dropped (`FallbackConfig.drop_own_alt_on_agree`, on by default). The re-run's alternatives are told apart by the merge's "the re-run read ..." messages, now passed to the fallback. CHOSEN_POLICY, the triggers and the prompts are unchanged.

Free replay with the stored tile and crop replies (`perception_eval.fallback_run --replay`): T4 off reproduces every stored scene exactly (36/36, 36/36, 45/45 ×5).

| run (crop_always) | images changed | alternatives dropped | code F1 | sign recall |
|---|---|---|---|---|
| set T, Haiku `d1ff09db5bf4` | 9 of 36 | 10 | 73.5% → 73.5% | 89.2% → 89.2% |
| set T, Sonnet `a366b7c37100` | 4 of 36 | 5 | 78.7% → 78.7% | 95.8% → 95.8% |
| public_dev Haiku `9981d8112688` (checkpoint 2) | 6 of 45 | 6 | 74.2% → 74.2% | 89.5% → 89.5% |
| public_dev Haiku `023c1a474288` (checkpoint 2) | 5 of 45 | 6 | 75.4% → 75.4% | 90.2% → 90.2% |
| public_dev Haiku `b83d5dae690e` (checkpoint 2) | 3 of 45 | 6 | 77.1% → 77.1% | 90.2% → 90.2% |
| public_dev Haiku `1c9ca7368074` (H2) | 6 of 45 | 7 | 73.8% → 73.8% | 92.3% → 92.3% |
| public_dev Haiku `b490cd60479f` (H3) | 8 of 45 | 10 | 71.8% → 71.8% | 91.6% → 91.6% |

- **Code F1 and recall do not change**, by construction: they score each sign's main code, and T4 only removes alternatives. Strict F1 and the non-duplicate F1 are unchanged too.
- **What the dropped alternatives were** (50 in all, against gold): main code right and alternative wrong 33; both on the same catalog row 5; main wrong and alternative right **1** (set T, Haiku); both wrong 4; sign not matched or excluded 7.
- **End-to-end preview, engine only** (the T2 runs' stored programs on the T4 scenes): 30 questions sit on changed images; **10 "uncertain" answers become rules answers** (`0036` ×3, `0038` ×3, `0037`, `0072`, `0086`, `0093`), 3 stay uncertain, the rest keep their verdict. The paid replay grades them.

### Tuning T4: end to end (public_dev, tuned, T4; 2026-11-16)

Replays of the T2 runs with the T4 scenes (`--allow-scene-changes`; scenes changed on 6, 6 and 8 images, as the free replay found): `2a108f86371b`, `3c127f06d946`, `c8880835ee4a`. Score output (local): `eval/runs/e2e/score_tuned_T4.json`. **Spend $0.25.** D8 count: 3 of 5.

| pooled over H1–H3 | step 2 | T1 | T2 | **T4** |
|---|---|---|---|---|
| overall | 80.7% | 81.0% | 81.7% | **84.6%** |
| strict | 77.1% | 77.8% | 79.1% | 82.4% |
| Yes/No | 83.3% | 83.3% | 83.3% | 81.9% |
| Natural QA | 78.4% | 79.0% | 80.2% | **87.0%** |
| non-duplicate (n=57; 95% CI) | 85.1% (74–92) | 85.1% (74–92) | 86.8% (76–93) | **96.5% (88–99)** |
| duplicate (n=96) | 78.1% | | | 77.6% |
| rule coverage | 54.9% | 54.9% | 54.9% | **61.4%** |
| rules-only | 86.9% (84) | 87.5% (84) | 87.5% (84) | 88.8% (94) |
| fallback rate | 45.1% | 45.1% | 45.1% | 38.6% |
| fallback failures | 6 | 6 | 1 | **0** |
| template rate, faithfulness | 7.8%, 100% | 0%, 100% | 0%, 100% | **0%, 100%** (94 writer answers) |

- **Gate (D5): PASS.** Faithfulness 100% (94 of 94), template rate 0%.
- Per run, overall: T4-H1 87.3%, T4-H2 81.4%, T4-H3 85.3%.
- **What T4 changed:** 10 "uncertain" triggers became rules answers (uncertain triggers 34 → 24), all graded right or as before:
  - `0036` ×3 (P.131b, odd days);
  - `0037` in H3;
  - `0038` ×3;
  - `0072` in H1;
  - `0086` and `0093` in H2.
- **Score changes caused by the fallback being called again** (on a changed image whose question still goes to it):
  - `0092` in H2: 0.5 → 1;
  - `0005` in H2: 1 → 0 (it now answers "Chưa xác định được");
  - `0001` in H3: 1 → 0.5 (a slip in the parenthesis on even/odd days).
- **Perception metrics are unchanged** (code F1 and recall, previous section): T4 shows only end to end.
- The non-duplicate gain is large but from 57 questions (19 per run, shared images), so its CI is wide.
- **Phase-4 spend so far: about $3.32** of the $10 ceiling (step 2 $2.20, T1 $0.20, T2 $0.59, T4 $0.25, plus earlier test calls).

### Step 5: the freeze (owner, 2026-11-16)

**Freeze approved; no fourth tuning run.** The last development figures are the T4 table above (public_dev, tuned): overall 84.6%, strict 82.4%, Yes/No 81.9%, Natural QA 87.0%, non-duplicate 96.5% (95% CI 88–99, n=57), rule coverage 61.4%, rules-only 88.8%, fallback rate 38.6%, faithfulness 100%, template rate 0%.

**The frozen configuration** is recorded in `eval/frozen_phase4.json` (committed; `eval/freeze.py show | check`):

| stage | prompt id | model, effort, max_tokens |
|---|---|---|
| perception | `scene/v4@153536ec5975` | Haiku 5.5, medium, 8000; re-run on |
| scene fallback: tiles | `scene/v4-tile@a052a9fc72f7` | Haiku 5.5, medium, 8000 |
| scene fallback: crops | `scene/v4-crop@30e2d18b84d9` | Haiku 5.5, medium, 3000 |
| scene fallback: combining | CHOSEN_POLICY `crop_always`, `drop_own_alt_on_agree` true (T4) | |
| parser | `parser/v6@2d0ec50e3611` (sha256 of the system prompt) | Sonnet 5.5, medium |
| answer writer | `answer/v3@7d0f2b8ddf1f` | Haiku 5.5, low, 1200 |
| answer fallback | `answer_fallback/v2@8678a19681a9` (schema.json) | Sonnet 5.5, medium, 1500 |
| judge | `judge/v1@7c500c35df27` | Opus 5.5, medium, 1500 |

- The record also holds the full sha256 of each prompt and the PipelineConfig defaults (context year 2025). The run-specific fields (`cache_dir`, `cache_only`, `max_spend`) are left out.
- `tests/test_freeze.py` checks that the current defaults and prompt pins equal the record, and that the pipeline calls the models it names.
- **Holdout guards** (`eval/e2e_holdout.py`, tested). The run refuses to start unless:
  - `--confirm-frozen` is given;
  - the git working tree is clean;
  - the live configuration equals the record;
  - the holdout has never run: no committed sentinel `eval/holdout_ran.json` and no aggregate file.
- The sentinel is written before the first call, so a run that stops part way still counts as the one run.
- The aggregate report records the git commit, the full frozen configuration and the prompt ids.

### Step 6, first start stopped before any call (2026-11-16)

The first holdout start (run `ec99ce25eb37`, 07:31 UTC, commit `db587c1`) stopped before any API call, with `KeyError: 'public_holdout'`:
- **Cause:** the default image resolver called `gold_signs.image_path`, which knows only train and public_dev. The test had passed its own resolver.
- **What happened:** the usage log has no call after the start; nothing was answered, scored or printed. Only the sentinel `eval/holdout_ran.json` (status `started`) was written, as designed.
- **Fix:** `e2e_holdout.image_file` reads the public test image folder. Tested, including a run through the default resolver; all 49 holdout questions' images resolve (count only).
- **The sentinel is left in place and uncommitted:** whether this start counts as the one run is the owner's decision.
- **Voided by the owner (2026-11-16):**
  - the start: sentinel run_id `ec99ce25eb37`, started 2026-11-16T07:31:29 UTC at commit `db587c1`;
  - the error: `KeyError: 'public_holdout'`;
  - the usage log has no API call after 07:31 UTC, and the start produced no result.
  - The sentinel `eval/holdout_ran.json` was deleted (never committed). The one holdout run is still to come.

### Step 6: public_holdout, once, frozen (2026-11-16)

Run `0ec3209c0324`, 07:37–08:11 UTC, at commit `2528621` with the frozen configuration. Guards passed: clean tree, live configuration equal to `eval/frozen_phase4.json`, no earlier run. Fresh perception, no cache.
- Prompt ids: `scene/v4@153536ec5975`, `scene/v4-tile@a052a9fc72f7`, `scene/v4-crop@30e2d18b84d9`, `parser/v6@2d0ec50e3611`, `answer/v3@7d0f2b8ddf1f`, `answer_fallback/v2@8678a19681a9`, `judge/v1@7c500c35df27`.
- 49 questions on 45 images, aggregate figures only. The report is `eval/runs/e2e/holdout_aggregate_0ec3209c0324.json` (local; no question or image ids). The sentinel `eval/holdout_ran.json` is committed with this entry.
- **Spend $0.62**; phase 4 total about $3.94 of the $10 ceiling. 39.7 s and $0.0127 per question.

| | **public_holdout (once, frozen)** | public_dev (tuned, T4, pooled over 3 runs) |
|---|---|---|
| questions | 49 (Yes/No 13, Natural QA 36) | 153 (Yes/No 72, Natural QA 81) |
| **overall** | **83.7%** (41 of 49) | 84.6% |
| strict (partial = 0) | 81.6% | 82.4% |
| Yes/No | 100% (13 of 13) | 81.9% |
| Natural QA (judge) | 77.8% (27 correct, 2 partial, 7 wrong) | 87.0% |
| **non-duplicate images** (95% CI) | **89.6%** (21.5 of 24; 72–97) | 96.5% (88–99; n=57) |
| duplicate images (also in train) | 78.0% (19.5 of 25) | 77.6% |
| rule coverage | 51.0% | 61.4% |
| rules-only | 78.0% (19.5 of 25) | 88.8% (94) |
| fallback answers | 89.6% (21.5 of 24) | |
| fallback rate | 49.0% | 38.6% |
| fallback triggers | out_of_scope 9, uncertain 9, unreadable_sign 2, unknown 2, program_cannot_run 1, parse_failed 1 | |
| fallback failures | 0 | 0 |
| faithfulness | 100% (25 writer answers) | 100% (94) |
| template rate | 0% | 0% |

- **This is phase 4's real measure**, reported as it came out. Nothing is changed after it.
- **Overall is close to the tuned public_dev figure** (83.7% vs 84.6%); the parts differ:
  - the holdout has fewer Yes/No questions (13 of 49), and all 13 are right;
  - Natural QA is lower (77.8% vs 87.0%);
  - the rules answer fewer questions (coverage 51.0% vs 61.4%), and less accurately (rules-only 78.0% vs 88.8%);
  - the fallback carries more of the score (21.5 of 24).
- **Non-duplicate images: 89.6%** on 24 questions. The CI (72–97) is wide and overlaps the tuned public_dev interval; the tuned 96.5% did not hold up at that level.
- Gate (roadmap phase 4, D5) was measured on public_dev and passed. On the holdout, faithfulness is 100% and the template rate 0%.

### Phase 4: closing (2026-11-16)

**Phase 4 is closed:** no API calls, no push, no phase-5 code. The branch `phase-4` is not merged into `main`.

**Commits (`main..phase-4`, oldest first):**
- **Plan:** `a5133c9` plan approved.
- **Items 1–5:**
  - `61c3bbf` writer, guard, templates, answer/v1;
  - `557c5ff` raw pass-1 replies, backfill-raw, warm;
  - `c42f4cd` answer/v2;
  - `a74a1e2` answer-level fallback and pipeline;
  - `274db32` e2e eval, oracles, judge, holdout, leakage tests.
- **Oracle A diagnosis and item 1b:**
  - `35020d7` diagnosis;
  - `83ee6b8` plan 1b;
  - `674641d`, `5f486fb`, `4b07a60`, `c0d8b90` engine and KB fixes 1b.1–1b.4;
  - `18081b0` oracle A rerun;
  - `8b588c5` gold fix for 0094 (owner).
- **Step 2:** `10347dc` results and diagnosis.
- **Tuning:**
  - `1b0b0d7` T1 + T3 and the replay tool, `696fefd` T1 results;
  - `905f717` T2, `0861365` T2 results;
  - `e1044b3` T4, `f309265` T4 results.
- **Freeze and holdout:**
  - `db587c1` freeze record and holdout guards;
  - `8b71beb` holdout image fix;
  - `2528621` voided start;
  - `ab7261a` holdout result;
  - `741a02a` aggregate-only wording.

**Frozen configuration** (`eval/frozen_phase4.json`):

| stage | setting |
|---|---|
| perception | Haiku 5.5 `scene/v4@153536ec5975` with the re-run |
| scene fallback | tiles `scene/v4-tile@a052a9fc72f7`, crops `scene/v4-crop@30e2d18b84d9`, `crop_always`, `drop_own_alt_on_agree` (T4) |
| parser | Sonnet 5.5, medium, `parser/v6@2d0ec50e3611` |
| answer writer | Haiku 5.5, low, `answer/v3@7d0f2b8ddf1f` |
| answer fallback | Sonnet 5.5, medium, `answer_fallback/v2@8678a19681a9` |
| judge | Opus 5.5, medium, `judge/v1@7c500c35df27` |

**Results:**
- public_holdout, once, frozen: 83.7% overall; 89.6% on non-duplicate images (n=24, 95% CI 72–97).
- The rules scored 78.0% on their 25 answers, below the fallback's 89.6% on 24; on public_dev (tuned) it was the reverse, 88.8% against 78.0%.
- The gate (D5) passed on public_dev after T1.

**Spend, from `logs/api_calls.jsonl`** (calls from the phase-4 start at 04:53 UTC; 1,854 calls):

| purpose | calls | USD |
|---|---|---|
| judge (Opus) | 335 | 1.730 |
| answer fallback (Sonnet) | 260 | 0.955 |
| parser (Sonnet) | 278 | 0.757 |
| answer writer (Haiku) | 485 | 0.129 |
| scene, re-run, tiles, crops (Haiku) | 496 | 0.368 |
| **total** | 1,854 | **$3.94** of the $10 ceiling |

**Open items:**
- **`0094`'s gold plate reading** (the owner's decision). It affects the oracle runs only, not the holdout figure.
- **`0068`, disputed gold answer.** The gold answer is Sai; the engine's Đúng (the S.505a plate is a truck) is believed correct. It is scored as is.
- **Deferred KB items:**
  - the B.25 overtaking exception ("kể cả xe được ưu tiên", `0011`);
  - the warning-sign rule;
  - counting signs;
  - guide-sign content.
- **Catalog rows awaiting the owner's review:**
  - `kb/sign_catalog.yaml`: 78 of 80 rows not `reviewed_by: human`, including the effect_unmodelled rows R.302(a,b,c), R.303, R.411, R.420 and R.403a, R.403b, R.404a, R.307. 45 rows have no visual review.
  - `kb/sign_catalog_meaning.yaml`: 110 of 149 rows not `reviewed_by: human`; visual review: 124 none, 5 assistant (W.242(a,b), W.243(a,b,c), IE.451a, IE.471, IE.473).
- **Carried over:**
  - the parser version key should include the catalog hash (the freeze record now hashes the parser's full system prompt, catalog included);
  - standalone local notices are not modelled;
  - the private gold labels and the pictogram ablation (proposed).

### Phase 5: benchmark and evaluation (in progress, branch `phase-5`)

- **Plan approved (owner, 2026-11-16)**: `docs/plans/phase-5.md` (P1–P11; the draft is removed). `phase-4` merged into `main` at `5e1664c` (no push); `c054b83` plan and the CLAUDE.md P6 exception (only the owner reads private answers, for human scoring, after every automatic score is committed).
- **Item 1 built, not run:** `eval/e2e_private.py` (no API calls made).
  - Guards as the holdout's: `--confirm-frozen`, clean tree, live configuration equal to `eval/frozen_phase4.json` with its perception model (Haiku 5.5), never run (sentinel `eval/private_ran.json`, no `private_aggregate_*.json`), git ignores the replay folder; counts (146 questions, 104 images) and every image file checked before the sentinel.
  - Aggregate-only report: commit, frozen configuration, prompt ids, catalog review state, overall / strict / Yes/No / Natural QA, all and non-duplicate images (against train and public, Wilson CI), rule coverage, rules-only and fallback scores, score per trigger, faithfulness, template rate, cost and seconds per question, and the by-feature breakdown.
  - **The feature rules are new** (`e2e_private.FEATURES`): the rules behind DESIGN's section 8 table were never committed. On train (rewritten by the owner) they give claim 8%, vehicle class 30%, turns etc. 18%, speed 13%, lanes 9%, time 12%, meaning 20%, weight/seats 5%, violation 3%.
  - Replay records (P4) under `cache/private_run/<run_id>/` (gitignored): the run's scene cache and `records.jsonl` (model outputs and trace; no gold, no question text, no grade).
  - Tests: `tests/test_e2e_private.py` (31) and two leakage tests (only this module names the private question file; it prints counters only). Full suite 840 passed.
- **Estimate for the private run:** $1.83 (holdout rate $1.85; range $0.9–2.7), about 97 minutes.

### Two-pass perception trial (set T; public_dev tuned), 2026-11-16

A perception-only trial of the original two-pass design (owner's brief): **find** (one Haiku call on the photo: boxes, coarse type, look, rank, side; no codes), then **read** (all crops of one photo in one call, 20% padding, each crop with its coarse type's candidate list, the v4 pictograms, and an escape to the full catalog or UNKNOWN), then the existing wire conversion and verification unchanged (no re-run). Eval-only: `eval/two_pass_trial.py`, prompts `scene/v5-find-trial@61b2089130a3` and `scene/v5-read-trial@04e209a5fb40` (pinned by sha256), `9383678`. Nothing in `vqa/`, the freeze record, the existing prompts, gold, holdout or private changed. **No decision on adopting it.**

- **Runs:** Haiku 5.5, medium, one run per set, no cache. Set T `8fa0b31b88cb` ($0.0516), public_dev `37386c61f54d` ($0.0617); total **$0.113**. A first start (`9abb86f3b44e`) stopped before any call (no API key in the shell; $0, header-only file). No failed images, no retries.
- **Compared with:** frozen Haiku v4 + fallback: set T `d1ff09db5bf4` (over pass 1 `4e6780670d2f`), public_dev the mean of checkpoint-2 runs `b83d5dae690e` / `023c1a474288` / `9981d8112688` (which reproduces 89.98% / 75.6%). Scoring: perception_gate_v2, bootstrap CIs over images.

| | set T trial | set T frozen | public_dev trial (tuned) | public_dev frozen, mean of 3 |
|---|---|---|---|---|
| sign recall, all (95% CI) | **95.8%** (92–100) | 89.2% (81–96) | **93.7%** (88–100) | 90.0% (85–96) |
| code F1, all (95% CI) | 67.1% (59–76) | **73.5%** (67–81) | 66.7% (61–73) | **75.6%** (69–83) |
| code F1 strict | 67.1% | 70.9% | 65.4% | 74.9% |
| rule-bearing F1 | 78.9% | 77.3% | 75.6% | 78.8% |
| value accuracy | 100% | 100% | 89.5% | 86.4% |
| non-duplicate: recall / code F1 | 94.4% / 68.0% (26 images) | 88.9% / 74.7% | 100% / 73.0% (17 images) | 86.4% / 74.9% |
| cost per image | **$0.0014** | $0.0028 | **$0.0014** | $0.0028 |

- **One run per set.** Haiku's code F1 varies about 2.9 points between runs, so a gap smaller than that is not evidence. public_dev is tuned (its errors were seen in phase 3 and 4).
- **The trade:** the find step lists more: fewer misses (set T 13 → 5; public_dev 14.3 → 9) but many more false positives (7 → 51; 15 → 41), most of them objects read as UNKNOWN (33 of 51; 30 of 41). Code F1 falls by 6.4 (T) and 8.9 (public_dev) points, beyond the run-to-run spread.
- **Against the frozen scene on the same image** (public_dev: mean over the 3 frozen runs):

  | | set T | public_dev |
  |---|---|---|
  | codes fixed / broken (right → wrong) | 16 / 6 | 12 / 14.3 |
  | misses removed / added | 10 / 2 | 10.3 / 5 |
  | numbers fixed / broken | 0 / 0 | 1.7 / 1.3 |
  | plates fixed / broken | 3 / 2 | 3.7 / 1.3 |

- **Error kinds** (trial vs frozen): confident wrong codes rose (T 6 → 11; public_dev 10.7 → 15), most within the right coarse type (7 and 11), so candidate lists did not stop them; low/UNKNOWN wrong codes fell on T (15 → 8) and rose on public_dev (9.7 → 13).
- **Escape:** used on 11 of 178 sign crops (T) and 5 of 200 (public_dev), counted from the code; the model flagged 12 and 5. Free check on gold before the run: 5% (T) and 4% (public_dev) of gold codes fall outside their coarse type's list.
- **Plates:** 14 (T) and 25 (public_dev) plate objects; 12 and 17 assigned by the read pass's `belongs_to`, the rest by geometry; plates missing on right-code signs 6 → 6 (T), 6.3 → 5 (public_dev).
- **Before the run (free):** today's errors on set T were 13 misses, 6 confident wrong codes, 15 low/UNKNOWN wrong codes, 0 of 14 wrong numbers, 9 of 14 wrong plates (6 missing); public_dev (mean of 3): 14.3, 10.7, 9.7, 2.3 of 17, 9 of 17.3.
- Report code changed after the runs, scoring only: a key-name typo, and false positives split by UNKNOWN. Re-scoring is free from the stored replies (`two_pass_trial.py report`, `rebuild`).

### Two-pass trial: free variants and the phase-4.5 option (2026-11-16; no API calls)

- `eval/two_pass_variants.py` (stored replies and runs only; nothing in `vqa/` changed): **trial minus UNKNOWN** (UNKNOWN signs dropped after the fact) and **hybrid** (frozen scene plus trial signs with a catalog code whose box overlaps no frozen sign), scored like the trial, plus an engine-only answer replay. public_dev frozen scenes are those of the frozen runs H1-H3 (perception `9981d8112688`, `1c9ca7368074`, `b490cd60479f`, rebuilt with T4; the replay reproduces all 153 stored routes and verdicts). Set T uses `d1ff09db5bf4`'s stored scenes (no raw replies, so pre-T4).
- **Code F1, set T / public_dev (tuned):** frozen 73.5% / 73.3%; trial 67.1% / 66.7%; minus UNKNOWN **77.4% / 76.5%**; hybrid 74.7% / 73.9%. Recall: frozen 89.2% / 91.1%; trial 95.8% / 93.7%; minus UNKNOWN 93.3% / 88.8%; hybrid 94.2% / 92.8%. One trial run; Haiku varies about 2.9 points of code F1 between runs.
- **Minus UNKNOWN loses real signs:** 4 of the 44 dropped on set T and 9 of 51 on public_dev matched a readable gold sign.
- **Answers (public_dev, 153 question-runs):** trial 43 changed, graded net −6, estimate −3.5; minus UNKNOWN 44 changed, graded net −9, bounds −30.5 to −1.5; hybrid 4 changed, net 0, estimate +0.3. Set T: only 6 questions have a program without a parser call; the hybrid changes none, the others 2 each (ungraded).
- **Recommendation: keep the frozen system** (`docs/plans/phase-4.5-option-perception.md`, an option, not approved). Cost per image as a real pipeline: frozen $0.0028, minus UNKNOWN $0.0014, hybrid $0.0042.

### Change of requirement: rules-only report; private run on hold (owner, 2026-11-16; no API calls)

- **The report counts rule-based answers only** (the fallback is for the demo). Decided = the rules answer yes / no / value; target about 80% decided coverage. The private run is **on hold** (`docs/plans/phase-5.md`).
- **Rules-only figures** (`eval/coverage_analysis.py`, stored runs only):
  - public_dev T4 (H1-H3 pooled, tuned): decided **61.4%** (54–69), accuracy on decided 88.8%, overall with non-decided wrong 54.6%;
  - **public_holdout** (aggregate only): decided **51.0%** (37–64), accuracy on decided **78.0%**, overall **39.8%** (27–54);
  - oracle A (gold scenes and programs, today's engine): decided 72.5%, accuracy on decided 89.2%.
- **Non-decided public_dev question-runs (59 of 153):**
  - uncertain 24 (the alternative from pass 1's own alt 11, a crop 9, the re-run 4);
  - out_of_scope 24 (guide-sign content 3 questions, warning-sign behaviour 2, counting 1, traffic lights 1, open advice 1);
  - unreadable sign 7, unknown lane count 2, parse failed 2.
  - Deciding uncertain answers on the primary reading gets Yes/No right only 4 of 7.
  - The two-pass variants change decided coverage by −3.2 to +2.0 points.
- **Validation pool:** 197 train questions on 114 untouched images (no set T, gold, few-shot, prompt, fixture, test, kb or docs mention, no duplicate with public, private or an excluded image).
- **Proposed:** `docs/plans/phase-4.5.md` (fixes ranked by coverage per day, targets fixed now, validation set, new freeze, then the private run once with rules-only figures as the main result). Not approved; nothing built.

### Phase 4.5: started (approved 2026-11-16)

- **Plan approved** (owner, Q1–Q6; targets fixed: 80% decided coverage is the aim, the 70% floor must hold). `phase-5.md` updated: private run held until the phase-4.5 freeze, P11 replaced, A1 (no fallback) is the main system.
- **Item a built (no API calls):**
  - **Validation set** `data/splits/train_validation.json` (`eval/make_validation_split.py`, seed 20261116): **110 questions on 54 images** (Yes/No 53, Natural QA 57) from the 197-question untouched pool, Yes/No images drawn first. Ids only; aggregate only (CLAUDE.md).
  - **Fallback-off switch:** `PipelineConfig.answer_fallback` (default on, the frozen behaviour). Off, a non-decided question gets the engine's template answer, with no fallback or writer call, and `answered_by: not_decided`; decided answers are unchanged. Left out of the freeze comparison (`freeze.POST_FREEZE_SWITCHES`), since the phase-4 record lists its run-specific fields verbatim; `freeze check` still matches.
  - **Runner** `eval/e2e_validation.py`: labels `baseline` (frozen phase 4) and `final` (phase-4.5 freeze), holdout-style guards, its own sentinels, aggregate only (the three figures with Wilson CIs, causes, by type, targets and floors).
  - Tests: `tests/test_validation.py` (18), fallback-off pipeline tests (4), the freeze switch test; leakage scan extended. Full suite 927 passed.
- **Baseline estimate:** $0.67 (range $0.34–1.01; $0.88 if every question is decided), about 55 minutes.

### Phase 4.5 baseline validation (Q4), once, frozen phase-4 system, fallback off (2026-11-16)

Run `5c9251f5f207`, 15:47–16:25 UTC, at commit `2e1ff41`, with `eval/frozen_phase4.json` (prompt ids as phase 4). Guards passed. Fresh perception. 110 untouched train questions on 54 images (split sha256 `b23e283a748b…`). **Aggregate only:** the report `eval/runs/e2e/validation_aggregate_baseline_5c9251f5f207.json` (local) has no question or image ids. Sentinel `eval/validation_ran_baseline.json` committed with this entry. **Spend $0.663** ($0.0060 and 20.3 s per question).

| | baseline (validation, 110) | target | floor | public_holdout | public_dev T4 (tuned) |
|---|---|---|---|---|---|
| **decided coverage** (95% CI) | **30.0%** (22–39) | 80% | 70% | 51.0% | 61.4% |
| **accuracy on decided** (95% CI) | **72.7%** (56–85; strict 63.6%) | 88% | 85% | 78.0% | 88.8% |
| **overall, non-decided = wrong** (95% CI) | **21.8%** (15–30) | 70% | 60% | 39.8% | 54.6% |

- **Not decided (77 of 110), by cause:** out_of_scope 43, uncertain 12, unreadable sign 8, program can't run 8, unknown 4, parse failed 2.
- **By question type:** Yes/No 16 of 53 decided (30.2%), 87.5% right; Natural QA 17 of 57 decided (29.8%), 58.8% right (judge: 7 correct, 6 partial, 4 wrong).
- **Every target and floor is missed at the start**, as expected for a baseline. The main gap is out_of_scope: 39% of validation questions against 16% on public_dev. The fixes in `phase-4.5.md` were sized on public_dev's causes, so on this set they cover a smaller share of the gap.
- Nothing is tuned on this run. The validation questions stay unread; the targets don't move.

### Phase 4.5 scope round: dev run and analysis (2026-11-17)

- **Dev run** `13ded0d75451` (frozen system, fallback off, 87 dev questions, all Natural QA): decided **40.2%** (31–51), accuracy on decided **80.0%** (64–90), overall 32.2%. **$0.612**; round spend $0.61 of $5.
- **52 undecided:** parser wording or selector 5, new sign-group slot 4, perception 4, new types with a law basis 31 (guide-sign content 21, conduct 4, STOP 2, placement 2, presence 1, scope 1), out of scope with no law article or outside v1 8 (speed by road type 4, speed range 2, lights 1, why 1).
- **Wrong or partial decided (7 points):** missing expressway rule (Law 36 art. 25), missing S.501 plate, P.127's vehicle coverage, a group name, two `choose` answers with unknown options counted as decided, R.411 without lane rows, one misread guide sign.
- **`law_db` has no article for speed limits by road type,** so those questions stay out.
- **Proposed** (`docs/plans/phase-4.5.md` section 10, awaiting approval): ranks 1–8 (accuracy, expressway, selector and lane fixes; parser v7; sign group; conduct + STOP; presence; scope and placement), about $2.55 and 8.5 days, projected dev coverage about 58%; rank 9 (guide-sign content) only past a stopping point.

### Phase 4.5: coverage first; stage A proposal (owner, 2026-11-17; no API calls)

- **Priorities changed** (`phase-4.5.md` section 11): keep a change if dev overall doesn't drop and accuracy on decided stays ≥ 70%. Success = final validation coverage and overall outside the baseline's CI, accuracy reported. CLAUDE.md gains the knowledge-based-rule exception.
- **Stage A, step 1** (`eval/sign_popularity.py`, train only): of the 80 most popular codes, 38 modelled, 37 meaning-only, 4 effect_unmodelled, 1 missing (R.415). Train text names codes almost never; the ranking rests on gold and perception readings.
- **Steps 2–4 proposed** (`docs/plans/phase-4.5-stageA-signs.md`, awaiting the owner's OK): family templates F3–F7 (new effect keys `zone`, `conduct`, `permits`, `pass_side`, `yield_from`, `informational`), rows R.415(a,b), R.122, S.501; 7 knowledge-based rules (KB-1–KB-7) plus an optional KB-8.
- **Two findings:** speed limits by road type come from Circular 38/2024, outside the allowed sources, so they stay out. The approved rank-1 item "P.127 covers every vehicle" contradicts QCVN 41 B.27 (motor vehicles only); the proposal replaces it with a parser v7 fix in stage B.
- Round spend unchanged: $0.61 of $5.

### Phase 4.5 stage A built (2026-11-17; no API calls)

- **Built:**
  - rank 1 (choose with an unknown option → unknown; R.411 bears on direction claims; art. 11 group names);
  - families F3–F7, with effects for 37 meaning rows in `kb/sign_catalog_effects.yaml` and new rows R.421, R.122, S.501 (R.415 was not missing);
  - rank 2 (`kb/rules/zones.pl`: expressway entry and stopping, Law 36 art. 25; KB-8 law-cited, Law 36 art. 18.4 i; Circular 38/2024 default speeds as interpretations);
  - rank 3 (selector colours, KB-6).
- "P.127 covers every vehicle" was dropped (B.27: motor vehicles only).
- **Frozen prompts stay reproducible** (`listed_from: phase45` rows are left out of scene v1–v4 and parser v1–v6 listings); `freeze check` still matches the phase-4 record.
- **Dev replay:** decided 35 → 32 (40.2% → 36.8%), accuracy on decided **80.0% → 93.8%**, overall **32.2% → 34.5%**. The guardrail holds at every step. Grades for 81, 287 and 308 are provisional (assistant-graded).
- Tests 982 passed. Round spend unchanged: $0.61 of $5.
- **Stage-B proposal** (`phase-4.5.md` section 12): B1–B5 about 6 days and $2.57; B6 guide content gated, about 3.5 days and $0.80. Awaiting the owner's decision.

### Phase 4.5 stage B, step 1: scene v5 and the B6 guide test (2026-11-17; no API calls)

- **Stage B approved** (`phase-4.5.md` section 13): B3 and the B6 test first, then B1 + B2 by type, then B4, with B6 gated and B5 last. About $0.70 is always kept for the final validation.
- **Scene v5 built:** `scene/v5@7a3291ea5dff`, `v5-tile@d5269387761f`, `v5-crop@cee1140f62d7`, which are v4's files plus the catalog listing with R.421, R.122 and S.501. v4's ids are unchanged; `freeze check` still matches. `perception_eval fallback` uses the tile and crop prompts of the pass-1 run's family.
- **Set-T check (not run):** v5 pass 1 + fallback on set T, about $0.10 ($0.054 + $0.045 measured on v4).
- **B6 guide test built (not run):** `eval/guide_trial.py`, prompt `scene/v5-guide-trial@c921108016d7` (pinned); 24 dev images hand-labelled in `eval/guide_trial/labels_dev.yaml` (assistant-checked). Variant A is the photo alone; variant B adds enlarged crops of the boards the dev scene listed. Estimate $0.04 ($0.06 with margin).
- **Found while labelling:**
  - expressway boards print their own speed discs (80/60, 90/60, 120/60), which v4 never read; that is the cause of dev 254, 352, 381 and 413;
  - two dataset answers disagree with their boards (train_230 direction and distance; train_248 calls a blue minimum-speed disc a maximum).
- Tests 995 passed. Round spend $0.61 of $5.

### Scene v5 set-T check (2026-11-17)

- **Runs:** v5 pass 1 `82fe91ce935e` ($0.055) + fallback `3861a1816d1a` (v5-tile / v5-crop, `crop_always`; $0.059). Total **$0.114**; round $0.72 of $5.
- **v5 + fallback** against frozen v4 + fallback (`d1ff09db5bf4`), set T, development:
  - recall 90.8% (85–97) against 89.2% (81–96);
  - code F1 72.9% (65–81) against 73.5% (67–81);
  - strict 71.3% against 70.9%; rule-bearing 74.8% against 74.5%;
  - non-duplicate recall / F1 91.1% / 73.6% against 88.9% / 74.7%.
- **Passes:** the code-F1 gap (−0.6 points) is inside Haiku's 2.9-point run-to-run spread; the new rows don't hurt reading. One run each.

### B6 guide-board test (dev, 24 hand-labelled images; 2026-11-17)

Run `dev_guide_trial_d454d4d13cfa` (Haiku 5.5, medium, `scene/v5-guide-trial@c921108016d7`), **$0.021**; round $0.74 of $5. Scored against `eval/guide_trial/labels_dev.yaml` (assistant-checked).

| | entry recall | entry precision | distance accuracy | arrow accuracy (strict / lenient) | speed-disc recall / precision | boards on no-text images | cost |
|---|---|---|---|---|---|---|---|
| **A: photo alone** | **93.9%** (46 of 49) | 82.1% | **100%** (15 of 15) | 84.8% / **89.1%** | **100%** (10 of 10) / 71.4% | 0 | $0.009 |
| B: photo + board crops | 81.6% (40 of 49) | 76.9% | 93.3% | 100% / 100% | 100% / 90.9% | 0 | $0.011 |

- **Both clear the bar proposed before the run** (entry recall ≥ 80%, distance ≥ 85%, lenient arrows ≥ 75%, speed recall ≥ 85%, no made-up boards). A has the better recall and costs less.
- **Precision is understated:** most "extra" lines are ones the labels file under `other` (NOI BAI AIRPORT, NHẬP LÀN, KẾT THÚC, the safe-distance board) or bus-stop route lines the labeller judged too small, which Haiku read. The extra speed discs are real discs that aren't on guide boards. No made-up place names were seen.
- **Weak spots:** arrows on a roundabout diagram board (A gave no direction); route plates (QL 1, QL 217) not listed as entries; B merges stacked lines.
- **The speed discs on expressway boards were all read** (80/60, 90/60, 100/60, 120/60), the content behind dev 254, 352, 381 and 413.
- **Recommendation:** B6 is worth building, with variant A's reading (the photo alone, a separate call only on images where perception lists an I/IE board). The decision is the owner's.

### B6 question-level check (dev, variant A's stored output; 2026-11-17; no API calls)

B6 approved (owner, 2026-11-17), variant A, and folded into B1/B2: one parser v7, one gate rerun, one dev re-parse.

**25 dev questions** (the 21 guide-content questions and the 4 that turn on speed discs printed on boards):
- **22 ask about something printed on a board; variant A read all 22 correctly** (against the board).
- **3 are not answered by board text:** 159 (an I.409 pictogram; its meaning comes from the code), 515 (a lane-arrow board with no text: lane directions), 521 (the dataset answer is a generic "Đi theo biển chỉ dẫn").
- **Of the 22, the dataset answer agrees with the board on 19.** It disagrees on 230 (the board says QL 1A right, 2 km; the answer says left, 5 km), 248 (the "40" disc is blue, a minimum; the answer says maximum) and 249 (the board says VSIP 4 km; the answer says it is "ở ngay vị trí đặt biển"). So at best 19 of 25 can match the dataset.

One line each (✓ = the asked fact is right in A's output):
- 80 ✓ directions on the green board (right: H. Thạch Thành, TX. Bỉm Sơn); the answer "Hướng ra" also needs the board's meaning.
- 159 — pictogram only (I.409); A reads no text, correctly.
- 230 ✓ QL 1A right, 2 KM (the dataset disagrees).
- 231 ✓ no line gives a QL 1A–Đông Hà distance, so "Không" follows.
- 248 ✓ min 40 (blue), Đường Tránh Vinh left, Đường Lê Ninh straight (the dataset calls 40 a maximum).
- 249 ✓ VSIP 4 Km (the dataset disagrees).
- 250 ✓ Đường Tránh Vinh left, VSIP 4 km.
- 254 ✓ discs 80 / 60.
- 258 ✓ Cam Lâm 2, Vĩnh Hảo 103, Phan Thiết 204 km.
- 259 ✓ route CT.01, EXPRESSWAY.
- 261 ✓ Phan Thiết 204 km.
- 325 ✓ CT.01 Đà Nẵng – Quảng Ngãi, KẾT THÚC.
- 327 ✓ Chùa Bắc Ngà left.
- 329 ✓ T.T Lộc Bình 10 KM.
- 348 ✓ Cầu Biêu right.
- 352 ✓ discs 90 / 60 (85 km/h is the lawful option).
- 361 ✓ "ĐIỂM DỪNG XE BUÝT".
- 381 ✓ discs 120 / 60 (70 and 110 lawful).
- 397 ✓ Pháp Vân straight.
- 413 ✓ discs 80 / 60.
- 414 ✓ QL.10 2 KM, TP.Hải Phòng 24 KM, Quốc lộ 5 slight right.
- 415 ✓ next exit QL.10 2 KM.
- 515 — lane arrows without text: not board text.
- 521 — generic answer.
- 525 ✓ Quốc lộ 1 straight.

### Phase 4.5 B1 + B2 built (2026-11-17; no API calls)

Commits `dee78d7` (B1 types), `3f0243a` (B6 guide content), `d295c32` (parser v7), and the B4 tooling commit. Suite 1080 passed; `eval/freeze.py check` matches the phase-4 record.

**Review of the WIP `0cd33cf`, fixed before building on it:**
- the group aspect refused any scene with an unreadable candidate; it now drops and lists it, as `Engine.single_sign` does (dev 160);
- conduct cited art. 22 / 32 (the name lists); now art. 21 / 27 / 31, the articles that say "phải chấp hành" and what warning signs require;
- the scope line took an S.502 distance (distance *to* the section) as the scope; only S.501 counts;
- presence matched by catalog row, so P.124a stood for P.124b; it now matches the sign's own code;
- `board_read` was imported from the engine inside a loop in facts.py; moved to facts.py.

**What was built, in the approved order:**
1. **Sign group:** `meaning(aspect=group)`: decided when every readable selected sign (and every reading) falls in one art. 11 group; value `{"group": ...}`.
2. **Conduct + STOP:** `meaning(aspect=conduct)`: the row's F5 items, banned actions with their vehicles, allowed directions and speed duties, then art. 21 / 27 / 31. A warning row without items gets art. 27's three duties. W.203 adds C.3 d) (oncoming traffic). R.122: "dừng lại ..., kể cả xe ưu tiên" (D.1 b).
3. **Presence:** `present(code | meaning | category)`, used in `choose` with `expect: false`; an unread sign of a matching look makes "absent" unknown.
4. **Divider and vehicle lists:** `road_divided` on `speed_ok` / `speed_limit` overrides the scene's; `speed_limit.vehicles` gives one limit per vehicle, decided only when every one is.
5. **Scope and placement:** `meaning(aspect=scope | placement)` from `kb/sign_info.yaml` (art. 16, 26, 30, 34, 39, C.39, D.17, D.18; every line checked against the law_db text).
6. **Guide content (B6):** `vqa/perception/guide.py`, the approved variant-A call (`scene/v5-guide`, the trial's spec and examples byte for byte), made only when the scene lists an I / IE board or an unread non-red board, cached as a region record over the whole image. Scene schema 1.3 `guide_boards` (left out of the dump when empty). Board speed discs become P.127 / R.306 signs `g1, g2, ...` unless the scene already has that value. `guide(ask=direction | distance | destinations | route, destination)` reads the boards; no legal conclusion. `PipelineConfig.guide_reading` (default off; in `freeze.POST_FREEZE_SWITCHES`).
7. **Templates** for every new value type, and **validator** checks (present targets, no every_vehicle in a vehicle list, a destination for direction / distance). Guide values carry the distance as printed ("5 km") so templates pass the guard.
8. **Lane fix:** a lane counted from the right is negative (`schemas.QuestionLane`; -1 = rightmost); the engine numbers it from the scene's lane count, and answers unknown when there is none. Before, the parser dropped such lanes and the claim became a whole-road claim.
9. **Parser v7** (`prompts/parser/v7`): the intents and slots above, selector `category`, "xe cảnh sát / công an" = motor_vehicle with priority as stated, negative lanes kept on every claim, guide content in scope. Few-shots: v6's 18 (train_215 now a guide program) plus 11 from train outside the dev and validation sets and their images, exact text (train_109, 197, 344, 5, 457, 120, 417, 206, 294, 233, 460); none shares a duplicate group with a dev or validation image. Tests: no 6-word window of a dev question or a public_dev gate question in the spec. **No train question outside dev and validation mentions a police car, a divider or placement**, so those three have spec lines only. The retry sends only the error from v7 on (v1–v6 keep their echo).
10. **Scene fallback per version:** `fallback.config_for(scene_version)`: v5 uses v5-tile / v5-crop; v4 gives exactly the frozen `FallbackConfig()`.

**Engine-only dev replays (87 questions, no call).** Stored parses are the guardrail; the hand-program rows use programs written by hand in the form v7 is meant to produce (`eval/runs/e2e/dev_v7_handprograms.json`, local; only programs v7 can produce: the parser never sees codes, so 260 was dropped) and, for boards, the B6 trial's stored variant-A readings merged into the dev scenes (`dev_v7_handscenes.json`: 37 questions on 23 images; 3 dev images with a board have no trial reading). **Indicative only: these are not parses.** New decided answers carry provisional grades (assistant, against the dataset answer, conservative 0.5 where wording is partial), for the judge to confirm in B4.

| step | decided | coverage | accuracy on decided | overall (non-decided = wrong) | kept? |
|---|---|---|---|---|---|
| stored parses (stage A) | 32 | 36.8% | 93.8% | 34.5% | — |
| + group (hand programs) | 35 | 40.2% | 94.3% | 37.9% | yes |
| + conduct + STOP | 38 | 43.7% | 90.8% | 39.7% | yes |
| + presence | 38 | 43.7% | 90.8% | 39.7% | yes (107 uncertain) |
| + divider, vehicle lists | 43 | 49.4% | 88.4% | 43.7% | yes |
| + scope, placement | 46 | 52.9% | 88.0% | 46.6% | yes |
| + guide boards and guide programs | **59** | **67.8%** | **86.4%** | **58.6%** | yes |
| stored parses + boards only | 35 | 40.2% | 92.9% | 37.4% | (352, 381 now right) |

- **Stays undecided, and why:** 99 and 107 (P.124a with a low P.123a alternative: readings disagree), 432 (four signs, three with alternatives), 337 and 375 (STOP read UNKNOWN by v4; v5 lists R.122), 520 (a warning sign among guide boards: two groups), 159 (an unread board alternative), 325 (a destination list doesn't answer "which expressway ends"), 260, 248, 250, 414 (compound questions), 231, 259, 80, 515, 521, 254 / 413 (speed ranges), 341, 351, 421, 450, 514, 518, 316.
- **Wrong or partial among the new decided:** 230 and 249 (the boards disagree with the dataset; graded 0), 14 (the 90 disc isn't tied to lane 1 in the scene: car 80, gold 90; 0.5), 56 / 58 ("xe máy" may be a moped, so 60 / 50 is conditional; 0.5), 269 (art. 26.3: P.101–P.120 have no end sign; the dataset says "đến biển hết cấm"; 0.5), 413 (a range asked, the max given; 0.5), 216 / 219 / 222 (duties right, wording partial; 0.5).

### B4 step 1: parser v7 gate run 1 (public_dev gold intents, Sonnet 5.5 medium; 2026-11-17)

- **Run `pred_claude-sonnet-5-5_medium_v7_20261117-124116`: $0.194.** Program accuracy **78.7% (37/47)** against v6's 93.6% (three runs); 8 retries, no failed parse. Runs 2 and 3 were not made: the no-regression rule already fails.
- **`compare` against v6's three runs:** `meaning` drops (27/30 → 6/10) even after giving back design-change rows; `forbidden` (0/1) and `out_of_scope` (4/8) drop only through rows that use a v7 feature.
- **The eight rows v6 got right and v7 missed** (public_dev, readable):
  - **real errors, fixed in v8:** 0055 and 0070 (a stated claim about a board's direction, "đúng hay sai", parsed as `guide`, which gives a value, not a verdict); 0073 (a stated claim about what the driver need not do, parsed as `conduct`); 0022 and 0086 ("loại biển báo gì / nào" parsed as `group`; it asks what the sign is, and a `name` answer names the group); 0002 (`only: true` added to a colour selector);
  - **design changes, kept:** 0065 ("2 làn bên phải" as lanes -1 and -2, where the v6 gold had a missing lane slot); 0087 (an open "nên làm gì" as `conduct`).
- **Parser v8** (`prompts/parser/v8`): v7 with those three spec fixes, the same 29 few-shots. v7 is pinned. The candidate (`eval/e2e_dev.py --candidate`) now uses v8.
- **Spend this round: $0.93 of $5** ($0.70 reserved; $3.37 free).

### B4 step 1: parser v8 gate run (public_dev gold intents, Sonnet 5.5 medium; 2026-11-17)

- **Owner, 2026-11-17: one run is enough; from v8 on, one run decides the gate** (`parser_eval.gate_runs`; v6 and v7 keep their three-run rule). v8 runs 2 and 3 are not made.
- **Run `pred_claude-sonnet-5-5_medium_v8_20261117-124724`: $0.180.** Program accuracy **89.4% (42/47)** against the v6 gold, 95% CI 77.4–95.4%; non-duplicate 88.2% (n=17); no failed parse; out-of-scope precision 100%, recall 87.5%.
- **No-regression rule (set before the run): met.** `regressed_types_without_design` is empty; all six real v7 errors are fixed (0002, 0022, 0055, 0070, 0073 back to the gold).
- **The 90% gate on the v6 gold: FAIL by one question.** Three of the five misses are design changes the v6 gold can't write: 0065 (lanes -1 and -2 for "2 làn bên phải"), 0086 ("các biển ... thuộc loại biển báo nào" as `group`), 0087 (an open "nên làm gì" as `conduct`). The other two (0005, 0025) were also wrong under v6. **With the design rows given back: 95.7% (45/47).**
- **Spend this round: $1.11 of $5** ($0.70 reserved; $3.19 free).

### B4 step 2: judged candidate dev run (scene v5 + guide reading + parser v8, fallback off; 2026-11-17)

- **Run `dev_candidate_7caed6170de6`: $0.81** (estimate $0.84). Fresh perception (the dev re-perception), parser v8 (the dev re-parse), the judge on every decided answer.

| dev (87 Natural QA) | decided coverage (95% CI) | accuracy on decided (95% CI) | overall, non-decided = wrong |
|---|---|---|---|
| frozen phase 4 (`13ded0d75451`) | 40.2% (31–51) | 80.0% (64–90) | 32.2% |
| stage A, engine replay (provisional grades) | 36.8% | 93.8% | 34.5% |
| **candidate, judged** | **74.7% (65/87; 65–83)** | **83.8% (73–91)** | **62.6%** |

- **Guardrail met:** overall 62.6% ≥ 34.5%; accuracy on decided 83.8% ≥ 70%. The hand-program replay had predicted 59 decided, 86.4%, 58.6%.
- **Provisional grades checked by the judge:** 81 right (1.0), 308 right (1.0). **287 wrong (0.0), but for a new reason:** scene v5 reads its sign as P.101 where v4 read P.102 (the same happens on 90). The selector fix itself is untested here.
- **Wrong or partial among the 65 decided (12):**
  - perception: 287 and 90 (P.102 read as P.101 by v5; v4 had it right), 526 (an interchange sign read as I.414), 80 (green boards named, the "exit" meaning missed);
  - the dataset disagrees with the board: 230, 249;
  - parser: 231 ("có cho biết khoảng cách ... không?", a yes/no question about a board, parsed as `guide distance`; the v8 rule names only "đúng hay sai / đúng không");
  - partial value: 254 (a speed range asked; min 60 given and the 80 maximum missed), 325 (the route code CT.01 given, not the route name), 14 (both limits given, not tied to the vehicles: lane-bound discs), 216 / 219 / 269 (0.5, wording or, for 269, art. 26.3 against the dataset).
- **Not decided (22):** out of scope 11 (248, 259, 260, 341, 351, 361, 386, 413, 414, 515, 15), uncertain 6 (138, 159, 432, 450, 517, 521), unknown 3 (415, 421, 451), program can't run 1 (145), unreadable 1 (514).
- **Lane questions:** 414, 421 and 451 are not decided; no lane answer was decided wrongly through a read board.
- **Guide call:** made on 26 images; boards in 40 question scenes.
- **Spend this round: $1.92 of $5** ($0.70 reserved; **$2.38 free**).
- **B4 is done. Next, on the owner's go-ahead: B5** (the phase-4.5 freeze `eval/frozen_phase45.json` with scene v5, parser v8, guide reading on; then the final validation once). Free fixes worth weighing first, each needing its own check: a parser rule for yes/no questions about board content (231; a new parser version and one gate run, about $0.18), and whether v5's P.101 / P.102 confusion (287, 90) is worth a scene-prompt change (it would need the set-T check again).

### Parser v9: one yes/no rule for every intent (owner, 2026-11-17: B4 accepted; no API calls)

- **v9 = v8 with one spec line replaced** (v8's narrower "value intents never answer a stated claim"): yes/no wordings for every intent ("..., đúng hay sai?", "... đúng không?", "... phải không?", "có ... không?", "có phải ... không?", "... được không?") take the claim the question asks about, never a value program; a sign's group asked this way is `is_sign` with `category`; a sign being in the photo is `present`; a fact with no claim form (board places, directions, distances; driver duties; scope; placement) is out of scope.
- **Five new few-shots from train**, outside dev and validation and their images, exact text: train_136 (group → `is_sign` category), train_127 (in the photo → `present`), train_124 and train_424 (board facts asked yes/no → out of scope), train_19 ("có phải ... không?" → a ban for every vehicle). Not fitted to dev 231; tests check that no 6-word window of a dev or public_dev gate question is in the spec.
- **v8 is pinned.** `eval/e2e_dev.py reparse`: a new parser version on a stored dev run, no perception call; it re-parses the yes/no-worded dev questions (chosen by pattern), runs the engine on the stored scenes, and calls the writer and judge only for decided answers whose program changed.
- **Commands (owner runs them):**
  1. Gate run, one run, same no-regression rule against v6's three runs. **Estimate $0.19 (range $0.17–0.22)**, from v8's measured $0.180:
     ```
     .venv/bin/python eval/parser_eval.py run --model claude-sonnet-5-5 --effort medium --version v9 --max-spend 0.40
     .venv/bin/python eval/parser_eval.py score logs/parser_eval/pred_claude-sonnet-5-5_medium_v9_*.jsonl
     .venv/bin/python eval/parser_eval.py compare --old logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-140559.jsonl logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141622.jsonl logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141902.jsonl --new logs/parser_eval/pred_claude-sonnet-5-5_medium_v9_*.jsonl
     ```
  2. If it passes: the dev re-parse of the 4 yes/no-worded dev questions (81, 231, 341, 515) on the candidate run's stored scenes. **Estimate $0.07** (one prompt-cache write, four parses, the writer and judge for at most two changed decided answers):
     ```
     .venv/bin/python eval/e2e_dev.py reparse --from eval/runs/e2e/dev_candidate_7caed6170de6.jsonl --version v9 --max-spend 0.20
     ```
- **Spend this round: $1.92 of $5** ($0.70 reserved).

### Parser v9 gate run (public_dev gold intents, Sonnet 5.5 medium, one run; 2026-11-17)

- **Run `pred_claude-sonnet-5-5_medium_v9_20261117-133917`: $0.192.** Program accuracy **91.5% (43/47)**, 95% CI 80.1–96.6%; non-duplicate 94.1% (n=17); no failed parse. **Gate (≥ 90%, one run): PASS.**
- **No-regression rule: met** (`regressed_types_without_design` empty). 0086 is back to the v6 gold. Misses: 0005 and 0025 (wrong under v6 too), 0065 and 0087 (design: negative lanes; open "nên làm gì" as conduct).
- **v9 is the last passing parser version.** Spend this round: **$2.11 of $5** ($0.70 reserved).

### Dev re-parse with parser v9 (`dev_reparse_v9_8bbb5eb01cff`, on the candidate run's scenes; 2026-11-17)

- **$0.011.** The 4 yes/no-worded dev questions (81, 231, 341, 515) were re-parsed; **only 231 changed**: "có cho biết khoảng cách ... không?" is now out of scope (it was a decided, wrong `guide distance`). No decided answer changed, so no judge call.
- **Dev, scene v5 + guide reading + parser v9:** decided **73.6% (64/87; 95% CI 63–82)**, accuracy on decided **85.2% (74–92)**, overall **62.6%** (unchanged).
- Spend this round: **$2.12 of $5** ($0.70 reserved).

### B5 prepared, not run (2026-11-17; no API calls)

- **`eval/frozen_phase45.json` written** (`eval/freeze.py write --profile phase45`; it refuses to overwrite). **Profile `phase45`:** scene v5 with v5-tile / v5-crop, the guide-board call on (`scene/v5-guide`), **parser v9** (the last passing version), writer `answer/v3`, answer fallback `v2`, scene fallback `crop_always` with T4 (`drop_own_alt_on_agree`), and every prompt's id and full sha256 (scene, tile, crop, guide, parser, answer, answer fallback, judge). `answer_fallback` is left out of the comparison: each runner sets it (validation: off; private: the default).
- **Freeze profiles** (`eval/freeze.py`): `PipelineConfig()` defaults stay the phase-4 configuration, so `eval/frozen_phase4.json` still matches and the baseline, holdout and frozen dev runs are untouched. A record names its profile; `check` compares a record with its profile's live configuration; the runners build their pipeline from it.
- **`eval/e2e_validation.py`:** `final` checks `frozen_phase45.json` and runs the phase-4.5 profile, fallback off; the report records the profile. **`eval/e2e_private.py`:** checks `frozen_phase45.json` by default and runs its profile. Tests: each refuses a mismatch (parser version, guide reading, scene version or hash, guide hash, policy, profile) before writing its sentinel.
- **The final validation (owner runs it once, after reviewing `kb/sign_info.yaml`):**
  ```
  .venv/bin/python eval/freeze.py check --profile phase45
  .venv/bin/python eval/e2e_validation.py run --label final --confirm-frozen --max-spend 1.3
  ```
  **Estimate $0.77 (range $0.62–1.00; $0.86 if every question is decided)**: 110 questions on 54 images (53 Yes/No, 57 Natural QA; split counts only), at the candidate dev run's measured rates (perception with fallback and guide $0.0019 per image, parser $0.0038 per question, writer and judge per decided answer) and dev's 74% decided. It is above the $0.70 reserve; the round has $2.88 left.
- **Spend this round: $2.12 of $5.**

### Phase 4.5 final validation, once, frozen phase-4.5 system, fallback off (2026-11-17; aggregate only)

- **Run `7a3dbec997f7`**, `eval/frozen_phase45.json` (profile phase45: scene v5 + tile / crop, guide reading, parser v9, writer v3), commit `3fe5b77`, 110 questions on 54 images, **$0.83**, 17 s per question. Sentinel `eval/validation_ran_final.json` (finished). Report `eval/runs/e2e/validation_aggregate_final_7a3dbec997f7.json` (local). No per-question result was read.

| validation (110 q: 53 Yes/No, 57 Natural QA) | decided coverage (95% CI) | accuracy on decided (95% CI) | overall, non-decided = wrong (95% CI) |
|---|---|---|---|
| baseline, frozen phase 4 (`c015055`) | 30.0% (22–39) | 72.7% | 21.8% (15–30) |
| **final, frozen phase 4.5** | **47.3% (52/110; 38–57)** | **77.9% (65–87)** | **36.8% (28–46)** |

- **Success criterion (fixed before the work): met.** Decided coverage 47.3% > 39.1% and overall 36.8% > 30.4% (both above the baseline's upper CI bound). The CIs overlap the baseline's at their edges.
- **Targets and floors (fixed, reported as met or missed): all missed.** Coverage 47.3% (target 80%, floor 70%); accuracy on decided 77.9% (target 88%, floor 85%); overall 36.8% (target 70%, floor 60%).
- **By type:** Yes/No 39.6% decided, 90.5% right when decided, 35.8% overall; Natural QA 54.4% decided, 69.4% right when decided, 37.7% overall. Judge labels on decided Natural QA: 17 correct, 9 partial, 5 wrong.
- **Not decided (58), by cause:** out of scope 28, uncertain 16, unknown 7, unreadable sign 4, program can't run 2, parse failed 1.
- **Dev against validation:** dev (tuning set) gave 73.6% decided and 85.2% accuracy; validation gives 47.3% and 77.9%. Most of the stage-B gain was fitted on dev's question mix (all Natural QA, guide-heavy); the validation set is half Yes/No.
- **Spend this round: $2.95 of $5.**

## Next steps, in order

### Handoff (2026-11-18): phase 4.8c, new question types

#### Phase 4.8: closed and frozen (`f8bcb67`)

- **Frozen system:** `eval/frozen_phase48.json`, profile `phase48`: scene v5 (with tile and crop prompts and the guide call), **parser v16**, writer v3, answer fallback v2, reading policy `higher_confidence`, signals off (`kb/v6_fields_47.yaml`), engine switches **several_signs on, confusable_pairs off** (`kb/switches_48.yaml`), engine-code hash (64 files). `eval/e2e_private.py` accepts profile `phase48` only.
- **Figures:**
  - **dev2** (biased, gap-finding only): **79 decided, 64.6% on decided, 51.0% overall** (baseline under phase 4.7: 74 / 58.8% / 43.5%);
  - **dev guardrail:** **69.0% overall, 81.1% on decided** (bars 68.4% / 70%).
- **Known regressions:** v16 lost dev2 **433** and **491** (right before, now out of scope); new wrong answers on dev2 **169** (B6 picks R.403b; the answer lists who it bans), **207**, **400**. Still listed: **train_250** (decided again under v16, but fragile: the two-part board question) and **own_65** (stop line parsed as another claim).

#### Where dev2 loses its points (49 per 100, owner's breakdown)

| cause | points | examples |
|---|---|---|
| perception | about 24 | P.130 / P.131a swap (about 4), invented P.101 / P.102, variants (W.201a/b, P.124a/c), sign charts, lane arrows not read (R.411, R.415a, P.127c), unreadable signs |
| parser out of scope | 13 | single wordings with no DSL form (seasonal times, fines, symbol meanings, compound claims, numbered sign clusters) |
| answer composition | about 7 | value answers that list too much (all signs, pedestrians), conditional lanes written as undecided |
| rules or gold | about 5 | |

#### Not kept in phase 4.8

- **Voting** three Haiku reads: +1.9 F1 on set T, under the +2.9 bar.
- **Scene v7** (visual notes for P.130 / P.131a, P.125 / P.103a, P.117 / P.101): +3.6 F1, −2.5 recall in one run; it removed the P.131a → P.130 swap. **A candidate for a later round, judged on repeated runs.**
- **Opus and Sonnet** as the perception model: cost (Opus about $2.5–4.5 for one set-T run).
- **The confusable table** (`kb/confusables_48.yaml`): built, switched off; it failed its keep rule (dev overall 67.2% < 68.4% on the free estimate).
- **Haiku's run-to-run spread on set T is about 4 F1 points** (three reads: 73.0%, 77.0%, 73.7%). Single-run perception comparisons can't resolve gains under that.

#### The owner's next step: phase 4.8c

1. **New question types (parser v17)** plus the free batch (engine and rule-only fixes), then one gate.
2. **Re-freeze as `phase49`** (new profile and record; point `e2e_private.py` at it, with its tests).
3. **dev3** (not built yet): untouched questions, aggregate only, runs once, like the validation set.
4. **Then the private run.**

#### Spend

- **Phase 4.8: $2.69 of $5.00, $2.31 left.** Keep about **$1.00 for dev3**. The private run has its own budget.

#### Key files and commands

- **Freeze:** `eval/freeze.py` profiles `phase4`, `phase45`, `phase46`, `phase47`, `phase48` (records `eval/frozen_phase4.json` ... `frozen_phase48.json`, each written once). The phase-4.7 record's tests check its engine hash at 4ad9137 (`tests/freeze_at.py`); a later freeze needs the same for phase 4.8 if the engine changes again.
- **dev2:** `data/splits/train_dev2.json` (`eval/make_dev2_split.py`, seed 20261118); runner `eval/e2e_dev2.py` (`estimate`, `run` with `--scene-version` / `--parser-version` for a candidate, `summary`). Latest judged dev2: `eval/runs/e2e/dev2_reparse_v16_c95f3934da5c.jsonl`; latest judged dev: `dev_reparse_v16_248e38bd215e.jsonl`.
- **Rejudge and re-parse** (both read dev and dev2 runs; the tree must be clean):
- **Replay** (free): `eval/phase48_replay.py check` (baseline at `b1f6b80`; `INTENDED` lists the planned changes; `--several-signs`, `--confusable-pairs` override the switches).
- **Paid-script pattern:** a script in the session scratchpad, run by the owner in the terminal tab where `ANTHROPIC_API_KEY` is set (from the keychain), piped through `tee` to a log; the assistant watches the log for a done marker. The assistant's own shell has no key.

```zsh
.venv/bin/python eval/freeze.py check --profile phase48
.venv/bin/python eval/phase48_replay.py check
.venv/bin/python eval/e2e_dev.py rejudge --programs <run> --scenes <run> --dry-run
.venv/bin/python eval/e2e_dev.py reparse --from <judged run> --version <vN> --select all --reading-policy higher_confidence --max-spend <cap>
.venv/bin/python eval/e2e_dev2.py summary <file>
.venv/bin/python eval/e2e_dev2.py run --label <label> --parser-version <vN> --max-spend <cap>
.venv/bin/python eval/parser_eval.py run --model claude-sonnet-5-5 --effort medium --version <vN> --max-spend 0.45
.venv/bin/python eval/perception_eval.py score <run> ...
.venv/bin/python eval/e2e_private.py estimate
```

### Private benchmark, hand-graded by the owner (2026-11-21): V2 82.2% (sd 1.8), V1 decides at 82.3%

- **The owner hand-graded** the V1 and V2 workbooks (3 runs × 146 questions each; `eval/owner_workbooks.py`, kept outside the repo). Aggregates from `eval/owner_workbook_scores.py`, run by the owner; the assistant did not read the workbooks.

| private, 146 questions | run 1 | run 2 | run 3 | **mean (sd), human** | judge mean |
|---|---|---|---|---|---|
| V1, rules only, non-decided wrong | 54.8% | 54.8% | 55.5% | **55.0% (0.4)** | 54.9% |
| V1 on the rules-decided questions | 83.3% (96) | 80.8% (99) | 82.7% (98) | **82.3% (1.3)** | 82.1% |
| **V2, rules + live RAG fallback** | 82.9% | 80.1% | 83.6% | **82.2% (1.8)** | 82.2% |
| V2's RAG part (triggered questions) | 82.0% (50) | 78.7% (47) | 85.4% (48) | 82.0% | |

- **The judge agrees with the owner on 140–142 of 146 answers per run** (4–6 changed, almost all "Một phần" resolved to Đúng or Sai; one Đúng → Sai in V2 run 1). The hand grades leave every mean within 0.1 point of the judge's, so the judge-graded figures above stand and the main table can be reported as human-graded.
- **Like-for-like with the baselines** (owner's hand grades): V2 82.2% vs LowCost and LexiSignVQA ~78%. RAG alone (79.2%) is judge-graded only.

### Error analysis on the public test, phase52 (2026-11-21; no API calls)

- **Full write-up** (local, gitignored, quotes dataset questions): `eval/runs/public52_error_analysis.md`. Here ids and categories only.
- **V2 loses points on 19 of 100 questions:** 14 rules answers wrong or partial, 5 RAG fallback answers wrong.

| Cause | Cases | Ids (public_natural_) |
|---|---|---|
| Perception: sign misread | 6 | dev 0002, 0014, 0025; holdout 0069, 0081, 0100 |
| Perception: guide-board text | 1 | holdout 0079 |
| Rules / KB gap | 3 | dev 0011 (P.125: B.25's "được phép vượt xe máy 2 bánh, xe gắn máy" not modelled), 0051 (plate text "XE GẮN MÁY" mapped to `motorbike`, the question's `moped` not covered); holdout 0064 (W.203c answered with the family row's name) |
| Writer / explanation | 1 | dev 0092 |
| Gold or question ambiguous | 3 | dev 0043 (two-photo collage); holdout 0007 (plate says rush hour), 0052 (R.420 is a mandatory sign, D.18) |
| RAG fallback wrong | 5 | dev 0083 (starts from a P.131a → P.130 misread); holdout 0006, 0046, 0077, 0089 |

- **Perception dominates** (7 of 14 rules errors, plus one RAG error that starts from a misread). The three rules / KB gaps are one-line fixes, post-benchmark only. None involves the payload fix.
- **Routing (future work):** on decided questions the writer's low-confidence hedge separates the two: hedged (6) rules 58.3% vs RAG 83.3%; not hedged (75) rules 89.3% vs RAG 84.0%. Routing the hedged ones to the RAG: decided accuracy 87.0% → 88.9%. Measured on public (tuning data) and 6 questions; not part of the benchmarked system.
- **Worked examples** for Chapter 4 (proof trees replayed from the stored scenes and programs): dev 0042 (time window cleared, QCVN 41 B.30 / F.10), dev 0048 (P.106b covers tractors and special machines, B.6), dev 0082 (IE.452 makes an expressway, Law 36 art. 25 keeps motorbikes off it).

### phase52 on the whole public test, with the RAG fallback (2026-11-21): V2 84.5%, RAG alone 82.0%

- **Runs** (frozen phase52, rules only, fresh perception): public_dev `a30895cfad39` ($0.50, at `59425af`) and public_holdout `32cf475921a1` ($0.58, from the worktree `~/abc-phase52`, branch `phase52-holdout` at `f30e048`, the pre-fix code). **Merges** with the RAG's saved public predictions (config C): $0.14 and $0.18; the rules' grades are reused, only the RAG's Natural QA answers are judged. Combined report `eval/public52_report.py` -> `eval/runs/public52_report.json` (gitignored).

| | public_test (100) | public_dev (51) | public_holdout (49) |
|---|---|---|---|
| V1 decided coverage | 81.0% | 82.4% | 79.6% |
| V1 accuracy on decided | 87.0% | 85.7% | 88.5% |
| V1 overall (non-decided wrong) | 70.5% | 70.6% | 70.4% |
| **V2 rules + RAG fallback** | **84.5%** (CI 76.1–90.3%) | 86.3% | 82.7% |
| V2 strict | 81.0% | 84.3% | 77.6% |
| RAG alone | 82.0% | 82.4% | 81.6% |
| RAG alone strict | 80.0% | 80.4% | 79.6% |
| rules vs RAG on the decided questions | 87.0% vs 84.0% | 85.7% vs 81.0% | 88.5% vs 87.2% |
| V2 vs RAG alone, paired strict (only V2 / only RAG) | 8 / 7, p 1.0 | 6 / 4, p 0.75 | 2 / 3, p 1.0 |

- **Reading:** the two halves agree (V1 overall 70.6% vs 70.4%), so phase52 shows no sign of overfitting to public_dev. On public, the rules decide 81% at 87.0%, higher than on private (66.9% at 82.1%). V2 is 2.5 points above RAG alone, mostly from partial credit: on strict grades the two are tied (81% vs 80%). The RAG on the 19 triggered questions scores 73.7%. As on private, the rules and the RAG are right on different questions (8 vs 7 on the decided ones).

### public_holdout readable per question (owner, 2026-11-21; no API calls yet)

- **Rule lifted (owner, 2026-11-21), recorded in CLAUDE.md:** after the private benchmark, public_holdout may be read question by question like public_dev, for the Chapter 4 error analysis. It is no longer held out; the earlier holdout figures stay as reported.
- **Runner:** `eval/e2e_public_dev52.py run --split public_holdout` (and `merge --split public_holdout`), output in the gitignored `eval/runs/public_holdout52/`. 49 questions, 45 images, 36 Natural QA; the RAG's saved predictions cover all 49.
- **System:** phase52 as benchmarked (owner), run from a worktree at the pre-fix commit so the code matches `eval/frozen_phase52.json`; the payload fix is not in it.

### Post-benchmark fix: a lane sign's truck weight is the payload (owner, 2026-11-21; no API calls)

- **Found by the owner while hand-grading the private workbooks:** on R.415a the engine read the number on a truck as the gross mass, so some answers were wrong. **QCVN 41 D.14** (lane signs): "ghi trị số khối lượng chuyên chở cho phép của xe tải lên thân xe trong hình vẽ của biển (Ví dụ: "<3,5t")": it is the permitted **payload**. D.16 (R.415a) says nothing about weights, so D.14 applies; P.106b already reads payload (B.6).
- **Cause:** the scene prompt's only weight example is `gross_t`, so perception records a lane-board truck's "3,5t" as gross mass, and lane rows passed it through unchanged.
- **Fix:** catalog `lane_truck_weight: load_t` on R.412c and R.415a (D.14 quoted in the YAML; `reviewed_by: assistant`), and `vqa/reasoning/facts.py` `_lane_vehicles` reads a truck's gross-mass condition on those signs' lane rows as a payload condition. Example: a truck with a 3 t payload on a "<3,5t" truck lane goes from unknown to yes. Tests `tests/test_lane_truck_weight.py` (5).
- **The benchmark stands as run.** The three private runs used the frozen phase52 system; this fix is post-benchmark and is never scored on private. The phase-5.2 record no longer matches the tree: tests use `tests/freeze_at.py` `phase52_record_for_this_tree` (checked at `0b882c3`), and a real run from this tree with the real record is refused. The fix's effect is to be measured on public_dev / the train dev set only. In the thesis it belongs in the error analysis, with the number of affected private questions from the owner's grading.

### The private benchmark, complete (2026-11-21): V2 82.2% (sd 2.1), RAG alone 79.2%, V1 decides 66.9% at 82.1%

- **Run 3's merge:** `e2e_private_rag.py run --run 3`, sentinel `eval/private_rag_ran_3.json`, aggregate `eval/runs/e2e/private_rag_aggregate_e243362cb98e.json` (no ids), **$0.78**. Live vs saved RAG answers: 34 of 48 identical.
- **All three runs** (146 private questions; judge `judge/v1`, Opus 5.5; Yes/No by polarity):

| | run 1 | run 2 | run 3 | **mean (sd)** |
|---|---|---|---|---|
| V1, rules only, non-decided wrong | 53.8% | 54.8% | 56.2% | **54.9% (1.2)** |
| V1, accuracy on decided (coverage) | 81.8% (65.8%) | 80.8% (67.8%) | 83.7% (67.1%) | **82.1% (1.5)** at 66.9% (1.1) |
| **V2, rules + live RAG fallback** | 82.2% | 80.1% | 84.2% | **82.2% (2.1)** |
| RAG alone (saved predictions) | 79.1% | 79.5% | 79.1% | **79.2% (0.2)** |

- **Same questions, paired (strict; runs 2 and 3, the split was added after run 1's merge):**

| | rules / V2 | RAG alone | only rules/V2 right | only RAG right | McNemar p |
|---|---|---|---|---|---|
| run 3, 98 rules-decided | 83.7% | 76.5% | 15 | 8 | 0.21 |
| run 3, 48 triggered (live vs saved RAG) | 85.4% | 84.4% | 2 | 1 | 1.0 |
| run 3, all 146 | 84.2% | 79.1% | 17 | 9 | 0.17 |
| run 2, all 146 | 80.1% | 79.5% | 15 | 13 | 0.85 |

- **Reading:** V2 is above RAG alone in every run (+3.1, +0.6, +5.1; mean +3.0) and above the two hand-graded baselines (~78%), but no single run's difference is significant on 146 questions. RAG alone's answers are the same in every merge and its score moves 0.2 points across three judgings, so V2's spread (2.1) is the neuro-symbolic side's own run-to-run variance, not the judge's. On the decided questions the rules and the RAG are each right where the other is wrong on 8–15 questions: better routing between them is the clearest future work. The baselines' figures are the owner's hand grades; the hand grades of V1, V2 and RAG alone (the `owner_grading*.csv` sheets) are still to come.
- **Cost of the benchmark:** private runs $4.08, merges $2.24, live RAG on the owner's GPU.

### The RAG merge, run 2 (owner run, 2026-11-21): V2 80.1%, RAG alone 79.5%, no significant difference

- **Merge:** `e2e_private_rag.py run --run 2` at `335b6e5` (with the same-question split), sentinel `eval/private_rag_ran_2.json`, aggregate `eval/runs/e2e/private_rag_aggregate_3163188d23b7.json` (no ids), **$0.74**.

| run 2 | overall | 95% CI | strict | Yes/No | Natural QA |
|---|---|---|---|---|---|
| **V2, rules + live RAG fallback** | **80.1%** | 72.9–85.8% | 78.8% | 77.1% | 82.9% |
| RAG alone (saved predictions) | 79.5% | 72.2–85.2% | 77.4% | 75.7% | 82.9% |

- **Same questions, paired (strict):**

| | V2 | RAG alone | both right | only V2 | only RAG | both wrong | McNemar p |
|---|---|---|---|---|---|---|---|
| 99 rules-decided | 80.8% (rules) | 80.3% | 65 | 13 | 12 | 9 | 1.0 |
| 47 triggered | 78.7% (live) | 77.7% (saved) | 35 | 2 | 1 | 9 | 1.0 |
| all 146 | 80.1% | 79.5% | 100 | 15 | 13 | 18 | 0.85 |

- **Reading:** on the questions the rules decide, the rules and the RAG are tied (80.8% vs 80.3%), and they are right on different questions (13 vs 12 discordant, 9 both wrong). The run-1 estimate of RAG alone at 77–78% on the rules' questions (from the aggregates) was wrong. V2's accuracy is on par with RAG alone; the rules add proofs, citations and 100% faithfulness on two-thirds of the questions, not accuracy. Live vs saved RAG answers: 33 of 47 identical.

### The private benchmark, run 3, and V1 over the three runs (owner run, 2026-11-21): decides 66.9% at 82.1%

- **Run 3:** `e243362cb98e`, 03:06–04:01 UTC, at `4e71a18`, same frozen phase52 record (sentinel `eval/private_ran_3.json`; aggregate `eval/runs/e2e/private_aggregate_e243362cb98e.json`, no ids). **$1.36.** Replay records and `owner_grading.csv` in `cache/private_run/e243362cb98e/` (gitignored). Not decided (48): out of scope 20, unknown 20, unreadable sign 5, parse failed 2, program cannot run 1.

| V1, rules only | run 1 | run 2 | run 3 | **mean (sd)** |
|---|---|---|---|---|
| decided coverage | 65.8% (96) | 67.8% (99) | 67.1% (98) | **66.9% (1.1)** |
| accuracy on decided | 81.8% | 80.8% | 83.7% | **82.1% (1.5)** |
| accuracy on decided, strict | 79.2% | 78.8% | 80.6% | 79.5% |
| overall, non-decided wrong | 53.8% | 54.8% | 56.2% | **54.9% (1.2)** |
| Natural QA: decided, accuracy | 52, 77.9% | 54, 79.6% | 54, 81.5% | |
| Yes/No: decided, accuracy | 44, 86.4% | 45, 82.2% | 44, 86.4% | |
| cost | $1.33 | $1.39 | $1.36 | $4.08 |

- **Next:** the RAG merges for runs 2 and 3 (`e2e_private_rag.py run --run 2`, then `--run 3`, the same two live files), then V2 and RAG alone as means over the three runs.

### The private benchmark, run 2 (owner run, 2026-11-21): V1 decides 67.8% at 80.8%

- **Run:** `3163188d23b7`, 02:10–02:58 UTC, at `20f5926`, same frozen phase52 record as run 1 (sentinel `eval/private_ran_2.json`; aggregate `eval/runs/e2e/private_aggregate_3163188d23b7.json`, no ids). **$1.39.** Fresh scene cache; replay records and `owner_grading.csv` in `cache/private_run/3163188d23b7/` (gitignored).

| V1, rules only | run 1 | run 2 |
|---|---|---|
| decided coverage | 65.8% (96) | 67.8% (99) |
| accuracy on decided | 81.8% (strict 79.2%) | 80.8% (strict 78.8%) |
| overall, non-decided wrong | 53.8% | 54.8% |
| Natural QA: decided, accuracy | 52, 77.9% | 54, 79.6% |
| Yes/No: decided, accuracy | 44, 86.4% | 45, 82.2% |

- **Not decided (47):** out of scope 20, unknown 20, unreadable sign 5, program cannot run 1, parse failed 1. Faithfulness 100%.
- **Next:** run 3, then the merges for runs 2 and 3 (the live RAG files cover all 146 questions).

### The RAG merge, run 1 (owner run, 2026-11-21): V2 82.2%, RAG alone 79.1%

- **Live RAG** (owner's vast RTX 5090, RAG repo `db75c4b`, config C as plan F1): the private questions captioned and embedded live, the law-corpus and train-bank index from their hash-verified caches. Run 1's 50 triggered questions, then the other 96, so all 146 are covered for runs 2 and 3. **A second live pass on the 50 matched the first on 50 of 50.** Files `rag_live.jsonl` in `cache/private_run/a51605785ace/` and `cache/private_run/live_rest/` (gitignored).
- **Merge:** `e2e_private_rag.py run --run 1`, sentinel `eval/private_rag_ran.json`, aggregate `eval/runs/e2e/private_rag_aggregate_a51605785ace.json` (no ids), **$0.72**. A first start stopped at the first judge call (no API key in that shell, $0) and its sentinel was removed (owner).

| | overall | 95% CI | strict | Yes/No | Natural QA |
|---|---|---|---|---|---|
| V1, rules only (run 1, non-decided wrong) | 53.8% | 45.7–61.7% | | 54.3% | 53.3% |
| **V2, rules + live RAG fallback** | **82.2%** | 75.2–87.5% | 80.8% | 82.9% | 81.6% |
| RAG alone (B2, saved predictions) | 79.1% | 71.8–84.9% | 76.7% | 75.7% | 82.2% |

- **V2 by part:** the rules' 96 decided answers 82.3% (re-judged; V1 graded them 81.8%, a one-answer judge difference); the live RAG on the 50 triggered 82.0% (Yes/No 76.9%, Natural QA 87.5%). By trigger: out of scope 85.7% (21), unknown 73.7% (19), unreadable sign 83.3% (6), program cannot run 3 of 3, parse failed 1 of 1.
- **Live vs saved RAG answers: 33 of 50 identical.** The live pipeline reproduces itself exactly but not the saved batch run; possible causes: torch 2.15.0+cu132 vs the saved run's build, the encoder's unpinned revision, caption differences. Not investigated.
- **Live fallback latency per question** (warm models): total mean 7.2 s (p50 6.5, p95 12.9, max 22.5); caption 2.7 s, embedding 0.01 s, retrieval 0.02 s, answer 4.4 s.
- **Next:** private runs 2 and 3, then their merges (`--run 2`, `--run 3`, same two live files); the report gives V1, V2 and RAG alone as means over the three runs.

### Private benchmark: 3 runs for the mean and spread (owner, 2026-11-21; no API calls)

- **Rule change (owner, 2026-11-21):** the private test runs 3 times on the frozen phase52 setup, because perception, parsing and the writer are Claude calls whose output varies from run to run. All 3 runs are reported (mean and spread), never the best one, and nothing is tuned between them. Recorded in CLAUDE.md and `docs/plans/rag-fallback.md` F4.
- **Runner:** `eval/e2e_private.py run --run N` with N in {2, 3}. Run 1 stays `a51605785ace` (`eval/private_ran.json`, unchanged). Runs 2 and 3 write `eval/private_ran_2.json` and `eval/private_ran_3.json` before the first call, each with its own run id, replay folder `cache/private_run/<run_id>/` (fresh scene cache, `records.jsonl`, `owner_grading.csv`) and aggregate `eval/runs/e2e/private_aggregate_<run_id>.json`. It refuses N outside {2, 3}, a run whose sentinel exists, a run before every earlier one has finished on the same freeze record, and a private aggregate no earlier run wrote; every run-1 guard stays (`--confirm-frozen`, clean tree, phase52 only, ignored replay folder, no resume, answer fallback off, spend guard).
- **Estimate:** $1.49 per run with the fallback off ($1.19–1.93), about 42 minutes; run 1 cost $1.33 in 44 minutes. **Next (owner's terminal, one after the other):** `run --run 2 --confirm-frozen --max-spend 2.25`, then `--run 3`. The RAG merge for runs 2 and 3 is adapted separately.

### The private benchmark, run 1, on phase52, rules only (owner run, 2026-11-20): V1 decides 65.8% at 81.8%

- **Run:** `a51605785ace`, 14:11–14:55 UTC, at `3f45ba6` (phase52: scene v5 + guide, Haiku 5.5 perception, parser v18, writer v3, policy A, signals off, no scene re-run), **answer fallback off**. Sentinel `eval/private_ran.json` (status finished); aggregate `eval/runs/e2e/private_aggregate_a51605785ace.json` (local, no ids). **$1.33** (estimate $1.49), 16.5 s and $0.0091 per question. Replay records and the owner's grading sheet `owner_grading.csv` in `cache/private_run/a51605785ace/` (gitignored).
- **V1, rules only** (146 questions, 104 images; judge `judge/v1`, Opus 5.5):

| | value | 95% CI |
|---|---|---|
| decided coverage | **65.8%** (96 of 146) | 57.7–73.0% |
| accuracy on decided | **81.8%** (strict 79.2%) | 72.9–88.2% |
| overall, non-decided counted wrong | **53.8%** | 45.7–61.7% |

| by type | questions | decided | accuracy on decided | overall |
|---|---|---|---|---|
| Natural QA | 76 | 52 (68.4%) | 77.9% | 53.3% |
| Yes/No | 70 | 44 (62.9%) | 86.4% | 54.3% |

- **Not decided (50):** out of scope 21, unknown 19, unreadable sign 6, program cannot run 3, parse failed 1. These go to the RAG in V2 (`eval/e2e_private_rag.py`).
- **Writer:** 96 decided answers, faithfulness 100% (every written verdict equals the engine's), 2 template answers.
- **By feature** (score with non-decided answers as their template text; rule coverage): time 71% (87%), weight or seats 81% (92%), speed 63% (69%), turns, stops, parking and overtaking 58% (70%), violation 56% (56%), vehicle class 52% (64%), meaning 50% (63%), lanes 43% (52%).
- **Compared with the development sets** (phase52, judged): dev decided 85% at 81.1%, dev2 79% at 69.6%. Private coverage is lower (65.8%), with accuracy on decided in line with dev.
- **Next:** the RAG merge (`eval/e2e_private_rag.py`, about $0.7) for V2 and RAG alone; then the owner's hand grading (P6).

### v18 dev guardrail: re-parse of dev and dev2 on phase52 (owner runs, 2026-11-20): dev passes, dev2 −1.5

- **Runs:** from the phase49 judged runs (`dev_rejudge_ce47ca5037a7`, `dev2_rejudge_32f3582f8b1c`), parser v18, `--select all --reading-policy higher_confidence`, phase52 engine (commit `69003cd`). dev `eval/runs/e2e/dev_reparse_v18_916b52fcedf2.jsonl` (two resumes: `d1332c67c4ae.partial` stopped by the $0.55 cap at 82 of 87, `cc0e7474e96c.partial` by the guard's worst-case reservation); dev2 `dev2_reparse_v18_1780bb064874.jsonl`. **Cost $1.01** (dev about $0.55, dev2 $0.459). A v18 parse costs about $0.0043 against v17's $0.0034 (the prompt is 14% longer), and each resume after a pause pays one cache write (about $0.07).
- **A batch re-parse was built and dropped (owner, 2026-11-20):** with a 27k-token cached system prompt, batch requests get best-effort cache hits, so a batch is likely dearer than live cached calls (about $1.47 against $0.43 for dev2 at half hits); its worst-case guard needs a $5.50 cap.

| | decided | accuracy on decided | overall |
|---|---|---|---|
| dev, phase49 (v17) | 73 | 81.5% | 68.39% (59.5 of 87) |
| **dev, phase52 (v18)** | **74** | **81.1%** | **68.97%** (60.0 of 87; +0.5, passes the 68.39% bar) |
| dev2, phase49 (v17) | 79 | 71.5% | 56.5% |
| **dev2, phase52 (v18)** | **79** | **69.6%** | **55.0%** (−1.5) |

- **dev, 13 changed, net +0.5:** train_386 out of scope → `meaning` name, 1.0 (+1.0); train_159 unknown → `meaning` name, 0.5 (+0.5); **train_250 1.0 → unknown (−1.0)**: v18 shortens the second part's destination to "khu công nghiệp", so no board line matches.
- **dev2, 16 changed, net −1.5:** **train_169 1.0 → 0.0** (`which_vehicles` → `applies_to`, which lists the wrong classes for R.403b); **train_437 1.0 → 0.5** (`meaning` → `which_vehicles`, drops "cấm rẽ phải"); **train_459 0.5 → out of scope** (the v18 out-of-scope wording reaches an open "quy định gì" question); train_347 out of scope → 0.5 (+0.5); train_350 undecided → decided 0.0 (**v18 maps "xe ba bánh" to `cyclo`, against CLAUDE.md's `motor_tricycle`**); train_504 0.0 → out of scope (0).
- **Reading:** v18 passes the dev guardrail and loses 1.5 points on dev2 (biased, tuned). Its losses are parser intent choices (`applies_to` / `which_vehicles` / `meaning`), one destination shortening, and the "xe ba bánh" mapping. Development figures, not benchmark results. **Owner decision (2026-11-20): the private run uses phase52 (v18).**

### RAG fallback plan approved; private run rules-only on phase52, RAG merged in after (owner, 2026-11-20; no API calls)

- **Plan:** `docs/plans/rag-fallback.md`, approved and revised the same day. The owner's RAG (`~/UNIVERSITY/Capstone/RAG`) is the only answer fallback, used as it is (its similarity-chosen train few-shots kept; CLAUDE.md's leakage guard now covers `vqa/` and `app/` only). Reports give scores on all images only.
- **Private run:** `eval/e2e_private.py` now builds its pipeline with `answer_fallback=False` (`ANSWER_FALLBACK`), and the report records it. The run gives V1 (rules only) and keeps each question's trigger in the replay records. phase52 is unchanged (`eval/` is outside the engine hash); `freeze.py check --profile phase52` matches.
- **RAG merge:** `eval/e2e_private_rag.py` (new, scoring code, runs once, sentinel `eval/private_rag_ran.json`). After the private run it grades, in memory, V2 (rules where no trigger fired, RAG where one did) and B2 (RAG alone) from the RAG's saved `predictions.jsonl`, and writes one aggregate file.
- **The RAG is deterministic:** its two saved Q4 private runs (`answer_comparison/private_models_Qwen_Q4_run1` and `_run2`) give the same answer on all 146 questions, and their `run_config.json` is the plan's F1 configuration. Checked without reading private answers: the run1 predictions cover exactly the 146 private question ids, all `COMPLETED`.
- **Next:** (recommended) the v18 dev and dev2 re-parse (~$0.85); then the private run (~$1.49, fallback off); then the merge (~$0.7 judge).
- Tests: `tests/test_e2e_private_rag.py` (9), a fallback-off test in `tests/test_e2e_private.py`, and `tests/test_freeze.py`'s private-run check updated. Suite: 2,390 passed.

```zsh
.venv/bin/python eval/e2e_private.py run --confirm-frozen --max-spend 2.5
.venv/bin/python eval/e2e_private_rag.py run --confirm --max-spend 1 \
  --rag-predictions ~/UNIVERSITY/Capstone/RAG/artifacts/experiments/text_based_rag/natural_qa/answer_comparison/private_models_Qwen_Q4_run1/private_test/predictions.jsonl
```

### Freeze phase52: phase51 with the lane_reserved_is fixes (owner request, 2026-11-20; no API calls)

- **Record:** `eval/frozen_phase52.json`, profile `phase52` in `eval/freeze.py` = phase51's configuration and prompts unchanged (parser v18, scene v5 + guide, no scene re-run, writer v3, policy A, signals off, same engine switches), with the engine-code hash of `8b45e0b` (bare R.412 lane rows, every kind of bus on R.412a). `freeze.py check --profile phase52` matches; only `engine_code`, `profile` and `what` differ from phase51.
- **Private runner on phase52 (owner, 2026-11-20):** `eval/e2e_private.py` checks `frozen_phase52.json` by default and accepts profile `phase52` only; phase51 and older records are refused by their profile. Any later change to `vqa/` or `kb/` makes the run refuse until a new record is written.
- **Not checked:** no dev / dev2 run of v18 or the 65bbfbb and 8b45e0b fixes.
- Tests: `tests/test_freeze.py` (phase52 is phase51 with new engine code only; written once) and `tests/test_e2e_private.py` (defaults and profile phase52; phase51 added to the refused records). CLAUDE.md's freeze line names phase52.

### Freeze phase51: phase50 with parser v18 (owner request, 2026-11-20; no API calls)

- **Record:** `eval/frozen_phase51.json`, profile `phase51` in `eval/freeze.py` = phase50 (scene v5 + guide, no scene re-run, parallel calls, writer v3, policy A, signals off, same engine switches) with **parser v18** (`parser/v18@b370b923cccb`) and the engine-code hash of `65bbfbb` (67 files; the rule and engine fixes, `kb/rules/fixes50.pl`). `freeze.py check --profile phase51` matches. Nothing else differs from the phase50 record.
- **v18 gate** (run `pred_claude-sonnet-5-5_medium_v18_20261120-140742.jsonl`, $0.23; scored offline here): 80.9% (38/47), the same nine wrong rows as v17; `regressed_types_without_design` empty, so it passes the no-regression rule. The 90% point gate fails, as for every version since v6's three-run mean.
- **Not checked:** v18 and the 65bbfbb fixes have no dev / dev2 run, so the dev guardrail is not measured for this record.
- **Second v18 gate run** (owner run, 2026-11-20, `pred_claude-sonnet-5-5_medium_v18_20261120-163440.jsonl`, $0.23): 78.7% (37/47), one failed parse; mean of the two v18 runs 79.8%. `regressed_types_without_design: ["forbidden"]`, so the no-regression rule fails on this run. Cause: public_natural_0065 came back as prose plus JSON on both attempts (`Extra data at line 3`; the open "bad_json first replies" item), so it has no program; run 1 parsed it (wrong, a design row). The other new wrong row, public_natural_0080, uses `code: I.419` where gold has `meaning: chi_dan_dia_gioi` (I.419a); on its gold scene both runs' programs answer yes, as the dataset does (side-by-side check, a recorded exception). Only 0065, 0070 (reason wording) and 0080 differ between the two runs.
- **`lane_reserved_is` fix (2026-11-20, no API):** an R.412 lane row that lists no vehicles now takes the catalog's reserved classes (`vqa/reasoning/facts.py`); before, the lane counted as open to every vehicle and a truck lane gave a confident no. New tests `tests/test_lane_reserved.py` (hand-made R.415a and R.412 scenes). The owner's `tests/test_fixes50.py` (untracked) already tested the intent and fixes the narrower-class reading: on a lane for all cars (R.412f), "dành riêng cho ô tô con" is no, as trucks may use it too. **Exception (owner, 2026-11-20): "xe buýt" on an R.412a bus-and-coach lane is yes.** R.412a reserves the lane for coaches "kể cả ô tô buýt", so every kind of bus counts as one there: `lane_reserved_group(bus)` and `q_lane_reserved_group/3` in `kb/rules/fixes50.pl`, used by `Engine._lane_reserved_is`. Only reserved-lane signs (R.412) with a listed class; an R.415a board for buses and an R.412f car lane keep the narrower-class reading (no). Tests: `tests/test_lane_reserved.py` (14).
- **Freeze:** the fix changes `vqa/`, so the phase51 record no longer matches the tree and a private run from it is refused. Tests check the record's hash at its freeze commit `598a6c1` (`tests/freeze_at.py`, `phase51_record_file`), as for phase49 and phase50. A private run on this code needs a new record. Suite: 2,375 passed.
- **Private runner on phase51 (owner, 2026-11-20):** `eval/e2e_private.py` checks `frozen_phase51.json` by default and accepts profile `phase51` only (`PRIVATE_PROFILES`); the phase49 and phase50 records are now refused by their profile, like the older ones. This replaces the phase49 private run of the approved plan; phase50's "not for the private test" note is superseded by this record. Any later change to `vqa/` or `kb/` makes the run refuse until a new record is written.
- Tests: `tests/test_freeze.py` (phase51 is phase50 with v18; written once) and `tests/test_e2e_private.py` (defaults and profile phase51; phase49 and phase50 refused; mismatch cases add parser v17 and `scene_rerun` on). Suite: 2,348 passed.

### Re-run removal: paired public_holdout check (owner run `aa10b2294ae7`, 2026-11-19): no change, adopted as phase50

- **Plan:** `docs/plans/rerun-removal.md`, approved by the owner. **H0:** "public_holdout is never touched again" was lifted for this one paired run. **R3** was fixed before the run. Runner: `eval/e2e_holdout_rerun.py`. Its sentinel `eval/holdout_rerun_ran.json` is committed; the aggregate is in the gitignored runs folder. Spend **$0.548** (estimate $0.69, cap $1.00).
- **Design:** 49 questions on 45 images, phase49, fallback off, fresh perception. Arm A is the frozen pipeline with the re-run. Arm B is the same pass 1, tiles and guide board, without the re-run, plus new crops where its boxes differ. Both arms use the same v17 program per question.

| public_holdout, rules only (49 q) | A: with re-run | B: without | 95% CI (both) |
|---|---|---|---|
| decided | 38 (77.6%) | 38 (77.6%) | 64–87 |
| accuracy on decided | 92.1% (strict 86.8%) | 92.1% (strict 86.8%) | 79–97 |
| overall, non-decided wrong | 71.4% | 71.4% | 58–82 |
| non-duplicate images (24 q) | 19 decided, 94.7%, overall 75.0% | the same | 55–88 |

- **Paired:** 2 of 49 answers changed, with the same grades; net correct 0.0. No question was fully right in one arm only, so McNemar's p is undefined. **R3: adopt arm B** (net ≥ −1 and decided ≥ A − 1).
- **Latency:** 20 re-run calls on 45 images (44%), 11.5 s each. That is **5.1 s per image** and 21.7% of perception time; the re-run sits alone on the critical path, so this is the time removed. On private's mix (1.4 questions per image) that is about −3.7 s per question, so roughly **22.7 s → ~19 s** after the parallel calls. Re-run cost: $0.017 over 45 images.
- **Note:** these are the first rules-only phase49 figures on public_holdout. They are not comparable to phase 4's holdout result (83.7%, with fallback, scene v4). The holdout has now been used a second time; it is no longer clean for later decisions.
- **R5 applied:** `eval/frozen_phase50.json` is phase49 plus `scene_rerun: False`, code hashed at this commit's `vqa/` (parallel calls and the switch). Profile `phase50` in `eval/freeze.py`. `PipelineConfig()` defaults are unchanged; only the `phase50` profile turns the re-run off.
- **Rebase (2026-11-19, owner's request):** `perf/parallel-calls` was rebased off `exp/option-c` onto the pre-experiment base, dropping the Option C experiment commit (`5fd4db7`, `eval/kb_articles.py` only). Old to new hashes: `bd897a6` → `a16d32c` (parallel calls), `b7a6254` → `9fc6eec` (plan and runner), `79b3e21` → `8ab1a60` (phase50), `175039f` → `618ad20` (test fix). The sentinel `eval/holdout_rerun_ran.json` is write-once and still names `b7a6254`, the commit the run used. Its tree differs from `9fc6eec` only by `eval/kb_articles.py`, so `vqa/`, `kb/`, `prompts/` and the runner are identical. The local branch `perf/parallel-calls-pre-rebase` keeps `b7a6254` reachable.
- **Tests:** the phase49 record pins the code before `a16d32c`. As for phase 4.7 and 4.8, the tests now check its hash at the freeze commit `e8f9134` (`tests/freeze_at.py`, `phase49_record_file`). The run-time guards are unchanged, so a private run from this tree with the real record is still refused. Suite: 2,342 passed.

### Latency: parallel API calls (branch `perf/parallel-calls`, 2026-11-19): 32.9 s → 22.7 s per question, same answers

- **Where the time went** (stage gaps in `logs/api_calls.jsonl`, holdout and validation runs): perception accounts for about 80% of an estimated ~31 s per question. Pass 1 takes ~11 s; the re-run ~15 s on ~48% of images; four tiles ~14 s each, one after another, on ~15%; crops ~7 s each, one after another; the guide-board call ~5 s. The parser (~2 s), engine (<1 s) and writer (~2.4 s) are small.
- **Change (latency only):**
  - `vqa/perception/fallback.py`: the uncached tile and crop replies are fetched in parallel (`REGION_WORKERS = 4`) and then used in the loop's own order. Issues, replies, costs and the scene are the same as when the calls run one at a time.
  - `vqa/pipeline.py`: perception runs in a worker thread beside the parser, which sees the question only (D7). Prolog stays on the calling thread. When perception fails, the parse is already paid: its cost is counted and its trace is kept with `"used": false`, and the answer is unchanged.
  - `vqa/llm/spend.py`, `vqa/llm/client.py`: the spend guard reserves each request's worst case under a lock (`reserve` / `settle`), so parallel requests can't jointly pass the limit. The usage log is locked, and a bad-JSON error carries its own usage.
- **Same outputs:** tests check that parallel and one-at-a-time runs give identical results, with replies finishing out of order. The cached dev and dev2 scene rebuild (137 images, 187 questions, no API call) is byte-identical before and after the change.
- **Timing run (owner, 2026-11-19), $0.138:** 10 dev questions on 10 distinct images, fresh scene cache, phase49 with fallback off. Mean 22.7 s against 32.9 s for the same calls one at a time; the two tiled images went from 66.7 s to 33.8 s and from 88.0 s to 47.5 s. Answers were not judged.
- **Cost:** the same calls and tokens. Parallel calls on a cold prompt cache each write the prompt: about +2% in batch runs, up to ~15–20% when requests are more than 5 minutes apart. The owner chose to leave this as is.
- **Freeze:** `vqa/` changed, so `engine_code.sha256` no longer matches `frozen_phase49.json`. The 12 freeze-record tests (`test_e2e_private.py`, `test_freeze.py`) fail for that reason only. A future frozen run on this code needs a new freeze record.
- **Re-run ablation (free, cached dev and dev2):** without the scene re-run, the same number of questions is decided (dev 73, dev2 79). Grades are unchanged except dev2 train_142 (graded by hand, −1.0), and alternative readings fall by about 40%. It would save ~15 s on about half of images. **Not applied:** it changes outputs and needs the owner's decision and a new freeze record.

### Phase 5 baseline B1 Sonnet on private, once (owner run, 2026-11-18): 85.3% overall

- **Owner decision:** run B1 Sonnet on private now, without the public_dev prompt check and before the system benchmark. This departs from P1 (benchmark first) and from item 2 ("prompts fixed on train and public_dev"). Prompt v1 was pinned unchanged (`ca7d665`).
- **Run:** `e4e251bb8aee`, batch `msgbatch_01AfoTyFa793Mr5CZPCpVE4y`, 12:40–12:49 UTC, at `ca7d665`. 146 requests, all succeeded (no refusal, truncation, error or expiry). Sentinel `eval/baseline_ran_b1_sonnet.json` (committed with this entry). **Aggregate only:** `eval/runs/e2e/b1_private_aggregate_sonnet_e4e251bb8aee.json` (local, no ids). Answers for P6 are kept in `cache/private_run/b1_sonnet_e4e251bb8aee/` (gitignored).
- **Spend $0.673:** batch $0.275, judge $0.398 (estimate $1.20). A first submit was refused by the spend guard ($3.36 worst case > $3.30 cap; nothing written or sent). The estimate now reports the guard's worst case.
- **Public_dev batch canceled:** `msgbatch_011ahBy58nJAgisW33wijPtb` (51 requests) was submitted, then canceled before collect. Requests already processed are billed, not logged; the cost is in the Console only.

| B1 Sonnet, private | score | n |
|---|---|---|
| **overall** | **85.3%** (strict 83.6%) | 146 |
| Yes/No | 78.6% (1 answer with no yes/no first word, graded wrong) | 70 |
| Natural QA | 91.4% (strict 88.2%); judge 67 correct, 5 partial, 4 wrong | 76 |
| non-duplicate images | 86.4% (95% CI 71–94) | 33 |
| duplicate images | 85.0% | 113 |

- **By feature (score, n):** claim 78.6% (70), vehicle class 82.1% (95), turn / stop / park / overtake 83.8% (40), speed 86.1% (36), lanes 73.9% (23), time 83.9% (31), meaning 100% (8), weight or seats 84.6% (13), violation 77.8% (9), no feature 95.0% (10).
- **Not run yet:** B1 Haiku and Opus, B2, and the system benchmark (`eval/e2e_private.py`).

### Phase 5 baseline B1 "Claude alone" built (2026-11-18; no API calls)

- **What:** `eval/baseline_b1.py` with prompt `eval/prompts/baseline/v1` (`baseline/v1@e0914f00eb6e`): the photo (prepared as the scene call sends it, `img1`) and the question go to Haiku, Sonnet or Opus 5.5, effort medium, max_tokens 4000, one plain prompt (no rules, no scene graph, no law_db, no few-shots). The requests go through the Message Batches API (P5). Grading is the system's: Yes/No by the first word, Natural QA by the Opus judge `judge/v1`.
- **public_dev** (for fixing the prompt, readable): `submit --split dev` then `collect <state>`. This writes graded per-question lines to `eval/runs/e2e/b1_dev_<model>_<run_id>.jsonl`.
- **Pin:** `pin --version vN` writes the write-once `eval/baseline_pinned.json`. The private submit refuses any other prompt.
- **Private, once per model, aggregate only:**
  - `submit --split private --confirm-pinned` checks, before anything is written: a clean tree, the pinned prompt, no sentinel `eval/baseline_ran_b1_<model>.json`, no aggregate for that model, git ignoring the answers folder, and counts and image files.
  - The sentinel is written before the batch is created. Request ids are indexes (`q0001`); the sentinel keeps only a hash of the question order.
  - `collect-private` grades in memory and writes `b1_private_aggregate_<model>_<run_id>.json` (no ids). It keeps the model's answers for the owner's P6 scoring in `cache/private_run/b1_<model>_<run_id>/answers.jsonl` (gitignored, model outputs only).
  - The submit checks the batch's worst case (every request at max_tokens) against `--max-spend`.
- **Estimates (counts only, rough):**

| B1 Sonnet | batch expected | batch range | batch worst case | judge | total expected |
|---|---|---|---|---|---|
| public_dev, 51 q | $0.27 | $0.16–0.44 | $1.17 | $0.15 | **$0.42** |
| private, 146 q | $0.78 | $0.47–1.25 | $3.36 | $0.42 | **$1.20** |

- The worst-case column is what the submit checks (the rough prompt count padded by 30%); `estimate` prints it with `min_max_spend_usd` (fixed after the private run, which first used the unpadded $3.25).
- Tests: `tests/test_baseline_b1.py` (27).

```
.venv/bin/python eval/baseline_b1.py estimate --split dev --model sonnet
.venv/bin/python eval/baseline_b1.py submit --split dev --model sonnet --max-spend 1.2
.venv/bin/python eval/baseline_b1.py collect eval/runs/e2e/b1_dev_sonnet_<run_id>.state.json --max-spend 0.3
.venv/bin/python eval/baseline_b1.py pin --version v1
.venv/bin/python eval/baseline_b1.py submit --split private --model sonnet --max-spend 3.4 --confirm-pinned
.venv/bin/python eval/baseline_b1.py collect-private --model sonnet --max-spend 0.6
```

### dev3 estimate (2026-11-18; no API calls, no question text read)

- **Pool (ids and types only):** the train working set minus every dev and dev2 question **and image**, the train few-shots of parser v7–v17 and the train rows of `gold_v12_new`: **118 questions on 95 images** (82 Natural QA, 36 Yes/No). dev3 is not built yet (split builder and runner: aggregate only, runs once, fallback off, like the validation set).
- **Cost** (the private runner's rates with v17's gate rate for the parser, $0.0050 per question; calibration x1.146; fallback off; decided share 0.839 from dev; 20 seeded draws per size):

| size | images | estimate | range (x0.8–x1.3) |
|---|---|---|---|
| 80 (56 Natural QA, 24 Yes/No) | 65–73 | **$0.93–0.95** | up to $1.24 |
| 100 (70 / 30, as dev2) | 80–84 | $1.16–1.17 | up to $1.52 |
| all 118 | 95 | $1.37 | $1.09–1.78 |

- **Budget:** phase 4.8 has **about $1.20** left. Only the 80-question draw fits with its range near the cap; a run stopped by the spend guard would leave a partial aggregate on a set that runs once.
- **Superseded:** the assistant's free check (dev 68.97% with asked_only also off) was not used; the owner froze phase49 with asked_only on and the 0.01-point exception (`e8f9134`).

### Phase49 freeze: v17 accepted by owner (2026-11-18)

- **Owner decision:** “frozen v17 because 0.01% is fine”. Freeze v17 with the retained switches. This is an explicit exception to the dev overall guardrail, not a claim that the original threshold passed.
- **Final measured configuration:** scene v5 + guide reading, parser v17, writer v3, reading policy higher_confidence, signals off; several_signs, sign_charts (N=20), one_sign_g1 and asked_only on; confusable_pairs and stated_exceptions off.
- **Completed rejudges:** dev `dev_rejudge_ce47ca5037a7` (87 rows, 73 decided, 59.5 points; overall **68.3908046%**, decided **81.5068493%**); dev2 `dev2_rejudge_32f3582f8b1c` (100 rows, 79 decided, 56.5 points; overall **56.5%**, decided **71.5189873%**). All five rejudged grades stayed unchanged. These are development figures, not independent benchmark results.
- **Guardrail:** overall misses 68.4% by **0.0091954 percentage points**; the owner accepts this shortfall. Decided accuracy passes 70%. The original bar remains documented unchanged.
- **Rejudge provenance correction:** both raw headers inherited `stated_exceptions: true` from their source. Their recorded commit `7efaccc` has it off. Raw files are preserved; this entry records the correction. Future rejudges now record current switches explicitly.
- **Cost:** $0.0294 + $0.0134 = **$0.0428**; phase spend approximately **$3.80/$5.00**, about **$1.20 remaining** (prior totals rounded). No API calls made to freeze.
- **Freeze:** `eval/frozen_phase49.json`; private runner requires profile phase49 and rejects earlier records. Previous freeze files are preserved. No private or dev3 run is started by this decision.
- **Validation:** freeze check matches the live configuration; full suite **2301 passed**. Private runner tests verify phase49 defaults and reject older records and altered configuration.

### Phase 4.8c PAID 2: v17 re-parse of dev2 and dev, B switches all on (owner runs, 2026-11-18)

- **Runs:** dev2 `eval/runs/e2e/dev2_reparse_v17_4083af459b9b.jsonl`, **$0.448** (cap $0.60); dev `dev_reparse_v17_d589c26e853c.partial.jsonl` stopped by the spend guard after 75 of 87 ($0.347, cap $0.45), resumed with the new `--resume` into `dev_reparse_v17_39c2d86ba1c1.jsonl` (**$0.043**, cap $0.25). Phase 4.8: **$3.76 of $5.00, $1.24 left.**

| | decided | accuracy on decided | overall |
|---|---|---|---|
| dev2, phase 4.8 (v16) | 79 | 64.6% | 51.0% |
| **dev2, v17 + all switches** | **79** | **71.5%** | **56.5%** (net +5.5 over 23 changed answers) |
| dev, phase 4.8 (v16) | 74 | 81.1% | 69.0% |
| **dev, v17 + all switches** | 73 | **81.5%** | **68.39%**: under the 68.4% bar by 0.01 point (59.5 of 87; the bar needs 59.51) |

- **dev2 by cause (keep rule: its changed answers judge better):**
  - **v17: +2.5, kept.** 433, 491 and 502 recovered (+1 each; 502's wording equals few-shot train_468's); 347 0.5 → out of scope; 400 and 447 wrong → undecided; 17, 350, 504 stay 0.
  - **one_sign_g1: +1.5, kept.** 89, 315, 326 0.5 → 1.0; 320 stays 1.0.
  - **asked_only: +0.5 to +1.5, kept.** 195 0.5 → 1.0; 169 0 → 1.0 (shared with v17); 121, 163, 165, 356, 527 unchanged.
  - **sign_charts: kept** (the assistant's reading of the rule, flagged for the owner). Its one change, 131, goes from wrong and decided to undecided: accuracy on decided rises, overall is unchanged.
  - **stated_exceptions: 0, not kept** (switched off). 342 and 356 stay 0.5; the writer did not use the exception.
- **dev:** 107 0.5 → 1.0 and 159 0.5 → undecided (v17); **212 1.0 → 0.5** (asked_only and stated_exceptions; the v17 text is a near-paraphrase of v16's, "là căn cứ" against "quy định việc này", so probably judge variation); 515 and 518 unchanged; the rest keep their grades.
- **The configuration to freeze differs from the one measured** (stated_exceptions off). With it off, dev 212, 280, 428 and dev2 342, 356 get new answers (the switch's value keys go; their banned lists equal v16's). Measuring that configuration: `rejudge` (dry runs: dev $0.025, dev2 $0.016).
- **Fix:** `rejudge` took a `dev2_reparse` file for a dev run (it compared the kind to "dev2" exactly); it now matches `dev2*`, as `reparse` does.

### Phase 4.8c PAID 1: parser v17 gate (owner run, 2026-11-18): passes, v17 kept

- **Run:** `logs/parser_eval/pred_claude-sonnet-5-5_medium_v17_20261118-152942.jsonl`, **$0.234** (estimate $0.23, cap $0.45). Phase 4.8: **$2.92 of $5.00, $2.08 left** (about $1.00 kept for dev3).
- **Rule: `regressed_types_without_design: []`, so v17 passes.** Program accuracy **80.9%** (38/47; non-duplicate 76.5%, n=17); v16 78.7%. Out-of-scope precision 100%.
- **Against v16, row by row:** v17's 9 wrong rows (0005, 0021, 0025, 0055, 0063, 0065, 0085, 0086, 0087) are a subset of v16's 10; **0043 is right again** (v16's one lost design row). No row v16 had right is lost, so no side-by-side check was needed. The lost rows against v6 are the same design rows as before.
- **Step 2 next:** the dev2 and dev re-parse with v17 on stored scenes, B switches as in `kb/switches_48.yaml` (all on); the re-parse header now records the switches (`switches_48`).

### Phase 4.8c built: parser v17 and the free batch (owner, 2026-11-18; no API calls)

#### A1. Out-of-scope groups (dev2's 13 under v16, plus the train working set by wording)

The working set is train minus dev and validation (validation ids dropped before any text was read). Train wordings are matched by pattern, not parsed, so their scope under v16 is a guess. **Bold** = dev2.

| group | questions | n | law_db | built? |
|---|---|---|---|---|
| a vehicle kept to a set of lanes ("phải đi ở một trong hai làn") | **433**, 438 (which vehicle is in the wrong lane) | 2 | D.14, D.16, B.27c | **yes: `lanes_only`** |
| which rule a named vehicle in the photo breaks ("vi phạm lỗi gì") | **502**, 468 | 2 | each sign's article (B.2, B.3) | **yes: `violation_kind`** |
| an absence claim ("không có giới hạn tốc độ", "không có biển nào chỉ hướng rẽ") | **491**, **276** | 2 | (existing `present`) | **a v17 wording line** (no new type; both are dev2, so no few-shot) |
| directions from lane arrows ("được đi theo những hướng nào") | **11** | 1 | D.13 | no: one question; R.411 rows are not read (perception) |
| every vehicle except a class / a weight range minus a subtype | **256**; **213** | 1 + 1 | B.27, B.6 | no: two different asks; "xe bán tải" is no law class |
| a board's symbols (a direction; a count of services) | **198**; **363** | 1 + 1 | none for the symbols | no: two different asks; perception reads no symbols |
| seasonal change of ban hours | **3** | 1 | none | no |
| what happens to an offender ("bị xử lý thế nào") | **224** | 1 | none (Decree 168 is not in law_db) | no |
| the shape of a junction ("chữ Y") | **378** | 1 | C.5's figure only | no |
| numbered sign clusters | **470** | 1 | — | no: perception numbers no clusters |
| a ride-hailing car picking up at midday | **504** | 1 | — | no: one wording, no exact time |

- **433 and 491 (lost in v16):** v14 parsed 433 as `any_of` of two lane permissions and 491 as `verify(present speed_limit, expect=false)`. v16's spec line "a set of lanes ... is out of scope" took 433; 491 went out of scope on its second attempt. v17 narrows that sentence and adds `lanes_only` (433) and the absence line (491).
- **Interpretations:** none. Both types package existing rule answers (`q_lane`, `q_permitted`); no new rule, no knowledge-based row.

#### A2–A4. Parser v17 (`prompts/parser/v17/`)

- **spec:** v16 with one sentence narrowed (the yes/no paragraph no longer lists "a set of lanes" as out of scope) and a "Parser v17 additions" section of three lines: `lanes_only`, `violation_kind`, the absence wording. The examples in those lines are written fresh; a test checks they share no 4-word run with the owner questions and no 5-word run with any dev or dev2 question.
- **few-shots:** v16 plus **train_438** (`choose` of four `lanes_only` options, `expect: false`) and **train_468** (`violation_kind` car), exact text, both in the train working set, in no dev, dev2 or validation set and in no earlier version. **Note:** train_468's wording is identical to dev2 502's ("Ô tô trong ảnh vi phạm lỗi gì?"), so 502's v17 parse leans on a train example with the same words.
- **Engine** (`vqa/reasoning/engine.py`): `lanes_only` decides from the per-lane `q_lane` answers (no when a lane outside the set is open or every lane inside is closed; yes when every lane outside is closed and one inside is open); a verdict that rests on an open lane is unknown when an unreadable or unmodelled sign could bear on lanes. `violation_kind` asks `q_permitted` for each action and lists the actions the rules ban, with their signs (unknown when none is surely banned). Lane sets count from the right like `lane`.
- **Additive:** with every new switch off, the free replay changes **0** stored dev or dev2 answers.

#### B. The free batch (each switch in `kb/switches_48.yaml`, on pending the keep rule)

| switch | what | dev / dev2 answers it changes (free replay) |
|---|---|---|
| `sign_charts` (B1), N = 20 | more than 20 signs = a sign chart: claims one sign decides (permitted, forbidden, speed_ok, required, exists_violation, is_sign, present, sign_applies, speed_limit_is, rule_permitted, lanes_only) are unknown, with a note. N from the stored scenes: road photos read at most 16 signs (dev2 282, 400), the two charts 25 and 26 (dev2 131, 298) | dev2 131 (0, decided → unknown). 298 is a value question and stays |
| `one_sign_g1` (B2) | under G1, a question pointing at one sign names one: board discs the guide call added (g1, g2) are dropped when a sign remains, then a sign read with strictly higher confidence | dev2 89 (0.5), 315 (0.5), 320 (1.0), 326 (0.5) |
| `asked_only` (B2) | `vqa/answer/asked.py`, before the writer and template: pedestrians dropped from vehicle lists unless the question names them; per-lane rows dropped when no lane was asked and the overall limit is decided | dev2 121, 163, 165, 169, 195, 356, 527; dev 212, 280, 428; undecided dev2 164, dev 341 |
| `stated_exceptions` (B3) | which_vehicles bans name "trừ các xe được ưu tiên theo quy định" when every banning sign's article says so (`kb/stated_exceptions_48.yaml`, 19 articles quoted from law_db, `reviewed_by: assistant`); a guide direction answer carries the board's other text (e.g. "30M" on a route diagram) | dev2 342, 356; dev 212, 280, 428 |
| all on | | **18 changed: 16 were decided (dev2 13, dev 3), of which dev2 131 becomes undecided; dev2 164 and dev 341 stay undecided** |

- **Not built in B2:** time windows. No stored answer adds a window the question didn't ask (dev2 170's two windows are what perception read on the plate).
- **B3, route steps:** the scene schema keeps one arrow per board line, so only the board's other text can be carried; dev2 342's "đi thẳng thêm 30 m rồi rẽ trái" needs perception.

#### B4. Checks against law_db (no change)

- **73** (R.415a's group, gold "biển chỉ dẫn"): QCVN 41 art. 32.1 lists "Biển số R.415: Biển gộp làn đường theo phương tiện" among the mandatory signs (biển hiệu lệnh, art. 31–32). The rule is right; **gold disagreement recorded**, nothing changed.
- **204** (P.115 against axle load, gold "trên 13 tấn"): the photo shows a plain "13t" disc, P.115. B.15 bans "trọng tải toàn bộ xe ... vượt quá trị số ghi trên biển" (gross mass); axle load is P.116 (B.16, "tải trọng trục xe"). The answer is right to say P.115 sets no axle load; **gold disagreement recorded** (the question's premise names the wrong quantity), nothing changed.

#### Tests and tools

- `tests/test_phase48c.py` (23): both types on hand scenes (R.415a four-lane board, P.103a, P.104), the wire, v17's spec and few-shot checks, each switch on and off. `eval/phase48c_replay.py check` (free; per switch and all on; ids and verdicts only).
- **Freeze tests:** the engine changed again, so the phase-4.8 record's tests check its engine hash at freeze commit `f8bcb67` (`tests/freeze_at.py`, as for phase 4.7 at `4ad9137`) and require its two recorded switches to keep their values. The run-time guards are unchanged: the private run refuses this tree with `frozen_phase48.json` until the phase-49 freeze.

#### Paid steps (owner runs; nothing spent yet; phase 4.8: $2.69 of $5.00, $2.31 left, about $1.00 kept for dev3)

| # | step | estimate | cap |
|---|---|---|---|
| 1 | parser v17 gate (public_dev gold, Sonnet 5.5 medium, no-regression against v6) | $0.23 ($0.20–0.27; v16's gate was $0.222, the v17 prompt is about 2% longer) | $0.45 |
| 2 | dev2 and dev re-parse on stored scenes (v17 if kept, else v16), changed answers judged | after step 1 | set then, at most what is left above $1.00 |

```zsh
.venv/bin/python eval/parser_eval.py run --model claude-sonnet-5-5 --effort medium --version v17 --max-spend 0.45
read -r 'gate_run?Path of completed v17 predictions: '
.venv/bin/python eval/parser_eval.py score "$gate_run"
.venv/bin/python eval/parser_eval.py compare --old \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-140559.jsonl \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141622.jsonl \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141902.jsonl --new "$gate_run"
```

- **Gate rule:** `regressed_types_without_design` empty. If it fails on a row v16 got right: the free side-by-side check (that row's v16 and v17 programs on its stored scene); an identical answer is a recorded exception, a different one keeps v16 (B still applies). No v18.

### Phase 4.8 closes: freeze phase48, private runner on it (owner, 2026-11-18; no API calls)

- **Freeze `phase48`** (`eval/freeze.py`; `eval/frozen_phase48.json`, written once, a second write refused; `freeze.py check --profile phase48` matches): scene v5 (`scene/v5@7a3291ea5dff`, tile v5-tile, crop v5-crop, scene fallback `crop_always`) with the guide call on, **parser v16** (`parser/v16@b296b65cb7cb`), writer v3, answer fallback v2, reading policy `higher_confidence`, `v6_fields_off: ["signals"]`, **`engine_switches: {several_signs: true, confusable_pairs: false}`** (`kb/switches_48.yaml`, new in the record), and the engine-code hash (64 files). `answer_fallback` is left out as before (the private run keeps the default, on).
- **What changed from phase 4.7:** batch 1 (Law 36 art. 25.3 in speed claims, R.415a vehicles D.16 a, conflicting lane boards and no-vehicle violations unknown, G1 several-sign meaning), batch 2 (misplaced `priority` dropped in the wire, `meaning` aspect `limit`, loose group words for value questions; the confusable table built but off), parser v16. Perception is unchanged.
- **Private runner** (`eval/e2e_private.py`): checks `frozen_phase48.json` by default and accepts profile `phase48` only (`PRIVATE_PROFILES`); the phase-4.5, 4.6 and 4.7 records are refused by their profile before the sentinel, and any mismatch with the phase-4.8 record (parser, scene, guide, reading policy, field switch, engine switches, engine hash, scene fallback) is refused. Tests: `tests/test_e2e_private.py` (defaults now phase 4.8; phase 4.7 added to the refused records; two switch fields added to the mismatch cases) and `tests/test_freeze.py` (the phase-4.8 record matches and is written once). CLAUDE.md's freeze line names phase 4.8.
- **Private estimate, re-based** (`e2e_private.py estimate`, no private file read; 146 questions, 104 images, 76 Natural QA): the phase-4.7 rates with parser v16 at $0.0047 per question (its gate run), calibration x1.146.

| decided share | fallback on (the private run) | fallback off (rules only) |
|---|---|---|
| 0.851 (dev, phase 4.8) | **$1.76** ($1.41–2.28) | $1.49 ($1.19–1.93) |
| 0.79 (dev2, phase 4.8; biased) | $1.84 ($1.47–2.39) | $1.45 ($1.16–1.89) |
| 0.473 (the phase-4.5 final validation) | $2.25 ($1.80–2.92) | $1.29 ($1.03–1.67) |

- **Spend: phase 4.8 $2.69 of $5.00.** The private run has its own budget and is the owner's decision.

```zsh
.venv/bin/python eval/freeze.py check --profile phase48
.venv/bin/python eval/e2e_private.py estimate
.venv/bin/python eval/e2e_private.py run --confirm-frozen --max-spend <cap>
```

### Phase 4.8 PAID 4: v16 re-parse of dev2 and dev (owner run, 2026-11-18): kept

- **Runs:** dev2 `eval/runs/e2e/dev2_reparse_v16_c95f3934da5c.jsonl` (from `dev2_rejudge_a240669b19bf`), **$0.463** (cap $0.95); dev `dev_reparse_v16_248e38bd215e.jsonl` (from `dev_rejudge_f1f0ba0d2f8c`), **$0.363** (cap $0.70). Scene v5 (stored scenes), parser v16, policy A, switches several_signs on and confusable_pairs off; unchanged answers keep their grades. Phase 4.8: **$2.69 of $5.00.**

| | decided | accuracy on decided (95% CI) | overall (non-decided wrong) |
|---|---|---|---|
| dev2 baseline (frozen phase 4.7) | 74 | 58.8% | 43.5% |
| dev2 after batch 1 | 79 | 62.7% | 49.5% |
| **dev2, phase 4.8 (v16 + batch 1 + batch 2)** | **79** | **64.6%** (53.6–74.2) | **51.0%** |
| dev guardrail (bars: overall ≥ 68.4%, accuracy ≥ 70%) | 74 of 87 | **81.1%** (70.7–88.4) | **69.0%** |

- **Keep rules:** v16 passed its gate and the dev guardrail holds (69.0% ≥ 68.4%; 81.1% ≥ 70%): **v16 is kept.** Perception stays scene v5 (step 2). The confusable table stays off (it failed its rule on the free estimate). G1 stays on (75% on its answers).
- **dev2 changes against batch 1** (net +1.5):
  - limit (B3): 151 +1, 252 +1; 196 kept 1.0, 204 stays 0;
  - wire (A2): 282 +1;
  - scope (B4): 346 +0.5;
  - others: 298 +0.5;
  - newly decided and wrong: 169 0 (B6 picks R.403b; the `applies_to` answer lists who it bans, the gold the vehicles it is for), 207 0, 400 0;
  - **lost to out of scope:** 433 (was 1.0), 491 (was 1.0), 213 (was 0.5);
  - lost as unreadable: 9 and 350 (were 0), 11 and 504 out of scope (were 0).
- **dev changes against phase 4.7** (net +0.5): **train_250 is decided again (+1.0, the known v14 regression)**; train_107 1.0 → 0.5; the other 8 changed answers keep their grades.

### Phase 4.8 PAID 3b: parser v16 gate (owner run, 2026-11-18): passes

- **Run:** `logs/parser_eval/pred_claude-sonnet-5-5_medium_v16_20261118-142601.jsonl`, **$0.222** (cap $0.45). Phase 4.8: **$1.86 of $5.00.**
- **Rule: `regressed_types_without_design: []`, so v16 passes** (stopping rule: step 4 with v16). Program accuracy 78.7% (37/47; non-duplicate 76.5%, n=17), as v14. **public_natural_0049 is right again** (`lanes_for`).
- **Lost rows are all design rows:** 0021, 0055, 0063, 0065, 0085, 0086, 0087 (as in v14), plus **0043**, a design row v14 had right: v16 parses it as `meaning` `aspect: scope` on P.107 where the gold is `ban_times`, so B4's scope wording reaches a "when" question. 0070 moved from a wrong `guide_claim` to out of scope (still lost). Without design rows: ban_times 1.0, meaning 0.9, out_of_scope 1.0, lanes_for 1.0.
- **Step 4 prepared (free):** `e2e_dev.py reparse` reads a dev2 run (profile pipeline, dev2 questions, `dev2_reparse_*` file). Perception is unchanged (scene v5), so step 4 re-parses both sets with v16 on their stored scenes; with `--reading-policy higher_confidence` the engine also re-runs on unchanged parses, so batch-2 engine changes are judged too. Unchanged answers keep their grades.

| | source | estimate | cap |
|---|---|---|---|
| PAID 4a, dev2 v16 re-parse | `dev2_rejudge_a240669b19bf` (batch 1 judged) | $0.70 ($0.56–0.91): parser 100 × $0.0047 × 1.146, ~20 changed answers written and judged | $0.95 |
| PAID 4b, dev guardrail v16 re-parse | `dev_rejudge_f1f0ba0d2f8c` (the phase-4.7 judged dev) | $0.53 ($0.42–0.69): parser 87 questions, ~8 changed | $0.70 |

### Phase 4.8: parser v16 built, confusable table off (owner, 2026-11-18; no API calls)

- **Option 1 (owner):** parser v16 = v15 plus one general wording line on `lanes_for`: "How many lanes a vehicle may use ("mấy / bao nhiêu làn") is `lanes_for` too." Few-shot added: **train_484**, exact text ("Theo biển trong ảnh, ô tô chạy 50 km/h được đi trên bao nhiêu làn?" → `lanes_for` car, 50 km/h); it is in the train working set, not in dev, dev2 or validation, and no earlier version uses it. Nothing else changed. `parser/v16@b296b65cb7cb`.
- **Stopping rule (owner, set before the run):** v16 passes → step 4 with v16. v16 fails on a row v14 got right → the free side-by-side engine check: identical answer → a recorded owner exception; different answer → step 4 with v14. No v17.
- **Confusable table off:** `kb/switches_48.yaml` `confusable_pairs: false` (it failed its keep rule on the free estimate, dev overall 67.2% < 68.4%); the code and `kb/confusables_48.yaml` stay for the record. Free replay: dev **73 of 73 decided identical**, dev2 changes only 121, 466, 502, 516.
- **Recorded for later rounds:**
  - **Haiku's measured run-to-run spread on set T is about 4 points** of code F1 (three reads of scene v5 + fallback: 73.0%, 77.0%, 73.7%), more than the 2.9 points the keep rule assumes.
  - **Scene v7 removed the P.131a → P.130 swap** (+3.6 F1, −2.5 recall in one run). A candidate for a later round, judged on repeated runs.
- Tests: `tests/test_phase48_fixes.py` (v16 is v15 plus one line and train_484; the switch is off).

```zsh
zsh /private/tmp/claude-501/-Users-leloc--claude-spares-spare-x5gOhA/80adfa26-b1ec-41eb-92d5-9e80078e7ae5/scratchpad/paid3b.sh   # the v16 gate (estimate $0.23, cap $0.45)
```

### Phase 4.8 PAID 3: parser v15 gate (owner run, 2026-11-18): fails on one row

- **Run:** `logs/parser_eval/pred_claude-sonnet-5-5_medium_v15_20261118-141806.jsonl`, **$0.222** (runner's expected $0.40, cap $0.45; 47 questions). Phase 4.8: **$1.64 of $5.00.**
- **Rule:** `regressed_types_without_design` must be empty. **It is `["lanes_for"]`: v15 fails.**
  - The row: **public_natural_0049** ("... xe ô tô được phép đi vào mấy làn đường ...?", gold "2 làn đường"). v6 (three runs) and v14 parsed `lanes_for` (car), the gold program; v15 answered out of scope ("asks for a count of lanes a car may enter, which no intent expresses").
  - Other lost rows are the 7 design rows v12 and v14 also lost (0021, 0055, 0063, 0065, 0070, 0085, 0087); without design rows forbidden 1.0, meaning 0.9, out_of_scope 1.0, is_sign 1.0 (5/5).
- **Side-by-side engine check (free; public_dev gold scene `public_test_5_4`, R.415a with lanes 1–2 for cars):** the v14 program answers **lanes 1 and 2 (lane_count 4)**, the gold, and oracle A judged that answer correct; v15's out of scope gives unknown. **The regression is real for this row:** a decided right answer becomes undecided.
- **Likely cause:** "mấy làn" reads as a count, and v15's new out-of-scope wording ("when no catalog name tells the asked shape apart") or the `limit` line ("the number ...") makes a count look unanswerable. One run; Sonnet's run-to-run spread is about two questions.
- **The working set has the same wording:** train_484 ("ô tô chạy 50 km/h được đi trên bao nhiêu làn?"), not in dev, dev2 or validation, and not a few-shot in any version.

### Phase 4.8 PAID 2 (c): scene v7, set T (owner run, 2026-11-18): not kept (recall)

- **Run:** `T_claude-haiku-5-5_v7+fb_1073eec9742b.jsonl` (pass 1 + fallback with v7-tile / v7-crop), **$0.093**. Phase 4.8: **$1.42 of $5.00.**

| set T | recall | code F1 (95% CI) | strict F1 | rule-bearing F1 | predicted | non-dup recall / F1 |
|---|---|---|---|---|---|---|
| baseline v5 `3861a1816d1a` | 90.8% | 73.0% (64.8–80.6) | 71.3% | 74.8% | 124 | 91.1% / 73.6% |
| **v7** `1073eec9742b` | **88.3%** | **76.6%** (69.0–85.3) | 73.2% | 74.3% | 115 | 85.6% / 75.9% |

- **Rule:** F1 +3.6 points clears the +2.9 bar, but **recall fell 2.5 points** (non-duplicate −5.5), and the rule requires it not to be lower. **v7 is not kept.** It lists fewer signs (115 against 124), which raises precision and costs recall.
- **The targeted swaps:** P.131a read as P.130 went to **0** (v5 reads: 3, 1, 2); P.125 as P.103a stays at 1 in every read. The notes work for the pair they name; the loss is elsewhere (fewer signs listed).
- **Step 2 outcome:** neither (a) nor (c) passed alone, so no combination is tried. The perception for step 4 stays **scene v5 + fallback** (the frozen one); (b) was not run (cost).

### Phase 4.8 PAID 2 (a): three Haiku reads voted, set T (owner run, 2026-11-18): not kept

- **Runs:** reads 2 and 3 are `82d929851fad` (pass 1 `fa685c76eb6c`) and `a25c2e6e55a4` (pass 1 `2a8b8f23e4e6`), each scene v5 + fallback `crop_always`, **$0.111 + $0.112**. Read 1 is the stored baseline `3861a1816d1a`. Vote: `T_claude-haiku-5-5_v5+fb+vote3_9cda0c31f6c2.jsonl` (free). A first start was stopped by the owner after 11 images (`01cc158e12a8.stopped`, $0.022). Phase 4.8: **$1.33 of $5.00.**

| set T (36 images, 120 gold signs) | recall | code F1 (95% CI) | strict F1 | non-dup recall / F1 |
|---|---|---|---|---|
| read 1 = baseline `3861a1816d1a` | 90.8% | 73.0% (64.8–80.6) | 71.3% | 91.1% / 73.6% |
| read 2 `82d929851fad` | 92.5% | 77.0% (68.4–85.6) | 74.6% | 91.1% / 77.5% |
| read 3 `a25c2e6e55a4` | 92.5% | 73.7% (63.6–83.7) | 71.3% | 90.0% / 73.9% |
| **vote of the three** | **93.3%** | **74.8%** (67.4–82.4) | 73.2% | 92.2% / 74.7% |

- **Rule: F1 at least 75.9% with recall not lower. The vote gives 74.8% (+1.9): (a) is not kept.** Recall holds (93.3%).
- The single reads of one configuration span 73.0–77.0% F1 (4 points), above the 2.9-point spread the rule assumes. The vote lands at their mean (74.6%), so voting removes run-to-run noise but adds no reading skill. A one-run comparison of v7 against the baseline is just as exposed to this spread.

### Phase 4.8 batch 2 built (2026-11-18; no API calls)

- **A1, the confusable table** (`kb/confusables_48.yaml`, switch `confusable_pairs` in `kb/switches_48.yaml`, on for step 4's measurement): a low- or medium-confidence sign with no alternative, read as a table code, gets the partner as a low-confidence alternative. **Under the frozen policy A an alternative alone changes nothing** (the higher-confidence reading wins), so a disagreement that comes from a table partner answers **unknown** (note "often confused with another sign").
  - Pairs, with evidence: P.130 / P.131a (set T 8; dev2 119, 17, 20); P.101 / P.102 (dev2 508: a P.102 read as P.101 at high confidence, seen in the photo; 509; 298); P.103a / P.125 (set T 6); P.103a / P.107 (dev2 508); W.202 / W.228 (dev2 135, a series of bends read as "Đá lở"; the brief's W.201 / W.228 has no evidence); W.201a / W.201b (dev2 102).
  - **Free estimate from stored grades:** dev2 loses 8 decided answers worth 3.0 points (119 0, 131 0, 135 0, 347 0.5, 410 0, 448 1, 495 1, 527 0.5), so accuracy on decided goes from 62.7% to 65.5% and overall from 49.5% to 46.5%. **dev loses train_222 (was right): overall 67.2%, under 68.4%.** As things stand, the table fails its keep rule, and step 4 confirms it. The dev2-based pairs are fitted on dev2 itself.
- **A2, wire:** a `priority` key on an intent node (dev2 282) is dropped instead of rejecting the parse; the vehicle's own `priority` is kept, and other unknown fields are still rejected.
- **B3, limit values (engine half):** `meaning` gets `aspect: limit` (schema and wire): each selected sign's number with its catalog attribute, comparison and unit, citing the row's article (P.106b B.6, P.115 B.15, P.117 B.17, ...); speeds are left to `speed_limit`; an unread number is unknown. Template line: "cấm xe có chiều cao (kể cả hàng) trên 4,3 m".
- **B6, loose group words (engine):** for value questions only (`meaning`, `applies_to`, `which_vehicles`), a `category` that selects nothing falls back to the signs with that group's usual look (information → board, prohibitory → red circle or red board, mandatory → blue circle, warning → triangle), with the note "no sign of the group the question names (...) is in the photo; answered for the sign(s) that look like one, whose group is ...". Claims (`is_sign`, `present`, `count`, `sign_applies`) keep the strict selection. dev2 169 now selects R.403b.
- **Parser v15** (`prompts/parser/v15`, `parser/v15@dcbda79eba59`): v14 plus three spec lines (B3 `limit`; B4 `scope` covers where a ban ends, "khi nào mới được vượt"; B5 a warning sign's "phía trước có ... phải không" is `is_sign` with the meaning whose catalog name says it, out of scope when no catalog name tells the asked shape apart). Few-shots: v14's plus train_240, train_501 (limit) and train_153 (railway crossing, W.211), from the train working set, exact text, none in dev, dev2 or validation. No few-shot for B4: the working set has none.
  - **B5 doesn't cover 378:** W.205's variants share one catalog name ("Đường giao nhau"), and C.5's text doesn't name the Y shape, so "giao lộ hình chữ Y" stays out of scope by the rule.
- **Free replay:** dev's decided answers are identical except train_222 (the table, listed in `INTENDED`); `--confusable-pairs off` gives the batch-1 changes only.
- Tests: `tests/test_phase48_fixes.py` (27).

### Phase 4.8 step 2 prepared: set-T perception candidates (2026-11-18; no API calls)

- **Baseline (no new run):** today's frozen perception on set T is run `3861a1816d1a` (scene v5 pass 1 `82fe91ce935e` + fallback, `crop_always`): **recall 90.8% (85–97), code F1 72.9% (65–81)**; non-duplicate (26 images) 91.1% / 73.6%.
- **Keep rule (owner, fixed before any run):** code F1 above 72.9% by more than 2.9 points (so **≥ 75.9%**), recall not below 90.8%. Non-duplicate figures reported. Parts combine only if each passed alone.
- **Swap evidence** (7 stored Haiku set-T runs with the fallback, v4 / v5 / v6; gold signs v1): P.131a read as P.130 **8 times (7 at high confidence)**; P.127b as IE.452 8 (low / medium); IE.464 as IE.454 6; P.125 as P.103a 6; P.117 as P.101 5; P.124c as P.118 5 (all high); P.111a as P.104 4 (all high).
  - So the A1 table as worded (low or medium confidence, no alternative) would catch **1 of the 8** P.130 / P.131a swaps on set T. Set T shows no P.101 / P.102 swap (P.101 appears as a misreading of P.117) and no W.201 / W.228 swap; those come from dev2 answers only (102, 135).
  - (d) adds alternatives without changing a sign's first code, so set-T code F1 can't measure it; step 4's judged runs decide it.
- **(a) voting:** `vqa/perception/vote.py` (signs clustered across reads with `matching.match(relate=True)`; kept if seen in at least half the reads; the most frequent catalog row wins, ties go to the earliest read; the other codes become low-confidence alternatives, and a high reading the reads disagree on drops to medium). `eval/perception_vote.py` combines run files of one configuration and refuses mixed ones. The four stored v4 runs share one pass 1, so there's no free trial: two new v5 runs are needed (the stored v5 run is the third read).
- **(b) Opus 5.5:** $4.00 / $20.00 per MTok (`vqa/llm/pricing.py`), 40 times Haiku. The rough set-T estimate is **$1.21–2.34 for pass 1 alone**; with the tile and crop fallback, about $2.5–4.5 of the $3.91 left. Not proposed.
- **(c) scene v7** (`prompts/scene/v7`, `v7-tile`, `v7-crop`): v5 plus three visual notes read off the law_db figures: P.130 two red lines crossing, P.131a one slash, P.131b/c plus white bars (B.30, B.31); P.125 two cars side by side, P.103a one car under a slash (B.25, B.3); P.117 a number between two triangles, P.101 an empty disc (B.17, B.1). Pictograms and catalog listing unchanged.
- Tests: `tests/test_phase48_perception.py` (7).

### Phase 4.8 PAID 1: dev2 rejudge of batch 1 (owner run, 2026-11-18): G1 kept

- **Run:** `eval/runs/e2e/dev2_rejudge_a240669b19bf.jsonl`, **$0.0595** (estimate $0.074, cap $0.15). Phase 4.8: **$1.09 of $5.00.**
- **dev2 (100, biased):** 79 decided (was 74), **accuracy on decided 62.7%** (was 58.8%), **overall 49.5%** (was 43.5%).
- **G1, kept** (rule: its changed answers judge at least 70% right): 4.5 of 6 = **75%**. 89 0.5 (lists all three signs), 142 1.0, 315 0.5, 320 1.0, 326 0.5, 498 1.0. 315, 320 and 326 got near-identical answers but grades of 0.5, 1.0 and 0.5 (judge variation).
- **Batch-1 rule fixes:** 466 0 → 1.0 (Yes/No), 121 0 → 0.5 (lists pedestrians and the unknown non-motor vehicles), 502 decided → undecided (was 0). 516 stays 0: its "value" answer with two conditional lanes counts as decided, but the text says "chưa xác định".
- dev is unchanged (the replay plans no dev answer), so the guardrail stays at 68.4% overall and 81.5% on decided.

### Phase 4.8 batch 1: rule fixes and G1 (owner, 2026-11-18; no API calls)

- **Step 1, free checks on the stored dev2 scenes and programs:**

| id | cause | fix | before → after |
|---|---|---|---|
| 466 | rule gap: `speed_ok` ignored Law 36 art. 25.3 ("xe mô tô, xe gắn máy ... không được đi trên đường cao tốc") | a vehicle surely banned from the expressway fails any speed claim there (`kb/rules/fixes48.pl`, cites art. 25); broader classes and three-wheelers keep the speed signs' answer | yes → **no** |
| 121 | rule gap: with no lane asked, R.415a's lane rows were not used | D.16 a ("loại xe được phép lưu thông trên từng làn đường"): a motor vehicle on no lane of the board may not travel on its lanes; a non-motor vehicle is unknown (D.16 d, "làn đường cơ giới"); pedestrians are not covered | every vehicle → **car, motorbike, motor tricycle, bicycle** (+ pedestrian, not covered) |
| 516 | perception (the left board read with cars on every lane), made worse by the engine merging two boards' rows | a lane closed by one board and open on another is unknown (`lane_conflict/4`) | no lane → lane 1 no, **lanes 2–3 conditional** |
| 502 | perception (no vehicle recorded) answered closed-world | `exists_violation` with no vehicle read is unknown (three-valued logic) | no → **unknown** (undecided) |

- **G1** (switch `several_signs` in `kb/switches_48.yaml`, on): `meaning` with `only` over several readable codes lists one meaning per code; `any_of` over `is_sign` claims on one `only` selector is checked sign by sign. Gains 6 questions (89, 142, 315, 320, 326, 498) on **6 distinct image ids**; 315, 320 and 326 have identical sign sets, so probably one scene.
- **G2 needs the parser:** v14 marks 151, 168 and 252 out of scope, and no intent returns a limit's value (`meaning` returns the sign's number, but the parser doesn't choose it). A one-line v15 rule would need the parser gate (v14: $0.22, and the runner refuses a cap under about $0.41) plus a pattern re-parse: **about $0.25–0.45 of the $0.97 left**. Not built (no parser change without the owner's OK).
- **G5, no rule-only fix:** both questions are parsed out of scope. 346's answer is already in the KB (P.125 scope, `kb/sign_info.yaml`, art. 26.8; B.25 c names P.133 / P.135); 378's Y shape is only in C.5's figure, not its text.
- **Free replay** (`eval/phase48_replay.py`, baseline at `b1f6b80`): dev **73 of 73 decided answers identical**; dev2's changed decided answers are exactly 121, 466, 502, 516, plus the 6 G1 gains. A first version of the 466 rule changed dev 352 and 381 (the default `motor_vehicle` includes motorbikes); it now applies only when the ban is certain.
- **Rejudge plan** (dry run): dev2 judges 89, 121, 142, 315, 320, 326, 466, 498, 516, estimate **$0.074** (Yes/No 466 and 498 need no judge); dev plans nothing, so the guardrail stays at 68.4% overall and 81.5% on decided.

```zsh
.venv/bin/python eval/e2e_dev.py rejudge --programs eval/runs/e2e/dev2_baseline_9a403f66bb06.jsonl \
  --scenes eval/runs/e2e/dev2_baseline_9a403f66bb06.jsonl --max-spend 0.15
```

- **Known perception limits (no rule fix):** P.130 / P.131a swapped (17, 20, 119, 459); unreadable signs (G3: 37, 164, 224); lane rows not read on R.411, R.415a and P.127c boards (G4: 207, 235, 429).
- **Intended behaviour changes (owner, 2026-11-18):** 516 and 502 go from "no" to unknown because perception didn't read what the claim needs (which board covers which carriageway; any vehicle). `eval/phase48_replay.py check` lists 121, 466, 502 and 516 as intended (`INTENDED`) and fails on any other changed decided answer.
- **Hash blocker, option 1** (owner, 2026-11-18; `af8af5e`): the phase-4.7 record's tests check its engine-code hash against freeze commit 4ad9137 read from git (`tests/freeze_at.py`), as for phase 4.6 in `6b014df`. The run-time guards are unchanged, so the private run can't run from this tree with `frozen_phase47.json`; step 5 writes a phase-4.8 record.
- **G1 tests:** `test_single_sign.py`'s "stays unknown" test runs with the switch off (unchanged expectation); a new test covers it on.
- **Phase 4.8 budget raised to $5.00** (owner, 2026-11-18). Spent $1.03.

### Phase 4.8 dev2 baseline (owner run, 2026-11-18): biased, for gap-finding only

- **Run:** `eval/runs/e2e/dev2_baseline_9a403f66bb06.jsonl`, frozen phase47, fallback off, **$1.03** (estimate $1.11, cap $1.55). Phase 4.8: **$1.03 of $2.00; $0.97 left.** (An earlier start with no API key left a header-only file, `dev2_baseline_d5adebf8fc9d.jsonl`.)
- **Figures (100 questions):** 74 decided (CI 65–82), **accuracy on decided 58.8%** (CI 47–69), **overall 43.5%**. Natural QA 52/70 decided, 56.7% on decided; Yes/No 22/30, 63.6%.
- **Wrong decided answers lose more than undecided ones:** 30.5 points against 26. Most of the loss comes from sign readings (P.130 / P.131a swapped; P.101 or P.103a read where absent; W.201a/b, W.228), and a few look like engine paths to check (R.415a lanes: 121, 516; motorbike on an expressway: 466; `exists_violation` with P.103a: 502).
- **The 26 undecided, by cause:**

| group | ids | n | fix kind |
|---|---|---|---|
| G1 several readable signs under `only` (`meaning`, `is_sign`) | 89, 142, 315, 320, 326, 498 | 6 | engine (H3, decision O3 reopened) |
| G2 a limit's value asked (height, load, gross mass) | 151, 168, 252 (and decided-wrong 204, partial 195) | 3 | parser + engine, catalog values (B.6, B.15, B.17) |
| G3 unreadable sign | 37, 164, 224 | 3 | perception; no rule-only fix |
| G4 lane rows not read (R.411, R.415a, P.127c boards) | 207, 235, 429 | 3 | perception; no safe fix |
| G5 single wordings out of scope | 3, 198, 256, 346, 363, 378, 400, 470 | 8 | mostly none; 378 and 346 possible |
| G6 other | 167 (one option unknown), 169 ("biển chỉ dẫn" for R.403b), 282 (`priority` inside `rule_permitted`, wire refused) | 3 | each its own |

  - 315, 320 and 326 have the same three signs (IE.452, P.127, R.306), so G1's count may be inflated by one scene.

### Phase 4.8 step 1: dev2 split and runner (owner, 2026-11-18; no API calls)

- **Split:** `eval/make_dev2_split.py` → `data/splits/train_dev2.json` (ids only, `biased: true` with a note), **seed 20261118**. 100 questions on 77 images: **70 Natural QA, 30 Yes/No** (the working set's 232 / 101 of 333, largest-remainder rounding).
  - Pool: the train working set (train minus dev and validation questions and validation images; 333), minus dev and validation images (0 more), the train few-shots of parser v7–v14 (44), and the train rows of `gold_v12_new.yaml` (6): **283** (198 Natural QA, 85 Yes/No).
  - Drawn by question id inside each type (seeded sample). It reads the train QA file for id, image id and type only; `duplicates.json` is not read. Questions on one image may fall on either side.
  - Not excluded (not asked): D3's earlier v9 parse-only diagnosis covered the working set's Yes/No questions, so some of dev2's 30 Yes/No questions were seen there.
- **Runner:** `eval/e2e_dev2.py` (`estimate`, `run`, `summary`), on `e2e_dev.run_dev` with two new options: `profile` (the pipeline from `freeze.pipeline_config("phase47")`, fallback off; the record must be that profile's) and `prefix` (`dev2_<label>_<run_id>.jsonl`, `dev2_cache_<run_id>/` in the gitignored `eval/runs/e2e/`). Guards: dev2 disjoint from dev and validation (ids and images; checked before any text is loaded), profile `phase47` and the live configuration equal to `frozen_phase47.json` (engine hash included), clean tree. The header records `biased: true`, the split file and its sha256.
- **Tests:** `tests/test_dev2.py` (14: split equals the builder, counts and strata, disjointness, few-shot and gold exclusions, id-only selection, the seed, runner on phase47 with a fake SDK, wrong profile, mismatch, dirty tree, estimate).
- **Baseline estimate** (counts only; the private runner's phase-4.7 rates, calibration x1.146, fallback off): **$1.11** ($0.89–1.44) at dev's 83.9% decided share; $1.19 ($0.95–1.54) with every question decided. Suggested cap **$1.55**, of the $2.00 phase-4.8 budget.

```zsh
.venv/bin/python eval/e2e_dev2.py estimate
.venv/bin/python eval/e2e_dev2.py run --label baseline --max-spend 1.55
.venv/bin/python eval/e2e_dev2.py summary eval/runs/e2e/dev2_baseline_<run_id>.jsonl
```

### Handoff (2026-11-18): phase 4.8, dev2

#### Phase 4.7: closed and frozen (`4ad9137`)

- **Frozen system:** `eval/frozen_phase47.json`, profile `phase47`: scene v5 (with tile and crop prompts and the guide call), parser v14, writer v3, answer fallback v2, reading policy `higher_confidence`, scene v6 field switch with **signals off** (`kb/v6_fields_47.yaml`), and the engine-code hash.
- **Owner exception:** the judged dev figure dropped 0.6 points (69.0% → 68.4%), all from train_250, under the rule set before the judged result (a drop of at most one question's worth, 1.15 points, keeps v14). Reason: judge and writer variation alone moved 1.5 points on unchanged answers in `c9c55bd`'s run.
- **Known regressions:** train_250 (v14 splits a two-part board question; the "Đường Tránh Vinh" part is unknown); own_65 (stop-line question parsed as a different claim).

#### Round 3's figures (judged dev, 87 questions, scene v5 + parser v14 + signals off)

- **83.9% decided** (73), **81.5% accuracy on decided**, **68.4% overall** (non-decided counted wrong).
- **Scene v6 rejected on dev:** 63.8% overall with v6 against 69.0%; its losses traced to sign readings (and one unread sign with no recorded look), and its set-T gain was within Haiku's run-to-run spread.
- **The 14 undecided, by cause:** guide boards 4, out of scope 5, selectors 2, choice options 2, lane count 1.

#### The owner's next step: dev2 (phase 4.8)

- **dev2:** 100 questions from the train working set, stratified and seeded, selected by id only. Exclude every parser few-shot and every new-types gold row (`gold_v12_new.yaml`). Mark it **biased** (train is the rules' source); it is used to find and fix coverage gaps, not to report scores.
- Keep the existing rules: validation and holdout stay aggregate only; private answers are never opened.

#### Must not be forgotten

- `eval/e2e_private.py` checks `frozen_phase47.json` by default and accepts profile `phase47` only (`PRIVATE_PROFILES`). **Any later freeze must be added as a new profile and record, and the private runner pointed at it** (default `frozen` argument, `PRIVATE_PROFILES`, and its tests).
- The engine-code hash covers `vqa/**/*.py`, `kb/**/*.pl` and `kb/**/*.yaml`: any engine or KB change after a freeze makes its check fail, by design.

#### Spend

- Round 3: **$2.41 of $2.60.** Phase 4.8: **$2.00 new.** The private run has its own budget (estimate $1.76, $1.40–2.28, at the dev decided share; $2.23, $1.78–2.90, at the validation share).

#### Key files and commands

- **Freeze:** `eval/freeze.py` profiles `phase4`, `phase45`, `phase46`, `phase47` (records `eval/frozen_phase4.json` ... `frozen_phase47.json`, each written once).

```zsh
.venv/bin/python eval/freeze.py check --profile phase47
.venv/bin/python eval/phase47_replay.py check            # free replay on dev + D3 cached scenes: 88/88 identical
.venv/bin/python eval/e2e_dev.py rejudge --programs <dev_run> --scenes <stored-scene runs> --dry-run   # free plan
.venv/bin/python eval/e2e_dev.py rejudge --programs <dev_run> --scenes <stored-scene runs> --max-spend <cap>
.venv/bin/python eval/e2e_dev.py summary <file>
.venv/bin/python eval/parser_newtypes.py score <newtypes_run>
.venv/bin/python eval/e2e_private.py estimate
```

- **Runs:** judged dev, scene v6 `eval/runs/e2e/dev_phase47_d6790322b0dc.jsonl`; the phase-4.7 candidate, judged, `eval/runs/e2e/dev_rejudge_f1f0ba0d2f8c.jsonl`; step 6 (last kept before) `dev_reparse_v11_f52e160181ca.partial.jsonl`.
- **Rules and data:** `kb/rules/general47.pl`, `signals47.pl`, `coverage47.pl`, `v13_47.pl`; `kb/general_duties_47.yaml`, `kb/signals_markings_47.yaml`, `kb/v6_fields_47.yaml`; review list `docs/plans/phase-4.7-review.md`.
- **Parser:** `prompts/parser/v14` (v13 plus one line; few-shots v12's).

### Phase 4.7 closes: scene v5 + parser v14 + signals off, frozen (owner, 2026-11-18)

- **Owner exception (rule set before the judged result, 2026-11-18):** a drop of at most one question's worth (1.15 points on 87 questions) keeps v14 as a recorded owner exception. **Reason:** judge and writer variation alone moved 1.5 points on unchanged answers (same program, same signs) in the scene-v6 dev run of `c9c55bd` (train_212, train_269, train_58).
  - The judged drop is **0.6 points** (69.0% → 68.4%), all from train_250, so **v14 is kept**.
- **Known regression for the next round: train_250.** v14 splits a two-part board question ("rẽ hướng nào ... qua Đường Tránh Vinh", "còn bao xa đến khu công nghiệp") into two `guide` parts; the direction to "Đường Tránh Vinh" is unknown on the board as read, so the question is no longer decided (v11, judged right, asked both parts about VSIP). Also still listed: own_65 (stop line).
- **Freeze `phase47`** (`eval/freeze.py`, profile `phase47`; `eval/frozen_phase47.json`, written once; a second write is refused): scene v5 (`scene/v5@7a3291ea5dff`, tile `scene/v5-tile@d5269387761f`, crop `scene/v5-crop@cee1140f62d7`, scene fallback crop policy) with the guide call on, parser v14 (`parser/v14@c67e28a10b34`), writer v3 (`answer/v3@7d0f2b8ddf1f`), answer fallback v2, reading policy `higher_confidence`, `v6_fields_off: ["signals"]`, and the engine-code hash (60 files: `vqa/**/*.py`, `kb/**/*.pl`, `kb/**/*.yaml`). `answer_fallback` is left out, as in phase 4.5 and 4.6 (each runner sets it; the private run keeps the default, on). `freeze.py check --profile phase47` matches.
- **Private runner** (`eval/e2e_private.py`): checks `frozen_phase47.json` by default and accepts profile `phase47` only (`PRIVATE_PROFILES`); an unchanged phase-4.5 or phase-4.6 record is refused by its profile before the sentinel, and any mismatch with the phase-4.7 record (parser, scene, guide, reading policy, field switch, engine hash, scene fallback) is refused. Tests in `tests/test_e2e_private.py` (the phase-4.5 default tests now name phase 4.7) and `tests/test_freeze.py`.
- **Private estimate, re-based** (`e2e_private.py estimate`, no private file read; 146 questions, 104 images, 76 Natural QA): measured rates of this configuration, parser v14 $0.0046 per question, writer $0.00026 per decided answer, judge $0.00555 per judged answer (dev run `d6790322b0dc`), perception v5 + fallback + guide $0.0021 per image (candidate run `7caed6170de6`), fallback answer $0.008 (phase-4 rate); calibration x1.146 as before.

| decided share | fallback on (the private run) | fallback off (rules only) |
|---|---|---|
| 0.839 (the judged phase-4.7 candidate on dev) | $1.76 ($1.40–2.28) | $1.46 ($1.17–1.90) |
| 0.473 (the phase-4.5 final validation) | $2.23 ($1.78–2.90) | $1.27 ($1.02–1.65) |

  - The private run always runs with the fallback on (the runner never sets `answer_fallback`); its report also gives the rules-only figures. The fallback-off line is the cost of a rules-only run, which the runner does not offer.
- **Doc update (step 8, D5):** DESIGN.md, new section "Schema 1.3 and 1.4, and the phase-4.5 to 4.7 intents and rules" (1.3 guide boards; 1.4 the scene v6 fields, not in the frozen system; the phase-4.5 to 4.7 intents and rule files; the uncertain verdict under policy A; the phase-4.7 freeze and the owner exception), and the uncertain-readings line. CLAUDE.md: the schema line, the verdicts under policy A, the later rule files and the field switch, the freeze and the private runner. `SCHEMA_VERSION` stays "1.2".
- **Spend:** $2.41 of $2.60 (round 3). The private run is the owner's decision (D6).

```zsh
.venv/bin/python eval/e2e_private.py estimate
.venv/bin/python eval/e2e_private.py run --confirm-frozen --max-spend <cap>
```

### Candidate judged: scene v5 + parser v14 + signals off (owner run, 2026-11-18): 0.5 point under the bar

- **Run:** `eval/e2e_dev.py rejudge` → `eval/runs/e2e/dev_rejudge_f1f0ba0d2f8c.jsonl`, **$0.0347** (estimate $0.049, cap $0.15). 79 of 87 rows kept from step 6 (identical engine answers, judged grades); 6 changed decided answers written and judged; 2 now undecided.
- **Judged figures (87 questions):** 73 decided (83.9%, CI 74.8–90.2); **accuracy on decided 81.5%** (CI 71.1–88.8; ≥ 70% holds); **overall 68.4%** (59.5 points). The bar is 69.0% (step 6: 60.0 points), so **the candidate is 0.5 point under it.**
- **Changed answers, judged:** train_80 0.0 (provisional 0.5; step 6 0.0), train_81 1.0, train_159 0.5 (was undecided: +0.5), train_231 0.0, train_272 1.0, train_295 1.0. Not decided now: **train_250 (was 1.0: −1.0)**, train_514 (was 0.0).
  - The net −0.5 is train_250 (−1.0) against train_159 (+0.5). train_250: v14 splits "rẽ hướng nào ... qua Đường Tránh Vinh" and "còn bao xa đến khu công nghiệp" into two `guide` parts, and the direction to "Đường Tránh Vinh" is unknown on the board read; v11 asked both parts about VSIP and was judged right.
- **Spend:** $2.38 + $0.03 = **$2.41 of $2.60; $0.19 left.**
- Not decided by cause: 7 unknown, 5 out of scope, 2 program cannot run.

### Phase 4.7 candidate: scene v5 + parser v14 + signals off (owner, 2026-11-18; no API calls)

- **Owner's decision:** scene v6 is not kept (it fails the dev guardrail, and its set-T gain is within Haiku's run-to-run spread). The candidate is **scene v5 + parser v14 + signals off**.
- **Free estimate:** each v14 program from `dev_phase47_d6790322b0dc` run on step 6's stored v5 scene (`dev_reparse_v11_f52e160181ca`; train_526's from `dev_reparse_v9_8bbb5eb01cff`, as step 6 carried it over), engine with reading policy higher_confidence and signals off. An answer identical to step 6's keeps its judged grade.
  - 74 identical, 12 changed (train_526 identical to its v9 row).
  - Changed and still decided, **provisional grades** (assistant against the dev answer): train_80 0.5 (was 0; names the green boards, gold "Hướng ra"), train_81 1.0 (was 1.0; `all_of` "no" for the three classes), train_159 0.5 (was undecided; I.409 "Chỗ quay xe" plus an extra board), train_231 0.0 (as before; "yes" where the gold is "Không"), train_272 1.0 (as before; same choice, label wording), train_295 1.0 (as before; R.301b conduct "chỉ được rẽ phải").
  - Changed to not decided: train_250 (was 1.0; one `guide` part for "Đường Tránh Vinh" is unknown), train_514 (was 0.0; now out of scope).
  - Changed but undecided both times: train_15, train_341, train_361, train_414.
- **Figures (87 questions):**

| | decided | accuracy on decided | overall (non-decided wrong) |
|---|---|---|---|
| step 6 (last kept) | 74 (85.1%) | 81.1% | 69.0% |
| scene v5 + parser v14, provisional | 73 (83.9%) | 82.2% (CI 71.9–89.3) | **69.0%** |

  - At the 69.0% bar, not below it. The two judgement calls (train_80, train_159) move overall between 67.8% and 70.1%, so judged grades decide it.
- **Judging the changed answers:** `eval/e2e_dev.py rejudge` (new; writer + judge only, no perception or parser call). Its dry run lists the 6 changed decided answers above; estimate **$0.05**, cap $0.15, of the $0.22 left. Tests: `tests/test_phase47_rejudge.py` (hand-made run files, dry run).

```zsh
.venv/bin/python eval/e2e_dev.py rejudge --programs eval/runs/e2e/dev_phase47_d6790322b0dc.jsonl \
  --scenes eval/runs/e2e/dev_reparse_v11_f52e160181ca.partial.jsonl eval/runs/e2e/dev_reparse_v9_8bbb5eb01cff.jsonl \
  --max-spend 0.15
.venv/bin/python eval/e2e_dev.py summary <dev_rejudge_file>
```

- **train_381 checked (free): no marking rule leaks into speed answers.** Removing the three markings from its v6 scene leaves the 70 and 110 km/h options unknown. The cause is an unread sign (s7) that scene v6 recorded with no shape or colour: its visual category is "unknown", which by the documented rule ("nothing recorded: always") could bear on any claim, so `speed_ok`'s closed-world yes becomes unknown. In the v5 scene the same sign is a rectangle board read by the guide call, so it does not count. No rule-only fix proposed. (With scene v5 the question is decided again.)
- **Still a known risk:** own_65 (stop line).

### Judged dev run, scene v6 + parser v14 (owner run, 2026-11-18): fails the guardrail

- **Run:** `eval/runs/e2e/dev_phase47_d6790322b0dc.jsonl`, 87 of 87 questions, **$0.9351** of the $1.10 cap. Signals off.
- **Summary:** 73 decided (83.9%, CI 74.8–90.2), **accuracy on decided 76.0%** (CI 65.1–84.4; ≥ 70% holds), **overall 63.8%** with non-decided counted wrong. Not decided: 9 unknown, 4 out of scope, 1 program cannot run.
- **Guardrail:** overall must not drop below the last kept 69.0% (step 6, `dev_reparse_v11_f52e160181ca`: 73 decided, 81–82% on decided). **63.8% < 69.0%: the candidate is not kept.**
- **Per question against step 6** (dev may be read question by question): net −4.5 points over 15 changed grades.
  - **No loss comes from parser v14:** all 11 losses keep the step-6 program.
  - **Scene v6 readings, −5.5:** train_446 (−1; P.102, R.302a read as R.301d), train_520 (−1; a W.221b read where v5 had UNKNOWN, so the selected signs are not one group: unknown), train_381 (−1; same codes, three markings read, the speed options undecided), train_138, train_14, train_219, train_222, train_268 (−0.5 each; an extra or different sign: P.130, R.403a, W.245a, P.131a).
  - **Same program and signs, answer text graded lower, −1.5:** train_212, train_269, train_58 (−0.5 each; writer or judge variation).
  - **Gains, +2.5:** train_159 (+1) and train_80 (+0.5) from v14's programs; train_414 (+0.5, program and scene); train_450 (+0.5, P.124c read where v5 had P.124a).
- **Reading:** scene v6 improved set T (code F1 72.9% to 75.6%) but loses on dev; parser v14 alone gains here.
- **Spend:** $1.44 + $0.94 = **$2.38 of $2.60; $0.22 left.** A judged rerun with scene v5 + parser v14 (cached v5 scenes; step 6 cost $0.41) does not fit.
- **Free option (no API call):** run each v14 program from this run on step 6's cached v5 scene; a question whose engine answer is identical to step 6 keeps its judged grade, a changed one is graded provisionally. That estimates scene v5 + parser v14 without spending.

### Signals switched off (owner, 2026-11-18)

- **Decision:** `kb/v6_fields_47.yaml` now has `"off": [signals]`, by the fixed 70% rule. **Small n:** set-T precision 66.7% rests on 3 predictions (2 right, 1 wrong; 5 missed, recall 28.6%). Markings (100% on 13) and arrows (nothing to judge) stay on.
  - Light questions now give unknown and go to the fallback, including `at_signal` checks and the v13 green-arrow override; the rules stay in the KB and are tested with every field on.
- **Latent bug found and fixed:** the file's bare `off:` key is YAML 1.1 for `false`, so `yaml.safe_load` read `{False: [...]}` and the switch was never readable (harmless while the list was empty). The key is now quoted, `"off":`; no code change. The pipeline builds `Engine(reading_policy=...)`, which reads the file, so the dev run applies the switch.
- **Replay** (dev and D3 cached scenes): 88/88 decided identical, `decided_changed: []`. No decided answer changed: the cached scenes are scene v5 and carry no lights.
- **Tests (existing ones changed, because the default now has signals off):** the engine fixtures of `tests/test_phase47_scene_v6.py`, `test_phase47_remaining_cells.py` and `test_phase47_v13_rules.py` pin `Engine(v6_fields_off=())`, so they keep testing the light rules; in `test_phase47_v6_fields.py` the "on" cases pin it too, and `test_all_fields_are_on_until_measured` became `test_the_switch_records_the_owners_decision` (signals off, quoted key).
- **Value accuracy on set T** fell from 100% to 92.9%: one value, on a duplicate image (non-duplicate images stay 100%).
- **Next (owner runs it):** the judged dev run, scene v6 + parser v14, estimate $0.84 ($0.67–1.10), **cap $1.10** of the $1.16 left:

```zsh
.venv/bin/python eval/e2e_dev.py run --label phase47 --candidate --scene-version v6 --parser-version v14 --reading-policy higher_confidence --max-spend 1.10
.venv/bin/python eval/e2e_dev.py summary <dev_run>
# guardrail: overall >= 69.0% (judged), accuracy on decided >= 70%
```

### Scene v6 set-T check (owner run, 2026-11-18): v6 stays; signals below 70% precision

- **Runs:** scene `T_claude-haiku-5-5_v6_b12d72995442.jsonl` ($0.0582), fallback crop_always `T_claude-haiku-5-5_v6+fb_7f0df4bf2f7b.jsonl` ($0.0599); **$0.118** in all, of the two $0.10 guards. (A first fallback attempt from the session shell had no API key and stopped before any call, $0.)
- **Signs, against v5 + fallback (`T_claude-haiku-5-5_v5+fb_3861a1816d1a`), 36 images, 120 gold signs:**

| | v5 + fallback | v6 + fallback |
|---|---|---|
| sign recall | 90.8% (CI 85.4–96.8) | 91.7% (CI 86.5–97.1) |
| sign code F1 | 72.9% (CI 64.8–80.6) | 75.6% (CI 69.0–82.4) |
| code F1, rule-bearing | 74.8% | 77.1% |
| value accuracy | 100% | 92.9% |
| non-duplicate (26 images): recall / code F1 | 91.1% / 73.6% | 91.1% / 76.8% |

  - Rule: keep v6 if recall holds and code F1 is within 2.9 points of v5 + fallback. Both hold: **v6 stays.** Value accuracy fell on all images (100% to 92.9%; non-duplicate stays 100%).
- **v6 fields (`eval/v6_fields.py score`):** signals precision 66.7% (2 tp, 1 fp, 5 fn; recall 28.6%): **below 70%, switch off by the rule**; markings precision 100% (13 tp, 0 fp, 25 fn; recall 34.2%): keep on; arrows: nothing to judge (1 board skipped as incomplete), stays on.
  - `kb/v6_fields_47.yaml` records the owner's decision; it is not changed yet (`off: []`).
- **Spend:** $1.32 + $0.118 = **$1.44 of $2.60; $1.16 left** for the judged dev run (estimate $0.84, $0.67–1.10).

### Owner decisions and one rule-only fix (2026-11-18, no API calls)

- **Duties stays on at 2/3** (owner): its miss (own_47) is an abstention that goes to the fallback, not a wrong answer.
- **Round 3 raised to $2.60** (owner). Spent $1.32; **$1.28 left.**
- **Fix, rule-only (owner):** `marking_meaning` that names no marking (no `kind` and no `pattern`) answers only when the photo shows exactly one marking; with more than one it is unknown, with the note "the question did not say which marking, and more than one was read in the photo". Covers the own_58 / own_62 class (painted arrows parsed with no kind). A question with a kind or a pattern is unchanged. No parser change, no new version. Tests on hand-made scenes in `tests/test_phase47_v13_rules.py`; replay 88/88 decided identical.
- **Known risk for the next round:** own_65 (is this the stop line) parses as `verify(rule_permitted past_stop_line, at_signal)`, a different claim.
- **Next, the owner runs them:**

| # | check | estimate | cap |
|---|---|---|---|
| 3 | scene v6 set-T check | $0.13 | $0.20 (two $0.10 guards) |
| 4 | judged dev run, scene v6 + parser v14 | $0.84 ($0.67–1.10) | $1.08 ($1.28 minus set-T's $0.20 cap) |

```zsh
.venv/bin/python eval/perception_eval.py run --set T --model claude-haiku-5-5 --version v6 --max-spend 0.10
.venv/bin/python eval/perception_eval.py fallback <scene_run> --policy crop_always --max-spend 0.10
.venv/bin/python eval/perception_eval.py score eval/runs/perception/T_claude-haiku-5-5_v5+fb_3861a1816d1a.jsonl <scene_fb>
.venv/bin/python eval/v6_fields.py score <scene_fb>
# keep v6 if recall holds and code F1 is within 2.9 points of v5 + fallback (90.8% / 72.9%);
# a field below 70% precision goes into kb/v6_fields_47.yaml off:
.venv/bin/python eval/e2e_dev.py run --label phase47 --candidate \
  --scene-version v6 --parser-version v14 --reading-policy higher_confidence --max-spend 1.08
# --scene-version v5 if set-T fails
.venv/bin/python eval/e2e_dev.py summary <dev_run>
# guardrail: overall >= 69.0% (judged), accuracy on decided >= 70%
```

### New-types run with parser v14 (owner run, 2026-11-18)

- **Run:** `newtypes_v14_20261118-091655.jsonl`, 76 questions (train 6, owner_written 50, owner2 20), **$0.3627** of the $0.55 cap.
- **owner_written:** applies_to 4/4, count 4/5, count_is 4/4, marking_meaning 3/3, rule_permitted 9/9, sign_applies 4/5, signal_meaning 4/5 pass; **duties 2/3 below 80%** (owner's yes needed); marking_is 1/1 not decided.
  - Fixed since v12: own_36 (obligation, now negated), own_41, own_61 (hatched).
- **owner2 (assistant-authored batch):** count_bound 3/3, officer 3/3, precedence 3/3, size_check 3/3 pass; joining_road 2/2, relative_selector 2/2, right_of_way 2/2, vehicle_class 2/2 reported (fewer than 3).
- **Misses (4):**
  - own_05 (count): a W.207 variant for "ngã tư" instead of duong_giao_nhau (as under v12);
  - own_26 (sign_applies, "có tính cả xe máy điện không"): parsed `forbidden` motorbike. Right under v12; v14's new line ("does this sign ban X" stays forbidden) now catches it. Same answer on a ban sign; on a non-ban sign it asks about a ban, not who the sign covers;
  - own_47 (duties, U-turn duties): out of scope, goes to the fallback (as under v12);
  - own_55 (signal_meaning, a red X lane-control light): out of scope, goes to the fallback.
- **Gap rows (gold out of scope; reported apart, gold unchanged):**
  - own_38 (pedestrians on green) is now out of scope, the A2 fix;
  - own_14 (`count_is` ge 2), own_20 (`applies_to`, the sign next to the light: unknown) and own_46 (`right_of_way`, my_road branch) get v13's forms, which fit them;
  - own_48 (an officer, no gesture) and own_68 (painted arrow) fail validation, so they go to the fallback;
  - **risky:** own_58 and own_62 (painted arrows) parse as `marking_meaning` with no kind, so the answer describes the other markings read; own_65 (is this the stop line) parses as `verify(rule_permitted past_stop_line, at_signal)`, a different claim.
- **Spend:** $0.96 + $0.36 = **$1.32 of $2.30; $0.98 left.** Next: scene v6 set-T check ($0.13, cap $0.20), then the judged dev run with v6 + v14 ($0.84, $0.67–1.10; cap = $0.98 minus the set-T spend, so about $0.85 at the estimate, $0.78 if set-T hits its cap).

### Parser v14 gate (owner run, 2026-11-18): passes the fixed rule

- **Run:** `pred_claude-sonnet-5-5_medium_v14_20261118-090623.jsonl`, $0.2240 of the $0.45 cap (47 questions). Program accuracy 78.7% (37/47); non-duplicate 76.5% (n=17, 95% CI 52.7–90.4%).
- **Rule:** `regressed_types_without_design: []`, so **v14 passes**. public_natural_0048 is right again (all_of 3/4, as v6's 0.75).
- **Lost rows:** the same 7 design rows as v12 (0021, 0055, 0063, 0065, 0085, 0086, 0087); the other wrong rows (0005, 0025, 0084) were wrong under v6. Without design rows: forbidden 1.0, meaning 0.9 (v6 0.9), out_of_scope 1.0.
- **Spend:** $0.74 + $0.224 = **$0.96 of $2.30; $1.34 left.**
- **Next, in order:** new-types rerun with v14 (estimate $0.40, cap $0.55); scene v6 set-T check ($0.13, cap $0.20); judged dev run with v6 + v14 ($0.84, $0.67–1.10; cap = $1.34 minus the two runs' actual spend). At the estimates the three come to $1.37, $0.03 over what is left; at the estimates step 4 gets about $0.81.

### Parser v14 built (owner, 2026-11-18: "Build v14"; no API calls)

- **v14 = v13 plus one spec line** (`prompts/parser/v14/spec.md`, last bullet of "New and extended forms"): a ban asked about a vehicle stays `forbidden`, one claim per vehicle (`all_of` for several); `sign_applies` only for "áp dụng cho" / "dành cho" wording. Few-shots are v13's (v12's). P.116 is listed (parser v13 and later).
- Nothing else changed: no rule, catalog row, engine path or gold. `eval/parser_newtypes.py` takes `--version v14` (same estimate as v13). Tests: `tests/test_phase47_parser_v14.py` (exactly one added line, no owner text, the runner).
- The owner's uncommitted edits to `owner_questions.txt` and `labels_v6_fields.yaml` are not part of this commit.

#### Paid checks for v14, in order ($0.74 spent; $1.56 left of $2.30)

| # | check | estimate | cap |
|---|---|---|---|
| 1 | parser v14 gate (no-regression rule against v6) | $0.23 (v13 measured $0.2243) | $0.45 (the runner refuses below its expected, about $0.41) |
| 2 | new-types rerun: train + owner_written + owner2 (76) | $0.40 | $0.55 |
| 3 | scene v6 set-T check | $0.13 | $0.20 (two $0.10 guards) |
| 4 | judged dev run, scene v6 + parser v14 | $0.84 ($0.67–1.10) | $1.56 minus steps 1–3's actual spend |

- **Does not fit at the estimates:** $1.60 against $1.56. At the estimates step 4 gets about $0.80, below its own estimate, so its guard may stop it partway; if steps 1–3 hit their caps, step 4 gets $0.36. A full sequence needs about $0.30 more, or one step left out (the owner decides).

```zsh
.venv/bin/python eval/parser_eval.py run --model claude-sonnet-5-5 --effort medium --version v14 --max-spend 0.45
.venv/bin/python eval/parser_eval.py score <gate_run>
.venv/bin/python eval/parser_eval.py compare --old \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-140559.jsonl \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141622.jsonl \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141902.jsonl --new <gate_run>
.venv/bin/python eval/parser_newtypes.py run --version v14 --sources train owner_written owner2 --max-spend 0.55
.venv/bin/python eval/parser_newtypes.py score <newtypes_run>
# steps 3 and 4 as in the v13 handoff below, with --parser-version v14
```

### Parser v13 gate (owner run, 2026-11-18): fails the fixed rule

- **Run:** `pred_claude-sonnet-5-5_medium_v13_20261118-085146.jsonl`, $0.2243 of the $0.45 cap. Program accuracy 76.6%.
- **Rule:** `regressed_types_without_design = ['all_of']`, so v13 fails. The one row is public_natural_0048:
  - v12: `all_of` of two `forbidden` claims (enter; tractor, then special_machine; sign meaning no_trucks_over_load), matching the gold;
  - v13: `sign_applies` with both vehicles and the same sign.
- **Free check (no API call):** both programs on 0048's cached scene (image public_test_5_10; cache-only; the only cached scene is under the phase4 profile: s1 P.106b 2.5, s2 P.130 with a 06:00-22:00 time plate), engine reading policy higher_confidence.

| | v12 program | v13 program |
|---|---|---|
| verdict | yes | yes |
| value | `{"parts": ["yes", "yes"]}` | `{"per_vehicle": {"tractor": "yes", "special_machine": "yes"}}` |
| citations | QCVN 41 B.6, 22 | QCVN 41 B.6, 22 |
| reasons | s1 true, s1 true | s1 true, s1 true |
| uncertain signs, note, basis | none | none |

- **Result:** verdict, citations and reasons are identical; the value differs in shape (a list of two parts against a dict by vehicle), with the same yes for each vehicle. By the owner's instruction (verdict, value and citations compared), the programs differ, so **v13 fails**. The owner decides whether to treat 0048 as an exception ("equivalent program, same answer"); the gold and the rule are unchanged.
- **Proposed v14:** v13 plus one spec line: "does this ban cover X?" stays `forbidden`; `sign_applies` only for "áp dụng cho / dành cho" wording.
- **Spend:** $0.52 + $0.2243 = **$0.74 of $2.30; $1.56 left.**

### Parser v13 built (owner, 2026-11-18; no API calls): before the one gate

#### Built (branch `phase-5`, not pushed)

- **A. Fixes** (spec wording only, `prompts/parser/v13/spec.md` = v12 plus one section "Parser v13 additions"):
  1. obligations asked yes/no become the permission claim with the negation (`forbidden` for a sign's ban, else `verify(..., expect=false)`), own_36's class;
  2. yielding to pedestrians or to anyone the photo can't show is out of scope, own_38's class;
  3. "vạch chéo" = `kind: hatched`, own_61's class.
  - No owner or owner2 question text in the section (a test checks four-word runs; only the law's term "người điều khiển giao thông" is shared).
- **B and C. New forms**, all in `kb/rules/v13_47.pl` with the law_db text quoted, and in `vqa/schemas.py` / `vqa/parsing/wire.py`:
  - 4 `count_is` with `op` (ge, gt, le, lt; eq is the default and keeps today's path);
  - 5 duties `joining_road` (Law 36 art. 22, 22.1, 25.1 a), cited 22 and 25;
  - 6 `officer_signal`, `officer_permits` (Law 36 art. 11.3; side unknown gives unknown except the all-directions stop);
  - 7 relative selectors (`relative`, `anchor`): above / below from `rank_top_down` on the same side; left / right / next to and lights have no recorded position, so unknown;
  - 8 `right_of_way`, `must_yield` (R.122, W.208: you yield; I.401, W.207: others yield; a read light: unknown, E.1 b; else 22.2 / 22.3; `my_road`, `roundabout` from the question);
  - 9 `precedence`, `precedence_is` (Law 36 art. 11.2, 11.12; QCVN 41 art. 4); in `rule_permitted` with `at_signal`, a green arrow for the very action overrides a sign's ban, a round green never does;
  - 10 `vehicle_class`, `vehicle_class_is` (Law 36 art. 34; moped by design speed, cm3, kW; a broader class gives unknown);
  - 11 size checks: **P.117 height, P.118 width and P.119 length were already modelled**; **P.116 axle load is new** (`axle_t`, QCVN 41 B.16), `listed_from: parser_v13` so only parser prompts v13+ list it and no earlier prompt id changes. P.120 is still not in the catalog.
- **Review list:** `docs/plans/phase-4.7-review.md`, "Parser v13 additions for review": one interpretation (`r_officer_right_turn_only`), the "được đi" reading, the approach assumption for right of way, the light-over-sign change, P.116.
- **No few-shot added:** v13's few-shots are v12's. The train working set was not searched for the new types this round.
- **Existing tests changed (4), each because of a new row, rule or the owner2 group:**
  - `tests/test_gold_signs.py:454` used P.116 as its unknown code ("not in the catalog yet"); now P.199;
  - `tests/test_meaning_rows.py`: the pinned assistant-checked rows add the parser-v13 row P.116;
  - `tests/test_phase47_law_consistency.py`: the interpretation set adds `r_officer_right_turn_only` with its premise phrase;
  - `tests/test_phase47_newtypes.py`: the group and row counts add owner2 (20 rows; 176 in all), and owner2 types with 2 questions are "not decided".
- **One existing answer can change:** `rule_permitted` with `at_signal`, a green arrow for the asked action and a sign banning it was no and is now yes (QCVN 41 art. 4.1). The replay has no such case.
- **Gate:** `eval/parser_eval.py` gives v13's new forms back as design only on gold out-of-scope rows (`V13_FEATURES`), as for v12.
- **Matrix:** 1223 cells: 728 modelled, 0 to build, 483 n/a, 12 out (was 1158: 713 / 0 / 435 / 10); five topic rows added (officer, precedence, right of way, size and axle limits, vehicle classes).
- **Replay:** 88/88 decided identical, `decided_changed: []`.

#### owner2 gold (20 rows, for the owner's check)

`data/annotations/gold_v12_new/gold_v12_new.yaml`, source `owner2`, the "owner2 |" lines of `owner_questions.txt` at `d427da1`, verbatim. The file marks this batch "assistant-authored at user request; not independent owner-written evidence", so its rates come from the same model family as the parser. Decided where a type has ≥ 3 rows: count_bound, officer, precedence, size_check. Reported only: joining_road, relative_selector, right_of_way, vehicle_class (2 each).

| id | line | type | expected program |
|---|---|---|---|
| own2_01 | 73 | count_bound | `{intent: count_is, sign: {category: prohibitory}, n: 3, op: ge}` |
| own2_02 | 74 | count_bound | `{intent: count_is, sign: {category: warning}, n: 4, op: le}` |
| own2_03 | 75 | count_bound | `{intent: count_is, sign: {meaning: speed_limit}, n: 2, op: gt}` |
| own2_04 | 76 | joining_road | `{intent: duties, topic: joining_road}` |
| own2_05 | 77 | joining_road | `{intent: must_yield, other_from: main_road, my_road: branch}` (also: 1) |
| own2_06 | 78 | officer | `{intent: officer_signal, gesture: right_arm_up}` |
| own2_07 | 79 | officer | `{intent: verify, claim: {intent: officer_permits, gesture: arms_sideways, side: front, action: go_straight}, expect: false}` |
| own2_08 | 80 | officer | `{intent: officer_signal, gesture: arms_sideways, side: back}` |
| own2_09 | 81 | relative_selector | `{intent: meaning, sign: {relative: below, anchor: {meaning: no_parking}}}` (also: 1) |
| own2_10 | 82 | relative_selector | `{intent: forbidden, action: enter, vehicle: {vehicle_class: coach}, sign: {relative: left_of, anchor: {light: true}}}` |
| own2_11 | 83 | right_of_way | `{intent: right_of_way}` |
| own2_12 | 84 | right_of_way | `{intent: must_yield, other_from: cross_road}` |
| own2_13 | 85 | precedence | `{intent: precedence, between: [light, officer]}` (also: 1) |
| own2_14 | 86 | precedence | `{intent: rule_permitted, action: turn_left, at_signal: true}` |
| own2_15 | 87 | precedence | `{intent: precedence_is, winner: temporary_sign, over: permanent_sign}` |
| own2_16 | 88 | vehicle_class | `{intent: vehicle_class_is, vehicle: {vehicle_class: motorbike, design_speed_kmh: 45, motor_kw: 3}, of_class: moped}` |
| own2_17 | 89 | vehicle_class | `{intent: vehicle_class, vehicle: {vehicle_class: car, seats: 16}}` |
| own2_18 | 90 | size_check | `{intent: permitted, action: enter, vehicle: {vehicle_class: truck, width_m: 2.4}, sign: {meaning: width_limit}}` |
| own2_19 | 91 | size_check | `{intent: forbidden, action: enter, vehicle: {vehicle_class: motor_vehicle, length_m: 14}, sign: {only: true}}` (also: 2) |
| own2_20 | 92 | size_check | `{intent: permitted, action: enter, vehicle: {vehicle_class: motor_vehicle, axle_t: 8}, sign: {code: P.116}}` (also: 1) |

#### Paid checks, in order (the owner runs them; round 3 is $2.30, $0.52 spent, $1.78 left)

| # | check | estimate | cap |
|---|---|---|---|
| 1 | parser v13 gate (no-regression rule against v6) | $0.25 (v12 measured $0.23; prompt +8%) | $0.45 (the runner's own expected is about $0.41 and it refuses a lower cap) |
| 2 | new-types rerun: train + owner_written + owner2 (76 questions) | $0.40 (from the v12 run's measured costs) | $0.55 |
| 3 | scene v6 set-T check (label sheet done, `658d4b2`) | $0.13 | $0.20 (two $0.10 guards) |
| 4 | judged dev run, scene v6 + parser v13 | $0.84 ($0.67–1.10; `e2e_dev.py estimate --candidate`) | $1.78 minus steps 1–3's actual spend, at most $1.00 |

Steps 1–3 cap at $1.20, so step 4 is at least $0.58 even if all three hit their caps; at the estimates, step 4 gets about $1.00. Spend cannot pass $2.30.

```zsh
# 1. gate
.venv/bin/python eval/parser_eval.py run --model claude-sonnet-5-5 --effort medium --version v13 --max-spend 0.45
.venv/bin/python eval/parser_eval.py score <gate_run>
.venv/bin/python eval/parser_eval.py compare --old \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-140559.jsonl \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141622.jsonl \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141902.jsonl --new <gate_run>
# rule: regressed_types_without_design must be empty

# 2. new-types rerun
.venv/bin/python eval/parser_newtypes.py run --version v13 --sources train owner_written owner2 --max-spend 0.55
.venv/bin/python eval/parser_newtypes.py score <newtypes_run>
# rule: owner2 decides each new type at >= 80% where it has >= 3 questions; owner_written as before

# 3. scene v6 set-T check
.venv/bin/python eval/perception_eval.py run --set T --model claude-haiku-5-5 --version v6 --max-spend 0.10
.venv/bin/python eval/perception_eval.py fallback <scene_run> --policy crop_always --max-spend 0.10
.venv/bin/python eval/perception_eval.py score eval/runs/perception/T_claude-haiku-5-5_v5+fb_3861a1816d1a.jsonl <scene_fb>
.venv/bin/python eval/v6_fields.py score <scene_fb>

# 4. judged dev run (--scene-version v5 if step 3 failed)
.venv/bin/python eval/e2e_dev.py run --label phase47 --candidate \
  --scene-version v6 --parser-version v13 --reading-policy higher_confidence --max-spend <left, at most 1.00>
.venv/bin/python eval/e2e_dev.py summary <dev_run>
```

- **Out this round:** following distance, fine amounts, painted road arrows (the next perception field), pedestrians.

### Phase 4.7: parser v12 gate and new-types test run (owner, 2026-11-18; results accepted)

- **v12 gate** (`pred_claude-sonnet-5-5_medium_v12_20261118-074501.jsonl`, $0.23 of the $0.40 cap): **passes the phase-4.7 rule**, `regressed_types_without_design: []`.
  - Program accuracy 78.7% (37/47; the old ≥ 90% point-estimate gate does not apply to v12, which gives programs on gold out-of-scope rows). Non-duplicate 76.5% (n=17, 95% CI 52.7–90.4%).
  - All 7 lost rows are v7 design rows (0021, 0055, 0063, 0065, 0085, 0086, 0087): v12 gives a new-form program where v6's gold is out of scope. The other 3 wrong rows (0005, 0025, 0084) were already wrong under v6.
  - Without design rows: forbidden 1.0, meaning 0.9 (v6 0.9), out_of_scope 1.0.
- **New-types test, train + owner_written** (`newtypes_v12_20261118-075435.jsonl`, $0.29 of the $0.40 cap):
  - owner_written passes: applies_to 4/4, count 4/5, count_is 4/4, sign_applies 5/5, signal_meaning 5/5.
  - Below 80%, **kept on with the owner's yes**: rule_permitted 7/9, duties 2/3, marking_meaning 2/3. marking_is 1/1 is not decided (too few).
  - Misses: own_36 (an obligation asked yes/no, parsed without the negation: the verdict is inverted); own_41 (extra `action: overtake`, same verdict, citations and reasons on an empty and a double-solid scene; gold unchanged); own_47 (out of scope, goes to the fallback); own_61 (no `kind: hatched`); own_05 (a W.207 variant for "ngã tư"); train_243 (the selector without `category`).
  - Gap rows given a program: own_38 (yielding to pedestrians on green parsed as `rule_permitted` at `pedestrian_crossing`, which can give a wrong yes), own_20 (taken as the only sign). own_62, 66, 68 fail validation and go to the fallback.
- **Spend:** $0.52 of round 3. The owner raised round 3 to $2.30 (2026-11-18).
- **Next:** parser v13 (owner, 2026-11-18): the fixes for the own_36, own_38 and own_61 classes, plus new types (count bounds, joining roads, an officer's signals, relative selectors, right_of_way, precedence, vehicle_class, size checks), then one gate.

### Handoff (2026-11-18): phase 4.7, before the paid checks

#### Built (committed up to `17ac8bf`, branch `phase-5`, not pushed)

- **Matrix:** `docs/plans/phase-4.7-coverage-matrix.md`, generated by `eval/coverage_matrix.py matrix`.
  - 1158 cells: 713 modelled, **0 to build**, 435 n/a, 10 out.
- **9 new intents:** `count`, `count_is`, `applies_to`, `sign_applies`, `rule_permitted`, `duties`, `signal_meaning`, `marking_meaning`, `marking_is`.
- **Rule files and data:**
  - `kb/rules/coverage47.pl`: who a sign applies to;
  - `kb/rules/general47.pl`: Law 36 art. 13.3, 14.6, 15.4, 18.4, 25.1–25.2 and 27.4, plus Circular 38 art. 7 (interpretation);
  - `kb/rules/signals47.pl`: R.411 arrows (D.13), lights (art. 6) and markings (G.1);
  - new violation clauses in `kb/query.pl`: pictured vehicles against zones, arrows, lights and markings;
  - data: `kb/sign_info_47.yaml`, `kb/general_duties_47.yaml`, `kb/signals_markings_47.yaml`.
- **Scene v6:** `prompts/scene/v6`, `v6-tile`, `v6-crop`. Reads R.411 lane arrows, traffic lights and road markings; empty fields are left out of scene dumps.
- **Parser v12:** `prompts/parser/v12`, which is v11 plus the new forms and 7 train few-shots.
  - The gate gives v12 forms back as design only on rows whose gold is out of scope.
- **Field switch:** `kb/v6_fields_47.yaml`, with every field on. A field below 70% precision on set T goes into `off:`, and its rules then give unknown.
- **Circular 38 fix:**
  - trucks are grouped by payload (a gross mass up to 3.5 t still gives group 1);
  - coaches by seat count;
  - `bus` and group 4 stay unknown.
- **Other fixes:** a light question with no light read gives unknown (`at_signal`).
- **Review list:** `docs/plans/phase-4.7-review.md`.

#### New-types gold (`data/annotations/gold_v12_new/gold_v12_new.yaml`, scored by `eval/parser_newtypes.py`)

| group | rows | role |
|---|---|---|
| train | 6 (ids and programs only) | decides; at least 5 per type at 80% (no type reaches 5) |
| owner_written | 50, from `owner_questions.txt` at `2c31cd6`; the owner wrote them | decides; at least 3 per type at 80% |
| ai_drafted_owner_reviewed | 50, pinned to `owner_questions.txt` at `41291ef` | smoke test, reported apart |
| assistant_written | 50, written by the assistant | smoke test, reported apart |

- **DSL gaps among the owner rows:** 12 at `17ac8bf`, 11 after the reversing fix, reported apart from the type rates:
  - a count compared with a number (line 14);
  - a sign placed next to a light (line 20);
  - reversing (line 33; fixed 2026-11-18, now expressible);
  - pedestrians crossing on green (line 38);
  - yielding when joining a main road (line 46);
  - a traffic officer's signals (line 48);
  - painted road arrows (lines 58, 62, 68);
  - marking-kind claims (lines 65, 66);
  - the effect of a hatched area (line 69).
- **Expressible owner rows per type:** count 5, count_is 4, applies_to 4, sign_applies 5, rule_permitted 9 (8 at `17ac8bf`, plus line 33), duties 3, signal_meaning 5, marking_meaning 3, marking_is 1. marking_is is reported, not decided.

#### Done (2026-11-18): two additive fixes before the gate (owner lines 33, 34)

1. **Stopping and parking in a tunnel** (line 34). `tunnel_stop/2` in `kb/rules/general47.pl`, citing Law 36 art. 26.2 ("Không dừng xe, đỗ xe trong hầm đường bộ", quoted from law_db with its breakdown exception), using the emergency-lane pattern: `stop_reason: other` gives no, `breakdown` gives yes, no reason gives unknown. Line 34's program carries `stop_reason: other`.
2. **Reversing** (line 33). `maneuver: reverse` in `RulePermitted` and the wire schema; `general_ban(reverse, ...)` for every place art. 16.2 lists (quoted from law_db), with two new places `no_stopping_zone` and `limited_view`. Our reading: `curve_limited_view` and `hill_crest_limited_view` also count as "nơi tầm nhìn bị che khuất" (in the review list). Reversing elsewhere gives yes citing art. 16; no place gives unknown; markings, lights and signs do not decide it. Parser v12's spec gains the two places, the tunnel `stop_reason` and the reverse line (same version, before the gate). Line 33 is now reverse + intersection + car, no longer a gap: **11 DSL gaps** among the owner rows.
- **No few-shot.** The only train question about reversing is in the phase-4.5 validation set, so it cannot be used.
- **Validation exposure (2026-11-18, assistant):** while searching the train file for "lùi", the assistant saw the text and cited article of one validation question (citing art. 16; id not written here, since the validation tests treat ids named in the repo as used) before checking the validation id list. Nothing was built from it: the rule comes from law_db art. 16.2 and owner line 33, and it is not a few-shot, fixture or gold row. The owner decides whether to keep it in the validation aggregate.
- **Spec wording:** example phrases taken from owner lines 32–34 ("để xem bản đồ", "để thả người xuống", "ngã ba") were removed from the draft spec, since those lines decide the type rates.
- **Checks:** full suite passed; replay 88/88 identical, `decided_changed: []`; matrix regenerated, totals unchanged (713 modelled, 0 to build, 435 n/a, 10 out).

#### Next perception field

- **Painted road arrows** (G.4 9.3) stay out this round; owner lines 58, 62 and 68 need them.

#### Owner's open tasks

- **v6 label sheet:** fill `data/annotations/gold_v6_fields/labels_v6_fields.yaml` by hand before the set-T check: lights, markings and R.411 arrows for the 36 set-T images, with `checked: true`. Only `train_1_6` has an R.411 board in the gold sign labels.
- **Circular 38 boundaries:** confirm from the official text:
  - the vehicle groups (seats, payload, buses, motorcycles, group 4);
  - the numbers in `r_c38_outside` (90 / 80, 80 / 70, 70 / 60, 60 / 50 km/h);
  - the `r_c38_*` speeds, which were written from memory.

#### Paid checks, in order (the owner runs them; caps never sum past $2.00)

| # | check | estimate | cap |
|---|---|---|---|
| 1 | parser v12 no-regression gate | $0.21 | $0.40 (the runner refuses lower) |
| 2 | new-types test, train + owner_written only (56 questions) | $0.23 | $0.40 |
| 3 | scene v6 set-T check, with the v6 fields | $0.13 | $0.20 (two $0.10 guards) |
| 4 | judged dev run, scene v6 + parser v12 | $0.85 | what is left, at most $1.00 |

Steps 1–3 cap at $1.00, so step 4 is capped at $1.00 and the total cannot pass $2.00. The two fixes above changed parser v12's prompt before any gate ran.

```zsh
# 1. gate
.venv/bin/python eval/parser_eval.py run --model claude-sonnet-5-5 --effort medium --version v12 --max-spend 0.40
.venv/bin/python eval/parser_eval.py score <gate_run>
.venv/bin/python eval/parser_eval.py compare --old \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-140559.jsonl \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141622.jsonl \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141902.jsonl --new <gate_run>
# rule: regressed_types_without_design must be empty; on a failure stop (one v13 fix needs the owner's yes)

# 2. new-types test, deciding groups only
.venv/bin/python eval/parser_newtypes.py run --sources train owner_written --max-spend 0.40
.venv/bin/python eval/parser_newtypes.py score <newtypes_run>
# rule: >= 80% per type (>= 5 train or >= 3 owner_written questions); weaker types stay on only with the owner's yes

# 3. scene v6 set-T check (after filling the label sheet)
.venv/bin/python eval/perception_eval.py run --set T --model claude-haiku-5-5 --version v6 --max-spend 0.10
.venv/bin/python eval/perception_eval.py fallback <scene_run> --policy crop_always --max-spend 0.10
.venv/bin/python eval/perception_eval.py score eval/runs/perception/T_claude-haiku-5-5_v5+fb_3861a1816d1a.jsonl <scene_fb>
.venv/bin/python eval/v6_fields.py score <scene_fb>
# rules: keep v6 if recall holds and code F1 is within 2.9 points of v5 + fallback (90.8% / 72.9%);
# a field below 70% precision goes into kb/v6_fields_47.yaml off:

# 4. judged dev run (--scene-version v5 if step 3 failed)
.venv/bin/python eval/e2e_dev.py run --label phase47 --candidate \
  --scene-version v6 --parser-version v12 --reading-policy higher_confidence --max-spend <left, at most 1.00>
.venv/bin/python eval/e2e_dev.py summary <dev_run>
# guardrail: overall >= 69.0% (judged), accuracy on decided >= 70%
```

#### Proof replay

- **Result:** 88/88 decided answers identical after every committed part (baseline `464c1f8`, 107 questions: dev v11 and D3 cached).
- **Run:** `.venv/bin/python eval/phase47_replay.py check`. It must report `"identical": 88` and `"decided_changed": []`.
- **Suite:** run it as one chain with the commit: `set -o pipefail; .venv/bin/python -m pytest -q 2>&1 | tail -1 && ... && git add <files> && git commit`. Without `pipefail`, a piped pytest hides failures.

#### Rules

- **Additive only:** no existing rule, catalog row or field, intent, slot or engine behaviour is changed or removed. Existing tests stay unchanged; the only exception was the two final2 record tests (owner's option 1, `6b014df`).
- **Dev is a check, not a source:** rules come from the law (law_db first; interpretations carry a basis note).
- **Not touched:** validation data and sentinels, holdout, private, existing gold files outside `gold_v12_new`, any `frozen_*.json`.
- **Commits:** stage files by name and check the staged list.

#### Spend

- **$0 of round 3's $2.00.** No API call was made in phase 4.7.


### Handoff (2026-11-17): phase 4.7 free checks complete; owner approval next

- The engine, catalog, v11/v12 prompts and pre-existing tests are unchanged in this continuation. All checks used local inputs. API spend was $0.
- **Step 2** (`5f13eb9`): 784 generated cases passed. Two cases on one P.106b row had applied its truck load threshold to tractor and special machine. The test now checks the row's value classes and their subclasses. Zero remaining differences. Fifteen additional law-consistency checks passed, covering every live rule source, interpretation premises, numeric speed passages and posted-limit precedence. The corpus cannot authenticate the Circular 38 numbers.
- **Step 3** (`570b392`): the local v12 wire programs are `eval/runs/phase47/dev_v12_hand.json` and `d3_v12_hand.json` in the same directory. The standard and hand-program replays both preserved all 88 baseline decisions at `464c1f8`, with `decided_changed: []`. The hand run returned 89/107 decided; its extra yes used signs alone on a question about a light, with no signal observation. **Zero new evidence-backed cells on these cached scenes.** All five D3 override programs lack cached scenes. The generated matrix remains 700 modelled / 18 to build / 432 n/a / 8 out (1,158 total).
- **Review** (`99b7f5b`): `docs/plans/phase-4.7-review.md` inventories assistant-reviewed rows, interpretation bases and the four requested deferrals. Review `r_c38_outside` first; the official art. 7 table, vehicle group boundaries and mass basis remain unverified. Also decide whether to add a signal-specific claim that can abstain when no signal was read.
- **Paid checks prepared only:** the dev runner (`66bf4c7`) accepts scene/parser versions and reading policy for a fresh candidate run. The exact commands, comparison files and budgets are in `docs/plans/phase-4.7-review.md`, “Owner-run paid checks”. In order: v12 parser gate ($0.21 estimate, $0.40 cap), v6 set T ($0.13, $0.20 total over both passes), judged dev ($0.85, $1.05). Total estimate $1.19; caps $1.65 of $2.00. V12 compatibility on live model output and v6 perception quality await the paid checks.
- **Verification:** 2,070 tests pass with the CLI checks included. Each step was committed only after the full suite and the baseline replay passed.
- **Next action belongs to the owner:** review the findings and approve the paid sequence. No phase-4.7 freeze, validation or private run was performed.

### Phase 4.7: owner-written new-types questions added (owner, 2026-11-17; no API calls)

- **The 50 questions of `owner_questions.txt` at `2c31cd6`** are now `owner_written`, with their text verbatim. The basis is the owner's message "I just update 50 questions"; the lines have no "owner |" prefix.
  - The earlier 50 AI-drafted rows stay as a smoke test and point at their file version, `41291ef`.
- **12 owner questions are DSL gaps:** count comparisons, a selector relative to a light, reversing, pedestrians on green, junction yielding, an officer's signals, road arrows (3), marking-kind claims, and the hatched area's effect.
- **Expressible owner questions per type:** count 5, count_is 4, applies_to 4, sign_applies 5, rule_permitted 8, duties 3, signal_meaning 5, marking_meaning 3, marking_is 1 (reported, not decided).
- **Rule gap found:** Law 36 art. 26.2 ("Không dừng xe, đỗ xe trong hầm đường bộ") is missing from `kb/rules/general47.pl`, so parking in a tunnel is wrongly allowed. It is not fixed yet; the owner decides.
- **Run:** the deciding groups (56 questions), $0.23, cap $0.40. All 156 would be $0.55, cap $0.85, which is not recommended within $2.00.

### Phase 4.7: new-types question sources corrected (owner, 2026-11-17; no API calls)

- **Owner's correction:** the 50 rows from `owner_questions.txt` are AI-drafted, not owner-written; the earlier confirmation was wrong.
  - They are relabelled `ai_drafted_owner_reviewed` and kept as a smoke test, like `assistant_written`.
  - Their line numbers were re-pointed after `41291ef` shifted the file.
- **Owner-written rows:** none yet.
  - The owner's note says rewritten lines are marked "owner |"; the file at `41291ef` has no such line.
  - Its 50 newer questions carry no owner mark and are not in the gold.
- **Who decides:** only train (5 or more per type) and owner-written (3 or more per type), at 80% or better. With 6 train rows (no type has 5) and no owner-written rows, no type can be decided yet.
- **Estimate:** $0.39 for all 106 rows (cap $0.60); the deciding groups alone are 6 train rows, $0.07 (cap $0.20).

### Phase 4.7: measurements added before the paid checks (owner, 2026-11-17; no API calls)

- **Circular 38 check** (`5c46b5e`):
  - trucks are grouped by payload; a gross mass up to 3.5 t still gives group 1;
  - coaches go by seat count;
  - `bus` and group 4 (tankers, mixers, trailer towing; no vehicle class) stay unknown.
- **Matrix finished** (`6ab4bb1`): 713 modelled, 0 to build, 435 n/a, 10 out.
- **New-types parser test** (`58b95e1`): 56 rows, 6 train and 50 assistant-written, with every new intent at 5 or more; estimate $0.23.
- **v6 field measurement** (`1b14ba9`):
  - a set-T label sheet for the owner to fill;
  - `eval/v6_fields.py score`;
  - the switch `kb/v6_fields_47.yaml`, all fields on until measured.
- **Paid checks, in order:** `docs/plans/phase-4.7-review.md`, last section. Estimate $1.42; each cap is set as its step runs, staying within $2.00.

### Phase 4.7: light questions without a light read (2026-11-17; no API calls)

- **Fix** (owner's yes, before the v12 gate): `rule_permitted.at_signal`.
  - With the flag set and no vehicle light read, the answer is unknown, citing art. 6. Before, it could be a "yes" from the signs alone.
  - Parser v12's spec sets `at_signal: true` for every light question, so the v12 prompt id changes; no gate has run yet.
- **Replay:** 88/88 decided identical. The hand-program replay is also 88 decided; dev 341 is now unknown.
- **Next:** the paid checks in `docs/plans/phase-4.7-review.md`, in order: the v12 gate, then the v6 set-T check, then the judged dev run. If the v6 set-T check fails, run the dev run with `--scene-version v5 --parser-version v12`.

### Handoff (2026-11-17, later): phase 4.7 step 1 done; step 2 in progress (no API calls)

- **Built and committed:**
  - 1d, scene v6 (`4afcdab`): R.411 lane arrows, lights and markings; `kb/rules/signals47.pl`; prompts `scene/v6`, `v6-tile`, `v6-crop`.
  - 1e, parser v12 (`d882be8`): seven train few-shots; the gate gives back v12 forms only on gold out-of-scope rows.
- **Replay:** 88/88 decided answers identical after every part.
- **Matrix:** 1158 cells: 700 modelled, 18 to build, 432 n/a, 8 out.
- **Step 2, in progress, not committed:** `tests/test_phase47_generated.py` has 784 generated cases; 2 fail: P.106b × tractor and P.106b × special_machine.
  - The oracle treats P.106b's load condition as applying to every vehicle the row bans, but `value.applies_to` is truck only.
  - The oracle is probably wrong here, not the row: limit the condition to `value.applies_to` classes, then re-run.
- **Still to do:**
  - contradiction tests (no interpretation row contradicts a law_db article);
  - `docs/plans/phase-4.7-review.md`: the interpretation rows by risk, plus "existing rows that look wrong";
  - step 3: hand-written v12 programs on dev and D3, run with `eval/phase47_replay.py check --programs dev=... d3=...`, gains reported as matrix cells;
  - the paid commands, within $2.00: the v12 gate, the v6 set-T check, and a judged dev run.
- **Not built:** lane-set claims ("một trong hai làn trái"), R.411's applies_to, vehicles in the photo against lights and markings, and art. 51 marking scope.

### Handoff (2026-11-17): phase 4.7 step 1, parts 1a–1c built; 1d next (no API calls)

- **Owner's option 1** (`6b014df`): the two final2 record tests read the phase-46 engine-code hash at freeze commit `9d78dad` from git. This is the only edit to old tests.
- **Matrix columns** (`7aaa800`): guide-board, weight/height and photo-vehicle columns added; counting is one intent. Now 1158 cells: 686 modelled, 41 to build, 424 n/a, 7 out (`eval/coverage_matrix.py matrix`).
- **1a** (`9fea0d4`, fix `3d207fe`): `kb/sign_info_47.yaml` adds scope, placement and conduct lines, used only when no selected sign has a line.
- **1b** (`6a0e5a1`): two intent pairs.
  - `count` / `count_is` (art. 11; an unread sign that could match makes a range);
  - `applies_to` / `sign_applies` (`kb/rules/coverage47.pl`).
- **1c** (`5643d28`):
  - `rule_permitted` (`kb/rules/general47.pl`): Law 36 art. 13.3, 14.6, 15.4, 18.4, 25.1–25.2 and 27.4; Circular 38 art. 7 as an interpretation (`r_c38_outside`);
  - `duties` (`kb/general_duties_47.yaml`).
- **Proof** after each part: `eval/phase47_replay.py check` gives 88/88 decided identical (baseline `464c1f8`).
- **Next:**
  - **1d:** scene v6. R.411 lane directions, lights and markings; a new `listed_from` value so frozen prompts stay unchanged; the set-T check is paid.
  - **1e:** parser v12, covering the new intents, with train few-shots.
  - **Step 2:** generated tests (prohibitory × class, mandatory × direction) and contradiction tests.
  - **Step 3:** v12 hand-program replays.
  - **Then:** the review list and the paid commands, within $2.00.
- **Working rule learned:** run the suite as `set -o pipefail; pytest | tail`. `9fea0d4` went in with 2 failures because the pipe hid them; `3d207fe` fixed it.

### Phase 4.7, law-first approach: step 0 done, step 1 blocked (2026-11-17; no API calls)

- **Owner, 2026-11-17:** build the rule engine from the law (the 80 stage-A signs plus the general topics). The change is additive only, and existing tests must stay unchanged. This replaces the dev-driven plan below.
- **Step 0** (`464c1f8`): `docs/plans/phase-4.7-coverage-matrix.md`, generated by `eval/coverage_matrix.py`.
  - 979 cells: 475 modelled, 243 to build, 259 n/a, 2 out.
  - Wording check on 420 train questions; the 110 validation questions are excluded (CLAUDE.md).
- **Proof replay** (`43b069d`): `eval/phase47_replay.py`, run on dev v11 and D3's cached questions (D3 has v9 parses plus the v10 hand programs; no v11 parse of D3 exists).
  - Baseline at `464c1f8`: 107 questions, 88 decided; the re-check gives 88 identical.
- **Blocker:** `eval/frozen_phase46.json`'s `engine_code` hashes every `vqa/**/*.py`, `kb/**/*.pl` and `kb/**/*.yaml`.
  - Any added file or line there makes two existing tests fail: `test_final2_has_its_own_record_and_sentinel` and `test_the_final2_run_uses_the_phase46_profile`. A probe file in `kb/` showed this; the probe was removed.
  - Every step-1 item touches `vqa/` or `kb/`. Under the additive rule ("if a new rule would need an old test edited, don't build it"), step 1 waits for the owner's decision.

### Phase 4.7 plan proposed (2026-11-17; no API calls)

- **Plan:** `docs/plans/phase-4.7.md`, waiting for the owner's OK (decisions O1–O6, section 7). Nothing is built.
- **Findings:**
  - `law_db` covers markings, lights, lane use, expressways, priority vehicles and route codes, so only KB-9 (fined = violation, Decree 168 basis) and KB-10 are knowledge-based.
  - No train question asks a fine amount.
  - "Can't run" comes only from selectors: a free sweep of 82 programs × 60 scenes found no engine exception.
  - The auxiliary-plate selector can never match (145, D3 183).
- **Expected:** dev +8 of 13 without a scene change, +3 more with scene v6 (R.411 directions, lights, markings). Estimate $0.62 without v6, $1.17 with it, of the $2.00.

### Handoff (2026-11-17): coverage round 3 (phase 4.7)

#### Where things stand

- **Round 2 (phase 4.6) is closed.** Its one final2 validation ran (`fe2c16d80a18`, frozen `eval/frozen_phase46.json`, fallback off, aggregate only; sentinel `eval/validation_ran_final2.json`, committed in `f313294`):
  - **decided coverage 69.1% (76/110; 95% CI 60–77), accuracy on decided 76.3% (66–84), overall 52.7% (43–62)**;
  - against final's (phase 4.5) 47.3%, 77.9%, 36.8%, and the baseline's 30.0%, 72.7%, 21.8%.
  - Coverage and overall moved outside final's CI; accuracy on decided is about the same.
  - **Every phase-4.5 target and floor is still missed:** coverage 69.1% against the 70% floor (one question short), accuracy 76.3% against the 85% floor, overall 52.7% against the 60% floor.
  - By type: Yes/No 66.0% decided, 82.9% right when decided; Natural QA 71.9% decided, 70.7%.
- **What round 2 built:** `docs/plans/phase-4.6.md` sections 7–16.
  - Reading policy A (`reading_policy="higher_confidence"`);
  - F1 (`is_sign` with `only` over several signs);
  - F2 (unread red boards keep a negative presence claim unknown);
  - `when.day_parity`;
  - I1 `multi` and the `article` aspect;
  - I2 `guide_claim` and `guide` `road_type`;
  - I3 `explain`;
  - I4 `speed_limit` `kind: range` and `speed_limit_is`;
  - parser v11 (v10 failed the gate's no-regression rule; v11 is the one allowed fix);
  - `e2e_private.py` rules-only figures and a re-based estimate;
  - an engine-code hash in the freeze record.
- **Branch `phase-5`, nothing pushed.**

#### The owner's goal for round 3

- **More coverage through knowledge-based rules for the out-of-scope groups,** under CLAUDE.md's source rule:
  - cite `law_db` where it has the article;
  - otherwise a rule may come from knowledge of QCVN 41:2024, Law 36/2024 or Circular 38/2024, marked `law_id: interpretation` with a basis note, never counted as a law citation, and never contradicting `law_db`.
- **No final3.** The validation set has been used three times (baseline, final, final2). Round 3 is measured by the private run (and on dev, which is readable and tuned on, so optimistic).

#### Why questions are not decided

- **final2, validation (aggregate only; 34 of 110):** out of scope 18, unknown 7, program can't run 5, unreadable sign 3, parse failed 1, uncertain 0. No per-question cause may be read.
- **Dev under v11** (`eval/runs/e2e/dev_reparse_v11_f52e160181ca.partial.jsonl`, judged; train_526 carried over from v9; 13 of 87):
  - unknown 7: 15, 159, 248, 414, 415, 421, 451 (`multi` / `explain` parts undecided; 248's disc read as a minimum; 159 parsed as `guide`);
  - out of scope 4: 259 (a board's symbols), 341 (traffic light), 386 (junction contents), 515 (board directions for motorbikes plus a claim);
  - program can't run 2: 145, 361.
- **D3, the train Yes/No working set** (`821164d62679`, parsed with v9, biased; plan section 9). Its 17 out-of-scope questions:
  - guide-board claims 8 (104, 105, 124, 267, 301, 358, 390, 424; now covered by I2 except 358);
  - what lies ahead 2 (378 Y junction, 389 tunnel);
  - road markings 2 (94, 113);
  - who a sign applies to / every vehicle except one 2 (312, 256);
  - a speed-range claim 1 (359);
  - a set of lanes 1 (433);
  - counting signs 1 (332).
  - Out of scope by the owner's decision (2026-11-17): road markings, who a sign applies to, lane sets. Round 3 may reopen them as knowledge-based rules only with the owner's OK.
- **Other out-of-scope wordings in the train working set** (by wording only; plan section 2.3): counting signs about 4 (172, 243, 458, 469), road markings 2, traffic lights.

#### Required before the private run

- **`eval/e2e_private.py` still checks `frozen_phase45.json` by default** (`frozen_perception_model`, `guards`, `run_private`) and builds its pipeline from that record's profile. It must be pointed at the round-3 freeze record (a new profile and record written once, as `phase46` was), with a test.
- **D6, the private run's budget,** is the owner's decision. Estimate (counts only, phase-4.5 measured rates calibrated to final): $1.15 (0.92–1.50) with the fallback off, $2.10 (1.68–2.73) with it on. Re-base it on final2's measured $0.0082 per question.
- **Reviews still owed:**
  - `kb/sign_info.yaml`, `kb/sign_catalog_effects.yaml`, R.421 / R.122 / S.501, KB-1 to KB-8, Circular 38 speeds;
  - the v7–v11 spec lines without train examples;
  - the guide-trial labels;
  - F2's red-board rule and I2's `AHEAD_FEATURES` codes and words (`vqa/reasoning/engine.py`).

#### Still open

- **Step 8, the doc update (approved under D5):** schema 1.3 in CLAUDE.md and DESIGN.md, the phase-4.5 and 4.6 intents and slots, negative lanes, the guide call, and the uncertain-verdict wording changed by policy A. `SCHEMA_VERSION` stays "1.2" (owner). Doc-only; not done.

#### Spend

- **Round 2: $5.07 of $5.25** (the owner raised it by $0.25 for final2):
  - earlier round-2 spend $2.95;
  - D3 parse-only $0.4184;
  - gate v10 $0.1895;
  - gate v11 $0.1861;
  - dev re-parse v11 $0.4092;
  - final2 $0.9048.
- $0.18 left. Round 3 needs its own budget.

#### Key files and commands

- **Plans and records:** `docs/plans/phase-4.6.md` (decisions section 7; results 8–16), `docs/plans/phase-4.5.md`, this file, `CLAUDE.md`.
- **Freeze profiles** (`eval/freeze.py`, `PROFILES`; each record is written once):

  | profile | record | system | used by |
  |---|---|---|---|
  | `phase4` | `eval/frozen_phase4.json` | scene v4, parser v6 | public_holdout run; validation `baseline` |
  | `phase45` | `eval/frozen_phase45.json` | scene v5 + guide, parser v9 | validation `final`; `e2e_private.py` default (to change) |
  | `phase46` | `eval/frozen_phase46.json` | scene v5 + guide, parser v11, reading policy A, engine-code hash | validation `final2` |

  - Switches left out of older records: `POST_FREEZE_SWITCHES`, `EXCLUDED_SWITCHES`, `LATER_SWITCHES` (`reading_policy` defaults to "all", the phase-4.5 behaviour).
  - `.venv/bin/python eval/freeze.py check --profile phase46` (or `phase45`, `phase4`); `write --profile <new>` for a new record.
- **Dev** (`eval/e2e_dev.py`):
  - `reparse --from <run> --version vN --select all --reading-policy higher_confidence --max-spend X`; a stopped run is kept as `*.partial.jsonl`;
  - `summary <file>`.
  - The latest dev record is `eval/runs/e2e/dev_reparse_v11_f52e160181ca.partial.jsonl`.
- **Free analyses:** `eval/phase46_analysis.py` (`calibrate`, `uncertain`, `step1`, `step4`, `trainset`, `oos`); provisional grades in `eval/runs/e2e/phase46_provisional_grades.json` (local).
- **Train Yes/No runner** (biased, parse only): `eval/e2e_trainset.py estimate | run --max-spend X | summary <file>`.
- **Parser gate:** `eval/parser_eval.py run --model claude-sonnet-5-5 --effort medium --version vN --max-spend 0.40`, then `score <file>` and `compare --old <the three v6 runs> --new <file>`.
  - The cap must be at least $0.40, because the runner refuses below its own conservative expected cost.
  - Design features given back: `DESIGN_FEATURES`.
- **Validation:** `eval/e2e_validation.py`; labels `baseline`, `final`, `final2`, all used. No further label is planned.
- **Private:** `eval/e2e_private.py estimate`, then `run --confirm-frozen --max-spend X`; on hold until it points at the round-3 record and D6 is decided.

#### Working rules

- Stage files by name and check the staged list. Run the suite and the commit as one `&&` chain.
- No API call without the owner's go-ahead on an estimate; the owner runs paid commands.
- Not touched: the validation set beyond its aggregates, public_holdout, private, gold, and the written freeze records.

### Handoff (2026-11-17): phase 4.6 final2 done; D6 and the doc update are next (kept as a record)

- **final2** (`fe2c16d80a18`, once, aggregate only, $0.9048): **decided 69.1% (60–77), accuracy on decided 76.3% (66–84), overall 52.7% (43–62)**, against final's 47.3% / 77.9% / 36.8%.
  - Coverage and overall are outside final's CI; accuracy is about the same.
  - All targets and floors are missed; coverage falls short of the 70% floor by one question.
  - Details: `docs/plans/phase-4.6.md` section 16.
- **Spend:** $5.07 of the round's $5.25, so **$0.18 left**.
- **Next (owner):**
  - D6, the private run's budget: about $1.15 with the fallback off, $2.10 with it on (re-based in step 2), and `eval/e2e_private.py` pointed at `frozen_phase46.json`;
  - step 8, the doc update (D5 approved, free).
- **Not touched:** the validation set beyond its aggregate, public_holdout, private, gold, `frozen_phase4.json`, `frozen_phase45.json`.

### Handoff (2026-11-17): final2 prepared; the owner runs it (kept as a record)

- **The owner raised the round by $0.25 to $5.25:** $4.16 spent, **$1.09 left**.
- **Freeze `eval/frozen_phase46.json`** (parser v11, policy A, scene v5 + guide; plus an engine-code hash). Label `final2`, sentinel `eval/validation_ran_final2.json`. Plan section 15.
- **Next (paid):**
  ```
  .venv/bin/python eval/e2e_validation.py run --label final2 --confirm-frozen --max-spend 1.05
  ```
  Estimate $0.86 (range $0.70–1.05). Once, aggregate only.
- **Then:** D6 (the private run's budget, and pointing `e2e_private.py` at `frozen_phase46.json`), and step 8 (the doc update).

### Handoff (2026-11-17): step 6 judged; final2 below the $0.90 floor, so it is the owner's decision (kept as a record)

- **Step 6** (`f52e160181ca`, $0.4092; 86 of 87 questions, train_526 carried over from v9): judged dev **85.1% decided, 81.1% on decided, overall 69.0%** (was 73.6% / 85.2% / 62.6%). Guardrail met. Details: plan section 14.
- **Spend:** $4.16 of $5, so **$0.84 left**, below final2's $0.90 floor.
- **Owner decisions now:** final2 (raise the round by at least $0.25, or no final2), then D6 (the private run's budget), then step 8 (the doc update, approved under D5, free).

### Handoff (2026-11-17): v11 passes the gate rule; step 6 (dev re-parse) ready for the owner's go-ahead (kept as a record)

- **v11 gate** ($0.1861): 85.1%, no type regressed without design. v11 is the parser.
- **Next (paid, the owner runs it):**
  ```
  .venv/bin/python eval/e2e_dev.py reparse --from eval/runs/e2e/dev_reparse_v9_8bbb5eb01cff.jsonl --version v11 --select all --reading-policy higher_confidence --max-spend 0.50
  .venv/bin/python eval/e2e_dev.py summary eval/runs/e2e/dev_reparse_v11_<run_id>.jsonl
  ```
  Estimate $0.37 (range $0.33–0.45); it needs a clean git tree.
- **Spend:** $3.75 of $5, so **$1.25 left**. About $0.88 would be left after step 6, below final2's $0.90 floor, so final2 is the owner's call then.

### Handoff (2026-11-17): v10 failed the gate's no-regression rule; v11 built, its gate is next (kept as a record)

- **v10 gate** ($0.1895): 76.6%; `permitted` and `which_vehicles` regressed without design. The cause and the v11 fix are in `docs/plans/phase-4.6.md` section 12.
- **Next (paid, the owner runs it):**
  ```
  .venv/bin/python eval/parser_eval.py run --model claude-sonnet-5-5 --effort medium --version v11 --max-spend 0.40
  ```
  Then `score` and `compare --old <the three v6 runs> --new logs/parser_eval/pred_claude-sonnet-5-5_medium_v11_*.jsonl`. Estimate $0.19. If v11 fails, stop for the owner.
- **Spend:** $3.56 of $5, so **$1.44 left**. About $0.92 would be left before final2, against its $0.90 floor.

### Handoff (2026-11-17): phase 4.6 step 4 built; step 5 (the v10 gate) (kept as a record)

- **Step 4** (`bd16777`): F1, F2 (with a corrected diagnosis), `day_parity`, I1–I4 and parser v10, and the free replays. Details: `docs/plans/phase-4.6.md` section 10.
  - Dev, indicative: **86.2% decided, 80.0% on decided, overall 69.0%**, with hand-written programs and provisional grades.
  - D3 cached scenes: 15 decided, 13 right (was 11 and 9).
- **Next (paid, the owner runs it):**
  ```
  .venv/bin/python eval/parser_eval.py run --model claude-sonnet-5-5 --effort medium --version v10 --max-spend 0.40
  .venv/bin/python eval/parser_eval.py score logs/parser_eval/pred_claude-sonnet-5-5_medium_v10_*.jsonl
  .venv/bin/python eval/parser_eval.py compare --old logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-140559.jsonl logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141622.jsonl logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141902.jsonl --new logs/parser_eval/pred_claude-sonnet-5-5_medium_v10_*.jsonl
  ```
  Estimate $0.21 (range $0.19–0.25). The cap is $0.40, because the runner refuses below its own expected $0.37.
- **Spend:** $3.37 of $5, so **$1.63 left.**

### Handoff (2026-11-17): phase 4.6 steps 1–2 built; D3 ready for the owner's go-ahead (kept as a record)

- **Plan:** `docs/plans/phase-4.6.md`, approved with D1–D6 (section 7). Built so far is listed in section 8.
- **Step 1, policy A** (`43f5b10`, `8fc3d66`): this is `Engine(reading_policy="higher_confidence")`, set through `PipelineConfig.reading_policy`.
  - The default `"all"` keeps the frozen behaviour, and both freeze records still match.
  - Dev replay: **80.5% decided, 82.9% on decided, overall 66.7%** (was 73.6% / 85.2% / 62.6%). The grades are provisional (6 answers) until step 6's judge. Kept under the guardrail.
- **Step 2, `eval/e2e_private.py`** (`c3c9f40`): it now has the rules-only figures with the duplicate split, and an estimate from counts only.
  - Private estimate: fallback off **$1.15** (0.92–1.50); fallback on **$2.10** (1.68–2.73), at validation's decided share. **D6 is open** on these figures.
- **D3 runner** (`08630ce`): `eval/e2e_trainset.py`, biased set, parse only.
- **D3 ran** (`821164d62679`, **$0.4184**; the first start, `4f32405389d8`, stopped on a missing API key at $0, and its file is marked `aborted_nokey`).
  - Of 101 parses: 82 ok, 17 out of scope, 2 invalid.
  - The largest Yes/No gap is claims about guide boards (10 of 101), so I2 needs a claim form.
  - It also found F1 (`is_sign only` over several signs), F2 (a negative presence claim with unreadable signs; an accuracy bug, 276) and two parser v10 items. Details: plan section 9. F1 and F2 need the owner's OK.
- **Spend this round:** $3.37 of $5, so **$1.63 left**.
- **Then:** I1–I4 and parser v10 (step 4, free), the gate (step 5), the dev re-parse (step 6), the freeze and final2 (step 7), and the doc update (step 8, D5 yes).

### Handoff (2026-11-17): coverage round 2

#### Where things stand

- **Phase 4.5 is closed.** Its one final validation ran (`7a3dbec997f7`, frozen `eval/frozen_phase45.json`, fallback off, aggregate only; sentinel `eval/validation_ran_final.json`, committed): **decided coverage 47.3% (52/110; 95% CI 38–57), accuracy on decided 77.9% (65–87), overall 36.8% (28–46)**, against the baseline's 30.0%, 72.7%, 21.8%. The fixed success criterion is met (coverage > 39.1%, overall > 30.4%); **every target and floor is missed** (coverage 80% / 70%, accuracy 88% / 85%, overall 70% / 60%). Details: "Phase 4.5 final validation" above.
- **Frozen system (`eval/frozen_phase45.json`, profile `phase45`):** scene v5 + v5-tile / v5-crop, guide-board call on (`scene/v5-guide`), parser v9, writer `answer/v3`, answer fallback v2, `crop_always` + T4. `eval/freeze.py check --profile phase45` matches; `eval/frozen_phase4.json` still matches the phase-4 profile.
- **Branch `phase-5`, nothing pushed.**
- **Spend this round: $2.95 of $5** (B3 + B6 tests $0.135; dev run $0.612; parser gate runs v7 $0.194, v8 $0.180, v9 $0.192; candidate dev run $0.81; v9 dev re-parse $0.011; final validation $0.83). **$2.05 left.**

#### The owner's goal for round 2

- **More coverage before the private run.** The private test stays on hold until then.

#### Why questions are not decided

- **Validation (aggregate only; 58 of 110):** out of scope 28, uncertain 16, unknown 7, unreadable sign 4, program can't run 2, parse failed 1. By type: Yes/No 39.6% decided (90.5% right when decided), Natural QA 54.4% decided (69.4%). No per-question cause may be read.
- **Dev (readable; the v9 re-parse `dev_reparse_v9_8bbb5eb01cff`, 23 of 87):**
  - out of scope 12: 15, 231, 248, 259, 260, 341, 351, 361, 386, 413, 414, 515 (compound questions 248 / 414; speed ranges 413; a board's symbols 259 / 260; traffic light 341; "why" 351; lane arrows 515; yes/no about a board 231);
  - uncertain 6: 138, 159, 432, 450, 517, 521 (alternative readings disagree);
  - unknown 3: 415, 421, 451; program can't run 1: 145; unreadable sign 1: 514.
- **Dev overstates validation** (73.6% vs 47.3% decided): dev is all Natural QA and guide-heavy, and stage B was tuned on it; validation is half Yes/No, and Yes/No is where coverage is lowest. "Out of scope" and "uncertain" are the two largest causes on both.

#### Fix before the private run

- **`eval/e2e_private.py` lacks the rules-only figures.** Its aggregate reports overall (with the fallback) and `rule_coverage`, not decided coverage, accuracy on decided and overall with non-decided counted wrong (the phase-4.5 requirement). Add them, as `eval/e2e_validation.py`'s `aggregate` does.
- **Its estimate uses phase-4 rates** (`HOLDOUT`: fallback rate 0.49, $0.0127 per question; `ee.COST`). Re-base it on the phase-4.5 measured rates (final validation: $0.0076 per question with the fallback off, plus the fallback's share if it stays on).
- It already checks `frozen_phase45.json` by default and builds its pipeline from that profile.

#### Open decision (owner)

- **A "final2" validation run.** `validation_ran_final.json` blocks a second `final`. Measuring round-2 changes on the validation set needs a new label (e.g. `final2`, its own freeze record and sentinel), and the owner's decision on whether the validation set may be used a second time: each use spends some of its independence. Without it, round 2 is measured on dev only (readable, tuned on, optimistic) before the private run.

#### Key files and commands

- Plans and records: `docs/plans/phase-4.5.md` (sections 11–15), this file, `CLAUDE.md` (data rules). DESIGN.md and CLAUDE.md still describe schema 1.2: the 1.3 boards, the new intents and slots, negative lanes and the guide call are not written up yet.
- Freeze: `eval/freeze.py` (`PROFILES`, `check --profile phase45`, `write --profile ...`; a record is written once).
- Dev: `eval/e2e_dev.py` (`run --candidate`, `reparse --from ... --version ...`, `summary`, `estimate --candidate`); runs in `eval/runs/e2e/` (local): `dev_candidate_7caed6170de6.jsonl`, `dev_reparse_v9_8bbb5eb01cff.jsonl`.
- Engine-only replay: `eval/dev_replay.py` (`--programs`, `--scenes`; provisional grades `eval/runs/e2e/dev_provisional_grades.json`).
- Parser gate: `eval/parser_eval.py run --version vN --max-spend 0.40` (one run decides from v8 on), `score`, `compare --old <v6 runs> --new <run>`.
- Validation: `eval/e2e_validation.py` (aggregate only; labels `baseline`, `final`, both used).
- Private: `eval/e2e_private.py` (on hold; fix the two items above first).
- Code added in phase 4.5: `vqa/perception/guide.py`, `vqa/reasoning/sign_info.py` + `kb/sign_info.yaml`, `kb/sign_catalog_effects.yaml`, `kb/rules/zones.pl`, `prompts/parser/v7`–`v9`, `prompts/scene/v5*`.
- Reviews still owed before the private run: `kb/sign_info.yaml`, `kb/sign_catalog_effects.yaml`, R.421 / R.122 / S.501, KB-1 to KB-8, Circular 38 speeds, the v7–v9 spec lines without train examples (police car, divider, placement), the guide-trial labels.

#### Working rules

- Stage files by name and check the staged list; no API call without the owner's go-ahead on an estimate; the owner runs paid commands.
- Not touched: the validation set beyond its aggregate, public_holdout, private, gold.

### Handoff (2026-11-17, later): B1 + B2 built; B4 ready for the owner's go-ahead

- **Where things stand:** B1 + B2 are built and committed (see "Phase 4.5 B1 + B2 built"). Branch `phase-5`, nothing pushed. The freeze record `eval/frozen_phase4.json` still matches. **Spend this round: $0.74 of $5**, $0.70 reserved for the final validation, **$3.56 free**. No call was made in this step.
- **Next: B4, on the owner's go-ahead (the owner runs the commands).** In this order; stop after each and look:
  1. **Parser gate rerun on public_dev gold intents, parser v8 (v7 failed the rule on run 1; entry above), Sonnet 5.5 medium, 3 runs.** v7's measured run cost $0.194 (v6: $0.12–0.16; v8's prompt is v7's plus four lines). **Estimate $0.19 per run, $0.58 for three (range $0.50–0.70).** **Cap (owner, 2026-11-17):** `--max-spend 0.40` per run. The tool now refuses only when the expected cost or one call's worst case is over the cap; the spend guard checks each call's worst case (about $0.086) against what is left, so a run never passes $0.40 and stops near $0.31. A stopped run is renamed `*.partial.jsonl` and is not a gate run. (The old up-front check needed the whole-run worst case, $8.09 for v7.)
     ```
     .venv/bin/python eval/parser_eval.py run --model claude-sonnet-5-5 --effort medium --version v8 --max-spend 0.40
     .venv/bin/python eval/parser_eval.py run --model claude-sonnet-5-5 --effort medium --version v8 --max-spend 0.40
     .venv/bin/python eval/parser_eval.py run --model claude-sonnet-5-5 --effort medium --version v8 --max-spend 0.40
     .venv/bin/python eval/parser_eval.py score logs/parser_eval/pred_claude-sonnet-5-5_medium_v8_*.jsonl
     .venv/bin/python eval/parser_eval.py compare --old logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-140559.jsonl logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141622.jsonl logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141902.jsonl --new logs/parser_eval/pred_claude-sonnet-5-5_medium_v8_*.jsonl
     ```
     **Rule (set before the run):** no old gold intent type may have lower pooled accuracy than v6's three runs, after giving back rows whose v7 program uses a v7 feature the v6 gold can't write (`regressed_types_without_design` must be empty). The gate (mean ≥ 90%) is reported too. If a type regresses, the parser is fixed as a new version before any dev run.
  2. **Judged candidate dev run** (scene v5 + v5-tile / v5-crop, guide reading on, parser v8; fallback off; fresh perception, so it is also the dev re-perception and the dev re-parse; the judge grades every decided answer, including 81, 287 and 308). **Estimate $0.84 (range $0.67–1.10)**, from the frozen dev run's measured stage costs at 59 decided:
     ```
     .venv/bin/python eval/e2e_dev.py estimate --candidate
     .venv/bin/python eval/e2e_dev.py run --label candidate --candidate --max-spend 1.3
     .venv/bin/python eval/e2e_dev.py summary eval/runs/e2e/dev_candidate_*.jsonl
     ```
     Then the guardrail on the judged figures: overall ≥ 34.5% (stage A) and accuracy on decided ≥ 70%.
  - **B4 still to spend: about $1.42 (range $1.17–1.80)** ($0.58 gate + $0.84 dev run); after it about $1.95 free plus the $0.70 reserve.
- **Then B5 (owner's go-ahead):** the phase-4.5 freeze `eval/frozen_phase45.json` (scene v5, parser v7, guide reading on), then the final validation once.
- **Open items:**
  - **For the owner's review before the freeze:** `kb/sign_info.yaml` (scope, placement, conduct wording; reviewed_by assistant), the W.203 C.3 d) conduct item, the v7 spec lines without a train example (police car, divider, placement), and the earlier list (R.421, R.122, S.501, `kb/sign_catalog_effects.yaml`, KB-1 to KB-8, Circular 38 speeds).
  - **Provisional grades** (assistant) now cover 81, 287, 308 and the new decided dev answers in `eval/runs/e2e/dev_provisional_grades.json` (local); the judged run replaces them.
  - **Unread boards after the guide call:** once a scene has `guide_boards`, an unread blue / green / white board no longer counts as unreadable for any claim, lane claims included. Watch lane questions in the judged run.
  - **Board discs are whole-road limits:** a disc tied to one lane on the board (dev 14) is applied to every lane.
  - **DESIGN.md and CLAUDE.md** still say schema 1.2: the 1.3 boards, the new intents and slots, negative lanes and the guide call go in at B5.
  - Speed ranges ("trong khoảng tốc độ nào") and compound questions (two asks in one) stay out of the DSL.

### Handoff (2026-11-17): phase 4.5 stage B (kept as a record; B1 + B2 since built)

#### Where things stand

- **Branch `phase-5`; nothing pushed.** `main` has phase 4 merged at `5e1664c`.
- **Freeze record in force:** `eval/frozen_phase4.json`. `eval/freeze.py check` matches. Prompts frozen before phase 4.5 still rebuild exactly, because rows marked `listed_from: phase45` are left out of their listings.
- **Spend this round:** **$0.74 of the round's $5**, with **$0.70 reserved for the final validation** (about $3.56 free).
  - dev run $0.612;
  - set-T check $0.114;
  - guide test $0.021.
  - Earlier phase-5 spend outside the round: two-pass trial $0.113, validation baseline $0.663.
- **Commits since the phase-4 freeze record (`db587c1`), oldest first:**
  - `8b71beb` holdout image resolver fix
  - `2528621` stopped holdout start voided
  - `ab7261a` public_holdout result (once, frozen): 83.7%, non-dup 89.6%
  - `741a02a` holdout described in aggregate only
  - `52a58b2` DESIGN: phase 4 as built
  - `698d4f2` phase 4 closing entry
  - `5fe47be` phase 5 draft
  - `ea5b0a8` gold v1: 0094 plate covers cyclo (owner)
  - `5e1664c` merge phase-4 into main
  - `c054b83` phase 5 approved; CLAUDE.md P6 exception
  - `f530df4` e2e_private.py (guards, sentinel, aggregate only)
  - `9383678` two-pass perception trial built
  - `0b3594e` two-pass trial results
  - `c079da0` two-pass variants; phase-4.5 perception option (recommend frozen)
  - `50175ee` rules-only requirement; private on hold; coverage analysis; phase-4.5 plan proposed
  - `122db34` phase 4.5 approved; phase 5 updated (P11 replaced, A1 main)
  - `2e1ff41` validation set (110 q), fallback-off switch, validation runner
  - `c015055` baseline validation: decided 30.0%, accuracy on decided 72.7%, overall 21.8%
  - `3ab48e2` scope round: dev set (87 q), dev runner
  - `5f19c0e` dev run analysis and the ranked proposal
  - `e0338b7` coverage first; source exception; stage A proposal
  - `782a25e` stage A rank 1 (KB-7 choose, R.411, art. 11 group names); dev replay harness
  - `82075d7` stage A families F3–F7, zones, Circular 38 speeds, selector colours, KB-6
  - `4ef7064` scene v5 (+tile, crop); B6 guide test built
  - `a8e1d5f` scene v5 set-T check
  - `cf46e0d` B6 guide test results
  - `13047b2` B6 approved and folded into B1/B2; question-level check

#### What's built and decided

- **Stage A** (`82075d7`): rank 1 accuracy fixes; families F3–F7, with meaning-row effects in `kb/sign_catalog_effects.yaml` and new rows R.421, R.122, S.501; zones (Law 36 art. 25 expressway; art. 18.4 i pick-up points); Circular 38/2024 default speeds as interpretations; selector colours; KB-6.
  - **Engine-only dev replay:** decided 35 → **32** (40.2% → 36.8%), accuracy on decided 80.0% → **93.8%**, overall 32.2% → **34.5%**.
  - "P.127 covers every vehicle" was dropped (B.27: motor vehicles only); the police-car mapping goes to parser v7.
- **Scene v5** (`scene/v5@7a3291ea5dff`, `v5-tile@d5269387761f`, `v5-crop@cee1140f62d7`): v4 plus the new rows.
  - **Set-T check:** recall 90.8% / code F1 72.9% against frozen v4's 89.2% / 73.5%, within noise. Not yet the pipeline default (B5 switches it).
- **B6 guide-board test** (24 hand-labelled dev images, `scene/v5-guide-trial@c921108016d7`). Variant A (the photo alone): entry recall **93.9%**, distances **100%**, arrows 89.1% lenient, speed discs **10 of 10**, no made-up boards.
  - The bars set before the run (entry recall ≥ 80%, distance ≥ 85%, lenient arrows ≥ 75%, speed recall ≥ 85%, no made-up boards) were all met.
  - Question-level: 22 of 22 board facts right; at best 19 of 25 can match the dataset (230, 248 and 249 disagree with their boards).
- **B6 approved (owner), variant A:** a separate guide-board call, only on images where perception lists a guide board. **Folded into B1/B2** (one parser v7, one gate rerun, one dev re-parse).
- **Guardrail:** a change is kept if dev overall (non-decided = wrong) doesn't drop and dev accuracy on decided stays ≥ 70%. Accuracy on decided is reported every time.
- **Source exception** (CLAUDE.md): rules cite `law_db` when it has the article. Otherwise they may come from knowledge of QCVN 41:2024, Law 36/2024 **and Circular 38/2024/TT-BGTVT** (speeds by road type), marked `law_id: interpretation` with a `rule_basis` note, never counted as a law citation, and never contradicting `law_db`.
- **Success criterion (fixed):** the final validation's decided coverage above 39.1% and overall above 30.4% (outside the baseline's CI); accuracy on decided reported. **Targets** reported as met or missed: coverage 80% (floor 70%), accuracy on decided 88% (floor 85%), overall 70% (floor 60%).

#### Data rules for this work

- **Dev** (`data/splits/train_dev.json`, 87 Natural QA on 60 images) is readable question by question.
- **Validation** (`data/splits/train_validation.json`, 110 q on 54 images) is **aggregate only**, run only by `eval/e2e_validation.py`. Sentinels: `eval/validation_ran_baseline.json` (used) and `eval/validation_ran_final.json` (still to come).
- **public_holdout is never touched again.**
- **Private is held** until the phase-4.5 freeze (`eval/frozen_phase45.json`, B5).
- **Provisional grades** for dev 81, 287 and 308 (`eval/runs/e2e/dev_provisional_grades.json`, assistant-graded) are to be confirmed by the judge in B4's judged dev run.

#### Exactly what comes next, in order

1. ~~The free question-level check of the dev guide questions~~ **done** (`13047b2`; above).
2. **B1 + B2, guide content folded in (one parser v7),** in this order: sign group → conduct + STOP → presence → divided-road and several-vehicle speed → scope and placement → guide content (scene schema 1.3 boards, entries, distances, directions; speed discs on boards feeding the speed rules).
   - After each type, a free engine-only dev replay where parses exist; keep it per the guardrail.
   - Parser v7 few-shots from train, outside dev and validation, with the exact question text, including the police-car mapping and the lane fix.
   - **Uncommitted work in progress (tests pass, 995):**
     - `vqa/schemas.py`: `Selector.category`, `Meaning.aspect` (name / group / conduct / scope / placement), `Present`, `Guide`, `SpeedOk` / `SpeedLimit` `road_divided`, `SpeedLimit.vehicles`, and scene schema 1.3 `guide_boards` (left out of dumps when empty);
     - `vqa/parsing/wire.py`: the matching wire models;
     - `vqa/reasoning/engine.py`: handlers for the aspects, `present`, `guide`, divided road, vehicle lists; `unreadable_signs` skips non-red boards once boards were read;
     - `vqa/reasoning/facts.py`: no `unread_sign` for read boards;
     - `vqa/reasoning/sign_info.py` and `kb/sign_info.yaml`: conduct wording; scope and placement lines from art. 16, 26, 30, 34, 39, C.39, D.17, D.18.
   - **Still to build:**
     - tests for those;
     - `vqa/perception/guide.py` (the board call, promoted from the trial prompt as `scene/v5-guide`, cached as a region record, adding board speed discs as P.127 / R.306 signs);
     - the pipeline switch (`guide_reading`, default off, in `freeze.POST_FREEZE_SWITCHES`);
     - template answers for the new value types;
     - the validator dry runs;
     - `prompts/parser/v7/` (spec and few-shots);
     - the replays after each type.
3. **B4 (commands and estimates, then stop):** the parser-gate rerun on public_dev gold intents (no old type may regress), the dev re-perception with v5 plus the board reading, the dev re-parse, and a judged dev run.
4. **B5 (owner's go-ahead):** the new freeze `eval/frozen_phase45.json` (scene v5, parser v7, guide reading on), then the final validation once.

#### Working rules

- **Stage files by name** and check the staged list before every commit (never `git add -A`).
- **No API call without the owner's go-ahead on an estimate; the owner runs paid commands.** Give exact commands with real file names, never placeholders.
- **To reuse:**
  - `eval/dev_replay.py` (engine-only dev replay with provisional grades);
  - `eval/e2e_dev.py` (dev runs, fallback off, per-question records);
  - `eval/e2e_validation.py` (aggregate only);
  - `eval/guide_trial.py` and `eval/guide_trial/labels_dev.yaml` (board test and labels);
  - `eval/coverage_analysis.py` (decided figures, causes, validation pool);
  - `eval/sign_popularity.py`;
  - `kb/sign_catalog_effects.yaml` (effects for meaning rows; the generator would overwrite the meaning file);
  - `listed_from: phase45` on new catalog rows (`vqa.kb.FROZEN_PROMPT_VERSIONS`);
  - `kb/rules/zones.pl` (zones, defaults, `unread_sign/1`);
  - `freeze.POST_FREEZE_SWITCHES`.

#### Open items and things not verified

- **Not verified by the judge:** provisional grades 81, 287, 308; all stage-A gains are engine-only.
- **Labels** in `eval/guide_trial/labels_dev.yaml` are assistant-transcribed; the owner's spot-check is pending.
- **Dataset answers that disagree with what the image shows:** 230, 248, 249 (guide boards).
- **R.411** stays effect_unmodelled (lane directions need direction fields on lane rows).
- **Catalog rows awaiting the owner's review before the freeze:** R.421, R.122, S.501, and the effects in `kb/sign_catalog_effects.yaml`; KB-1 to KB-7 interpretations; Circular 38 speeds.
- **Defaults and boards:** expressway speed defaults must not answer where a board posts other limits. That is guarded only by "no posted sign and no unread sign"; B6's board discs are the real fix.
- **The dev set is all Natural QA,** so Yes/No question types are untested on dev.


**Next (2026-11-16): phase 4, procedure step 4 (tuning, D8: at most 5 runs).** Step 2 is done (above). The D5 gate failed on the template rate (7.8% > 5%). Tuning approved (owner, 2026-11-16; plan section "Tuning on public_dev"): T1 + T3, then T2, then T4, each its own run (D8: 3 of 5). **T1 + T3 done: D5 passes** (above). **T2 done** (above): fallback failures 6 → 1, overall 81.7%. **T4 done** (above): overall 84.6%, rule coverage 61.4%, D5 passes. 3 of 5 tuning runs used. **Phase 4 closed (2026-11-16; closing entry above).** Phase 5 plan approved (2026-11-16). **Next: the one private-test run** (`eval/e2e_private.py run --confirm-frozen --max-spend 3`), on the owner's go-ahead on its $1.83 estimate.

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
