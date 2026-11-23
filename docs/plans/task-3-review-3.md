# Plan: Task 3 before Review 3 (the defense checklist)

**Status: proposed (2026-11-21, revision 2), not approved.** Nothing is built yet.

Source: the faculty's checklist "Kiểm tra khối lượng Task 3 trước Review lần 3": 6 stages, 18 self-assessment rows, 17 expected committee questions, and 5 closing notes. This plan has three parts:

- **Part A:** every checklist item, and what we show for it;
- **Part B:** every committee question, its answer outline, and the number that backs it;
- **Part C:** the work packages that produce those items and numbers, in dependency order.

Where a checklist item does not fit this problem (no training, so no loss curves; the input is a road photo), the plan meets it in the closest honest form and says so in one line. It never invents a number.

## Ground rules

- **The benchmarked system stays frozen.** The private and public numbers come from `phase52` (`eval/frozen_phase52.json`), tagged `v1.0-benchmark` before any change below. The demo product is that configuration plus the RAG service. Anything that could change an answer (input guardrail, follow-up memory) lives in the app layer, can be switched off, and gets its own freeze record (`eval/frozen_demo.json`). Benchmark tables never contain demo-only behaviour.
- **The leakage guard still holds.** App code is inference code: no imports from `eval`/`tests`, and no split, fixture or QA files. User feedback and "edited ground truth" are stored, shown on the dashboard, and never read back by the pipeline.
- **Claude API spend** only behind the spend guard, and only after the owner's go-ahead on each line of the spend table.
- **Every claim is a number with its source:** run id or commit, hardware, number of trials, mean ± sd and p50/p95 (closing note 2). Limits are stated plainly, with their technical cause (closing note 1).

## Decisions already made (owner, 2026-11-21)

- **No umbrella folder.** `ns-vqa` (this repo) is the official repository.
- **The RAG comes in as code only,** under `services/rag/`, with its code history rewritten by `git filter-repo`. `artifacts/`, `reports/` and every private-test file stay out of git. `services/rag/ORIGIN.md` maps old hashes to new ones, so `trafficvqa-rag@db75c4b` stays citable.
- **The RAG's data and index are copied into `services/rag/{data,artifacts,models}`, gitignored,** with a committed sha256 manifest. A private bundle plus a fetch script covers a clean machine.
- **The two baselines' code is not included now.** Both baseline rows stay in Chapter 4 and the slides, both papers are cited, and the README links the upstream repos and the sha256s of the saved predictions.

## Facts the answers rely on (checked 2026-11-21)

- **Private benchmark, 146 questions, 3 runs, owner hand-graded:** V2 82.2% (sd 1.8); V1 decides 66.9% at 82.3%; RAG alone 79.2% (judge-graded); LowCost and LexiSignVQA about 78%.
- **Public test, 100 questions:** V2 84.5%, RAG alone 82.0%.
- **Latency, rules side:** 32.9 → 22.7 s per question with parallel API calls; removing the scene re-run would save about 3.7 s more (not applied, it changes outputs).
- **Latency, RAG fallback:** live, warm, on an RTX 5090 (vast): mean 7.2 s (p50 6.5, p95 12.9, max 22.5); caption 2.7 s, embedding 0.01 s, retrieval 0.02 s, answer 4.4 s.
- **RAG:** deterministic (two Q4 private runs identical on 146 of 146). Retrieval is exact cosine search in numpy over 1024-d `f2llm-v2-0.6b` vectors. It already manages its context window (`--context-size 65536`, `--current-context-budget 20000`). Saved Q4 and BF16 private runs exist.
- **Scene graphs carry a pixel box per sign** (`box`, marked debug-only in `vqa/schemas.py`), so the UI can draw boxes.
- **Tests:** 1,222 test functions in this repo.
- **The dev Mac** is an M1 with 8 GB RAM, too small for the whole stack plus the 9B model, so the demo needs a server (D5).

---

## Part A. Every checklist item

### Stage 1: UI/UX, packaging, model optimisation

