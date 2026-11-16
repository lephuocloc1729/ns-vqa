# Phase 4.5 option: two-pass perception (find, then read)

**Status: an option for the owner, not approved and not adopted (2026-11-16).** Nothing in `vqa/` or the freeze changes unless the owner approves a change. Everything below comes from the paid trial ($0.113, `docs/status.md`, "Two-pass perception trial") and two free experiments on its stored replies (`eval/two_pass_variants.py`, no API call).

## The candidates

| | what it is | perception cost per image as a real pipeline |
|---|---|---|
| **frozen** | Haiku v4 pass 1, re-run, tiles and crops (`crop_always`, T4) | $0.0028 |
| **trial minus UNKNOWN** | find + read, with crops the read step can't name dropped. As a real pipeline the read step would need a "not a sign" answer (a new prompt, so untested: the experiment drops UNKNOWN after the fact) | $0.0014 (measured trial cost; the extra answer adds a few output tokens) |
| **hybrid** | the frozen scene, plus trial signs with a catalog code whose box overlaps no frozen sign (the tile dedup's test) | $0.0042 (frozen + trial) |

Answer-level cost barely moves: per 153 public_dev question-runs, minus UNKNOWN sends 3 fewer questions to the Sonnet fallback (9 in, 12 out) and the hybrid 2 more, under $0.0002 per question either way.

## Perception (perception_gate_v2; one trial run per set)

Set T is the main evidence (development). public_dev is tuned, and its frozen row here is the mean of the scenes the frozen pipeline runs H1-H3 saw (perception runs `9981d8112688`, `1c9ca7368074`, `b490cd60479f`, rebuilt with T4), so it differs from the checkpoint-2 mean.

| set T (36 images, 120 signs) | recall (95% CI) | code F1 (95% CI) | strict | rule-bearing | non-dup recall / F1 (26 images) |
|---|---|---|---|---|---|
| frozen | 89.2% (81–96) | 73.5% (67–81) | 70.9% | 77.3% | 88.9% / 74.7% |
| trial | **95.8%** (92–100) | 67.1% (59–76) | 67.1% | 78.9% | 94.4% / 68.0% |
| trial minus UNKNOWN | 93.3% (87–99) | **77.4%** (69–86) | 77.4% | 78.9% | 92.2% / 76.5% |
| hybrid | 94.2% (90–98) | 74.7% (68–82) | 72.3% | 76.3% | 94.4% / 75.9% |

| public_dev (45 images, 143 signs; tuned) | recall | code F1 | strict | rule-bearing | non-dup recall / F1 (17 images) |
|---|---|---|---|---|---|
| frozen (H1-H3 mean) | 91.1% (87–97) | 73.3% (67–82) | 72.4% | 74.1% | 87.7% / 75.8% |
| trial | 93.7% (88–100) | 66.7% (61–73) | 65.4% | 75.6% | 100% / 73.0% |
| trial minus UNKNOWN | 88.8% (84–95) | **76.5%** (70–85) | 75.1% | 76.0% | 96.3% / 85.2% |
| hybrid (H1-H3 mean) | 92.8% (88–99) | 73.9% (68–83) | 73.0% | 73.4% | 90.1% / 77.3% |

- **Trial minus UNKNOWN** drops 44 signs on set T: 33 false positives, 7 matched to unreadable gold signs (neutral), and **4 real gold signs lost**. On public_dev it drops 51: 30 false positives, 12 unreadable gold, **9 real signs lost**. Misses rise from 5 to 8 (T) and from 9 to 16 (public_dev); false positives fall from 51 to 16 and from 41 to 7.
- **Hybrid** adds 16 trial signs on set T and 12 per run on public_dev. Misses fall from 13 to 7 (T) and from 12.7 to 10.3; false positives rise from 7 to 16 and from 15 to 23.7.
- **Every gap is one trial run.** Haiku's code F1 varies about 2.9 points between runs. Minus UNKNOWN beats frozen by 3.9 (T) and 3.2 (public_dev): just past that spread, from one run, and from a filter applied after the fact. The hybrid's +1.2 and +0.6 are inside it.

## Answers (engine-only replay, free)

Each scene variant goes through the rule engine with stored programs and the fallback trigger. The engine on the rebuilt frozen scenes reproduces all 153 stored routes and verdicts. Grading is free only where it is exact: unchanged answers keep their stored grade; Yes/No rules answers are graded from the verdict; questions that stay with the fallback keep theirs (an assumption). Everything else is ungraded, given with bounds and an estimate (rules 88.8%, fallback 78.0%, public_dev tuned).

| public_dev, 153 question-runs (H1-H3) | answers changed | to fallback (trigger) | to rules | net correct, graded part | ungraded | net correct: bounds / estimate |
|---|---|---|---|---|---|---|
| trial | 43 | 14 (uncertain 9, unreadable_sign 5) | 9 | −6 (12 graded) | 31 | −29.5 to +1.5 / −3.5 |
| trial minus UNKNOWN | 44 | 9 (uncertain 9) | 12 | **−9** (15 graded) | 29 | **−30.5 to −1.5** / −5.7 |
| hybrid | 4 | 2 (uncertain 1, program_cannot_run 1) | 0 | 0 | 4 | −3 to +1 / +0.3 |

- **Set T has almost no answer evidence:** only 6 train questions on set-T images have a reviewed gold program, and train has no stored parses. On those 6, the hybrid changes nothing; the trial and minus UNKNOWN change 2 answers each (1 to the fallback), both ungraded.
- **public_dev is biased toward the frozen scenes:** the writer, fallback and KB fixes were tuned on errors from these scenes. A different perception is at a disadvantage here, so these answer figures overstate the cost of change. They are still the only answer-level evidence.
- **Minus UNKNOWN loses answers even in its best case** (upper bound −1.5): better code F1 does not carry over, because it changes which code a sign gets on many images (public_dev: 12 codes fixed against 14.3 broken for the trial it is built on), and answers rest on particular signs.

## Recommendation: keep the frozen system

- **Trial minus UNKNOWN** has the best perception scores, but from one run and a filter applied after the run. As a real pipeline it needs a new read prompt ("not a sign") that is untested and may also drop real signs (4 of 120 on set T here). On public_dev it costs answers in every case the bounds allow. Not ready.
- **Hybrid** is the safe one: it raises recall (set T 89.2% → 94.2%) and leaves answers almost untouched (4 of 153 change). But its code F1 gain is inside run-to-run noise, the answer change is about zero, and it costs 50% more per image. No evidence it helps.
- **Frozen** stays: no variant shows an answer-level gain that is evidence, the private run is to measure the frozen system (P11), and changing perception now would need a new freeze with no clean data to check it on.

**If the owner wants to pursue this after the private run** (phase 6, on fresh data): build minus UNKNOWN for real (a read prompt with a "not a sign" answer), run it at least 3 times on set T, and judge it on answers, which needs train parses for set T (about $0.10 of Sonnet parser calls for its 62 questions) so that set T, not tuned public_dev, carries the answer evidence.
