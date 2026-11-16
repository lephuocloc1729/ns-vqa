# Phase 3 proposal: the two-pass fallback (plan item 7) and checkpoint 2

**Status: approved by the owner on 2026-11-16, with two changes.** The approved design, the changes (tile-sign ranks by option B "shift"; the gate refuses mixed configurations, `6338059`), the ceilings and the (d) policy are recorded in `docs/plans/phase-3.md`, item 7, "Approved design". Where the two differ, that record wins. This file is kept as the proposal text.

Written 2026-11-16, after public_dev checkpoint 1 (`docs/status.md`): Haiku v4 FAIL (mean of 3: recall 79.7%, code F1 68.1%). Sonnet v4 1 run, not decided, indicative FAIL (81.8% / 75.1%).

**Sources.** Every trigger, threshold and crop size below comes from the two set-T runs on the frozen prompt `scene/v4@153536ec5975`: Haiku `4e6780670d2f` and Sonnet `7a4f533fc335` (36 images, 120 readable gold signs). Costs come from the same runs' lines in `logs/api_calls.jsonl`. No public_dev per-image result, image or error was used. Checkpoint-1 aggregates appear only in (c) and (d) as context.

## Set-T facts the design rests on

The current figures (development):

| set T, prompt v4 | readable gold | predicted | found | code TP | recall | code F1 |
|---|---|---|---|---|---|---|
| Haiku | 120 | 104 | 100 | 81 | 83.3% | 72.3% |
| Sonnet | 120 | 112 | 109 | 81 | 90.8% | 69.8% |

Where the errors are:

| | Haiku | Sonnet |
|---|---|---|
| wrong code at `high` / `medium` confidence (out of reach of the crop trigger) | 4 / 1 | 3 / 4 |
| wrong code or `UNKNOWN` at `low` (in reach) | 9 wrong + 5 UNKNOWN = **14** | 10 wrong + 11 UNKNOWN = **21** |
| correct codes at `low` (at risk if a crop overrides them) | 15 | 10 |
| false positives (unmatched predictions), all `low` | 4 | 3 |
| missed signs, never listed by pass 1 | 20 | 11 |
| missed signs on images with ≥ 5 listed signs | **12** (train_1_6, 3_25, 6_38) | **8** (the same three images) |
| missed signs on sparser images | 8 (6_39 ×2, 6_40 ×2, 7_25 ×4) | 3 (5_36, 6_40 ×2) |

Other facts:
- **Confidence separates errors well.** At `high` 39 of 43 Haiku predictions are right (Sonnet 53 of 56). At `low` 15 of 40 are (Sonnet 10 of 41). All `UNKNOWN`s and all false positives are `low`.
- **Box sizes** (short side on the image as sent; boxes come back on 111/111 Haiku and 119/119 Sonnet predictions):

  | | correct codes | wrong codes | `UNKNOWN` |
  |---|---|---|---|
  | median short side | 80–84 px | 50–56 px | 24 px (Haiku), 36 px (Sonnet) |
  | median share of the image | 2.3% | 0.8–1.3% | 0.3–0.4% |

  The smallest `UNKNOWN` boxes are 20 px (train_8_8 P.125, train_7_46 P.103a).
