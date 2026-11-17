# Phase 4.7 owner review

## What the free replay establishes

The matrix currently has **700 modelled, 18 to build, 432 not applicable and 8 out** (1,158 cells). Rebuilding the matrix after hand-program replay adds zero structural cells. Against the first committed matrix with the same 1,158-cell layout (`7aaa800`, 536 modelled), the step-1 implementation and classifications add a net 164 modelled cells. The column deltas are identity/meaning/group +3, applicability +79, permission +9, speed +2, lane +5, scope +27, placement +2, conduct +35, compound/explain +1 and counting/presence +1. Other columns have zero net change. These are capability classifications; some changes reclassify previously inapplicable cells. The free replay tests whether those capabilities are exercised on stored scenes.

The ordinary replay preserves all 88 decided answers from baseline `464c1f8`. With the wire programs below it again preserves all 88 (verdict, value and citations). Of 107 total cases, 89 return a decided verdict, but **zero additional matrix cells have a newly verified decision on the cached scenes**.

| Matrix cell or form checked | Cached evidence |
|---|---|
| T8 traffic lights × permitted | The additional yes came from the sign-permission branch alone. The v5 scene had no signals, the answer had no article 6 citation and no light reason. This result cannot establish permission at the light. See the missing-signal issue below. |
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
| `kb/rules/general47.pl:16` | Law 36 art. 14.6 overtaking places, 15.4 U-turn places, 18.4 stop/park places and exceptions, 25.1c emergency-lane entry and 25.2 forced stops, 13.3 rightmost lane for rudimentary vehicles, 27.4 on-duty priority speed exemption. Also review all three Circular 38 speed groups above. |
| `kb/rules/signals47.pl:17` | R.411 lane arrows and permitted/excluded directions (D.13); vehicle lights and directional arrows, priority exemption and yellow at the line (6, Law 36 art. 27.4); crossing centre lines, changing across lane lines and hatched markings (G.1). Review how multiple, missing and side-dependent observations are combined. |

## Existing rows that look wrong

**Generated suite:** two failing cases on one catalog row, P.106b × tractor and P.106b × special machine. The B.6 row restricts the truck load condition through `effect.value.applies_to`. The test had applied it to both other classes. Restricting the oracle to the listed classes and subclasses resolves both cases. All 784 cases pass, zero catalog or rule changes, zero entries in `KNOWN_DIFFERENCES`. This establishes agreement with the tested catalog effects, not a human legal audit.

**Missing-signal issue in the already committed 4.7 path:** QCVN art. 6 makes passage depend on the signal. A question explicitly asking whether one may proceed at a light can return yes from signs alone when the signal is absent from the stored scene. The v12 wire form has no field marking a signal as required and `vqa/reasoning/engine.py:812` checks light rules only if signals are present. The free replay reproduced this. Owner decision needed before changing this committed behaviour; an additive signal-specific claim could preserve previous programs.

## Not built

- Lane-set claims with a set and an any/all or subset relation.
- R.411 applicability by vehicle class. Lane arrows support directions on a specified lane.
- Violations by pictured vehicles against lights or markings.
- Art. 51 marking scope and its interaction with signs under the priority order of art. 4.

## Owner-run paid checks, in order

No paid check was run during this handoff. Run from the repository root on the clean branch. The estimates sum to **$1.19** and the caps to **$1.65**, leaving **$0.35** of the $2.00 budget outside these caps. The comparisons and summaries below are offline. At each `read` prompt paste the exact output file path printed by the preceding run.

### 1. Parser v12 gate — estimate $0.21, cap $0.40

V11 cost $0.186. Use the $0.40 cap for the runner's up-front budget check. Score the one run, compare it to the three v6 runs, and use the stored v11 run to inspect compatibility on previously supported forms. The existing no-regression gate evaluates intent types; a passing aggregate alone cannot establish identical individual parses.

```zsh
.venv/bin/python eval/parser_eval.py run --model claude-sonnet-5-5 --effort medium --version v12 --max-spend 0.40
read -r 'gate_run?Path of completed v12 predictions: '
.venv/bin/python eval/parser_eval.py score "$gate_run"
.venv/bin/python eval/parser_eval.py compare --old \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-140559.jsonl \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141622.jsonl \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v6_20261115-141902.jsonl --new "$gate_run"
.venv/bin/python eval/parser_eval.py compare --old \
  logs/parser_eval/pred_claude-sonnet-5-5_medium_v11_20261117-184930.jsonl --new "$gate_run"
```

For a direct compatibility check, run the following offline after the gate. It compares normalized programs for previously supported gate forms on which v11 returned a program. It also detects missing predictions. Inspect any changed IDs on public_dev before accepting the parser.

```zsh
.venv/bin/python - "$gate_run" <<'PY'
import sys
from pathlib import Path
from eval.parser_eval import canonical, gate_rows, gold_type, load_gold, load_predictions
from vqa.schemas import QueryProgram

old_file = Path("logs/parser_eval/pred_claude-sonnet-5-5_medium_v11_20261117-184930.jsonl")
old = {r["id"]: r for r in load_predictions(old_file)}
new = {r["id"]: r for r in load_predictions(Path(sys.argv[1]))}
gate = gate_rows(load_gold(), "v12")
assert {g["id"] for g in gate} <= new.keys(), "incomplete v12 gate run"
supported = [g["id"] for g in gate if gold_type(g) != "out_of_scope"
             and old.get(g["id"], {}).get("status") == "ok"]
assert supported, "no comparable supported rows"
def program(row):
    return canonical(QueryProgram.model_validate(row["query"])) if row["status"] == "ok" else None
changed = [qid for qid in supported if program(old[qid]) != program(new[qid])]
print({"compared": len(supported), "identical": len(supported) - len(changed), "changed": changed})
PY
```

### 2. Scene v6 set-T check — estimate $0.13, combined cap $0.20

V5 cost $0.055 for pass 1 and $0.059 for the tile/crop pass. Each command creates its own spend guard, hence two $0.10 caps. Score the new fallback result against the existing v5 fallback result. V5 achieved 90.8% recall and 72.9% code F1. The plan keeps v6 when recall holds and code F1 is within the 2.9-point run-to-run spread.

```zsh
.venv/bin/python eval/perception_eval.py run --set T --model claude-haiku-5-5 --version v6 --max-spend 0.10
read -r 'scene_run?Path of completed v6 pass-1 run: '
.venv/bin/python eval/perception_eval.py fallback "$scene_run" --policy crop_always --max-spend 0.10
read -r 'scene_fb?Path of completed v6 fallback run: '
.venv/bin/python eval/perception_eval.py score \
  eval/runs/perception/T_claude-haiku-5-5_v5+fb_3861a1816d1a.jsonl "$scene_fb"
```

### 3. Judged dev — estimate $0.85, cap $1.05

The phase-4.5 candidate measured $0.81. If the gates support proceeding, the command below runs fresh perception with guide reading, parser v12, higher-confidence readings, the writer and dev scoring. Answer-level fallback is off. Verify the candidate settings and prompt IDs in the dev run header. Compare judged overall with 69.0% and accuracy on decided with the 70% guardrail.

```zsh
.venv/bin/python eval/e2e_dev.py run --label phase47 --candidate \
  --scene-version v6 --parser-version v12 --reading-policy higher_confidence --max-spend 1.05
read -r 'dev_run?Path of completed judged dev run: '
.venv/bin/python eval/e2e_dev.py summary "$dev_run"
```
