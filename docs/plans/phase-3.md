# Phase 3 plan: perception v1 (approved)

DESIGN.md roadmap phase 3. **Gate:** sign recall ≥ 0.90 and sign-code F1 ≥ 0.85 on public_dev, reported with a 95% CI and split into all images and non-duplicate images. Below that, the two-pass fallback is turned on for the images its trigger selects.

Branch `phase-3`, from `main` at `afe006c` (phase 2 merged). No code has been written. The owner decided D1–D10 on 2026-11-15.

## What phase 3 delivers

- `vqa/perception/`: image prep, the scene call, the wire model, verification, the scene cache, and the fallback if the gate needs it. One entry point: `perceive(image_path) -> PerceptionResult` (scene graph, verification issues, cost, cache hit).
- `prompts/scene/v1/`: the scene prompt, versioned like `prompts/parser/`.
- Gold sign labels (D1): public_dev (the gate set), 30–40 train images for prompt tuning (set T), and private labelled only after the benchmark run, kept local. An annotation guide and tooling in `eval/`.
- `eval/perception_eval.py`: estimate, run, score, with the gate fixed before any result.
- A wider leakage guard.

Not in phase 3: the answer writer, the pipeline (`answer(image, question)`), and passing the scene's sign list to the parser (phase 2 D2). Those are phase 4.

## Facts this plan rests on (measured 2026-11-15, no API calls)

- **Images are small.** After resizing to native size (long edge ≤ 1568 px, about 1.15 MP), train images average about 606 tokens and public_dev images about 535 (width × height / 750). The largest is about 1,533. Only train and public_dev images were measured.
- **public_dev has 45 images (51 questions); 28 of them are also in train,** so only 17 are non-duplicates. public_holdout has 45 images, 25 also in train.
- **The catalog has 219 rows** (70 rule rows, 149 meaning-only rows). A compact listing (code, Vietnamese name, shape, border, background) is about 22,000 characters. The parser's whole prompt, with a 15,000-character catalog table, reads 15,213 tokens from the cache. So the scene prompt should be about 10,000–14,000 tokens; the estimate below uses 12,000.
- **`LLMClient.json_reply` takes a text user turn only.** It needs an image content block for the scene call. Token counting before each call and the spend guard already work.

## Work items

### 0. Catalog review status (before the prompt is frozen)

The owner's check (2026-11-15) shows that almost nothing in the catalog has been checked by a person:

| field | rows | `human` | `assistant` | `none` |
|---|---|---|---|---|
| `visual_reviewed_by` | 219 | 0 | 5 | 214 |
| `reviewed_by`, rule rows (`kb/sign_catalog.yaml`) | 70 | 0 | 0 | 70 |
| `reviewed_by`, meaning rows (`kb/sign_catalog_meaning.yaml`) | 149 | 39 | 0 | 110 |

The five `assistant` rows are W.242(a,b), W.243(a,b,c), IE.451a, IE.471 and IE.473.

Perception uses a row's visuals in three places:
- the scene prompt lists them, so a wrong visual teaches the model a wrong look;
- verification compares a sign's reported look with its row's look and can lower the sign to `low`, which triggers a re-run (items 4 and D8);
- the gold guide tells the labeller to record what is seen, so gold does not depend on the rows.

The prompt is frozen by sha256 once a result exists, and the catalog's hash is part of it, so a later visual fix means a new prompt version and new runs. What the prompt and verification do with unreviewed visuals is **D10** (decided: option (c) with the owner's change). `reviewed_by` (names, letters, citations) matters to the rule engine more than to perception; this plan does not change how it is used.

**Rows to review visually before `prompts/scene/v1` is frozen (D10).** The rows that appear in:
- the set-T gold (known after `gold_signs.py import`; 30–40 images, so perhaps 25–50 rows);
- `tests/fixtures/train_*.json`: 9 rows (P.103a, P.107, P.107a, P.111b, P.111d, P.127, P.127c, P.130, R.412f);
- train question text: 3 rows (P.131a, and R.415a and R.415b from "R.415").