- **The originals hold almost no extra pixels.** Only 3 of the 36 set-T images are shrunk for the scene call (at most 1.95×; median 1.0). So a crop of the original adds detail on those 3 images only. Elsewhere it isolates the sign and upscales it. Upscaling adds no information to a 20 px sign.
- **Dense-scene rule, by how many signs pass 1 listed:**

  | rule | Haiku: images / misses covered (of 20) | Sonnet: images / misses covered (of 11) |
  |---|---|---|
  | ≥ 4 | 11 / 12 | 15 / 8 |
  | ≥ 5 or ≥ 6 | **6 / 12** | **7 / 8** |
  | ≥ 7 | 3 / 10 | 3 / 6 |

  "≥ 5" catches every dense-scene miss at the lowest image count. The sparse-scene misses (train_7_25's four I.407c arrows, 6_39, 6_40, 5_36) are on images with 1–3 listed signs, and no inference-visible signal on set T marks them.
- **Per-call cost on set T** (mean):

  | | scene call | re-run | cache read | output tokens |
  |---|---|---|---|---|
  | Haiku | $0.00087 | $0.00104 | 14.4k tokens | 1,229 (medium effort) |
  | Sonnet | $0.00634 | $0.00628 | 14.4k tokens | 269 |

## (a) The fallback

It runs after pass 1, the existing scene call with its D8 re-run, which is unchanged. It is inference code, using only what pass 1 returned and the image's own pixels. Two parts:

### A1. Region pass (dense scenes): runs first

- **Trigger:** pass 1 listed **≥ 5 signs** (from the table above).
- **Tiles:** a 2 × 2 grid over the **original** image with 20% overlap. Each tile is upscaled so its long edge is at most the scene prep's 1568 px and its area at most about 1.15 MP. This is a new prep rule for tiles only; the scene call's "never upscale" stays.
- **Each tile** gets the same catalog, pictograms and output format as the scene prompt, plus one line saying the image is a part of a larger photo.
- **Merging:**
  - tile boxes are mapped back onto the original;
  - a tile sign whose box overlaps a pass-1 sign (IoU ≥ 0.3, or its centre inside the pass-1 box) is a duplicate and is dropped;
  - duplicates among overlapping tiles are merged the same way;
  - every remaining tile sign is added at confidence `low`;
  - ranks and sides are recomputed from the boxes: rank top-down by box top, side by box centre against the image centre.
- **Why tiles:** box crops can't help here. On set T every missed sign was never listed, so it has no box.

### A2. Box crops (unsure codes): runs second, so it also re-reads the signs A1 added

- **Trigger:** any sign that is `low` or `UNKNOWN` after verification and the re-run. On set T that reaches 14 (Haiku) / 21 (Sonnet) of the code errors and touches 15 / 10 correct codes.
  - Widening it to `medium` adds 1 / 4 errors but 27 / 18 correct codes at risk, so `medium` stays out.
- **Crop:**
  - the pass-1 box on the original, widened by 50% of its width on each side and 50% of its height above;
  - widened by 100% of its height below, so a plate under the sign is in view;
  - at least 128 px on the short side of the original, clipped to the image;
  - upscaled to 384 px on the short side.

  The sizes come from the box table: the wrong or UNKNOWN boxes have a 20–56 px short side, which gives crops of about 128–160 px before the upscale.
- **Each crop is read alone** (plan item 7), with the scene prompt's catalog and pictograms and a short single-sign spec. The reply gives the code or `UNKNOWN`, the confidence, the value and unit, and at most one alternative. Plates, condition groups and lane rows stay as pass 1 read them.
- **Combining the readings (fixed before any result):**
  - pass 1 `UNKNOWN`, crop names a catalog code → the crop's code, kept at `low`;
  - the crop agrees with pass 1's code → keep it, raised to `medium`;
  - the crop agrees with pass 1's alternative → swap the two (the crop's code first, pass 1's as the `AltReading`), kept at `low`;
  - any other disagreement → keep pass 1's code and add the crop's as an `AltReading` (the engine answers `uncertain`); if the crop is `high`, the crop's code goes first instead;
  - crop `UNKNOWN` → no change.
  - **On set T, development:** these rules are checked against the three alternatives "crop always wins", "crop wins at high only" and "never override". Whichever does best is reported with the in-sample warning, and is frozen before checkpoint 2.
- **False positives** aren't handled: the crop never deletes a sign. The 4 / 3 set-T false positives stay.

### Prompts, leakage and code

- **Two new prompt folders:** `prompts/scene/v4-tile/` and `prompts/scene/v4-crop/`. v1–v4 are not touched. They are pinned by sha256 before checkpoint 2.
  - Per CLAUDE.md, new prompt versions need the owner's decision; approving this proposal is that decision for these two folders only.
- **Code:** `vqa/perception/fallback.py`, wired into `perceive`.
  - Its trigger reads only the pass-1 scene (counts, confidences, boxes).
  - The leakage-guard tests are extended: the fallback request depends on image bytes and pass-1 output only, with no scene id or file name.
  - Its cache records hold model output only, keyed by image hash + model + effort + the tile or crop prompt version + the box.
- **Eval:** `perception_eval.py fallback <pass-1 run file>` writes a new run file with the fallback's calls added. The unchanged pass-1 scenes come from the run file, so set-T development pays only for the tile and crop calls.
- **Tests for each rule:** the trigger, the crop geometry, IoU dedup, rank and side recomputation, and each combining case, with hand-made scenes.

## (b) Expected gain on set T, and cost

The bounds are counted from the error table above.

- **Upper bound:**
  - every in-reach code error fixed by crops, no correct code broken;
  - every dense-scene miss found by tiles with the right code, no new false positive.
- **Realistic:**
  - crops fix half the in-reach errors and break 1 correct code;
  - tiles find half the dense-scene misses, two-thirds with the right code, and add 2 false positives.

| set T, development | Haiku recall | Haiku code F1 | Sonnet recall | Sonnet code F1 |
|---|---|---|---|---|
| now (prompt v4, pass 1) | 83.3% | 72.3% | 90.8% | 69.8% |
| crops only, upper bound | 83.3% | 84.8% | 90.8% | 87.9% |
| tiles only, upper bound | 93.3% | 78.8% | 97.5% | 74.2% |
| **both, upper bound** | **93.3%** | **90.7%** | **97.5%** | **91.7%** |
| **both, realistic** | **88.3%** | **78.4%** | **94.2%** | **78.2%** |

- **The realistic figure still fails code F1 ≥ 85% for both models.** It reaches the recall gate for Sonnet only. The errors out of reach stay:
  - confident wrong codes: 5 for Haiku, 7 for Sonnet;
  - sparse-scene misses: 8 / 3;
  - false positives: 4 / 3.
- **Small signs limit the crops.** Most set-T crops add no pixels (see the facts above), and the `UNKNOWN`s are the smallest signs, so the crop half is the most uncertain number in this table.
- **The gains are in-sample.** The triggers are chosen on set T and measured on set T, so set-T gains overstate what public_dev will show. Checkpoint 2 is the out-of-sample measure.
- **Gold:** one known gold dispute affects set T: train_7_25's four arrow boards (gold I.407c, both models I.415; the owner kept I.407c).

**Cost per image** (set-T call costs above):
- crop calls: about 250 input tokens plus the cached prompt, and about 400 output tokens for Haiku (it thinks at medium) or 150 for Sonnet;
- tile calls: priced as a scene call;
- volume on set T: about 1.1 crops per image (40 / 36 Haiku, 41 / 36 Sonnet), and tiles on 6 / 36 and 7 / 36 images (× 4 tiles).

| per image | pass 1 + re-run (now) | tiles | crops | fallback total | all-in |
|---|---|---|---|---|---|
| Haiku | $0.0015 | ~$0.0006 | ~$0.0004 | **~$0.0010** (range $0.0005–0.002) | ~$0.0025 |
| Sonnet | $0.0090–0.0100 | ~$0.0049 | ~$0.0040 | **~$0.0089** (range $0.0045–0.018) | ~$0.019 |

**Development cost on set T:**
- Haiku: about $0.04 per fallback pass over the 36 images;
- Sonnet: about $0.32 per pass;
- proposed: up to 3 Haiku and 2 Sonnet passes, **ceiling $1.00**, each command with `--max-spend` and your go-ahead.

## (c) Checkpoint 2: models, runs, spend

- **Both models, 3 runs each** (3 = gate), with `perception_gate_v2` unchanged.
- **Configuration:** prompt v4 pass 1 plus the frozen fallback (`v4-tile`, `v4-crop`, the combining rule chosen on set T).
- **Pass 1 is reused where it exists.** Then the comparison is paired (the same pass-1 scenes with and without the fallback), and it costs less.
  - **Haiku:** the fallback is applied to the three checkpoint-1 runs (`e0128c462ed3`, `2dd3a6e61573`, `932c3d2b7009`). About 45 × $0.0010 × 3 ≈ **$0.14** (range $0.07–0.27).
  - **Sonnet:** two new pass-1 runs ($0.81, from checkpoint 1's $0.40 per run), then the fallback on all three (45 × $0.0089 × 3 ≈ $1.20). About **$2.0** (range $1.4–3.3).
  - The two new Sonnet pass-1 runs also complete checkpoint 1's Sonnet set. They are reported as "checkpoint 1, Sonnet completed at checkpoint 2", next to the 1-run figure already recorded.
- **Spend ceiling:** $0.35 for Haiku and **$2.60 for Sonnet** (per run `--max-spend 1.0` for pass 1, `--max-spend 0.6` per fallback pass). **$2.95 in all.**
  - Haiku runs first. Sonnet runs whatever Haiku's result, because (d) needs both to choose the phase-4 configuration.
  - Opus stays out (owner's decision).
- **Running total:** phase-3 spend is $1.84 now. With set-T development ($1.00 ceiling) and checkpoint 2 ($2.95 ceiling), the worst case is **$5.79**.

## (d) Pre-committed policy if the gate fails at checkpoint 2

Fixed now, before any checkpoint-2 result.

1. **What is reported** (via `eval/report.py`), labelled "public_dev checkpoint 2 (gate v2, prompt v4 + fallback)":
   - for each model, per run and mean of 3, pass 1 alone and with the fallback;
   - all 45 images and the 17 non-duplicates, with bootstrap CIs;
   - recall, code F1 (row and strict), rule-bearing F1, value accuracy, and the split by gold drafter;
   - trigger rates (images tiled, signs cropped), the share of crop readings that changed a code, and cost;
   - the gate verdict per model. A FAIL is stated as a FAIL. The threshold is never moved, and no other metric is promoted to "the gate" after the result.
2. **The configuration that goes into phase 4:**
   - the cheapest one that passes;
   - if none passes, the one with the highest mean code F1 (the gated metric) on all 45 images;
   - if Haiku is within 2 points of Sonnet on that figure, Haiku (it costs about 8× less).
   - The fallback goes in if it raised that configuration's mean code F1. Otherwise phase 4 uses pass 1 alone.
   - Phase 4 proceeds with the perception gate recorded as failed. Answers that are unknown or uncertain because of an unreadable or disputed sign already go to the answer-level fallback (CLAUDE.md), and perception's effect on answers is measured end to end on public_holdout (aggregate only).
3. **No checkpoint 3 in phase 3.**
   - **Why:** public_dev has 45 images, only 17 non-duplicates. Each further look at it as a gate set makes it a tuning set. Set T is heavily tuned already, so a further round would be tuned on T and checked again on public_dev, which is the loop the checkpoints exist to stop.
   - Any later perception change goes into phase 4 and is judged on the end-to-end pipeline score.
   - **Alternative, if you prefer it:** one checkpoint 3, allowed only for a change designed from a new, unlabelled-until-now train set (T2, chosen by `gold_signs.py select` under the same duplicate rules), and labelled "extra checkpoint". It would need new gold (owner time) and its own approved proposal.

## What you're asked to approve

1. (a) The fallback design: tiles at ≥ 5 listed signs, crops for `low` / `UNKNOWN`, the crop geometry, the combining rule and its set-T comparison, and the two new prompt folders.
2. (b) Set-T development up to **$1.00**.
3. (c) Checkpoint 2: both models × 3, with pass 1 reused, ceiling **$2.95**.
4. (d) The fail policy, including **no checkpoint 3** (or the T2 alternative).
