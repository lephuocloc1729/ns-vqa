# Load test: answer slots vs API processes, 2026-11-23

- **Runs:** GitHub Actions 45096273672 (1 × 1, 1 × 6, 2 × 1, 4 × 1) and 45102975468 (1 × 10), workflow `.github/workflows/load-test.yml`.
- **Setup:** the same as `load-test-2026-11-22.md`. Docker Compose stack, fake pipeline (about 0.96 s per answer, no Claude calls), 4-vCPU runners, the capacity ramp and the stress test with an API restart between them.
- **The four setups** are API processes × answer slots per process (PR #19):
  - **1 × 1:** the behaviour before PR #19;
  - **1 × 6** and **1 × 10:** one process with 6 or 10 answer slots (the demo server runs 10);
  - **2 × 1** and **4 × 1:** more processes, one answer at a time each.

## Answers per second at the ceiling (500 users)

| setup | answers/s | in theory |
|---|---:|---:|
| 1 process × 1 slot | 1.05 | 1.04 |
| 2 processes × 1 slot | 2.10 | 2.08 |
| 4 processes × 1 slot | 3.58 | 4.17 |
| 1 process × 6 slots | 6.15 | 6.25 |
| **1 process × 10 slots** | **10.33** | 10.42 |

The slots reach their theoretical ceiling, but 4 processes don't. New connections are handed to processes whether they are busy or not, so some answers wait behind a busy process. The slots of one process take the next question as soon as any of them is free.

## Time to the answer, p50 / p95 in seconds

| users | 1 × 1 | 2 × 1 | 4 × 1 | 1 × 6 | **1 × 10** |
|---:|---:|---:|---:|---:|---:|
| 10 | 1.0 / 2.6 | 1.0 / 1.8 | 1.0 / 1.9 | 1.0 / 1.0 | **1.0 / 1.0** |
| 25 | 4.9 / 7.7 | 1.8 / 4.0 | 1.0 / 2.1 | 1.0 / 1.0 | **1.0 / 1.0** |
| 50 | 19.4 / 23.8 | 5.1 / 12.7 | 1.3 / 3.3 | 1.0 / 1.0 | **1.0 / 1.0** |
| 100 | 29.1 / 48.1 | 11.7 / 34.3 | 4.8 / 20.1 | 1.0 / 1.6 | **1.0 / 1.0** |
| 200 | 65.1 / 73.2 | 36.3 / 55.4 | 18.9 / 38.8 | 6.9 / 10.5 | **1.0 / 2.0** |
| 300 | 88.2 / 112.3 | 60.0 / 100.1 | 32.9 / 58.4 | 18.6 / 22.4 | **3.7 / 4.6** |
| 500 | 132.5 / 148.1 | 52.9 / 131.7 | 44.6 / 94.2 | 27.9 / 41.7 | **15.7 / 22.7** |

**The knee** (p95 under 10 s) moves from about 25 users (1 × 1) to about 200 users (1 × 6) and **beyond 300 users (1 × 10)**. Up to 200 users, 1 × 10 answers as fast as with no load at all (p95 at most 2 s).

## Stress and recovery

| setup | 100 users: answers/s, p50 / p95 | 1000 users: answers/s, p50 / p95 | back to 20 users: p50 / p95 |
|---|---|---|---|
| 1 × 1 | 1.03, 27 s / 43 s | 1.04, 76 s / 111 s | 127 s / 140 s |
| 2 × 1 | 2.05, 17 s / 27 s | 2.07, 55 s / 100 s | 116 s / 136 s |
| 4 × 1 | 3.35, 7 s / 11 s | 4.09, 38 s / 89 s | 108 s / 131 s |
| 1 × 6 | 4.50, 1.0 s / 3.0 s | 6.11, 40 s / 77 s | 95 s / 108 s |
| **1 × 10** | **4.20, 1.0 s / 1.0 s** | **10.15, 31 s / 59 s** | **67 s / 72 s** |

**Failures: 0** in every step of every setup, including 1000 users.

## Cost in memory and CPU

The API container's peak was 141 MB with 6 slots and **163 MB with 10 slots**, against 114 MB with 1 slot: the slots share one pipeline. Four processes would need four pipelines.

## On the real system

A real answer takes about 20 s, almost all of it waiting on Claude.
- With 1 slot, the server finished about 3 answers a minute.
- With 10 slots it finishes about 30: ten questions run at once, each in about 20 s.
- **The account's rate limits** ("Evaluation tier": 1,000 requests, 500K input tokens and 80K output tokens per minute per model) cover 10 slots at full load:
  - about 90 requests a minute (9%);
  - about 270K Haiku input tokens a minute (~54%; perception sends each photo to Haiku).
  - At 20 slots, Haiku's input limit would be exceeded under sustained full load.
- **The RAG fallback** (when it is on) answers one question at a time on one GPU, mean 7.2 s, so about 8 fallback answers a minute.
  - With 19–33% of questions going to the fallback, it covers 10 slots at normal use.
  - Under sustained full load it becomes the bottleneck. After `VQA_RAG_TIMEOUT_S` (180 s) the API ships the rules' own answer instead.
- The demo server runs `VQA_ANSWER_SLOTS=10` since 2026-11-23 (6 earlier that day).
