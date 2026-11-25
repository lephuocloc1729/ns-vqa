# SignCite: neuro-symbolic answers about Vietnamese traffic signs

SignCite answers questions about the traffic signs in a road photo ("Xe tải có được rẽ trái ở đây không?"), under
QCVN 41:2024/BGTVT and Law 36/2024/QH15, and shows the legal reasoning behind every answer.

- A vision model reads the signs into a **scene graph**.
- A language model turns the question into a small typed **query program**.
- A **Prolog rule engine** decides the answer from the two, and returns a **proof** with the articles it used.
- Claude only phrases the answer, and a code check rejects any wording that leaves the engine's verdict.
- A question the rules can't decide goes to a **retrieval-augmented model** (Qwen3.5-9B on a GPU), and its answer
  is marked as not verified by the rules.

Live demo: https://signcite.xyz (login for testers). Design: [`DESIGN.md`](DESIGN.md).

## Results

The benchmark is the private test of VLSP 2025 MLQA-TSR (Natural QA version): 146 questions on 104 photos, run
3 times on the frozen system (tag `v1.0-benchmark`), every answer graded by hand.

| System | Private test |
|---|---|
| **V2: rules + RAG fallback** | **82.2%** (sd 1.8 over 3 runs) |
| V1: rules only | decides 66.9% of the questions, at 82.3% |
| RAG alone | 81.5% (119 of 146, hand-graded; judge 79.2%) |
| Baselines LowCost and LexiSignVQA | about 78% |

- On the public test (100 questions) V2 scores 84.5%.
- **Every rules answer comes with a proof and law citations that cannot contradict it**, and the system answers
  "undecided" instead of guessing when a fact is missing.
- A real answer takes 16–21 s on average and costs about $0.009.
- Red team (`docs/results/redteam-2026-11-24.md`): 30 of 30 attacks blocked, 0 of 40 normal questions refused.

## Run it

**On any machine with Docker** (no API key, no GPU). This starts the whole stack with a fake pipeline: the real
API, streaming, storage and monitoring, with sample answers and no Claude calls.

```bash
git clone https://github.com/lephuocloc1729/ns-vqa.git && cd ns-vqa
docker compose up -d --build
```

- The UI: http://localhost:8080 (a red banner marks the fake pipeline)
- Swagger: http://localhost:8080/docs
- Grafana: http://localhost:3000 (`admin` / `admin`)

**The real system** needs an Anthropic API key, the scene prompt's pictograms (made from the dataset, not in
git), and optionally a GPU for the RAG fallback. See [`docs/deploy.md`](docs/deploy.md).

**For development** (Python 3.11+, SWI-Prolog 9.1+):

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,api,eval]'
.venv/bin/python -m pytest -q                     # 2,612 tests, no API calls; line coverage of vqa/ and app/: 95% here, 94% in CI
cd web && npm install && npx vitest run && npx playwright test
```

## What is where

| Folder | Content |
|---|---|
| `vqa/` | the pipeline: perception, question parser, rule engine bridge, answer writer and faithfulness guard |
| `kb/` | the knowledge base: the sign catalog and the Prolog rules, each citing its law article |
| `prompts/` | versioned prompts and few-shot examples |
| `app/api/` | the FastAPI backend: streaming, storage, admin site, follow-up questions, readable proofs |
| `web/` | the React UI and the admin console |
| `services/rag/` | the RAG service (retrieval over the law corpus and few-shot bank, Qwen3.5-9B through llama.cpp) |
| `eval/` | evaluation: splits, judge, benchmark runners, load tests, red team, UAT pack |
| `docker/`, `docker-compose*.yml` | the stack: nginx, API, Postgres, Prometheus, Grafana, RAG tunnel, RAG |
| `tests/` | the test suite: one file per rule family, plus the API, UI back end and evaluation tools |
| `docs/` | `status.md` (the record of every step and number), `plans/`, `results/`, `deploy.md`, `runbooks/` |

### The standard layout, mapped

| Standard folder | Here |
|---|---|
| `src/` | `vqa/` (the pipeline), `app/` (the API), `services/rag/` (the RAG service), `web/` (the UI) |
| `tests/` | `tests/`; also `web/src/**/*.test.ts` and `web/e2e/` for the UI, and `services/rag/tests/` |
| `configs/` | `kb/` (the catalog and the engine switches, e.g. `kb/switches_48.yaml`), `prompts/<stage>/<version>/config.yaml`, `eval/frozen_phase52.json` (the frozen system's settings), `.env.example`, and `docker/` (nginx, Prometheus, Grafana) |
| `docker/` | `docker/` and `docker-compose*.yml` |
| `docs/` | `docs/`, `DESIGN.md`, and the Swagger docs at `/docs` on a running API |

The folders keep their names on purpose. The benchmark's freeze record (`eval/frozen_phase52.json`) fingerprints
the engine by hashing every file under `vqa/` and `kb/` together with its path. At the tag `v1.0-benchmark`,
`eval/freeze.py check --profile phase52` passes, which shows that the tagged code is the code that was benchmarked.
`main` has post-benchmark fixes (listed in `docs/status.md`), so the check reports a different fingerprint there,
as it should. Keeping the same folders keeps `main` and the tag directly comparable, file by file.

## Reproducing the numbers

The dataset (`VLSP2025-MLQA-Natural/`) is not in this repository. Get it from the VLSP 2025 organisers and put it
at the repository root, or set `VQA_DATASET_DIR`. Runs that call Claude need `ANTHROPIC_API_KEY`, and every paid
script has a spend cap (`--max-spend`).

| Number | Command | Record |
|---|---|---|
| The frozen system | `.venv/bin/python eval/freeze.py check --profile phase52` | `eval/frozen_phase52.json` |
| Private test, V1 (3 runs) | `eval/e2e_private.py run [--run 2\|3]`; each run is allowed once | `eval/private_ran*.json`, aggregates in `eval/runs/e2e/` |
| Private test, V2 and RAG alone | `eval/e2e_private_rag.py run --run N --rag-predictions … --rag-live …` | `eval/private_rag_ran*.json` |
| Public test, V2 | `eval/e2e_public_dev52.py run`, then `merge` | `docs/status.md`, "phase52" |
| Load tests | GitHub Actions › Load test (Locust, fake pipeline) | `docs/results/load-test-*.md` |
| RAG speed, memory, Q4 vs BF16 | `eval/rag_bench.py` on a GPU session | `docs/results/gpu-session-2026-11-21.md`, `rag-concurrency-2026-11-23.md` |
| Red team | `eval/redteam/redteam.py run --max-spend 0.65`, then `rag` and `report` | `docs/results/redteam-2026-11-24.md` |

The private test's answers are read only by the scoring code, which writes aggregates only. See the dataset rules
in [`CLAUDE.md`](CLAUDE.md).

## Data and licences

The dataset, its images and the law corpus figures are not redistributed here; the VLSP data agreement applies. The
RAG's model weights are public upstream (Qwen3.5-9B GGUF, F2LLM-v2 0.6B); `services/rag/assets_manifest.json`
lists the RAG's own files with their sha256.
