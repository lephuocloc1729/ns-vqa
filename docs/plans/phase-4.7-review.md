# Phase 4.7 owner review

## What the free replay establishes

The matrix currently has **700 modelled, 18 to build, 432 not applicable and 8 out** (1,158 cells). Rebuilding the matrix after hand-program replay adds zero structural cells. Against the first committed matrix with the same 1,158-cell layout (`7aaa800`, 536 modelled), the step-1 implementation and classifications add a net 164 modelled cells. The column deltas are identity/meaning/group +3, applicability +79, permission +9, speed +2, lane +5, scope +27, placement +2, conduct +35, compound/explain +1 and counting/presence +1. Other columns have zero net change. These are capability classifications; some changes reclassify previously inapplicable cells. The free replay tests whether those capabilities are exercised on stored scenes.

The ordinary replay preserves all 88 decided answers from baseline `464c1f8`. With the wire programs below it again preserves all 88 (verdict, value and citations). Of 107 total cases, 88 return a decided verdict after the `at_signal` fix (89 before it), and **zero additional matrix cells have a newly verified decision on the cached scenes**.

| Matrix cell or form checked | Cached evidence |
|---|---|
| T8 traffic lights × permitted | Before the `at_signal` fix the additional yes came from the sign-permission branch alone (no light in the v5 scene). With `at_signal: true` the answer is unknown, as art. 6 requires. See the missing-signal issue below. |
| T9 road markings × identity/meaning and permission | The solid-line separation and centre-line crossing programs validate. Neither D3 image has a cached scene for this replay. |
| R.303 × applicability and compound; counting × presence | The combined roundabout/vehicle-class claim and the two category-count claims validate. Both D3 questions are also v12 examples and neither has a cached scene. They supply no independent accuracy evidence. |
| T6 priority vehicles × speed | The on-duty speed claim validates. Both named vehicles share the priority class. The local program uses 51 as a representative point above 50. Its D3 scene is unavailable. |

One dev program and five D3 programs are saved locally. Old question forms keep their stored parses. Lane-set claims and an unrestricted “every vehicle except trucks” quantifier have no faithful new form. Replay loads every hand program through the wire converter, then executes D3 only where a scene was already cached. No image was relabelled and no fresh perception or parser output was obtained.

```sh
.venv/bin/python eval/phase47_replay.py check --programs \
  dev=eval/runs/phase47/dev_v12_hand.json d3=eval/runs/phase47/d3_v12_hand.json
```

## Interpretations for approval, highest risk first

Only the first row was added in phase 4.7. The remaining entries explain the scope of the contradiction checks. Source keys and basis strings are in `kb/rules/common.pl:35` and `:69`; the load basis is in `kb/sign_catalog.yaml:54`. No Decree 168 amount or interpretation was added.

| Rule | Basis to review | Adjacent corpus text and limits of the check |
|---|---|---|
| **r_c38_outside — highest, new** | Circular 38 art. 7, **from memory**. Divided/undivided defaults by group in km/h: 90/80, 80/70, 70/60. Posted maxima take precedence. | Law 36 art. 12.4 delegates detailed speed rules; QCVN D.18 ends the residential zone and B.27 governs posted maxima. Check the official table, including seat counting, truck mass definition, bus/coach and motorcycle classes and the one-way-road criterion. In particular, `general47.pl:112` assigns every coach to group 2 and uses a gross-mass test for trucks. The corpus does not verify these classifications. |
| r_c38_expressway | Circular 38 art. 9, believed 120 maximum and 60 minimum where no limit is posted. | Law 36 art. 25 governs expressway use; QCVN art. 47.3 describes IE.452 displaying limits, including per-lane limits. Check defaults, exemptions and road-specific minima. |
| r_c38_residential | Circular 38 art. 6, believed 60/50 depending on road division or qualifying one-way lanes. | QCVN D.17–D.18 delimit the zone; Law 36 art. 12.4 delegates speed detail. Verify the vehicle groups and road variants. |
| r_c38_moped | Circular 38 art. 8, believed 40 km/h. | Law 36 art. 34.1 defines a moped using a 50 km/h **design** speed. That classification figure and the operating limit serve different purposes. Check the Circular's scope. |
| r_kb4_expressway_zone | Infer the expressway boundary from IE.451b / IE.452 and IE.453b/c. | QCVN art. 47.2–47.4 and appendices P.2–P.4 distinguish entrance, start, end and advance notice. Law 36 art. 25 supplies zone rules. |
| r_kb2_roundabout | R.303 orders travel around the island and yielding to traffic from the left, while leaving the choice of exit open. | QCVN D.3 and Law 36 art. 22.3. |
| r_kb1_pass_side | R.302 orders passage on the indicated side of the obstacle. | QCVN D.2 describes the obstacle itself. This effect does not determine the next intersection turn. |
| r_load_implies_gross | A stated carried load is a lower bound on gross mass. | QCVN B.15 defines gross mass as vehicle mass plus people, luggage and cargo. The inference preserves strict lower bounds. |
| KB-3, catalog policy | Pure information boards give guidance without adding a ban or compulsory direction. | QCVN arts. 11 and 35 and each row's appendix article. This is `effect.informational`; there is no `r_kb3` source fact. |