That is 12 rows known now, and about 35–60 once set T is labelled. Rows are **not** chosen from the public_dev gold: look checks would then act on the gate set but not on holdout or private, and the gate would measure a stricter system than the benchmark. A row that appears only in the public_dev gold stays record-only.

**Accepted for v1:** the prompt lists all 219 rows' looks, and about 150–185 of them (219 minus the reviewed rows) stay unreviewed. A visual fix found later means prompt v2 and new runs.

### 1. Annotation guide and gold tooling (no API)

- `docs/gold_signs_guide.md`, the rules a labeller follows:
  - a sign is any QCVN 41 sign or plate facing the camera's road, including guide boards and local plates; adverts, street-name plates and signs facing away are left out;
  - each physical sign is listed once; a plate is listed under the sign above it; a lane board is one sign with lane rows;
  - per sign: code (the variant when visible), value and unit, plates (kind, text verbatim, time windows, vehicles), condition groups, lane rows, shape, border, background, rank top-down, side, and lane for lane boards;
  - `readable: false` for a sign the labeller sees but cannot read (too far, blurred, cut off). These count neither for nor against recall and precision (item 5);
  - vehicles and their actions only on public_dev and set-T images with a violation question (none on private, which is labelled without the questions).
- `eval/gold_signs.py` with `select`, `estimate`, `prefill`, `sheet` and `import`:
  - `prefill` drafts each image's list with Opus 5.5, one call at a time with prompt caching, through the spend guard (the phase-2 gold-intent pattern);
  - `sheet` writes a local HTML review page (the image next to its draft) and one editable YAML file per image;
  - `import` validates every label against the `Sign` schema and the catalog and writes `data/annotations/gold_signs_v1/gold_signs_v1.jsonl` (image ids and labels only).
  - Working files are gitignored. The public_dev and set-T gold is committed; private labels (C2) go to a separate gitignored folder and are never committed.
- **Pre-fill anchoring.** A labeller who corrects drafts tends to keep the drafter's readings. The owner's correction rate is recorded. Each label records the model that drafted it, and a model's gate score is marked as anchored on the images that model drafted (D2).

### 2. Gold labels (owner's work; D1 decided)

- **public_dev** (45 images): the gate set. Labels committed (image ids and labels only).
- **Set T** (30–40 train images): for prompt development. Picked by `gold_signs.py select` from train images that are in no duplicate group with a public_dev image (read from `data/splits/duplicates.json` by the eval tool), spread over rough sign categories. Labels committed.
- **Private** (C2): labelled blind to the questions and answers, only after the benchmark run. Labels are kept local in a gitignored folder and never committed. No vehicles are labelled there, since the violation images can't be told apart without the questions.
- **public_holdout:** not labelled.
- The first 8 public_dev images were pre-filled by Opus 5.5 (prompt p1); the other 73 by Haiku 5.5 (p2, the same prompt text), after the owner's change to D2. The owner then reviews every sign. Each pre-fill shows its cost estimate first and waits for the go-ahead.

### 3. The scene call

