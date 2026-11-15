# Proposal: scene prompt v3 with reference pictograms (not approved; no code yet)

2026-11-15. Follows the set-T runs (Haiku v1/v2, Sonnet v2). DESIGN.md lists "with vs without reference pictograms" as a planned ablation, and plan item 3 kept pictograms out of v1 until one was approved.

## Why

Most remaining code errors on set T are pictogram confusions that both models make: vehicle-ban pictograms (P.111b ×3, P.125 ×2), turn and U-turn bans (P.123b, P.124c, P.103c), warning triangles (W.207, W.205, W.245a), and expressway boards (IE.466 ×3). The v2 notes named these signs but gained only about 4 points for Haiku. A text name can't show the difference between two pictograms; the official figure can.

## Which rows (41, from the set-T errors of all three runs)

- **Vehicle bans:** P.103a, P.104, P.106a, P.110a, P.111a, P.111b, P.125
- **Turn and U-turn bans:** P.103c, P.123a, P.123b, P.124a, P.124b, P.124c
- **Size limits:** P.117, P.118, P.119
- **Stopping and parking:** P.130, P.131a
- **End signs:** DP.134, R.307, R.404a
- **Lane boards:** P.127b, P.127c, R.415a, I.417(a,b,c)
- **Guide boards:** I.407(a,b,c), I.409, I.414(a,b,c,d), I.415, I.444(…)
- **Expressway:** IE.452, IE.454, IE.464, IE.465, IE.466
- **Warning:** W.203(a,b,c), W.205(a,b,c,d,e), W.207(…), W.233, W.244, W.245a

These rows have 43 figure files in law_db. The figures are picked by caption, as `tools/visual_review_sheet.py` does (tested on R.403a inside D.10).

## The dataset rule this runs into

CLAUDE.md: "Never copy dataset files into the repo." The law_db figures are dataset files (VLSP data agreement). So the figures **cannot be committed under `prompts/`**. Proposed instead:

- `tools/build_scene_pictograms.py --version v3` (an offline tool; tools may read law_db) copies the chosen figures, resized to at most 320 px on the long edge, into `prompts/scene/v3/pictograms/`. **That folder is gitignored.**
- The tool writes `prompts/scene/v3/pictograms.yaml`, which **is committed**. Per row it holds the code, the source article, the figure file name, the caption, and the sha256 of the resized file. That's enough to rebuild the exact files from law_db, and nothing from the dataset is copied.
- The prompt hash covers `pictograms.yaml`, so the hashes pin the images. `prompt.py` refuses to build v3 if a file is missing or its sha256 doesn't match ("run tools/build_scene_pictograms.py").

## How the images reach the model

The API takes only text in `system`, so the pictograms go in the user turn, before the photo:

`[text "Reference figures:", (image, "P.111b Cấm xe ba bánh loại có động cơ") × 43, cache_control on the last figure] [text "The photo:", photo, instruction]`

The system prompt plus the figure blocks form a stable prefix, so the cache read covers them. A cache hit replays as before. The scene cache key already includes the prompt id, and v3's id covers the manifest.

## CLAUDE.md and leakage-guard changes

- **Dataset rules:** add an exception that law_db figures may enter the scene prompt only through `tools/build_scene_pictograms.py`, as resized local copies in a gitignored folder, pinned by a committed sha256 manifest. They are never committed.
- **Leakage guard:** inference still never reads law_db, and the ban on `images.fld` and `law_db` stays. `vqa/perception/prompt.py` reads only `prompts/scene/<version>/`.
- New test: inference code mentions no law_db path, and the v3 builder in `tools/` is the only code that does.
- New test: `prompts/scene/v3/pictograms/` is gitignored, and no image file under `prompts/` is tracked by git.

## Tokens and cost

- 43 figures at 320 px on the long edge come to about 2,500 image tokens (about 620 at 160 px). The small text labels add about 600. All of it sits in the cached prefix.
- **Per image:**
  - **Haiku:** about 3,100 more cache-read tokens per image, at $0.01 per million, which is about $0.00003. One cache write per run costs about $0.0004 more.
  - **Sonnet:** about 3,100 × $0.10 per million, about $0.0003 per image. The cache write costs about $0.008 more per run.
- **A set-T run:** Haiku about $0.05, Sonnet about $0.33 (the runs cost $0.045 and $0.32). The re-run rate may fall if fewer signs come back low.
- **Risk:** small images may be too small to tell some pictograms apart; 320 px is the proposed size. A larger size is a new manifest, and so a new prompt version.

## Tests

- **Manifest:** every listed row has a figure; each sha256 matches the local file; there's no public or private id; captions name the row's code.
- **Prompt:** v3 builds only with all files present; the hash changes when the manifest changes; the system prompt is v2's spec plus one line about the figures.
- **Request:** the figure blocks come before the photo; `cache_control` is on the last figure; the photo is last; the fake-SDK tests from `test_scene_call.py` carry over.
- **Leakage:** the two tests above.
- **The same evaluation:** set T only, Haiku and Sonnet one run each, compared with v2 by `rescore`, with no public_dev run.

## Also in v3 (text, from the set-T runs)

- Gantry signs get `left`, `center` or `right` like any other sign, not `overhead`. Matching can't fix this; see `935df91`.
- A lane board is one sign: don't split a P.127b board into separate P.127 and R.306 discs (Haiku v2, train_6_41).
- Soften v2's "always guess": give a code when the pictogram is clear, otherwise `UNKNOWN` with your look. v2 turned 6 false `UNKNOWN`s into wrong codes.

## What I need from you

1. A yes to the dataset-rule exception above (local copies plus a committed manifest), or a different way to handle it.
2. A yes to the 41 rows and the 320 px size.
3. A yes to the three text changes.
