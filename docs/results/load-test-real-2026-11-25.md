# Real end-to-end load run, 2026-11-25 (checklist 3.2, part 3)

The Locust runs (`load-test-2026-11-22.md`, `load-test-slots-2026-11-23.md`) used a fake pipeline, to measure our
own system without Claude calls. This run uses **the real pipeline on the demo server**, with Claude, the rule
engine and the follow-up rewriter. Owner's go-ahead: about $0.70, cap $0.80. **Spent: $0.37.**

## Setup

- **Server:** signcite.xyz (2 vCPU, 4 GB RAM), deployed commit `94e32a4`, phase52 profile, `VQA_ANSWER_SLOTS=10`,
  follow-ups on, **RAG fallback off** (no GPU connected), so undecided questions get the rules' "not decided"
  answer.
- **Client:** `eval/load/real_e2e.py`, run inside the API container against the API directly
  (`http://127.0.0.1:8000`, behind nginx's login), through the streaming endpoint.
- **Users:** each has its own photo: one of the server's 4 uploaded photos with one pixel changed, so its hash is new
  and **the first question really reads it** with the vision model. Each user asks 3 questions in one session:
  1. "Biển báo trong ảnh có ý nghĩa gì?" (the photo is read);
  2. "Xe ô tô có được đi vào đường này không?" (the scene comes from the cache);
  3. "Còn xe máy thì sao?" (a follow-up, rewritten into a complete question).
- **Steps:** 5 users at once, then 10 users at once. Started 2026-11-25 00:31 UTC, outside UAT hours.

## Results

| | 5 users | 10 users |
|---|---|---|
| Questions / answered / errors | 15 / 15 / **0** | 30 / 30 / **0** |
| Wall time | 35.3 s | 45.7 s |
| Answers per minute | 25.5 | 39.4 |
| First question (photo read): p50 / p95 / mean | 21.7 / 23.0 / 20.0 s | 18.1 / 31.6 / 19.6 s |
| Questions 2–3 (cached photo): p50 / p95 / mean | 4.6 / 5.2 / 4.5 s | 4.7 / 5.4 / 4.4 s |
| First stream event, p95 | 2.0 s | 4.7 s |
| Photos read fresh | 5 of 5 | 10 of 10 |
| Follow-ups rewritten | 5 of 5 | 10 of 10 |
| Routes | rules 10, not decided 5 | rules 20, not decided 10 |
| Claude cost | $0.260 | $0.113 |

## What it shows

- **No errors with 10 real users at once.** The 10 answer slots hold: a question on an already-read photo takes
  about 4.5 s whether 5 or 10 users ask together, and a first question about 20 s. That is the same as one user
  alone (16–21 s in the private runs), so the slots add no queueing at this load.
- **The photo read dominates the time** of a first question: about 20 s against 4.5 s for a later question about the
  same photo, which reuses its scene.
- **Under load, the first event comes later** (p95 4.7 s at 10 users). The follow-up rewrite (one Haiku call) runs
  before the turn is created, so the page shows its first stage only after the rewrite. A later change could
  create the turn first; the answer time is unaffected.
- **Cost:** the first step paid the parser's prompt-cache write (about $0.06–0.07 after the server sat idle); the
  second step reused the cache, at about $0.004 per question.
- **One question in three was not decided** (15 of 45): with the RAG off, these get the rules' "not decided"
  answer. With a GPU connected they would go to the RAG, which answers one at a time (about 8.6 s each,
  `rag-concurrency-2026-11-23.md`), so a burst of undecided questions would queue there.

## Not covered

- The RAG fallback under load (it needs a GPU session).
- More than 10 users at once on the real pipeline (the Locust runs cover up to 1,000 users with the fake one).
- The path through nginx and its login, which the Locust runs exercise.
