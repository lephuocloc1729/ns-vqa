# Review 3 self-assessment (state on 2026-11-26, UAT done)

The faculty's checklist "Kiểm tra khối lượng Task 3 trước Review lần 3" has 18 self-assessment rows. Each row
below gives its state, the evidence a reviewer can open, and what is still missing. The plan behind each item is
`docs/plans/task-3-review-3.md`; the running record is `docs/status.md`.

**State:** ✅ done · 🟡 in progress · ⬜ not started. A row is marked done only when its evidence exists today.

## Summary

| # | Row | State | Main evidence | Still missing |
|---|---|---|---|---|
| 1 | UI/UX | ✅ | https://signcite.xyz; `web/`; Playwright on desktop and phone | screenshots for the thesis; the video |
| 2 | Streaming | ✅ | SSE stage events and writer tokens; `tests/test_answer_stream.py`, `web/src/lib/sse.ts` | — |
| 3 | Optimisation | ✅ | Q4_K_M vs BF16: speed, memory and private accuracy (`docs/results/gpu-session-2026-11-21.md`); rules-side runtime optimisations | — |
| 4 | Latency and memory table | ✅ | GPU table; load tests; private-run seconds and cost per question | — |
| 5 | Citations and guardrails | ✅ | citations on every rules answer; faithfulness guard; red team (`docs/results/redteam-2026-11-24.md`); readable proof | — |
| 6 | CI/CD | ✅ | GitHub Actions: 191 CI runs since 21/11, 31 CD deployments with automatic rollback | — |
| 7 | Docker Compose | ✅ | `docker-compose.yml` (8 services); CI job `compose` starts it on a clean machine | a clean-VM screen recording (optional) |
| 8 | Monitoring | ✅ | Grafana dashboard "SignCite – hệ thống" (14 panels), Prometheus, node-exporter; admin overview | Phoenix (dropped, see row) |
| 9 | Unit and integration tests | ✅ | 2,612 pytest cases (94–95% line coverage of `vqa/` and `app/`), 36 Vitest, 17 Playwright; JUnit and coverage reports on every CI run | — |
| 10 | Load and stress | ✅ | Locust capacity and stress runs, 0 failures up to 1,000 users; a real end-to-end run, 10 users at once, 0 errors | the RAG under load (needs a GPU session) |
| 11 | UAT | ✅ | 15 moderated sessions, all 4 targets met: SUS 91.3 (A+), task success 97%, CSAT 4–5 100%, lowest task 93% (`docs/results/uat-2026-11-25.md`) | no law-savvy tester; no server-side figures (temporary server deleted); no complaints recorded |
| 12 | Thesis | 🟡 | full draft of all 6 chapters, front matter, appendices (about 24,000 words; owner's local folder, Markdown → pandoc → FPT-format .docx) | the owner's rewrite; owner items marked [TODO]: personal details, baseline papers and exact scores, UAT results, screenshots, Chapter 3 diagram rendering |
| 13 | References and plagiarism | 🟡 | IEEE list, 51 entries, numbered by first citation, both baselines cited | the two baseline papers' details; entries marked [VERIFY]; the plagiarism check |
| 14 | Slides | ⬜ | — | 22 slides + 4 backup |
| 15 | Slide review | ⬜ | — | the review pass for the five faults |
| 16 | Repository | ✅ | `README.md` (results, how to run, how to reproduce each number), `docs/`, `DESIGN.md`, Swagger at `/docs`, tag `v1.0-benchmark` | — |
| 17 | Artifacts | ✅ | GitHub release [`v1.0-benchmark`](https://github.com/lephuocloc1729/ns-vqa/releases/tag/v1.0-benchmark) (notes: `docs/release/v1.0-benchmark.md`): the model files' sha256, prompt versions, image digest; tag and freeze records | — |
| 18 | Video | 🟡 | script: `docs/defense/demo_video_script.md` | the recording |

## Headline results (for every row that cites them)

| System | Private test (146 questions, 3 runs) | Grading |
|---|---|---|
| **V2: rules + live RAG fallback** | **82.2% (sd 1.8)** | the owner by hand (the judge agrees within 0.1 point) |
| V1: rules only | decides 66.9% of questions, at 82.3% | the owner by hand |
| RAG alone | 81.5% (119 of 146) | the owner by hand (the saved Q4_K_M predictions; judge 79.2%) |
| Baselines LowCost / LexiSignVQA | 77.4% / 78.1% (each the best of 4 settings on the private test) | the owner by hand |

On the public test (100 questions) V2 scores 84.5%. By hand, V2 is 0.7 points above RAG alone, within its own
run-to-run spread, so the accuracy gain is over the two published baselines only. Beyond that, every
rules answer comes with a proof and law citations that cannot contradict it, and the system says "undecided"
instead of guessing.

---

## Stage 1: UI/UX, packaging, optimisation

### 1. UI/UX ✅
- **Input:** photo upload, drag and drop, paste, phone camera; question box; voice through the browser's
  Vietnamese speech recognition (Whisper was dropped, plan "Cut or reduced").
- **Output:**
  - sign boxes on the photo, numbered, with confidence shown by line style;
  - the answer streaming in;
  - citations as chips;
  - for RAG answers, a badge and the retrieved laws, kept apart from the rule citations.
- **Explanation, three folded levels** (2026-11-24): the reasoning steps (each Prolog step beside a plain
  Vietnamese sentence, the decisive condition marked), the rules as written in `kb/`, the full proof tree. Built
  from the engine's own proof, with no model (`app/api/proof_view.py`).
- **Conversation:**
  - history per session, and `#turn=` links;
  - follow-up questions ("Còn xe khách thì sao?" is shown as "Hiểu câu hỏi là: …", `app/api/followup.py`);
  - feedback: thumbs, a corrected answer, a note.
- **Admin console** (admin.signcite.xyz): an overview with interactive charts, the questions and feedback with CSV
  export, tester accounts, live settings, and the GPU connection.
- **Evidence:**
  - https://signcite.xyz;
  - `web/e2e/ask.spec.ts` (Playwright, desktop and phone);
  - the admin plan `docs/plans/admin-page.md`.

### 2. Streaming ✅
- `POST /v1/ask/stream` sends server-sent events:
  - `started`, then `perception` (with the boxes), `parsed` and `engine`;
  - `route`, then the writer's `token` events (`token_reset` withdraws a draft before a retry);
  - finally `answer` (authoritative) and `done`.
- RAG answers stream through the same events.
- A dropped stream recovers the stored answer (`GET /v1/turns/{id}`).
- **Evidence:** `tests/test_answer_stream.py`, `tests/test_api.py`, `web/src/lib/sse.ts` and its unit tests, the
  Playwright test "a dropped stream recovers the stored answer".

### 3. Optimisation ✅
- **RAG answer model: Qwen3.5-9B BF16 → Q4_K_M (llama.cpp GGUF).** Speed and memory measured on an RTX 5090
  (20 questions); accuracy on the private test (146 questions, RAG alone, the saved runs):

  | | Q4_K_M | BF16 |
  |---|---|---|
  | Peak GPU memory | **9.29 GB** | 19.61 GB |
  | Generation | **4.9 ms/token** (203 tokens/s) | 11.0 ms/token (91 tokens/s) |
  | Time per answer | **4.82 s** | 6.48 s |
  | Private accuracy, judge (score) | 79.2% | **84.6%** |
  | Private accuracy, by hand | **81.5%** (119 of 146) | **81.5%** (119 of 146) |

  **The trade:** Q4_K_M halves the GPU memory and generates 2.2× faster **with the same hand-graded accuracy**
  (81.5% for both). The judge scores BF16 about 5 points higher, so the judge and the human grader disagree on how
  the two models' wordings compare; the hand grades are the reference. Q4 was chosen before the private test, for
  speed and memory, and the benchmarked system keeps it. BF16 is one run (the owner's grading sheet; judge 121
  correct, 5 partial, 20 wrong).

- **Rules side, runtime optimisations** (no model weights of its own to prune or distil):
  - perception and parsing run in parallel;
  - a scene cache, so every question about a photo reuses one scene reading;
  - prompt caching for the long fixed prompts;
  - the RAG answer cache;
  - 10 answer slots in one process.
- **Speech:** the browser's recogniser instead of a Whisper service, so the Whisper FP16 → INT8 row was dropped.

### 4. Latency and memory table ✅

| What | Figure | Source |
|---|---|---|
| Real answer, private test (3 runs) | 16.5 / 18.5 / 21.1 s per question; $0.009 per question | `eval/runs/e2e/private_aggregate_*.json` |
| Follow-up on a cached photo, live | 2.7 s, $0.003 | live check 2026-11-24 |
| RAG service, 1 slot | 8.6 s mean (7.7 p50), 18.7 GB VRAM | `docs/results/rag-concurrency-2026-11-23.md` |
| API memory | 114 MB (1 slot), 163 MB (10 slots) | `docs/results/load-test-slots-2026-11-23.md` |
| First stream event under load | p95 < 100 ms up to 1,000 users | `docs/results/load-test-2026-11-22.md` |

## Stage 1.6 and the guardrails

### 5. Citations and guardrails ✅
- **Citations:**
  - every rules answer cites law and article (e.g. QCVN 41:2024/BGTVT B.23, Điều 22), taken from the proof;
  - interpretations that are not law are marked as such;
  - RAG answers show their retrieved passages separately.
- **Faithfulness guard:** the writer's text is rejected if it leaves the engine's verdict or adds codes or numbers.
  It held 100% on dev, with a 0% template rate.
- **Red team** (2026-11-24, $0.35):
  - 30 attacks: injection, jailbreak, harmful, off-topic, text written on the photo, false premise;
  - **30 of 30 blocked; 0 of 40 normal questions refused**;
  - through the live RAG path: 15 of 17 fully blocked, 2 role-play prompts partly followed, no harmful output.
- **Out-of-scope message:** a question that isn't about road signs gets a plain scope message.
- **Context:** follow-up questions are rewritten into complete questions; the RAG keeps its own 65K-token window.

## Stage 2: MLOps and DevOps

### 6. CI/CD ✅
- **CI** (`.github/workflows/ci.yml`), 5 jobs on every push:
  1. lint, Prolog KB load, leakage guard and the test suite;
  2. the RAG service tests;
  3. web typecheck, unit tests and build;
  4. web end to end (Playwright);
  5. the Docker Compose stack.
- **191 CI runs since 2026-11-21** (168 green).
- **CD** (`.github/workflows/cd.yml`):
  - after CI passes on `main`, it builds the images, pushes them to GHCR and deploys over SSH, then checks the
    stack;
  - **it rolls back by itself** if the check fails (tested on 2026-11-22);
  - 31 deployments.
- Other workflows: the base image, the RAG GPU image, the load test.

### 7. Docker Compose ✅
- **8 services:** `web` (nginx + UI), `api` (FastAPI + Prolog pipeline), `postgres`, `prometheus`,
  `node-exporter`, `grafana`, `rag-tunnel`, and `rag` (GPU profile).
- Overlays: HTTPS with Caddy, the real pipeline.
- **A clean machine** (no `.env`, no key, no GPU) starts the whole stack with a fake pipeline; CI does this on every
  push.
- Evidence: `docker-compose.yml`, `docs/deploy.md`.

### 8. Monitoring ✅
- **Grafana "SignCite – hệ thống", 14 panels:**
  - answers, by route and per minute;
  - Claude cost, total and per hour;
  - answer time p50 and p95, and time to each stage;
  - thumbs-up rate, feedback, failed requests;
  - server CPU and memory.
- Prometheus scrapes the API's `/metrics`; node-exporter gives the server.
- The admin overview adds daily charts.
- **Phoenix (LLM traces) was dropped** for time (plan "Cut or reduced"). Each Claude call's tokens and cost are
  logged per stage instead, and each answer's stages are stored with it.

## Stage 3: testing

### 9. Unit and integration tests ✅
- **pytest: 2,612 cases** (1,356 test functions in 99 files):
  - the rule families, the parser, perception, the pipeline;
  - the API (every route, SSE order, errors), the admin site, the leakage guard;
  - follow-ups, the readable proof, the red-team scoring.
- **Vitest: 36** (SSE parser, turn reducer, admin formatting).
- **Playwright: 17** on desktop and phone, against the real API with a fake pipeline.
- A JUnit report is uploaded on every CI run.
- **Coverage (2026-11-25): 94% of the lines in `vqa/` and `app/` in CI** (8,094 statements, 475 missed; 2,471
  tests, 126 skipped there because they need the local dataset), **95% locally** with all 2,612. Measured by
  `pytest-cov` on every CI run, shown on the run's summary page, and uploaded as `coverage.xml`. The Prolog rules
  in `kb/` are tested by the rule-family tests but not measured by Python coverage.

### 10. Load and stress ✅
- **Locust, Docker Compose stack, fake pipeline** (`docs/results/load-test-*.md`):
  - capacity 10 → 500 users;
  - stress up to 1,000 users and back.
- **1 process × 10 slots: 10.33 answers/s**; p95 ≤ 2 s up to 200 users.
- **0 failures at every step, including 1,000 users.** Overload shows as waiting, never as errors.
- **Real end-to-end run** (2026-11-25, `docs/results/load-test-real-2026-11-25.md`, $0.37): the real pipeline on
  the demo server, 5 then 10 users at once, each with a fresh photo, a first question and two follow-ups:
  - **45 questions, 0 errors**;
  - a first question (photo read) about 20 s (p95 31.6 s at 10 users), a later question about 4.5 s (p95 5.4 s);
  - the 10 answer slots add no queueing at 10 users.
- **Not covered:** the RAG fallback under load (it needs a GPU session).

### 11. UAT ✅
- **The pack:** `eval/uat/` has the task sheet, the form questions (SUS in Vietnamese), the moderator notes, the
  observation log, the scorers (`score_sus.py`, `turn_stats.py`) and the report template.
- **The sessions (2026-11-25):** 15 moderated video calls (12 students, 3 drivers; 8 on a computer, 7 on a phone),
  each with 5 fixed tasks and 2 free questions. The report is `docs/results/uat-2026-11-25.md`.
- **The targets, all met:**

  | Target | Result |
  |---|---|
  | SUS ≥ 68 | 91.3 (95% CI 88.8–93.8), A+ |
  | Task success ≥ 80% | 97% observed (73 of 75) |
  | CSAT 4–5 ≥ 70% | 100% |
  | Every task ≥ 60% | lowest 93% (T4 voice, T5 history) |

- **Limits, stated in the report:**
  - no tester who knows traffic law;
  - the sessions ran on a temporary copy of the deployed images, deleted afterwards, so there are no server-side
    waits, rules/RAG split or cost for the sessions;
  - the form's open questions and the log's tags and notes are empty, so there are no complaints to rank.

## Stage 4: the thesis

### 12. Thesis 🟡
- The guidelines' 6 chapters in the FPT template's format, in English, 60–100 pages.
- **Draft done (2026-11-25):** chapters 1–6, front matter (abstracts in English and Vietnamese, abbreviations, a suggested AI-assistance disclosure), appendices, five Chapter 4 charts. Every number names its source in a Word comment. Kept outside the repo (owner's thesis folder).
- B1 (Claude alone) is not reported anywhere (owner, 2026-11-25).
- **Still missing:** the owner's rewrite and the [TODO] items: name, student ID, supervisor, project code; the LowCost and LexiSignVQA papers, their exact scores and determinism; the UAT results (slot in Chapter 5); screenshots of the real site; the six Chapter 3 diagrams rendered from their Mermaid sources.

### 13. References and plagiarism 🟡
- IEEE reference list drafted (51 entries, numbered by first citation); both baselines cited, their paper details to be filled in; entries that could not be checked are marked [VERIFY].
- The plagiarism check: not started (owner).

## Stage 5: slides

### 14. Slides ⬜ · 15. Slide review ⬜
- 22 slides + 4 backup (`docs/plans/task-3-review-3.md`, stage 5); then the review pass for the five faults.

## Stage 6: hand-over

### 16. Repository ✅
- **Has:**
  - `DESIGN.md`, `docs/` (status, plans, results, deploy, runbooks);
  - Swagger at `/docs`;
  - the frozen benchmark tag `v1.0-benchmark` and its freeze records.
  - a root `README.md` (2026-11-25): the results table, `docker compose up` on any machine, the development
    setup, the folders, and the command and record behind each reported number.
- **Not done, not needed for the review:** the `vqa/` → `src/vqa/` move (D8).

### 17. Artifacts ✅
- **The GitHub release** [`v1.0-benchmark`](https://github.com/lephuocloc1729/ns-vqa/releases/tag/v1.0-benchmark), published by the owner's decision on 2026-11-25, on the tag
  `v1.0-benchmark` (`4e71a18`, the code of the 3 private runs). Notes: `docs/release/v1.0-benchmark.md`.
- **What it lists:** the rules system's own artifacts (`kb/`, `prompts/`, the freeze record, the gold annotations);
  the Claude model ids and prompt versions with their sha256; the RAG's model files (Qwen3.5-9B Q4_K_M and its
  projector, F2LLM-v2 0.6B, llama.cpp b11624) with source, revision and sha256, checked against upstream; the GPU
  image digest.
- **Not attached:** the weights are public upstream and linked with their hashes; the dataset, private-test files,
  grading sheets, caches and the private RAG bundle are left out (the notes say why).

### 18. Video 🟡
- Script: `docs/defense/demo_video_script.md`. Recording: the owner, with a GPU session for the RAG part.
