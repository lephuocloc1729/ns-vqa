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
