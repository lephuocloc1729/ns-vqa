# Submission to the thesis committee

This is the source code of SignCite, as submitted to the committee, at tag **`v1.1-submission`**
(https://github.com/lephuocloc1729/ns-vqa/tree/v1.1-submission). It is the full system as demoed at
https://signcite.xyz. The [README](../README.md) is the main guide; this page says how the submitted code relates
to the numbers in the thesis.

## Two versions of the code

| Tag | What it is | Use it for |
|---|---|---|
| `v1.1-submission` (this code) | The latest system: the benchmarked pipeline plus everything built after the benchmark (below) | Reading the code, the tests, the demo |
| `v1.0-benchmark` (`4e71a18`, 2026-11-21) | The frozen system of the three private-test runs | Checking the thesis numbers |
| `v1.0-benchmark-repro` (`42a1046`) | `v1.0-benchmark` plus a reproduction mode in `eval/` only | Re-running the private test |

**Every number in the thesis comes from `v1.0-benchmark`.** Its configuration is frozen in
`eval/frozen_phase52.json`, and each of the six private runs left a committed record (`eval/private_ran.json`,
`_2`, `_3` for rules only; `eval/private_rag_ran.json`, `_2`, `_3` with the RAG fallback) with the commit it ran
from and the hash of the freeze record. On this code the freeze check no longer matches, by design (see below), so
the private runners refuse to run here; check and re-run the benchmark from the tags:

```bash
git checkout v1.0-benchmark
.venv/bin/python eval/freeze.py check --profile phase52    # prints "matches the freeze record"
```

Re-running the private test is described in the README, "Reproducing the numbers", level 3.

## What changed since the benchmark

**In the reasoning code** (`vqa/`, `kb/`, `prompts/`), 11 files, three changes that can change an answer:

1. **A truck's weight on a lane sign is its payload** (`05e4b3b`; `vqa/reasoning/facts.py`, `vqa/kb.py`,
   `kb/sign_catalog.yaml`). On R.412c and R.415a the engine read the number as the gross mass; QCVN 41 D.14 says
   it is the permitted payload. Found in the hand grading of the private test, fixed after it.
2. **"Xe máy" means a two-wheeler** (`f28819f`, `97ee8fa`; `kb/ontology.pl`, catalog). A motorbike with a sidecar
   is no longer in the motorbike class, and P.103a/b/c read "except motorbikes" accordingly. The reading is marked
   as an interpretation, so it shows in proofs but is not counted as a law citation.
3. **The owner's review of the catalog** (`ad87b2c`). All 233 rows were checked by hand against their `law_db`
   article and figure; no row's content changed, only the review fields. The perception check that depends on the
   review state was kept on its old 55 rows, so perception behaves as before.

The other reasoning-code changes add features without changing the benchmarked path: the answer text streams token
by token (`vqa/answer/stream.py`, `vqa/answer/writer.py`, `vqa/llm/client.py`), the RAG fallback is called
from the API (`vqa/answer/rag_fallback.py`), and follow-up questions are rewritten into full questions
(`prompts/followup/v1/`).

**In the product** (`app/`, `web/`, deployment):

- the web app: live streaming of each step, a readable proof view, follow-up questions, a gallery of demo photos;
- the admin site: overview, questions and feedback with CSV export, accounts, live settings, the GPU connection,
  the demo photos;
- deployment: Docker Compose stack with HTTPS, monitoring (Prometheus, Grafana), CI/CD to the demo server, and
  the rented-GPU session modes for the RAG;
- checks: load and stress tests, a red-team pass and user acceptance tests (`docs/results/`).

## Running it

What each way of running needs (API key, GPU, data, cost) is in the README, "What you need". In short:

- **No key, no data, no cost:** the test suite (`pytest -q`, over 2,600 cases; tests that need the dataset are
  skipped) and the whole stack with a fake pipeline (`docker compose up -d --build`, then http://localhost:8080).
- **The real system:** an Anthropic API key (about $0.01 per question), the dataset for the scene prompt's
  pictograms, and a 24 GB GPU for the RAG fallback only.
- **The live demo:** https://signcite.xyz, until the defense on 2026-12-19.

## The data

The dataset is not in this code. The photos, the legal corpus (`law_db`) and the questions belong to the VLSP 2025
organisers and are distributed under their data agreement; they are sent to the committee separately, for
evaluating the thesis only. How the dataset can be obtained and rebuilt is in
[`docs/data_availability.md`](data_availability.md). Please don't redistribute it, and keep the private test
answers out of any training or tuning, so that the private test stays a clean benchmark.