| Item | What we show | Work |
|---|---|---|
| 1.1 Input layer | Image upload, drag-drop and camera capture; question text box; **voice:** Vietnamese speech-to-text with a self-hosted Whisper model; **video:** upload, pick a frame on a scrubber, or "auto": up to 5 keyframes, with the cost shown before asking; **PDF/DOCX:** extract the photos and questions from a document (e.g. an exercise sheet) and ask them as a batch. Progress per stage, clear errors (bad file, too large, service down) | W3, W4 |
| 1.2 Streaming | SSE from the API: stage events (`perception` with boxes → `parsed` program → `engine` verdict and proof → `writer` tokens), the writer on the Anthropic streaming call, and RAG tokens streamed through for fallback answers | W2, W1 |
| 1.3 Output and feedback | Sign **bounding boxes** with codes and confidence on the image; the proof tree; rule citations as chips (law, article, and article text if D3); for RAG answers, the retrieved passages **highlighted**, with score and source, kept apart from rule citations; a dashboard page with **charts** (questions per day, verdict mix, fallback rate, thumbs-up rate, latency); history per session; thumbs up/down and "edit the correct answer" | W3, W5 |
| 1.4 Optimisation | (a) RAG LLM: Qwen3.5-9B **BF16 → Q4_K_M** (llama.cpp GGUF quantisation); (b) speech model: Whisper **FP16 → INT8** (CTranslate2/faster-whisper); (c) rules side: runtime optimisations (parallel calls, scene cache, prompt caching). No pruning or distillation: the rules side has no weights of its own, which the report says in one line | W6 |
| 1.5 Benchmark table | One table per technique, before vs after: latency (ms/token and s/question for the LLM, real-time factor for Whisper), memory (VRAM/RAM, MB), and accuracy (private judge-graded for Q4/BF16; WER on a recorded question set for Whisper; same answers for the rules-side runtime changes). Best value in bold, units on every column, hardware and trial count in the caption | W6 |
| 1.6 RAG/LLM specifics | **Citations:** law id, article, clause, the law's title, the source file, and for RAG passages the chunk id and score. **Context window:** the RAG's token budget (above) plus app-level memory: a buffer of the last 3 turns, a short summary once the buffer passes a token budget, and the session's current image kept so follow-ups reuse its cached scene (D4). **Guardrails:** the DSL design, input and output checks, and a red-team test | W3, W4 |

### Stage 2: MLOps and DevOps

| Item | What we show | Work |
|---|---|---|
| 2.1 CI/CD | `.github/workflows/ci.yml`: ruff lint and format check, pytest (data, API, inference), leakage guard, Prolog load check, frontend lint and build, the RAG's own tests. `cd.yml` on `main` and tags: build 4 images, push to GHCR, deploy over SSH, smoke test. **Turned on in week 1,** so the run history is weeks long by the defense | W0, W7 |
| 2.2 Microservices | `docker-compose.yml`: `web` (nginx + bundle), `api` (FastAPI gateway + rules pipeline + SWI-Prolog), `rag` (RAG inference server, GPU), `stt` (Whisper), `qdrant` (vector DB), `postgres` (users, sessions, chat history, feedback), `prometheus`, `grafana`, `phoenix` (LLM traces). Two profiles: `full` (GPU) and `cpu` (fake model backends, for a clean machine and CI) | W7 |
| 2.3 Monitoring | Prometheus + Grafana: CPU, RAM, GPU (DCGM exporter), API response time per endpoint and per stage, error rate, fallback rate, **tokens and USD per model**, spend-guard headroom. Arize **Phoenix** (OpenTelemetry) for LLM traces: each Claude call and RAG stage, its latency and tokens, plus the faithfulness-guard pass rate as our "hallucination score". Dashboards are provisioned from JSON in the repo | W7 |

### Stage 3: testing