`tests/test_phase47_law_consistency.py` enumerates the live Prolog source facts. It checks every ordinary law/article pair and covers all eight interpretation IDs, KB-3 separately, the cited premises, and posted-sign precedence for all four Circular cases. The speed-text audit distinguishes sign design, vehicle design speed, signing/marking thresholds and posted limits (including B.27a's night-sign ceiling) from unposted road defaults. It detects new numeric passages and changes to the 14 reviewed articles containing numeric km/h expressions. These are scoped corpus checks. The Circular's own text is absent, and automated checks cannot establish exhaustive legal equivalence.

## Assistant-reviewed additions awaiting human review

The three YAML files carry file-level `reviewed_by: assistant`. The Prolog files implement companion rules and have no equivalent row field. The source files give the deciding Vietnamese phrase beside each entry.

| File and rows | Effects or duties to check against the article |
|---|---|
| `kb/sign_info_47.yaml:9` scope | DP.134 (B.34), R.404a (D.12), I.401 (39), I.407 (E.7), I.408 (E.8, 10 m before the next junction), general information category (15). |
| `kb/sign_info_47.yaml:35` placement | DP.134 at the end of the speed restriction (B.34); R.404a at the end of the road for cars (D.12). |
| `kb/sign_info_47.yaml:46` conduct | DP.134 (B.34), I.408 (E.8), I.409 (E.9), IE.452 and IE.451b (Law 36 art. 25), P.127b/c (B.27b/c), R.412b/f (D.14), R.415a (D.16), R.411 (D.13), R.420 (D.17), generic informational rows (35). Explicit conduct exclusions are IE.453b/c and R.404a. |
| `kb/general_duties_47.yaml:7` | Speed and distance (12), lane change (13), overtaking (14), turning (15), stopping/parking (18), yielding to a priority vehicle (27), expressway entry/exit/lanes (25), all Law 36. Review the conditions attached to each individual duty. |
| `kb/signals_markings_47.yaml:7` signals | QCVN art. 6: green, yellow, flashing yellow, red, green arrow, red arrow. Check stopping position, priority and arrow direction. |
| Same file, markings and separation | G.1 centre lines 1.1–1.4 (both orientations of the mixed line); same-direction lane lines 2.1, 2.2, 2.4; solid edge line 3.1; hatched 4.1; G.2 stop line 7.1. Centre and lane lines separate opposing and same-direction traffic respectively. |
| `kb/rules/general47.pl:16` | Law 36 art. 14.6 overtaking places, 15.4 U-turn places, 18.4 stop/park places and exceptions, 25.1c emergency-lane entry and 25.2 forced stops, 26.2 tunnel stops and parking (breakdown or force majeure only; added 2026-11-18), 16.2 reversing places (added 2026-11-18; our reading: `curve_limited_view` and `hill_crest_limited_view` count as "nơi tầm nhìn bị che khuất"), 13.3 rightmost lane for rudimentary vehicles, 27.4 on-duty priority speed exemption. Also review all three Circular 38 speed groups above. |
| `kb/rules/signals47.pl:17` | R.411 lane arrows and permitted/excluded directions (D.13); vehicle lights and directional arrows, priority exemption and yellow at the line (6, Law 36 art. 27.4); crossing centre lines, changing across lane lines and hatched markings (G.1). Review how multiple, missing and side-dependent observations are combined. |

## Existing rows that look wrong

**Generated suite:** two failing cases on one catalog row, P.106b × tractor and P.106b × special machine. The B.6 row restricts the truck load condition through `effect.value.applies_to`. The test had applied it to both other classes. Restricting the oracle to the listed classes and subclasses resolves both cases. All 784 cases pass, zero catalog or rule changes, zero entries in `KNOWN_DIFFERENCES`. This establishes agreement with the tested catalog effects, not a human legal audit.

**Missing-signal issue (fixed, owner 2026-11-17, before the v12 gate):** QCVN art. 6 makes passage depend on the signal, but a light question could return yes from the signs alone when perception read no light. `rule_permitted` now has `at_signal`. With it set and no vehicle light read, the answer is unknown, citing art. 6 with the note "the question is about a traffic light, and none was read in the photo". With a light read, the light decides as before. Without the flag, behaviour is unchanged. Parser v12's spec says to set `at_signal: true` for every light question. Hand-program replay: dev 341 is now unknown, not yes, so decided stays 88 of 107, all 88 identical.

## Not built

- **Painted road arrows (G.4 9.3): the next perception field** (owner, 2026-11-18). Three owner-written questions need them (lines 58, 62, 68 of owner_questions.txt); scene v6 reads no arrows on the road surface.

- Lane-set claims with a set and an any/all or subset relation.
- R.411 applicability by vehicle class. Lane arrows support directions on a specified lane.
- Violations by pictured vehicles against lights or markings.
- Art. 51 marking scope and its interaction with signs under the priority order of art. 4.

## Owner-run paid checks, in order (revised 2026-11-17: four checks, caps set as each runs)

Nothing has been spent. Run from the repository root on a clean tree. **Each cap is set when its step
runs, and the four never sum past $2.00:** the judged dev run's cap is what is left, at most $1.05.

| # | check | estimate (range) | cap |
|---|---|---|---|
| 1 | parser v12 no-regression gate (public_dev gold) | $0.21 ($0.19–0.25) | $0.40 (the runner refuses lower) |
| 2 | parser v12 new-types test, deciding groups (6 train + 50 owner-written) | $0.23 ($0.20–0.30) | $0.40 |
| 3 | scene v6 set-T check (sign reading + the v6 fields) | $0.13 ($0.11–0.16) | $0.20 (two $0.10 guards) |
| 4 | judged dev run, scene v6 + parser v12 | $0.85 ($0.67–1.10) | what is left, at most $1.05 |
| | **total** | **$1.42** | at the estimates, $0.58 is left beyond step 4's estimate. All 156 rows (with the 100 smoke-test rows) would be $0.55, cap $0.85, leaving step 4 at most $0.55: not recommended |

### 1. Parser v12 gate

```zsh
.venv/bin/python eval/parser_eval.py run --model claude-sonnet-5-5 --effort medium --version v12 --max-spend 0.40
read -r 'gate_run?Path of completed v12 predictions: '
.venv/bin/python eval/parser_eval.py score "$gate_run"
.venv/bin/python eval/parser_eval.py compare --old \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-140559.jsonl \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141622.jsonl \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141902.jsonl --new "$gate_run"
```

Rule: `regressed_types_without_design` must be empty; v12 forms are given back only on gold out-of-scope rows. If v12 fails, stop: one fix as v13 needs the owner's yes.

### 2. Parser v12 new-types test (separate from the gate)

```zsh
.venv/bin/python eval/parser_newtypes.py estimate
.venv/bin/python eval/parser_newtypes.py run --sources train owner_written --max-spend 0.40
read -r 'nt_run?Path of the new-types predictions: '
.venv/bin/python eval/parser_newtypes.py score "$nt_run"
```

Rules (fixed): per type >= 80% exact programs where it has >= 5 train or >= 3 owner-written questions; only those two groups decide (`decision`, `weaker_intents`). The AI-drafted owner-reviewed and assistant-written rows are smoke tests (left out of this run). Of the 50 owner-written questions, 12 are DSL gaps, reported apart (`gaps`); marking_is keeps 1 expressible owner question, so it is reported, not decided.

### 3. Scene v6 set-T check

Before it: fill `data/annotations/gold_v6_fields/labels_v6_fields.yaml` by hand (36 set-T images; set `checked: true`). Only train_1_6 has an R.411 board in the gold sign labels, so the arrows field is measured on at most one image.

```zsh
.venv/bin/python eval/perception_eval.py run --set T --model claude-haiku-5-5 --version v6 --max-spend 0.10
read -r 'scene_run?Path of the v6 pass-1 run: '
.venv/bin/python eval/perception_eval.py fallback "$scene_run" --policy crop_always --max-spend 0.10
read -r 'scene_fb?Path of the v6 fallback run: '
.venv/bin/python eval/perception_eval.py score eval/runs/perception/T_claude-haiku-5-5_v5+fb_3861a1816d1a.jsonl "$scene_fb"
.venv/bin/python eval/v6_fields.py score "$scene_fb"
```

Rules (fixed): v6 is kept when recall holds and code F1 is within 2.9 points of v5 + fallback (90.8% recall, 72.9% code F1). Each v6 field below 70% precision goes into `kb/v6_fields_47.yaml` `off:`, so its rules give unknown. If v6 fails the sign check, step 4 runs with scene v5.

### 4. Judged dev run

```zsh
.venv/bin/python eval/e2e_dev.py run --label phase47 --candidate \
  --scene-version v6 --parser-version v12 --reading-policy higher_confidence --max-spend <left, at most 1.05>
read -r 'dev_run?Path of the judged dev run: '
.venv/bin/python eval/e2e_dev.py summary "$dev_run"
```

With scene v5 if step 3 failed: `--scene-version v5`. Guardrail: overall >= 69.0% (judged), accuracy on decided >= 70%.
