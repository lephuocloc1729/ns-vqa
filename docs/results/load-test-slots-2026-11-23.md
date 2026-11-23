# Load test: answer slots vs API processes, 2026-11-23

- **Run:** GitHub Actions 45096273672, workflow `.github/workflows/load-test.yml`.
- **Setup:** the same as `load-test-2026-11-22.md`. Docker Compose stack, fake pipeline (about 0.96 s per answer, no Claude calls), 4-vCPU runners, the capacity ramp and the stress test with an API restart between them.
- **The four setups** are API processes × answer slots per process (PR #19):
  - **1 × 1:** the behaviour before PR #19;
  - **1 × 6:** what the demo server now runs;
  - **2 × 1** and **4 × 1:** more processes, one answer at a time each.

## Answers per second at the ceiling (500 users)

| setup | answers/s | in theory |
|---|---:|---:|
| 1 process × 1 slot | 1.05 | 1.04 |
| 2 processes × 1 slot | 2.10 | 2.08 |
| 4 processes × 1 slot | 3.58 | 4.17 |
| **1 process × 6 slots** | **6.15** | 6.25 |

The slots reach their theoretical ceiling, but 4 processes don't. New connections are handed to processes whether they are busy or not, so some answers wait behind a busy process. The slots of one process take the next question as soon as any of them is free.

## Time to the answer, p50 / p95 in seconds

| users | 1 × 1 | 2 × 1 | 4 × 1 | **1 × 6** |
|---:|---:|---:|---:|---:|
| 10 | 1.0 / 2.6 | 1.0 / 1.8 | 1.0 / 1.9 | **1.0 / 1.0** |
| 25 | 4.9 / 7.7 | 1.8 / 4.0 | 1.0 / 2.1 | **1.0 / 1.0** |
| 50 | 19.4 / 23.8 | 5.1 / 12.7 | 1.3 / 3.3 | **1.0 / 1.0** |
| 100 | 29.1 / 48.1 | 11.7 / 34.3 | 4.8 / 20.1 | **1.0 / 1.6** |
| 200 | 65.1 / 73.2 | 36.3 / 55.4 | 18.9 / 38.8 | **6.9 / 10.5** |
| 300 | 88.2 / 112.3 | 60.0 / 100.1 | 32.9 / 58.4 | **18.6 / 22.4** |
| 500 | 132.5 / 148.1 | 52.9 / 131.7 | 44.6 / 94.2 | **27.9 / 41.7** |

**The knee** (p95 under 10 s) moves from about 25 users (1 × 1) to **about 200 users** (1 × 6). Up to 100 users, 1 × 6 answers as fast as with no load at all.

## Stress and recovery

| setup | 100 users: answers/s, p50 / p95 | 1000 users: answers/s, p50 / p95 | back to 20 users: p50 / p95 |
|---|---|---|---|
| 1 × 1 | 1.03, 27 s / 43 s | 1.04, 76 s / 111 s | 127 s / 140 s |
| 2 × 1 | 2.05, 17 s / 27 s | 2.07, 55 s / 100 s | 116 s / 136 s |
| 4 × 1 | 3.35, 7 s / 11 s | 4.09, 38 s / 89 s | 108 s / 131 s |
| **1 × 6** | **4.50, 1.0 s / 3.0 s** | **6.11, 40 s / 77 s** | **95 s / 108 s** |

**Failures: 0** in every step of every setup, including 1000 users.

## Cost in memory and CPU

The API container's peak was **141 MB with 6 slots**, against 114 MB with 1 slot: the slots share one pipeline. Four processes would need four pipelines.

## On the real system

A real answer takes about 20 s, almost all of it waiting on Claude.
- With 1 slot, the server finished about 3 answers a minute.
- With 6 slots it finishes about 18: six questions run at once, each in about 20 s.
- The next ceiling is Anthropic's rate limits and the spend cap, not the server.
- The demo server runs `VQA_ANSWER_SLOTS=6` since 2026-11-23.