| Item | What we show | Work |
|---|---|---|
| 3.1 Unit and integration | The existing suite (engine, rules, parser, pipeline) plus new tests: **data ingestion** (image loading and normalisation, scene cache keys, RAG corpus chunking, the index manifest check), **API endpoints** (every route, SSE event order, feedback, errors), **inference pipeline** (fake models, real Prolog engine). Report: `pytest --junitxml` plus coverage %, attached to every CI run | W2, W8 |
| 3.2 Load and stress | Locust in three parts. (1) **Capacity:** `cpu` profile (fake models, real engine), ramp 10 → 500 users, 1/2/4 API workers. (2) **Stress:** push past the knee until errors appear, then check recovery. (3) **Real end-to-end:** 5–10 users, about 50 requests. Reported: concurrent users, RPS, mean/p95 response time, failure rate, and the point where p95 passes the threshold | W8 |
| 3.3 UAT | 15–20 users: drivers, students, 2–3 people who know traffic law. 5 fixed tasks plus 5 questions of their own, then **SUS** (10 items) and **CSAT** (1–5). Report: mean SUS with a 95% CI, the CSAT share at 4–5, task success rate, the top 3 complaints with a fix or an explanation for each | W8 |

### Stage 4: the thesis (60–100 pages)

| Part | Content and where it comes from | Work |
|---|---|---|
| Front matter | Cover, inner cover, task sheet, declaration, acknowledgements, contents, lists of tables, figures and abbreviations, abstract in Vietnamese and English | W9 |
| Ch. 1 | Why this topic; why it is urgent (Law 36/2024, QCVN 41:2024: new rules, citizens need answers they can check); goals; scope (the VLSP 2025 MLQA Natural task, signs and the law they carry); outline | W9 |
| Ch. 2 | Related work: VLSP 2025 TSR systems (the two baselines), VQA and neuro-symbolic VQA, LLM + RAG for legal QA, vision-language models, logic programming and proof trees, quantisation | W9 |
| Ch. 3 | The detailed problem; the proposed method (scene graph → DSL → Prolog rules → proof → writer, with the RAG fallback); the data pipeline (catalog, KB, the RAG's law corpus and few-shot bank); the system architecture (microservices), sequence diagrams (ask, stream, fallback, feedback), the database schema. **Diagrams are generated from code** (schema from the ORM models, the service graph from the compose file), so they match Ch. 5 | W9, W7 |
| Ch. 4 | Dataset statistics; imbalance (Yes/No vs Natural QA, sign-class long tail, image overlap between splits) and how it is handled without training (per-type scores, Wilson CIs, catalog coverage, the all-images rule); environment and settings (models, efforts, temperatures, prompt versions, RAG flags, seeds); metrics; **Baseline 1, Baseline 2, V1, V2** (+ RAG alone) on private; failure-case analysis (done); ablations; charts | W9, W6 |
| Ch. 5 | UI screenshots and workflows; Docker, CI/CD and monitoring; the test results (latency, load, UAT) | W9 |
| Ch. 6 | Results; honest limits (perception misreads dominate the errors, dependence on a paid API and its cost, about 20 s per question, unmodelled articles, the Mac cannot run the RAG); future work | W9 |
| Back matter | IEEE references from one BibTeX file; appendix with the source-code link, install guide and detailed result tables | W9 |

### Stage 5: slides (20–25) and defense

The checklist's 18-slide frame, widened to 22 slides: 1 cover; 2–3 problem and contributions; 4–6 pipeline, the method vs the baselines, the RAG data and vector DB; 7–11 data, the benchmark table, ablations, failure cases, charts; 12–15 architecture, CI/CD, tests, demo; 16–17 conclusion and limits; 18 thanks and Q&A; plus 4 backup slides for the Q&A (Part B). The five slide faults to avoid are checked in a review pass (W10). Deliverables: PPTX and PDF.

### Stage 6: hand-over

| Item | What we hand over | Work |
|---|---|---|
| 6.1 Repository | `src/`, `tests/`, `configs/`, `docker/`, `docs/`, `services/rag/`, `web/` (D8); README with the results table, `docker compose up`, Swagger (`/docs`), and how to reproduce each reported number (commands, run ids, freeze records) | W0, W10 |
| 6.2 Thesis | Official PDF; hard-bound copies (owner) | W9 |
| 6.3 Artifacts | The "model" of this system is its knowledge base, catalog, prompts and freeze records (in the repo, tagged). The RAG's GGUF weights are public upstream; we publish their exact files and sha256s. The RAG index is a private bundle. Processed data: the gold scene labels and gold intents (ids and annotations, no images or question text), if the course allows (D6) | W10 |
| 6.4 Slides and video | PPTX + PDF; 3–5 min demo video | W10 |

---

## Part B. Every committee question, and how we answer it

Each answer gets a backup slide or a page in `docs/defense/qa.md`, with its number and the source of the number. "To measure" means the number comes from the named work package.

**Stage 1**

1. **Why this UI stack, and how does the frontend scale?** React + Vite, built into static files served by nginx. The frontend holds no state, so it scales behind any CDN or more nginx replicas, and the load sits on the API. The API scales by worker processes: one SWI-Prolog engine per process, with the Claude calls async. Evidence: the W8 capacity test with 1/2/4 workers (to measure). Streamlit/Gradio were rejected because they run the UI in the same Python process as the model calls.
2. **How does streaming work, and can connections drop or buffers overflow?** FastAPI SSE. Each stage is an event, writer tokens are relayed as they arrive, there is a heartbeat every 15 s, a timeout per request, and a bounded queue per connection (a slow client is dropped, not buffered without limit). Every answer is stored under a request id, so a client that reconnects fetches it. Evidence: the W2 tests for disconnects and slow readers.
3. **How many ms and MB did quantisation save, and what did it cost in accuracy?** The W6 table: Q4_K_M vs BF16 for ms/token, s/question and VRAM (to measure on the RTX 5090), with private accuracy from the saved runs (judge-graded); and Whisper INT8 vs FP16 for speed, RAM and WER (to measure).
4. **On what hardware, averaged over how many trials?** Every row names the GPU, CPU and RAM. LLM timings: 3 warm-up runs, then the 100 public questions × 3 passes. Load tests: a fixed duration per step. Mean, sd, p50 and p95 are reported.
5. **Out-of-domain questions and hallucination?** Three layers. (a) The parser only outputs the DSL; anything it cannot express is `out_of_scope`. (b) The rule engine answers only from the scene and cited law, and the faithfulness guard rejects a writer text that leaves the engine's verdict or adds codes or numbers. (c) The RAG gate: below the low retrieval score it answers "no legal basis found", not a guess. Plus the input guard for off-topic questions. Evidence: the W4 red-team set (refusal rate on out-of-domain items) and the faithfulness pass rate on the dashboard.
6. **Prompt injection or jailbreak tests? How does the guardrail work?** Yes, the W4 set of about 60 items: injection in the question, instructions written in the image, role-play jailbreaks, harmful requests, out-of-domain. Mechanism: rules plus a Haiku classifier on the input, and an output check for leaked prompts and off-topic text. The DSL bottleneck means injected text cannot reach the rule engine as instructions. Reported: block rate and false refusals on 40 normal questions (to measure).

**Stage 2**

7. **Show the deployment history, and explain the workflow on a commit to main.** The live GitHub Actions page. Steps: lint → tests (with reports) → leakage guard → build images → push to GHCR → SSH deploy → `/health` smoke test → rollback to the previous tag if the smoke test fails.
8. **Will `docker compose up` work on a clean machine?** Yes, tested on a fresh VM (W7): `git clone`, `cp .env.example .env`, `docker compose --profile cpu up` works with no keys and no GPU (fake models). The `full` profile needs the API key, a GPU and `scripts/fetch_rag_bundle.sh`. No absolute paths; everything comes from `.env`. Evidence: a recording of the clean-VM run.
9. **Which protocols? What if the vector DB is congested?** REST + SSE (web ↔ api), REST (api ↔ rag, api ↔ stt), gRPC (rag ↔ qdrant), SQL (api ↔ postgres). Timeouts and a circuit breaker on every hop. If `rag` or `qdrant` is slow or down, the API answers with the rule engine alone and the UI shows "RAG unavailable". The rules side never needs the vector DB. Evidence: a W8 chaos test (stop `qdrant` under load: error rate and fallback behaviour).
10. **Which tools track resources and token cost? Show the dashboard.** The live Grafana dashboard (resources, latency, tokens and USD per model) and Phoenix traces, backed by the per-call usage log the project has kept since phase 2.

**Stage 3**

11. **Maximum concurrent users before the response time is unacceptable?** From the W8 knee point, with 1/2/4 workers (to measure). It is reported separately for the system and for the real end-to-end case, where the limit is the Claude rate limit and the single GPU, not our code. That cause is stated plainly.
12. **Maximum RPS, and the failure rate at peak?** The same W8 run: max sustained RPS, and the failure rate at the stress peak (to measure).
13. **How many UAT users, what SUS/CSAT score, and the main weakness?** 15–20 users; mean SUS with its CI and its grade on the standard scale; CSAT; the top complaint (we expect the ~20 s wait, and say what streaming does about it).

**Stage 4**

14. **Are references consistent IEEE, and are the baselines cited?** One BibTeX file, IEEE style, checked by a script for missing fields. Both VLSP 2025 papers (1.52, 1.53), the QCVN and laws, and every model and tool are cited.
15. **Plagiarism score?** The university's tool (owner), the % reported; analysis text is written by the team; quoted law text is marked as a quotation.
16. **Do the Ch. 3 diagrams and schema match the code in Ch. 5?** Yes by construction: the schema is generated from the ORM models and the service diagram from `docker-compose.yml`, by a script that fails CI if they differ from the files in `docs/figures/`.

**Stage 6**

17. **Can an outsider clone and reproduce the results?** Three levels, said plainly. (a) **Exact:** re-score every reported number from the stored predictions and freeze records with no API calls (`eval/` commands in the README). (b) **Re-run:** run the frozen system again with your own API key; answers vary from run to run because perception, parsing and the writer are LLM calls, which is why the private test was run 3 times and reported as mean and spread. (c) **The RAG** is deterministic, so it reproduces exactly from the bundle.

**Closing note 4 (every member answers everything):** `docs/defense/qa.md` holds all of the above; two mock Q&A sessions in W10.

---

## Part C. Work packages, in order

Each package ends with its done check.

### W0. Repo hygiene and CI first (week 1)

- Merge `phase-5` into `main`; tag `v1.0-benchmark`; push.
- Settle which copy is the source of truth (`~/capstoneproject` and `~/abc copy` differ from this repo).
- **CI now:** lint, tests, leakage guard and Prolog load on every push, so history builds up from week 1.
- Layout move if D8 = yes: `vqa/` → `src/vqa/` (imports unchanged, `pyproject` src layout, path-based tests updated); `configs/`, `docker/` and `web/` created.
- **Done:** CI green on `main`, tag pushed.

### W1. RAG in the repo and as a service (week 1)

- Import code only (`git filter-repo`), `ORIGIN.md` with the hash map, the gitignored data copy plus manifest, the bundle and fetch script.
- **F2:** `POST /answer`, `POST /answer/stream` (SSE), `/health`, `/version`, a fake-backend test.
- **Vector DB:** load the same `f2llm` vectors into Qdrant (exact search). **Equivalence gate:** the same top-k ids, in the same order, as the numpy search on all public questions. If it fails, the service keeps the numpy index and the thesis says why (D2).
- **F3:** `vqa/answer/rag_fallback.py` with failure handling and fake-server tests.
- **Done:** the live RAG answers through the service match the saved public answers on 100 of 100.

### W2. Backend API (week 1–2)

- FastAPI: `/v1/ask`, `/v1/ask/stream`, `/v1/batch` (documents), `/v1/sessions`, `/v1/history`, `/v1/feedback`, `/v1/stt`, `/health`, `/metrics`, Swagger at `/docs`.
- Postgres via SQLAlchemy and Alembic: `user`, `session`, `turn` (image hash, question, answer JSON, proof, citations, timings, cost), `feedback` (thumb, corrected answer, note).
- Streaming as in B2; workers as in B1.
- **Done:** endpoint tests green, and an SSE disconnect test.

### W3. Frontend (week 2)

- React + Vite: the ask page (inputs and outputs from 1.1 and 1.3), history, feedback, the dashboard page with charts, the RAG-unavailable state, Vietnamese UI text.
- **Done:** the 5 UAT tasks can be done end to end in the `full` profile.

### W4. Input types, guardrails, memory (week 2)

- `stt` service (faster-whisper); video frame extraction (ffmpeg in the API); PDF/DOCX extraction (PyMuPDF, python-docx).
- Guardrail layer and red-team set (`eval/redteam/`, hand-written, about 60 attacks plus 40 normal questions); app-level memory (buffer plus summary).
- **Done:** red-team report with block and false-refusal rates.

### W5. Visual output (week 2)

- Boxes from the scene graph drawn on the image; proof tree; citation chips; highlighted RAG passages.
- Article text if D3 (a gitignored sha256-pinned copy, as with the pictograms).

### W6. Optimisation benchmarks (week 2–3, GPU machine)

- Q4_K_M vs BF16: ms/token, s/question, VRAM (`nvidia-smi` peak), private accuracy from the saved runs.
- Whisper FP16 vs INT8: real-time factor, RAM/VRAM, WER on about 30 questions the owner records.
- Rules side: before/after from the existing measurements, plus one cold-vs-warm cache run.
- **Done:** the Ch. 4/5 tables and the slide table, each with hardware and trial count.

### W7. Compose, CD, monitoring (week 2–3)

- All containers, both profiles, `.env.example`, healthchecks, restart policies, named volumes.
- CD to the server (D5) with rollback; Grafana dashboards and Phoenix.
- Clean-VM test recorded.
- Diagram generators (schema, services) with their CI check.
- **Done:** a fresh VM reaches a working UI from the README alone.

### W8. Testing (week 3)

- New unit/integration tests and the coverage report.
- Locust capacity, stress and real runs; the chaos test (stop `qdrant`, stop `rag`).
- **UAT:** recruit users in week 1, sessions in week 3; task sheet, SUS/CSAT form, `eval/uat/score_sus.py`.
- **Done:** the test chapter's tables, and the evidence links in the self-assessment.

### W9. Thesis (weeks 1–4, owner writes, the assistant drafts material)

- Ch. 3–4 from DESIGN.md, status.md and the committed aggregates first (they exist now); Ch. 5 as W2–W8 land; Ch. 1, 2 and 6 last.
- Figures: architecture, sequence, results charts, the verdict confusion matrix (gold vs system, Yes/No questions), a **t-SNE of the question embeddings** coloured by question type and by whether the rules decided them (the closest honest stand-in for the checklist's t-SNE; no loss curves, since nothing is trained, said in one line).
- References in BibTeX/IEEE; plagiarism check (owner).
- **Done:** 60–100 pages, the 6 chapters complete against Part A.

### W10. Slides, video, hand-over, rehearsal (week 4)

- 22 slides + 4 backup; the review pass for the five faults (≥ 18 pt, bold best values, units, a limits slide, the backup video).
- Video, 3–5 min (script by the assistant, recording by the owner): upload → boxes → streaming answer → proof and citations → a fallback answer → a voice question → a blocked injection → history and feedback → Grafana.
- README final; artifacts published (D6); `docs/review3_self_assessment.md` with an evidence link for each of the 18 rows; `docs/defense/qa.md`; two timed rehearsals and two mock Q&A sessions.

## Self-assessment target

| # | Row | Today | Target | Evidence |
|---|---|---|---|---|
| 1 | UI/UX | not started | done | W3 screenshots, video |
| 2 | Streaming | not started | done | W2 tests, video |
| 3 | Optimisation | in progress | done | W6 tables |
| 4 | Latency and memory table | in progress | done | W6 |
| 5 | Citations and guardrails | in progress | done | W4 red-team report |
| 6 | CI/CD | not started | done | Actions history |
| 7 | Docker Compose | not started | done | compose file, clean-VM recording |
| 8 | Monitoring | in progress | done | Grafana and Phoenix |
| 9 | Unit and integration tests | mostly done | done | junit and coverage reports |
| 10 | Load and stress | not started | done | Locust report |
| 11 | UAT | not started | done | SUS/CSAT report |
| 12 | Thesis | unknown (D1) | done | PDF |
| 13 | References and plagiarism | not started | done | BibTeX check, tool report |
| 14 | Slides | not started | done | PPTX/PDF |
| 15 | Slide review | not started | done | review checklist |
| 16 | Repository | in progress | done | README, Swagger |
| 17 | Artifacts | not started | done | release, HF links |
| 18 | Video | not started | done | video file |

## Schedule: 9 days (Review 3 on 2026-11-30)

Review 3 is on **2026-11-30**; the thesis defense is on **2026-12-19** (owner, corrected 2026-11-22; this schedule was first written for a defense on 11-30). The schedule targets Review 3; the defense adds about three weeks. The plan above is the full version; this is what fits. The first cuts are the items the committee sees least.

**Cut or reduced:**
- PDF/DOCX input and video input: dropped. The thesis says why in one line (the input is a road photo).
- Voice: the browser's speech-to-text, not a Whisper service, so the Whisper INT8 row goes too.
- Phoenix: dropped (Grafana only).
- Qdrant: dropped, the numpy index stays, and the thesis explains why (D2).
- Chaos test and SSH auto-deploy: dropped. CD = build and push images to GHCR; deploy is one script on the GPU box.
- Red-team set: 30 items. UAT: 10–12 users through an online form.

| Day | Date | Work |
|---|---|---|
| 1 | Sat 21 – Sun 22 | W0 (merge, tag, CI); RAG import (W1); message UAT users; owner: thesis status (D1) |
| 2 | Mon 23 | API + streaming + Postgres (W2); RAG service on the GPU box (F2) |
| 3 | Tue 24 | Frontend: upload, text, voice, boxes, proof, citations, history, thumbs (W3, W5); F3 client |
| 4 | Wed 25 | Docker Compose + Prometheus/Grafana; deploy on the GPU box; Q4 vs BF16 measurement (W6, W7) |
| 5 | Thu 26 | API tests, Locust (capacity + small real run), guardrail + 30-item red-team; UAT opens |
| 6 | Fri 27 | UAT closes, SUS/CSAT; Ch. 5 numbers; slides draft |
| 7 | Sat 28 | Thesis finished, references, plagiarism check; demo video recorded |
| 8 | Sun 29 | Two timed rehearsals, Q&A sheet, buffer for anything that slipped |
| 9 | Mon 30 | Review 3 |

The thesis is the biggest risk. It runs alongside every day, and depends on D1 (where the draft is, and whether it must be submitted before the 30th).

## Decisions needed (owner)

| # | Question | Recommendation |
|---|---|---|
| D1 | Thesis: where is the draft, in which format (Word template or LaTeX), and how far along is it? | — |
| D2 | Vector DB: Qdrant behind an equivalence gate, or keep the numpy index inside `rag`? | Qdrant with the gate (meets 2.2; the answers stay the same) |
| D3 | Article text in the UI: a gitignored, sha256-pinned copy of the cited law_db articles? | Yes, the pictogram pattern |
| D4 | App-level memory (buffer + summary, pipeline unchanged)? | Yes |
| D5 | Demo server: the GPU machine for `rag` and `stt`, plus which host for the rest? | A small VPS for web, api, db and monitoring; the GPU box for rag and stt |
| D6 | Publish: GitHub release with the weights' sha256s; gold annotations on HF if the course allows? | Yes to both, private if unsure |
| D7 | Defense date; team members and who presents which part | Answered for the dates (owner, 2026-11-22): Review 3 on 11-30, defense on 12-19; who presents what is still open |
| D8 | Move `vqa/` → `src/vqa/` to match 6.1? | Yes, after the benchmark tag (imports unchanged) |
| D9 | Make `trafficvqa-rag` private or remove its private-test files from history? | Make it private |

## Spend (Claude API; no spend yet; each line asked for separately)

| Item | Estimate |
|---|---|
| Development and demo smoke tests (~100 questions) | ~$1.5 |
| Red-team and false-refusal set (~100 items, plus the Haiku guard) | ~$1.2 |
| Real end-to-end load test (~50 requests) | ~$0.7 |
| UAT (~20 users × 10 questions) | ~$2.5 |
| Rules-side cold/warm cache re-measure | ~$0.5 |
| Demo video takes and rehearsals | ~$1.0 |
| **Total** | **~$7.4** |

Based on about $0.01–0.015 per question from the private runs. GPU time is on the owner's machine.
