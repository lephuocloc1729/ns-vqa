# Plan: remove the scene re-run, tested once on public_holdout (paired, aggregate only)

**Status: approved (owner, 2026-11-19)**, with H0 lifted for one paired run and R3's thresholds accepted as written. **Done (2026-11-19):** the paired holdout run `aa10b2294ae7` ($0.548) gave identical figures in both arms, so R3 adopts arm B, and R5's `eval/frozen_phase50.json` is written. See `docs/status.md`, "Re-run removal".

## Why

- **Latency.** On about half of images the re-run is a second full-scene Haiku call (~15 s, ~1,600 output tokens) that waits for pass 1. Dropping it saves about 7 s per image on average. After the parallel calls (`a16d32c`, 32.9 s → 22.7 s on 10 dev questions), the private mix would go to roughly 17–19 s per question.
- **It overlaps the crops.** Both are triggered by a sign that is `low` or `UNKNOWN`, and under `crop_always` the crop's reading wins for those signs. The re-run dates from phase 3, before the crops existed, and has never been measured on top of them.
- **Free evidence so far** (cached dev and dev2, no API call; `docs/status.md`, "Latency: parallel API calls"): the same number of questions is decided (dev 73, dev2 79). Grades are unchanged except dev2 train_142 (graded by hand, −1.0, right partly by luck before). Alternative readings fall by about 40%. Both sets were tuned on, so this is not enough on its own.

## The owner decision this needs first

**H0: lift "public_holdout is never touched again" for one paired run.** The phase-5 plan and `docs/status.md` say the holdout is not touched again, and `eval/holdout_ran.json` marks its one run. This plan asks for **one more run, aggregate only, with its own sentinel**. It measures one perception switch, never a per-question result.
- It spends the holdout's independence a second time. After this run the holdout is no longer clean for any later decision; that is the cost.
- **If H0 is declined:** use the free dev and dev2 results only (R6), or skip the change.

## R1. A switch for the re-run (code, no API call)

- `PipelineConfig.scene_rerun: bool = True`. `Pipeline._perceive` passes it to `perceive(rerun=...)`. With `True` the behaviour is exactly as today.
- The replay paths in `eval/` (`e2e_dev.py` rejudge, `phase48_replay.py`) rebuild from stored scenes, which already include the re-run, so they don't take the switch. The free dev and dev2 check used `perceive(rerun=False)` on the cache directly.
- **Freeze (as built):** `scene_rerun` is added to `LATER_SWITCHES` for every profile, since it came after every record. `POST_FREEZE_SWITCHES` is unchanged, because the phase-4 record lists its excluded switches verbatim.
- **Tests:** with the switch off, no `scene rerun` call is made and a pass-1 record without a re-run reply is enough; with it on, nothing changes (the existing tests).

## R2. The paired holdout runner `eval/e2e_holdout_rerun.py` (code, no API call)

Built on `eval/e2e_holdout.py`, with the same leakage and aggregate-only rules.
- **Guards:**
  - `--confirm` is required;
  - the git tree is clean;
  - the live configuration equals `frozen_phase49.json`, apart from `engine_code` (recorded, since `a16d32c` changed it);
  - the runner's own sentinel `eval/holdout_rerun_ran.json` does not exist, and it is written before the first call;
  - the answer fallback is off (rules only).
- **Paired design**, all in memory, with a fresh temporary scene cache deleted afterwards:
  1. **Perception, arm A** (frozen, with re-run): pass 1, the re-run, tiles, crops and guide boards, cached in the temporary cache.
  2. **Perception, arm B** (no re-run): the same image from the same temporary cache with `rerun=False`. Pass 1, tile and guide replies are reused. Only crops on boxes that exist in arm B alone are new calls, so arm B is not biased by missing crops, as the free dev check was.
  3. **Parser:** once per question (v17). Both arms use the same program.
  4. **Engine:** on both scenes.
  5. **Writer and judge:** once per distinct decided answer. When both arms give the same decided answer, it is written and judged once and counts for both. When they differ, each arm's answer is written and judged.
- **Report (aggregate only; no question id, image id, question text or per-question line, printed or written):** per arm:
  - decided coverage, accuracy on decided, and overall with non-decided counted wrong, each with a 95% CI;
  - the same split by duplicate and non-duplicate image (`eval/report.py`);
  - re-run calls made, their total seconds and their cost;
  - paired counts: answers that changed, net correct (B − A), and McNemar's exact p on correct versus not correct.
- **Tests:** a fake SDK run checks the guards, the sentinel, that both arms share pass 1 and the program, that the report holds no ids, and that the stdout carries a counter only.

## R3. The decision rule, fixed before the run (owner to confirm)

**Adopt the change (arm B) only if, on the holdout:**
- net correct (B − A) ≥ **−1 question**;
- decided count (B) ≥ decided count (A) − **1**;
- and the dev and dev2 results agree (they do: 0 and −1).

**Otherwise keep the re-run.** The rule is applied as written. No threshold is moved after the result is seen, and nothing in the system is tuned on the holdout result.

## R4. Spend estimate (needs the owner's go-ahead before the run)

The holdout has 49 questions on about 45 images. Fresh calls are needed: its only run was phase 4 (scene v4), and no per-question programs were kept.

| Item | Estimate |
|---|---|
| perception, arm A (Haiku: pass 1, re-run, tiles, crops, guide) | ~$0.14 |
| arm B's extra crops | ~$0.01 |
| parser (Sonnet v17), incl. one cold prompt write | ~$0.23 |
| writer (Haiku), ~40 answers + changed ones | ~$0.02 |
| judge (Opus), ~40 answers + changed ones | ~$0.30 |
| **total** | **~$0.70; cap $1.00** |

## R5. If adopted

- **New freeze `phase50`:** phase49 plus `scene_rerun: False`, with the code hash at that commit, in `eval/frozen_phase50.json` (write-once, through `eval/freeze.py`). The private runner requires the `phase49` configuration.
- The default `PipelineConfig.scene_rerun` becomes `False` only through the phase50 profile; older profiles keep `True`.
- `docs/status.md`: the holdout paired figures (aggregate), the decision as applied, and the latency gain on the timing script (10 dev questions, about $0.13, its own go-ahead).

## R6. If H0 is declined

The free dev and dev2 results stand as the only evidence (0 and −1 on 152 decided answers, from tuned sets). The owner may adopt on that basis with the caveat stated in `docs/status.md`, or keep the re-run. No holdout run is made.

## Order

R1 → R2 (tests, no API call) → owner's go-ahead on R4 → the one holdout run → R3 applied → R5 or keep.
