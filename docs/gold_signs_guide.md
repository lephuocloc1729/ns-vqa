# Gold sign labels: the labeller's guide

Phase 3, item 1 (`docs/plans/phase-3.md`). These rules define what a "sign" is for scoring perception. The Opus pre-fill reads this file as its instructions, and the scene prompt (`prompts/scene/v1`) will use the same definition, so gold, pre-fill and system agree on what counts.

## Which images

| set | images | labels | where they go |
|---|---|---|---|
| public_dev | 45 | committed | `data/annotations/gold_signs_v1/gold_signs_v1.jsonl` |
| set T | 30–40 train images, listed in `data/splits/gold_signs_set_t.json` | committed | the same file |
| private | 104, only **after** the benchmark run (D1, C2), without the questions or answers | local only, never committed | `data/annotations/gold_signs_private/` (gitignored) |

public_holdout is never labelled.

## What counts as a sign

- **Listed:** every QCVN 41 sign that faces the road the camera is on: prohibitory, mandatory, warning, information and guide signs, lane boards, and auxiliary plates. Non-standard local plates (for example a red text plate "CẤM ĐỖ XE …") are listed too.
- **Left out:** adverts, shop signs, street-name plates, house numbers, signs facing away from the camera or for another road, traffic lights, and road markings.
- **One entry per physical sign.** Two identical signs on the left and the right are two entries.
- **A plate is not a sign of its own.** It goes under `plates` of the sign directly above it (or the sign it is clearly mounted with).
- **A lane board is one sign** (for example P.127b / P.127c / R.412 / R.415 families) with one `lanes` row per lane, or per lane and vehicle group.
- **A board with several (vehicle, time) pairs** uses condition groups (`rules`), not separate vehicle and time plates.

## Readable or not

- `readable: true` (the default): you can tell the code, and its number or text if it has one.
- `readable: false`: you can see a sign is there but can't read it (too far, blurred, cut off, hidden). Give your best `code` or `UNKNOWN`, and its look if you can see it. These signs count neither for nor against the system's recall and precision.
- A sign you can read only partly (the code is clear, a time plate is not) is `readable: true`; leave out what you can't read and say so in `notes`.

## Fields per sign

Write what you **see**, not what the catalog says the sign should look like.

| field | rule |
|---|---|
| `code` | the catalog code; the variant when it is visible (`W.207c`, `P.127b`), else the family row (`W.207(a,b,c)` or its stem). `UNKNOWN` only with `readable: false`. |
| `readable` | `true` or `false`, as above. |
| `value`, `unit` | the number on the sign and its unit: `km/h`, `t`, `m`, `seats`. Lane boards put speeds in `lanes`, not here. |
| `shape` | circle, triangle, rectangle, square, octagon, diamond, other. |
| `border` | red, white, blue, yellow, black, green, none, other. |
| `background` | the same colours. |
| `position.rank_top_down` | 1 for the highest sign in the image, 2 for the next, and so on over the whole image. |
| `position.side` | left, right, overhead, center, unknown. |
| `position.lane` | only for a sign that covers one lane (1 = leftmost). |
| `position.placement` | only when the image shows it: `before_intersection` or `after_intersection`. |
| `plates` | `kind` (time, vehicle, exception, lane, distance, text, local), `code` if known (`S.508a`), `text` verbatim, and what it says: `time_windows` (`{start: "06:00", end: "22:00"}`), `days` (even, odd), `vehicles`, `lanes`, `distance_m`. A `local` plate always keeps its `text`; only a local plate may have `actions` or `rules`. |
| `rules` | condition groups: `vehicles`, `time_windows`, `days`, `text`. |
| `lanes` | lane-board rows: `lane`, `vehicles`, `max_speed`, `min_speed`. |

Vehicle entries use the classes in `vqa/schemas.py` (`VehicleClass`) with optional conditions, for example `{class: truck, conditions: [{attr: gross_t, op: gt, value: 1.5}]}`. "xe khách" is `coach`; "xe ba bánh" / "xe lam" is `motor_tricycle`.

No pixel boxes: gold is a sign list only (DESIGN.md decisions).

## Vehicles

Only on public_dev and set-T images that have a violation question (`violation_question: true` in the label file). List each visible vehicle: `class`, `lane` if clear, `action` (driving, go_straight, turn_left, turn_right, u_turn, overtake, stop, park, crossing_line, unknown), and `target` for overtaking. Use `unknown` for an action a still image can't show. Private labels have no vehicles, since they are made without the questions.

## Label file

One YAML file per image under the working folder (gitignored), made by `eval/gold_signs.py sheet`:

```yaml
image_id: train_1_3
split: train            # train | public_dev | private
status: todo            # todo -> done when checked; skip to leave the image out
violation_question: false
signs:
  - code: P.107a
    readable: true
    value: 29
    unit: seats
    shape: circle
    border: red
    background: white
    position: {rank_top_down: 1, side: right}
    plates:
      - kind: time
        text: "06:30-08:00 16:30-18:30"
        time_windows: [{start: "06:30", end: "08:00"}, {start: "16:30", end: "18:30"}]
vehicles: []
notes: ""
```

When a pre-fill exists the file starts from it. Check every sign against the image: fix it, delete it, or add what is missing, then set `status: done`. `eval/gold_signs.py import` reads only `done` files, and records how many signs you kept unchanged from the draft (the pre-fill anchoring figure).

## Visual check of catalog rows (D10)

After set T is imported, `import` lists the catalog rows that appear in the set-T gold, in `tests/fixtures/train_*.json` and in train question text. For each, compare the row's `visual` with the signs you labelled, then correct it and set `visual_reviewed_by: human`: rule rows directly in `kb/sign_catalog.yaml`, meaning rows in `tools/draft_catalog_rows.py` (then regenerate). Rows that appear only in the public_dev gold are not on the list and stay record-only.