- **Image prep** (`vqa/perception/image.py`): apply EXIF orientation, convert to RGB, resize so the long edge is ≤ 1568 px and the area ≤ about 1.15 MP, never upscale. Keep the scale factor so boxes map back onto the original (DESIGN.md, coordinates guide). The image hash is the sha256 of the original file's bytes. The file name is never used.
- **Model:** Haiku 5.5 first (D3), at its default effort.
- **Plain JSON, checked in Python.** No JSON schema is sent.
  - A `code` enum over 219 rows plus the scene's optional fields would meet the same strict-schema limits the parser hit (24 optional and 16 union-typed parameters per request; phase 2 got "The compiled grammar is too large").
  - The reply is one JSON object, bare or in a ```json fence (`parse_json_reply`, already written).
  - `vqa/perception/wire.py` holds flat wire models that convert to `SceneGraph`. Codes, vehicle classes, actions, shapes and colours are checked against the catalog and the enums in `vqa/schemas.py`. Variant codes ("W.207c") are accepted as the catalog resolves them.
  - Malformed JSON or a failed check gets **one retry with the error only**. The rejected reply is not echoed back: that echo is the likely cause of Sonnet's bad_json retries in phase 2. A code still invalid after the retry becomes `UNKNOWN`; the raw reading stays in the cache record, not in the scene graph.
  - A refusal or a reply cut off at `max_tokens` is an error, with no retry (as in the parser).
- **What the model returns per sign:** code or `UNKNOWN`, confidence, value and unit, text, shape, border, background, rank top-down, side, lane, a pixel box (debug and fallback crops), plates, condition groups, lane rows, and at most one alternative reading when it is unsure. Plus road (type, lanes, intersection ahead) and vehicles (class, lane, action, target, confidence). `action: unknown` is allowed.
- **Prompt** (`prompts/scene/v1/`):
  - `spec.md`: the task, the output format, and the rules from the annotation guide (the same definition of a sign that gold uses);
  - `config.yaml`: `max_tokens`, image-prep parameters, and the effort per model;
  - the catalog listing is generated from the catalog at build time (code, Vietnamese name, shape, border, background, whether it carries a value). The catalog's hash goes into the prompt's hash, so a catalog change is a new prompt;
  - no image few-shots in v1. One or two text-only output examples, written from train images, show the format. Never selected per image;
  - reference pictograms from `law_db/images.fld` stay out of v1. They are the ablation DESIGN.md lists, for codes that turn out to be confused;
  - frozen by sha256 in a test once a result exists, like the parser prompts.
- **`vqa/llm/client.py`:** `json_reply` accepts a user turn with content blocks (image plus text). Token counting and the spend guard stay as they are.
- **Scene cache** (`vqa/perception/cache.py`, in `cache/scenes/`):
  - `cache/scenes/` is **not gitignored yet** (`git check-ignore` finds no rule). The item-3 commit adds it to `.gitignore`, before the cache writes anything;
  - key: image sha256 + model id + effort + prompt version (D5). The same commit updates CLAUDE.md's leakage-guard sentence on the cache key;
  - value: model outputs only: raw reply text, the parsed wire object, the re-run's reply if any, usage, cost, request id, time;
  - the scene graph is rebuilt from the cached reply by the current wire and verification code, so a verification change needs no new calls;
  - `--no-cache` for eval runs, so repeated runs are independent calls.

### 4. Verification and the low-confidence re-run (deterministic code)

- **Codes:** not in the catalog → `UNKNOWN` (after the retry above).
- **Values, per row:**
  - speeds from 5 to 120 km/h in steps of 5;
  - weights > 0 and ≤ 60 t; heights and widths > 0 and ≤ 10 m; lengths > 0 and ≤ 30 m;
  - time windows valid HH:MM;
  - a value on a row that takes none is dropped, with an issue;
  - a value-bearing row with no value lowers the sign to `low`.
- **Look vs. catalog:** the reported shape, border and background are compared with the row's visual and the mismatch is recorded as an issue. The reported look is kept, because questions select signs by what they look like. A mismatch also lowers the sign to `low` (and so triggers the re-run) **only on rows with `visual_reviewed_by: human`** (D10). On every other row it is recorded only.
  - *Changed by the owner on 2026-11-15, after the first set-T run:* on a human-reviewed row, a mismatch lowers the sign only when the shape or the background differs. A border-only mismatch (e.g. a white rim) is recorded, not lowered.
- **Plates:** a plate the model did not attach goes to the sign directly above it on the same side.
- **Lane rows:** sorted, numbered 1..n from the left with no gaps, and no more lanes than `road.lanes` when that is known.
- **Ids:** renumbered s1, s2, … top-down; vehicles v1, v2, ….
- **Re-run:** if any sign is `low` or `UNKNOWN`, the call is made once more. The two readings are paired with the same matching used for scoring (item 5).
  - Agreement keeps the sign.
  - Disagreement keeps the first reading and adds the second as an `AltReading`. The engine already answers `uncertain` when alternatives disagree.
  - A sign seen in only one of the two readings is kept at `low`.
- Every issue is returned with the scene, so error analysis can see what verification changed.

### 5. Perception eval and the gate (fixed and committed before any result)

`eval/perception_eval.py` with `estimate`, `run` and `score`.

- **The gate rules are code before they are used.** The D7 rules (thresholds, mean of three runs, matching, `readable: false` handling, row-level code correctness, bootstrap size and seed) go into one constant, `GATE`, in `eval/perception_eval.py`. A test pins its value. Both are committed before the first paid run, and changing them afterwards needs the owner's decision and a new constant name, as with phase 2's three-run rule.
- **Gate set:** the 45 public_dev gold images, minus any image used in the scene prompt (none in v1).
- **Where tuning happens (D1 T).** Prompt changes are made from errors on set T, which may be scored as often as needed. public_dev is scored only at fixed checkpoints, each recorded in `docs/status.md`:
  1. the gate runs of each model on the frozen prompt (item 6);
  2. the re-measurement after the two-pass fallback, if item 7 is needed (its trigger chosen from set-T errors).

  Any other public_dev score needs the owner's go-ahead and is labelled as an extra checkpoint.
- **Matching, per image, one to one.** Gold has no boxes, so pairs are chosen by a fixed score:
  - same catalog row, then same visual category (shape plus border and background group), then the closest rank top-down;
  - *Changed by the owner on 2026-11-15, after the first set-T run and before any public_dev result:* same side comes before closest rank (`perception_gate_v2`). On train_7_23 the model ranked a board first, every rank shifted by one, and rank-first paired the left 100 with the right 80;
  - a pair is allowed only if the code is the same row or the visual category is the same;
  - ties are broken by side, then by order in the list.
- **Sign recall** = matched readable gold signs / readable gold signs. An `UNKNOWN` prediction counts as found.
- **Sign-code F1**, micro over signs:
  - a true positive is a matched pair whose codes resolve to the same catalog row, and to the same variant when both name one;
  - precision is true positives / predictions, not counting predictions matched to `readable: false` gold signs;
  - **standalone local notices** (gold signs with `local_notice`, added 2026-11-15 with the owner's approval, before any result) are handled like `readable: false`: out of both recall and precision, and a prediction matched to one is neither a true nor a false positive. They are counted and reported apart (how many there are, how many the system found), because the engine doesn't model them yet;
  - recall is true positives / readable gold signs.
  - A strict variant-level F1 is reported next to it, not gated.
- **Runs:** the gate is decided on the **mean of three runs** of the same model, effort and prompt, with the range and each run's CI. This is phase 2's rule, set here before any result (D7).
- **Pass:** both point estimates (mean of three) reach their thresholds on all gate images (D7).
- **95% CI:** a bootstrap over images (10,000 resamples, fixed seed), because signs on one image are not independent. Added to `eval/report.py` next to `wilson_ci`.
- **Two scores every time**, via `eval/report.py`: all gate images, and images not in `duplicated_with_train`, with the CI. Only 17 public_dev images are non-duplicates, so that CI will be wide.
- **Reported, not gated:** value accuracy, plate accuracy (kind, times, vehicles), shape / border / background accuracy (the parser's selectors depend on these), rank accuracy, vehicle class and action accuracy where gold has vehicles, the rate of verification issues and re-runs, cost and seconds per image.
- **Unit tests for the matching rule,** with hand-made gold and prediction lists, no images:
  - two signs with the same code on one image (e.g. two P.123a, left and right): each pairs with the one at its rank and side, and a single prediction pairs with only one of them;
  - a plate vs. its main sign: a plate predicted as a separate sign does not match the main sign, and its main sign still counts as found;
  - an `UNKNOWN` prediction: counts for recall, not as a code true positive, and lowers precision;
  - a `readable: false` gold sign: absent from both denominators, and a prediction matched to it is neither a true nor a false positive;
  - plus a variant case (W.207c against W.207b: row-level correct, strict-variant wrong) and a no-pair case (different row and different visual category stay unmatched).
- **Tuning disclosure.** Prompt and trigger changes come from set-T errors, so public_dev checkpoint scores are not tuned figures. Only if the owner later approves a change driven by public_dev errors are later public_dev scores labelled as tuned, as in phase 2.

### 6. Runs and the model choice

1. Haiku 5.5, three runs on the gate set.
   Haiku drafted most of the gold, so Haiku's gate score is reported as **"anchored (Haiku pre-fill)"**, with its score on the Opus-drafted and the Haiku-drafted images shown apart (D2).
2. If Haiku fails: Sonnet 5.5, three runs. Opus 5.5 once, for comparison only, its score marked as anchored on the 8 images Opus drafted (D2).
3. Keep the cheapest model that passes (DESIGN.md). The owner makes the final choice, as in phase 2.

Each step shows its estimate first and waits for the go-ahead.

### 7. Two-pass fallback (only if the gate fails)

- The trigger can use only what inference sees, never which images failed against gold. Candidate signals, chosen from **set-T errors** and then applied to every image:
  - a sign that is still `low` or `UNKNOWN` after the re-run;
  - a lane board or a dense board (more than N signs);
  - a sign box smaller than a set share of the image.
- Pass 1 is the normal scene call (its boxes). Pass 2 crops each triggered sign from the original image, with a margin, and reads it alone with the same catalog prompt (`prompts/scene/v1-crop/`).
- public_dev is re-measured once, at the fallback checkpoint (item 5), with the same gate and matching. No trigger choice is made from public_dev results.

### 8. Leakage guard (written alongside item 3)

Extend `tests/test_leakage_guard.py`:
- add `gold_signs`, `gold_intents`, `public_dev`, `public_holdout` and `images.fld` (pictograms stay out until an approved ablation) to the strings inference code may not mention. The check reads docstrings too, so the docstring of `vqa/parsing/prompt.py`, which says few-shots come from "train and public_dev", gets reworded;
- the cache key is built from image bytes, model id and prompt version only: a test that renaming an image file keeps its key, and that changing any of the three changes it;
- the cache record has model-output fields only: a test against its field list;
- `perceive` never takes a scene id or file name into the call: a test that two copies of one image under different names give the same request;
- the scene prompt files hold no public or private image id, and their examples cite train image ids only (as `tests/test_parser.py` does for few-shots);
- the scene prompt is pinned by sha256 once a result exists.

### 9. Docs

`docs/status.md` after each step with commit hashes. DESIGN.md:
- the plain-JSON scene call;
- the gold-label decision (public_dev, set T, private after the run, no holdout labels);
- **the gate is measured on public_dev, not the whole public test** as roadmap item 3 says now; public_holdout is scored end to end only;
- the gate's matching and CI;
- the model choice.

## Cost estimate (no API calls made)

Assumptions: a 12,000-token system prompt read from the cache, about 700 input tokens per image (image plus text), 800–1,500 output tokens per scene, 45 public_dev images. Prices from `vqa/llm/pricing.py` (as of 2026-11-03). Thinking at higher effort may add output tokens; the band allows for some of that.

| item | model | per image | per run of 45 | three runs |
|---|---|---|---|---|
| scene call | Haiku 5.5 | $0.0006–0.0009 | ~$0.03–0.04 | ~$0.10–0.13 |
| scene call, set T (40 images) | Haiku 5.5 | $0.0006–0.0009 | ~$0.03–0.04 | |
| scene call | Sonnet 5.5 | $0.011–0.018 | ~$0.50–0.80 | ~$1.50–2.40 |
| scene call | Opus 5.5 | $0.021–0.035 | ~$0.95–1.60 | (one run only) |
| low-confidence re-runs | any | +0% to +100% | | |
| gold pre-fill, public_dev | Opus 5.5 | | ~$1.00–1.60 | |
| gold pre-fill, private, 104 images (C2, after the run) | Opus 5.5 | | ~$2.20–3.60 | |
| gold pre-fill, set T, 30–40 train images | Opus 5.5 | | ~$0.70–1.40 | |
| two-pass crops, if needed | Haiku 5.5 | about $0.0005 per crop | | |

- The first call of a run also writes the prompt to the cache: about $0.0015 for Haiku, $0.03 for Sonnet, $0.06 for Opus.
- **Spend guard:** every call is checked at its worst case (whole prompt written to cache plus `max_tokens` = 4096 out): about $0.004 for Haiku, $0.074 for Sonnet, $0.15 for Opus. A Haiku run fits the default $2 limit easily. A Sonnet three-run set or an Opus pre-fill needs `--max-spend 3`, set per command with the owner's go-ahead.
- **Re-runs (D8)** repeat the whole call for an image with any `low` or `UNKNOWN` sign, so they add between 0% (no such image) and 100% (every image) to a run's scene-call cost. The rate depends on how often the model reports `low` and, through D10, on how often look checks lower a sign. The first Haiku run on set T measures it; the estimates for later runs are updated from that figure before they are approved.
- **Likely phase total,** with the re-run share anywhere from 0% to 100%:
  - if Haiku passes: about $2–4 (pre-fill of public_dev and set T, about ten tuning runs on set T, three gate runs);
  - if Sonnet and Opus are needed too: about $5–9, up to about $12 if every image is re-run;
  - plus about $2.2–3.6 for the private pre-fill (C2), at the very end, after the benchmark run.
- **Measured estimate:** with `ANTHROPIC_API_KEY` set, `perception_eval.py estimate --count` uses the free token-counting endpoint for the real prompt and image sizes. Without the key it uses the character and pixel estimates above. Neither sends a message.
- Sequential calls with caching are the default, as in phase 2; the Batch API halves the price but its caching is best effort.


## Decisions

### Decided by the owner (2026-11-15)

- **D1, gold labels:** public **A** (public_dev only) plus **T** (30–40 train images in no duplicate group with public_dev; prompt tuning happens on T; public_dev is scored only at fixed checkpoints). No holdout labels (neither B1 nor B2). Private **C2**: labelled blind to questions and answers after the benchmark run, kept local and gitignored, never committed.
- **D2, pre-fill model:** Opus 5.5 at first. **Changed by the owner on 2026-11-15, after stage 1:** the remaining 73 drafts use Haiku 5.5; the owner reviews every label by hand.
  - The 8 Opus drafts from stage 1 (public_test_2_1, 2_10, 2_11, 2_2, 2_3, 2_4, 2_8, 3_1) stay as they are.
  - Haiku drafts are prompt version p2. The prompt text is the same as p1; the version marks the model change.
  - Consequence: the gold for Haiku-drafted images is anchored to Haiku, the first gate candidate. Haiku's gate score is reported as "anchored (Haiku pre-fill)".
  - Anchoring is labelled per image, by draft model: `import` records each label's `draft_model`, and the gate report splits the anchored images by drafter.
- **D3, first scene model:** Haiku 5.5 at its default effort, as written.
- **D4, output format:** plain JSON checked in Python, no schema, one retry that sends only the error, as written.
- **D5, cache key:** effort joins the key (image sha256 + model id + effort + prompt version). CLAUDE.md's leakage-guard sentence on the cache key is updated in the same commit that implements it.
- **D6, catalog review:** widened by the owner. Only 5 of 219 rows have any visual review (all by the assistant), and no rule row has a `reviewed_by`. Item 0 has the counts; the visual question became D10.
- **D7, gate rules:** as written, committed as code (`GATE` in `eval/perception_eval.py`, pinned by a test) before the first paid run. *Added by the owner on 2026-11-15, before any result:* gold signs marked `local_notice` (standalone local notices) are scored like `readable: false` and reported apart.
- **D8, re-run trigger:** any sign `low` or `UNKNOWN`, as written. Look mismatches lower a sign only on human-reviewed rows (D10).
- **D9, spending:** every paid step shows its estimate and waits for a yes, under the spend guard.
- **D10, visuals that no person has reviewed:** option (c), with the owner's change to which rows are reviewed.
  - Reviewed before `prompts/scene/v1` is frozen: the rows in the set-T gold, in `tests/fixtures/train_*.json` and in train question text (12 known now, about 35–60 after set T). Not the public_dev gold: choosing rows from it would make look checks act on the gate set but not on holdout or private, so the gate would measure a stricter system than the benchmark.
  - On human-reviewed rows a look mismatch lowers the sign to `low` and triggers the re-run. On all other rows, including rows that appear only in the public_dev gold, it is recorded only (b).
  - The prompt lists all 219 looks, about 150–185 of them unreviewed; this is accepted for v1. A visual fix later means prompt v2.
  - Order: gold review of set T, then the visual check of the listed rows (`gold_signs.py import` prints them), then `prompts/scene/v1` is frozen. public_dev gold review can run in parallel; it adds no rows to the list.
