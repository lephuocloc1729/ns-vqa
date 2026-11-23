# Plan: several answers at once in one API process (proposal, 2026-11-23)

**Goal:** the API answers several questions at the same time, instead of one at a time per process. Nothing changes in `vqa/`, in the frozen phase52 behaviour, or in what any answer says.

## Why one at a time today

`app/api/runner.py` runs answers on a single worker thread. An answer takes about 20 s, almost all of it waiting on Claude, so the whole server finishes about 3 answers a minute.

The load test of 2026-11-22 (`docs/results/load-test-2026-11-22.md`) found nothing else slow. Up to 1000 users, there were 0 failures, and every endpoint except answering kept p95 at or under 120 ms.

## Thread-safety review of the pipeline (read-only)

What one answer touches, and whether two answers in two threads can share it:

| Shared object | State written during an answer | Safe in threads? |
|---|---|---|
| **Prolog** (janus, one per process) | `clear_scene` then the scene's facts. They are `dynamic`, so global, not `thread_local` (`kb/scene.pl`) | **No.** Needs a lock (test below) |
| `Engine` | `_day_facts`, `_look_note` (per answer); `_parents` (a lazy cache, the same every time) | Yes, inside the same lock |
| `Engine.answer` callers | Only two: the pipeline's own call (`vqa/pipeline.py`) and the parser's dry run (`vqa/parsing/validator.py`) | Both go through `engine.answer`, which the runner already wraps |
| `SpendGuard` | `reserved`, `spent` | Yes: it reserves each call's worst case under a lock, so concurrent answers can't overspend |
| Usage log | appended lines | Yes: `_LOG_LOCK` |
| `SceneCache` | files written to a temporary path, then `os.replace` | Yes. Two answers on the same new photo at once could each pay for perception once; rare |
| `LLMClient.last_usage` | the latest call's token counts | Mostly not needed: successful calls return their own cost and usage. A few error paths read `last_usage`, so under concurrency one failed call's *trace* could show another call's token counts. Spend and cost are unaffected. Left as is (it is in `vqa/`) and documented |
| `ClaudeParser`, `AnswerWriter`, `AnswerFallback` | nothing outside `__init__`; a stream parser is made per call | Yes |
| `writer.on_event`, `fallback.on_event` | one listener per object, set by the API | **No** as the API sets it today: answer A's words could stream to answer B. Fixed in `app/` (below) |
| The runner's `_emit`, `_t0`, `_scale` | one per runner | **No** as written. Fixed in `app/` (below) |

**Test of the lock** (8 threads, 400 answers, 6 hand-made scenes such as a car under P.103a, a truck under P.106a, P.102, and an empty road, each compared with its sequential answer):
- **Without a lock:** 97 of 400 answers differed. For example, under P.102 (no entry) "may a car enter?" came back **yes**.
- **With a lock around `engine.answer`:** 0 of 400 differed, with no errors. janus works when called from 8 threads.

The Prolog step takes milliseconds, so the lock costs almost nothing. The Claude calls, the ~20 s, run in parallel.

## Design (all in `app/api/`)

1. **Answer slots.** `PipelineRunner` gets `VQA_ANSWER_SLOTS` worker threads.
   - The default is 1, so behaviour is unchanged until it is set.
   - One `Pipeline` (one Prolog) is shared, as today.
2. **A Prolog lock** in the runner's existing `engine.answer` wrapper. It covers the pipeline's call and the parser's dry run.
3. **Per-answer context** (emitter, start time, image scale) instead of the runner's single fields:
   - the answer's own thread finds it in a `threading.local`;
   - the writer's and fallback's `on_event` are set once, to a dispatcher that looks the context up;
   - perception runs in a thread the pipeline starts itself, so its events are routed by the image path. Each turn gets its own path, a hard link to the upload, so two questions about the same photo never mix. The scene cache is keyed by the image's content, so caching is unaffected.
4. **Settings and docs:**
   - `VQA_ANSWER_SLOTS` goes in `docker-compose.yml`, `.env.example` and `docs/deploy.md`.
   - Suggested value on the server: **6**. RAM is not a limit, since threads share one pipeline. The limits are Anthropic's rate limits and spend.

## Tests

- **Engine:** the threads test above, as a unit test (with the lock: equal to sequential).
- **Pipeline through the runner** (fake SDK, warmed scene caches, no spend): N concurrent answers on two photos and several questions give the same answers as sequential runs. Each turn's stream holds only its own events: perception signs, parsed program, tokens.
- **API:** two concurrent `/v1/ask/stream` calls each get only their own tokens and answer; the existing tests still pass.
- **Load test** rerun: slots 1 vs 6 (fake pipeline). Expect answers/s to rise about 6×, and p95 to stay low far longer.

## Risks and limits

- **Spend:** concurrent answers each reserve their worst case, so near the cap answers are refused a little earlier. That is conservative and correct.
- **Anthropic rate limits** become the ceiling. With 6 slots, a burst is up to ~18 calls in a few seconds; a throttled call fails like today's errors (the answer shows an error, nothing wrong is said).
- **Not a change to `vqa/`.** The `last_usage` trace detail above stays as is.
