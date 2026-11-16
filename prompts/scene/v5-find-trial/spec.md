# Task

You find the road signs and auxiliary plates in one photo from Vietnam, for a later step that reads them up close. You do **not** read or name the signs: give no sign codes, no numbers and no text. You only say where each sign and plate is and what it looks like.

Reply with only one JSON object: no prose before or after it, and no code fence. Leave out fields that don't apply.

# Output

```
{"objects": [ ... ], "road": { ... }, "vehicles": [ ... ]}
```

## objects

One entry per physical sign and one per auxiliary plate, in any order. Fields:

- `type`: the coarse type, from shape and colour only:
  - `red_circle`: a round sign with a red rim or a red face (bans, speed limits, no stopping);
  - `blue_circle`: a round blue sign (mandatory directions, minimum speed);
  - `yellow_triangle`: a triangular warning sign;
  - `red_rect`: a rectangular board with a red background or a red border;
  - `blue_rect`: a rectangular board with a blue background;
  - `green_rect`: a rectangular board with a green background;
  - `white_rect`: a rectangular board with a white or yellow background;
  - `plate`: an auxiliary plate mounted under or beside a sign (times, vehicles, distances, exceptions, local text);
  - `other`: anything else (an octagon, a diamond, a white round end-of-restriction disc, a shape you can't place).
- `shape`: `circle`, `triangle`, `rectangle`, `square`, `octagon`, `diamond`, `other`, as you see it.
- `border`, `background`: `red`, `white`, `blue`, `yellow`, `black`, `green`, `none`, `other`, as you see them.
- `box`: `[x0, y0, x1, y1]`, the object's tight pixel box in the image as you see it. Every object has a box, plates included.
- `rank`: 1 for the highest sign in the photo, 2 for the next, and so on over the whole photo. Plates get no rank.
- `side`: `left`, `right`, `center`, `overhead`, `unknown`. For signs on a gantry or an overhead board, give `left`, `center` or `right` by where the sign sits across the road; use `overhead` only when you can't tell.
- `lane`: only for a sign over one lane (1 = leftmost).

## road

`{"type": "urban|rural|expressway|unknown", "lanes": 3, "intersection_ahead": true}`. Leave out what you can't see.

## vehicles

List a vehicle only when it is clearly doing something a sign could rule on (turning, stopping, parking, overtaking, or driving in a lane that a lane sign covers): `{"class": "...", "lane": 2, "action": "driving|go_straight|turn_left|turn_right|u_turn|overtake|stop|park|crossing_line|unknown", "target": "<class, for overtaking>"}`. Classes: vehicle, motor_vehicle, car, passenger_car, taxi, bus, coach, city_bus, truck, motorbike, motorcycle, moped, sidecar, motor_tricycle, special_machine, tractor, rudimentary, bicycle, cargo_bicycle, cyclo, hand_cart, animal_cart, similar_rudimentary, pedestrian. Otherwise give `[]`.

# What counts as a sign

- **Listed:** every road sign that faces the road the camera is on: prohibitory, mandatory, warning, information and guide signs, lane boards, and auxiliary plates.
- **Left out:** adverts, shop and building signs, street-name plates, house numbers, signs facing away or for another road, traffic lights, road markings, and **standalone local notices** (a text board with no standard sign above it, such as "KHU VỰC CẤM ĐỖ Ô TÔ, XE MÁY", camera or variable-message notices).
- One entry per physical sign: two identical signs on the left and the right are two entries. A lane board is one object. Discs on their own posts or panels are separate objects, even when they stand side by side.
- List every sign you can see, even one too small or blurred to read: the next step decides what it is. Never leave a sign out because you're unsure.
- A plate is its own object of type `plate`, with its own box. A text board directly under a sign and mounted with it is a plate.
