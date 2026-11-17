# Phase 4.7 plan (proposed): coverage round 3

**Status: proposed for the owner's OK (2026-11-17). Nothing is built.** Every figure here is free: it comes from stored runs (dev v11 re-parse `f52e160181ca`, D3 `821164d62679`), the train working set's wording, and `law_db`. No API call was made. Not touched: the validation set (ids only, to leave it out), its sentinels, public_holdout, private, gold, and every `eval/frozen_*.json`.

**Goal (owner, 2026-11-17):** turn out-of-scope groups into scope with rules. `law_db` comes first. Where it has nothing, a rule may come from QCVN 41:2024, Law 36/2024 or Circular 38/2024, marked `law_id: interpretation` with a `basis` note. The owner kept the Decree 168/2024/NĐ-CP line, so fines may be added on the same terms. Road markings, who a sign applies to, and lane sets are back in scope. **Budget: $2.00 new.** There is no final3; the private run measures round 3.

## 0. Main findings

1. **`law_db` already covers almost every group, so very few rules are knowledge-based.**
   - Markings: QCVN 41 art. 48–51 and G.1–G.4.
   - Lights: art. 4, 6, 8.
   - Priority vehicles: art. 7, and Law 36 art. 27.4.
   - Lane use: Law 36 art. 13.
   - Expressways: Law 36 art. 25.
   - Route codes: art. 46 ("Đường cao tốc - CT, Quốc lộ - QL, Đường tỉnh - ĐT, Đường huyện - ĐH").
   - Only two candidate rules have no `law_db` article (KB-9, KB-10 in section 4).
2. **Fines add nothing measurable.** No question in the train working set asks for a fine amount (pattern "mức phạt / tiền phạt / phạt bao nhiêu", 0 hits). The two fine questions (15, 21) ask *which vehicle* is fined, and `explain` already reads that as "which vehicle breaks the rule". I propose no Decree 168 amount rules; section 2 (f) explains why.
3. **"Program can't run" is caused only by selectors.** A free sweep ran all 82 stored ok-programs (dev v11 and D3) on all 60 stored dev scenes, 4,920 runs. It found no engine exception or crash. Every can't-run came from a selector:

   | note | runs | intents |
   |---|---|---|
   | no sign matches the selector | 456 | `meaning` 324, `explain` 56, `multi` 49, `which_vehicles` 27 |
   | expected exactly one sign | 96 | `meaning` 84, `multi` 12 |

   Most of these runs pair a program with another image's scene, so the counts are stress, not errors. The code paths behind them are real, though, and four are bugs or gaps (section 2 (h)).
4. **Dev's 13 undecided, by fix:**
   - 7 are free fixes in the engine or parser: 145, 361, 159, 414, 415, 259, 386;
   - 1 needs lane case analysis: 15;
   - 3 need perception of something new: 451 and 515 (R.411 lane arrows), 341 (a traffic light);
   - 2 have no legally safe fix: 248 and 421 are perception gaps.

## 1. The evidence

**Dev, v11 re-parse, not decided (13 of 87):**

| id | cause today | what the question needs | group | fix |
|---|---|---|---|---|
| 145 | can't run: `meaning` with `category: auxiliary`. `Engine.resolve` drops auxiliary signs, and plates are not signs | the meaning of the "300M" plate under P.128 | h | H1 plate selector |
| 361 | can't run: `side: left` ("chỗ bên trái biển màu xanh"), but the lone I.434a is on the right | the meaning of the only blue sign (a bus stop) | h | H2 position relaxed for value intents |
| 159 | unknown: parsed as `guide destinations`, and no board was read; I.409 is in the scene | the meaning of I.409 (a U-turn place) | i / j | J1 `guide` falls back to the information signs |
| 414 | unknown: two places in one destination string; "mũi tên xiên" parsed as `straight` | the distances to QL.10 and Hải Phòng, and the slanted-arrow destination | j | J2: split destinations, `slight_left` / `slight_right` |
| 415 | unknown: "lối ra tiếp theo" matches no board line | the distance on the IE.454 board marked "LỐI RA / EXIT" (2 km) | j | J3 next exit |
| 259 | out of scope: the meaning of the "CT.01" route plate and its symbol | CT = expressway (art. 46), plus the board's expressway mark | j | J4 `guide` ask `route_meaning` |
| 386 | out of scope: "giao lộ phía trước có gì" | the meaning of W.209 (a junction with traffic lights) | j | J5 parser: what lies ahead, asked as a value, is `meaning` of the warning sign |
| 15 | unknown: the truck's limit depends on the lane, and no lane is given | the truck violates in every lane: lane 1 is R.412b (cars only) at 90; lanes 2–3 are 80 | i | I-1 lane case analysis |
| 451 | unknown: R.411 is `effect_unmodelled`; the board's lane arrows are not read | which lane allows which direction | d | D2 R.411 lane directions (scene v6) |
| 515 | out of scope: R.411 directions for motorbikes, plus a claim | as 451, plus `multi` | d | D2 + parser |
| 341 | out of scope: traffic light | the light's colour | e | E1 lights (scene v6) |
| 248 | unknown: the 40 disc was read as R.306 (a minimum); the board has no arrows for either place | a perception error | i | none safe (section 2 (i)) |
| 421 | unknown: R.415a read at low confidence with no lane rows; the lane count is unknown | a perception gap | i | none safe |

**D3's 17 out-of-scope questions** (train Yes/No working set, parsed with v9; biased):
- 8 board claims: covered by I2 since round 2, except 358 (a lane set);
- what lies ahead 2: 378 (a Y junction) and 389 (a tunnel, covered by I2);
- road markings 2: 94, 113;
- who a sign applies to 2: 312, 256;
- speed range 1: 359 (covered by I4);
- a lane set 1: 433;
- counting signs 1: 332.

So **7 are still out:** 94, 113, 312, 256, 433, 332, 358 (378 stays out; see (j)).

**Train working set, by wording** (train minus the validation set; dev included and marked; read by pattern, never parsed). These counts are biased and indicative only:

| group | ids (dev in bold) | count |
|---|---|---|
| a markings | 94, 113 | 2 |
| b who a sign applies to / except | 13, 50, 158, 169, 213, 256, 312, 469 | 8 (50, 158 and 169 are probably `which_vehicles` already) |
| c counting | 172, 243, 332, 458, 469 | 5 |
| d lane sets / lane directions | 101, 121, 217, 257, 358, 365, 371, 394, 396, 400, **421**, 429, 430, 433, 438, **451**, 460, 461; R.411: 9, 10, 235, **451**, **515** | about 8 new (217, 257, 365, 371 and 461 are probably in scope already) |
| e lights | **341** (282 is a priority vehicle's lights, not a signal) | 1 |
| f fines | **15**, 21: who is fined; none asks an amount | 0 new |
| g driver duties | 5, **216**, **219**, **222**, 242, **337**, 344, 392, 409, 422, **432**, **521** | coverage mostly exists (`meaning aspect conduct`); accuracy is the gap |

## 2. The groups

Each group gives:
- **DSL:** the intent or extension;
- **Rules:** the rules and their sources;
- **Perception:** what perception must supply;
- **Gain:** dev / D3 / train wording.

New knowledge-based rules are collected in section 4.

### (h) "Program can't run": causes and fixes (free)

final2 had 5, against final's 2. Validation causes can't be read, so the causes below come from dev, D3 and the sweep.

- **H1. Plates as a selector target (a bug).**
  - **The bug:** `resolve` drops auxiliary rows, and plates live on `Sign.plates`, so "biển phụ" questions always fail. This hits 145 and D3 183 ("biển nền trắng, viền đen, chữ đen" is a text plate).
  - **DSL:** none. In the engine, `category: auxiliary` (or an S code, or a colour matching a plate's white/black look) resolves to plates. A plate gets its meaning from its `code`, or else from its kind:
    - time → S.508 (F.8);
    - vehicle → S.505a (F.5);
    - lane → S.504 (F.4);
    - distance → S.502 (F.2), or S.501 (F.1);
    - text → S.509;
    - local → the non-standard plate rule.
  - **Ambiguity:** a `distance` plate with no code is S.501 or S.502, and the answer names both. 145 expects S.501, so its grade is probably partial.
  - **Rules:** art. 41 and the F articles, all in `law_db`.
  - **Perception:** none. The plate is already read.
  - **Gain:** dev +1 (145, likely partial), D3 +1 (183).
- **H2. Position words that point beside a sign** ("chỗ bên trái biển ...") **(a gap).**
  - **The rule:** for value intents only (`meaning`, `guide`), when `side` / `position` / `rank_top_down` empty the selection but the rest of the selector matches exactly one sign, that sign is used, and the note says the position was set aside.
  - **Never for claims:** `permitted`, `forbidden`, `speed_ok`, `required`, `is_sign`, `present` and `exists_violation` keep today's behaviour. It is a selection rule, with no legal conclusion.
  - **Gain:** dev +1 (361).
- **H3 (option). `meaning` with `only` over several readable codes.**
  - **Today:** unknown ("expected exactly one sign"). The sweep found 84 runs of this, and it is the likely cause on multi-sign validation images.
  - **The option:** answer for each readable sign, with a note. Natural QA answers then list several signs, so the judge may grade them partial.
  - **Decision O3:** yes, or keep unknown.
  - **Gain:** dev 0 (none of the 13); validation unknown.
- **H4. `multi` / `explain`.**
  - **Today:** a part's selector failure becomes the whole answer's can't-run note. The decided status is right, because every part must decide, but the cause label hides which part failed.
  - **The fix:** name the failing part in the note. It is a diagnostic only, with no coverage change.
- **H5. A regression test.**
  - The sweep becomes a free check (`eval/phase47_analysis.py sweep`, on stored runs only): no engine exception on any stored program × scene.
  - It also reports the can't-run counts before and after H1–H3.

### (i) "Unknown" from missing facts: which facts, and safe defaults

The rule: a default goes in `defaults_applied` only when every value it could stand for gives the same verdict, or when the law itself fixes it. Otherwise the answer stays unknown.

| dev | missing fact | safe default? | what to do |
|---|---|---|---|
| 15 | the truck's lane | **No default is needed: case analysis.** | **I-1:** for `exists_violation` and for `explain` / `choose` over "bị phạt / vi phạm", the engine tries every lane of the scene. The claim is decided when every lane gives the same verdict, as KB-6 already does for speed claims, and lane reservations count as violations. Here: lane 1 is R.412b, where trucks may not enter (Law 36 art. 13.4: "người điều khiển loại phương tiện khác không được đi vào làn đường đó"; R.412's own article); lanes 2–3 limit trucks to 80 < 85. So "truck violates" holds in every lane. The proof lists one reason per lane. Gain +1 (15). It also helps 383 and 347 in train (wording). |
| 159 | none: the parser chose `guide` | — | **J1** (section (j)) |
| 414, 415 | none: matching | — | **J2, J3** |
| 248 | the disc's real code (P.127 read as R.306) and the board's arrows | **None.** Reading R.306 as P.127 is a guess, and the board shows no arrow for either place. | stays unknown |
| 421 | the lane count, and the R.415a rows | **None.** KB-5 needs the board's rows, which weren't read, so a lane count would be a guess. | stays unknown (a perception item, not a rule) |
| 451 | R.411's lane arrows | none: they must be read | **D2** |

The time of day, the date and the vehicle's weight are not missing in any of dev's 7, so no new time or weight default is proposed.

### (j) Other groups found

- **J1. `guide` with no board read, but an information sign present** (159).
  - The answer comes from the meaning of the I / IE signs in the scene: I.409, E.9 "vị trí được phép quay đầu xe".
  - Selection only; the citation is the sign's own article. Dev +1.
- **J2. Guide matching** (414).
  - The parser (v12) splits "A và B" into one `guide` part per place.
  - `GuideDirection` gains `slight_left` and `slight_right`, which the board data already holds ("mũi tên xiên").
  - Dev +1, possibly partial.
- **J3. "Lối ra tiếp theo" / "lối ra phía trước"** (415).
  - It matches a board whose text has "LỐI RA" or "EXIT", or an IE.454 sign (`law_db` P.5: "Biển chỉ dẫn khoảng cách đến lối ra phía trước"), and the answer is that board's distance.
  - Dev +1.
- **J4. A route plate's meaning** (259).
  - New `guide` ask `route_meaning`: the prefix of the board's `route` maps to its road kind, from art. 46 (quoted in a YAML comment): CT expressway, QL national road, ĐT provincial road, ĐH district road. The board's "EXPRESSWAY" text and IE codes support it (art. 45).
  - Dev +1.
- **J5. What lies ahead, asked as a value** (386: "giao lộ phía trước có gì").
  - The parser (v12) maps it to `meaning` of the warning sign. W.209 is C.9 "Giao nhau có tín hiệu đèn".
  - The 378 Y junction stays out: W.205's family code doesn't say the shape.
  - Dev +1.
- **J6. Priority vehicles over the speed limit** (282, train).
  - Law 36 art. 27.4: "Xe ưu tiên ... không bị hạn chế tốc độ" for points a–d of clause 2, with their signals on.
  - Check first whether the engine already applies it to `speed_ok`. If not, it is a rule citing art. 27.4, used only when the question states the vehicle is on duty with its signals (`priority: true`). Train +1.
- **J7. Expressway emergency lane** (347, 383, 394, train).
  - Law 36 art. 25.1 c ("Không được cho xe chạy ở làn dừng xe khẩn cấp và phần lề đường") and 25.2 (stopping only for breakdown or force majeure).
  - Perception doesn't mark an emergency lane, so a question needs the lane named. The claims "chạy / dừng ở làn khẩn cấp" become `permitted` with action `driving` / `stop` and a new `QuestionLane` value `emergency`.
  - Train about +2; dev 0.

### (a) Road markings: vạch liền / vạch đứt / đè vạch / chuyển làn

- **DSL:**
  - new actions `cross_line` ("đè vạch", "lấn làn") and `change_lane` ("chuyển làn");
  - a claim `marking_is` for "vạch ... có dùng để ... không" (94);
  - `meaning` with a `marking` selector ("vạch liền trong ảnh").
  - `permitted` checks the markings next to the lane.
- **Rules (all `law_db`; the wording goes in YAML comments):**
  - G.1, 1.1–1.4 (centre lines): 1.1 "Xe được phép cắt qua"; 1.2 and 1.3 "xe không được lấn làn, không được đè lên vạch"; 1.4 by side;
  - G.1, 2.1–2.4 (same-direction lane lines): 2.1 "được phép thực hiện việc chuyển làn"; 2.2 "không cho phép xe chuyển làn ... không được đè lên vạch"; 2.3 a reserved lane; 2.4 by side;
  - 3.1 edge line;
  - 4.1–4.4 (channelising and hatched areas);
  - 6.1 and 6.2 (no parking, no stopping);
  - G.4 9.1 (no U-turn) and 9.2 (bus stop: "Các loại phương tiện khác ... không được dừng, đỗ trong phạm vi kẻ vạch và trong khoảng cách 15 m");
  - art. 51 and art. 4: a sign takes precedence over a marking (4.1.3 before 4.1.4).
  - Law 36 art. 13.2 (change lanes only where allowed, one lane at a time).
- **Perception:** a scene change (v6). `road.markings: [{kind: center | lane_line | edge | stop_line | hatched | no_parking | no_stopping | arrow, pattern: solid | dashed | double_solid | solid_dashed, colour: white | yellow, between_lanes: [i, i+1] | null, confidence}]`. Uncertain markings give unknown.
- **Gain:** dev 0, D3 +2 (94, 113), train wording 2. **Cost: high** (a scene prompt change, a set-T check, and a dev re-perception to measure it).

### (b) Who a sign applies to, and "every vehicle except X"

- **DSL:**
  - **`applies_to` claim:** "biển này áp dụng cho cả xe cơ giới lẫn xe thô sơ, đúng không?" (312). It holds when the sign's effect covers every named class.
  - **`every_vehicle` gains `except: [VehicleSpec]`** (256: "xe nào ngoài xe tải cũng được chạy tối đa 40", answer false). It quantifies over every class minus the named ones, with the same member rule as `every_vehicle`.
  - **`which_vehicles` gains `status: covered`:** the classes a sign's effect names, for "biển ... áp dụng cho những loại xe nào" (13, 50, 158). It does not depend on an action.
- **Rules:**
  - the sign's own article: B.1 "các loại xe" (P.102), B.38 (P.128) and the R.303 article;
  - 312's R.303 coverage: Law 36 art. 22.3 and the R.303 row's article;
  - 256: F.5 (S.505a: the plate narrows the sign to the named vehicles);
  - rudimentary classes: Law 36 art. 34.
  - No new law sentence: the engine reads `effective_prohibits` / `limit_applies`, which already exist.
- **Perception:** none.
- **Gain:** dev 0, D3 +2 (312, 256), train about +4 (13, 213, 312, 256; 50, 158 and 169 are probably decided already). **Cost: low.**

### (c) Counting signs by kind

- **DSL:**
  - `count`: a selector (group, shape, colour, code, meaning, "áp dụng cho xe máy") gives the number of signs;
  - `count_is`: the claim form, for 332 ("hai biển cấm và một biển chỉ dẫn"; an `all_of` of `count_is`).
- **Rules:**
  - The group comes from the catalog category (art. 11), or from `visual_category` for unread signs.
  - **Three-valued:** an unread sign that could match makes the count a range. The value is "at least n", and a claim is decided only when the whole range agrees, like F2.
  - Plates are not counted as signs (art. 41: "biển phụ" sits under a main sign).
  - "Áp dụng cho xe máy" (469) counts the signs whose effect covers the class, reusing (b).
- **Perception:** none. Counting accuracy depends on sign recall (90.8% on set T); a missed sign makes the count wrong, not unknown. That is a known accuracy risk.
- **Gain:** dev 0, D3 +1 (332), train about +5 (172, 243, 332, 458, 469). **Cost: low.**

### (d) Which lanes allow a vehicle (lane sets), and R.411 lane directions

- **D1. Lane sets, no scene change.**
  - **DSL:**
    - a lane slot may be a set (`lanes: [1, 2]`) with a quantifier: `any` = "một trong hai làn", `all` = "cả hai làn";
    - a claim `lanes_are` ("ô tô con có phải đi ở một trong hai làn bên trái không": `lanes_for(vehicle) ⊆ {1, 2}`; 433), and `lanes_for` with `speed_kmh` (217, 396, already present).
  - **Rules:**
    - P.127b / P.127c (B.27b / c), R.412 (D.14), R.415a (D.16);
    - Law 36 art. 13.3 (rudimentary vehicles keep to the right lane; motor vehicles go left) and 13.4 (reserved lanes).
  - **Gain:** D3 +1 (433), train about +4 (429, 433, 438, 460; 358 when combined with I2).
  - **Cost: low.**
- **D2. R.411 lane directions (scene v6).**
  - **DSL:** none new. `permitted` with `go_straight` / `turn_left` / `turn_right` / `u_turn` and a lane; `lanes_for` with an action.
  - **Engine:** R.411 leaves `effect_unmodelled`.
  - **Rules:** D.13 (R.411 "Hướng đi trên mỗi làn đường phải theo"; the exact wording goes in YAML). A turn-left arrow also allows a U-turn unless P.124 is there; art. 6.2.2 says this for lights, and for R.411 the D.13 text is to be checked before any such rule is written. If D.13 doesn't say it, U-turns under R.411 stay unknown.
  - **Perception:** `LaneSpec.directions: [straight | left | right | u_turn | slight_left | slight_right]` per lane on R.411 boards, plus vehicles per lane where the board shows them (515). This is a scene prompt change.
  - **Gain:** dev +2 (451, 515), train about +3 (9, 10, 235).
  - **Cost: high**, shared with (a) and (e) if they ride in the same v6.

### (e) Traffic lights

- **DSL:**
  - a new action `proceed`, with "đèn" in `permitted` ("gặp đèn ... có được đi tiếp không");
  - `meaning` with a `signal` selector.
- **Rules (`law_db`, quoted in YAML):**
  - art. 6.3.1 green "được đi";
  - 6.3.2 yellow: stop before the line, unless already on or past it. That position is a missing fact, so the answer is unknown unless the question gives it;
  - 6.3.3 red "cấm đi";
  - 6.4 arrow lights; 6.2.2 a left arrow allows a U-turn unless P.124;
  - 6.2.4 a red cross;
  - art. 4: lights rank above signs and markings;
  - Law 36 art. 27.4: priority vehicles may go regardless of lights.
- **Perception:** a scene change (v6). `signals: [{kind: vehicle | pedestrian, colour: red | yellow | green | off, arrow: none | left | straight | right, flashing, countdown, confidence}]`.
- **Gain:** dev +1 (341), train 0 more. **Cost: high** (as (a)).

### (f) Fines (Decree 168/2024 kept by the owner)

- **What the questions ask:** "xe nào bị phạt" (15, 21), never an amount. `explain` already maps it to "which vehicle breaks the rule". I-1 decides 15.
- **What Decree 168 would add:** amounts and point deductions, which no question asks for. Writing them as knowledge-based rules means quoting clauses that aren't in `law_db` and can't be checked against it. Every row would be an unreviewed figure for the owner.
- **Proposal:** no amount rules. Only **KB-9** (section 4): "bị phạt" is read as "commits a violation of a rule the engine models", with Decree 168 as the basis. It is shown in proofs and never counted as a law citation.
- **Decision O2:** this, or amounts for the few sign violations in the catalog.
- **Gain:** 0 beyond I-1.

### (g) Driver duties, by extending conduct

- **Today:** `meaning aspect: conduct` covers the F5 warnings, I.423 and IE.471. The dev duty questions (216, 219, 222, 337, 432, 521) are all decided, so the gap is accuracy (521 and 351 are wrong), not coverage.
- **Extensions (all `law_db`):**
  - R.122 STOP: D.1, "dừng lại", which covers priority vehicles too (337: the D.1 text is to be quoted);
  - R.303: go around the island (Law 36 art. 22.3; 422);
  - R.301 family: the arrow's direction (D.1a; 5, 125);
  - I.407: keep the one-way direction (E.7);
  - P.127: keep under the limit, which answers 242 ("giảm xuống mức nào", a `speed_limit` value);
  - Law 36 art. 12 (speed and distance), 13.2 (lane change), 22 (yielding at junctions; W.205 / W.207, 344).
  - **I.414 / I.415 guide boards:** "đi theo biển chỉ dẫn" (521). There is no conduct row today; art. 35 ("chỉ dẫn hoặc thông báo") gives "follow the indicated direction". The wording is to be checked; if art. 35 doesn't support it, the row is not added.
- **Perception:** none.
- **Gain:** coverage 0 on dev, about +1 in train (242, 344); accuracy +1–2 on dev (521, maybe 222). **Cost: low.**

## 3. Ranking: gain per cost

Gains are counts of questions likely to become decided. Dev is readable and tuned on, so its gains are optimistic. D3 and train are biased. Validation can't be read, and there is no final3.

| rank | item | dev (13) | D3 (17) | train wording | cost | scene change |
|---|---|---|---|---|---|---|
| 1 | **(h) H1–H2, H4–H5** selectors | +2 (145, 361) | +1 (183) | — | engine only, free | no |
| 2 | **(j) J1–J5** guide fallback, splitting, next exit, route meaning, ahead-as-value | +5 (159, 414, 415, 259, 386) | 0 | — | engine + parser v12 lines | no |
| 3 | **(i) I-1** lane case analysis | +1 (15) | 0 | +2 (347, 383) | engine | no |
| 4 | **(c)** counting | 0 | +1 | +5 | engine + DSL + parser | no |
| 5 | **(b)** applies to / except | 0 | +2 | +4 | engine + DSL + parser | no |
| 6 | **(d) D1** lane sets | 0 | +1 | +4 | engine + DSL + parser | no |
| 7 | **(g)** duties | 0 (accuracy +1–2) | 0 | +1–2 | catalog rows + tests | no |
| 8 | **(j) J6–J7** priority speed, emergency lane | 0 | 0 | +3 | engine + parser | no |
| 9 | **(d) D2** R.411 directions | +2 (451, 515) | 0 | +3 | scene v6 + set-T + dev re-perception | **yes** |
| 10 | **(e)** lights | +1 (341) | 0 | 0 | rides on v6 | **yes** |
| 11 | **(a)** markings | 0 | +2 | +2 | rides on v6 | **yes** |
| — | (h) H3 several-sign meaning | 0 | — | — | engine; accuracy risk | no (O3) |
| — | (f) fine amounts | 0 | 0 | 0 | many unreviewable rows | no (O2: not recommended) |

- **Without a scene change (ranks 1–8):** dev +8 of 13, from 74 to about 82 of 87 decided (94%). D3 +6 of 17 (183, 312, 256, 433, 332, plus the 2 marking questions only with v6).
- **With scene v6 (ranks 9–11):** dev +3 more (451, 515, 341), for about 85 of 87.
- **Dev's two left, 248 and 421, need better perception,** not rules.

## 4. New knowledge-based rules, for the owner's review

Every row here is `reviewed_by: assistant` until the owner checks it. It is shown in proofs, never counted as a law citation, and checked against `law_db` for contradiction.

| id | rule | `law_id` / basis | why `law_db` isn't enough |
|---|---|---|---|
| **KB-9** | "Bị phạt / bị xử phạt" in a question means "commits a violation of a rule the engine models"; the answer names the violation, never an amount | `interpretation`; basis: Decree 168/2024/NĐ-CP, believed to be art. 6 (cars) and art. 7 (motorcycles, mopeds), the clauses on not following signs, markings and speed limits. **The article numbers are from memory and must be checked by the owner** | `law_db` has no sanction text |
| **KB-10** (only if art. 35 doesn't say it) | At a direction board (I.414 / I.415), the driver's conduct is "đi theo hướng chỉ dẫn" | `interpretation`; basis: Law 36/2024 art. 11.1 (obey road signs), QCVN 41 art. 35 | art. 35 says what guide signs are for, not what a driver must do |

**Engine policies, not law** (listed so they are seen; no `law_id`):
- **P-1, I-1 lane case analysis:** a claim without a lane is decided when every lane gives the same verdict, and a lane-reservation breach counts as a violation.
- **P-2, H2:** position words are set aside for value intents only when one sign is left.
- **P-3, (c):** a count with a possibly-matching unread sign is a range, and a claim on it is decided only when the whole range agrees.
- **P-4, H1:** a code-less distance plate is read as S.501 or S.502, and both are named.

**Not knowledge-based, because `law_db` has the text:**
- markings (G.1–G.4, art. 48–51, art. 4);
- lights (art. 6, 8, 4);
- lane use (Law 36 art. 13);
- expressway lanes (Law 36 art. 25);
- priority vehicles (Law 36 art. 27.4, QCVN 41 art. 7);
- route codes (art. 46);
- next exit (P.5, IE.454);
- R.411 (D.13), R.122 (D.1), R.303 (Law 36 art. 22.3).

Each rule cites its article and quotes the deciding phrase in a YAML comment. Where the rule effect is in a `.pl` file, the quote goes beside its `rule_source/3` fact.

## 5. Steps

**Guardrail (every step, as in round 2):** a change is kept only if dev overall (non-decided counted wrong) doesn't drop below the last kept figure (69.0%, judged), and dev accuracy on decided stays **≥ 70%**. Free replays are indicative, and their grades are provisional until the judge confirms them.

1. **Engine-only fixes (free):** H1, H2, H4, H5 (the sweep), J1, J3, J4's engine half, I-1. Tests on hand-made scenes modelled on train (145-like plate, 361-like lone sign, 159-like I.409 without board, 415-like exit board, 15-like lanes). Free dev replay with the stored v11 parses. Commit.
2. **DSL, engine, templates for (b), (c), D1, (g), J2, J5–J7 (free).** `vqa/schemas.py`, `wire.py`, validator dry runs, `query.pl` entries, template answers, catalog conduct rows, and one test per rule. If KB-9 / KB-10 are approved: `rule_source` facts with `law_id interpretation` and basis notes. Commit.
3. **Parser v12 (free to build):** v11 plus spec lines for the new forms; the out-of-scope list shrinks to: junction shape, fine amounts, and (until v6) lights, markings and R.411 directions. Few-shots come from the train working set only (exact text; never dev or validation): candidates 256, 312, 332, 433, 172, 469, 13. A free replay with hand-written v12 programs on dev and D3's cached scenes.
4. **Parser gate v12 (paid, the owner runs it):** the same no-regression rule against v6's three runs, with v12's new forms given back as design. **Estimate $0.20, cap $0.40.** If it fails, one fix as v13; after that, stop.
5. **Scene v6 for D2 / (e) / (a) (only if O1 = yes; free to build):**
   - `LaneSpec.directions`, `road.markings` and `signals` in the schema, prompt `scene/v6` (+ tile / crop), facts, rules and tests;
   - the new fields get their own schema version (1.4), as the boards got `GUIDE_SCHEMA_VERSION` 1.3; `SCHEMA_VERSION` stays "1.2" unless the owner says otherwise.
6. **Set-T check of v6 (paid):** v6 pass 1 + fallback against v5 + fallback. It is kept only if code F1 is within Haiku's run-to-run spread (2.9 points) and recall doesn't drop. **Estimate $0.12, cap $0.20.** If it fails, v6 is dropped, and D2, (e) and (a) stay out.
7. **Judged dev run (paid):**
   - **With v6:** fresh perception (v6), parser v12, the judge on every decided answer. **Estimate $0.85 ($0.67–1.10), cap $1.05.**
   - **Without v6:** a dev re-parse with v12 and the judge on changed answers. **Estimate $0.42 ($0.35–0.50), cap $0.50.**
8. **Freeze `phase47`** (a new profile and record, written once; the engine-code hash included). Point `eval/e2e_private.py` at it, with a test. Status entry and doc update (D5's schema write-up, now including round 3). The private run stays the owner's D6.

## 6. Budget ($2.00 new)

| step | without v6 | with v6 |
|---|---|---|
| 4. gate v12 | $0.20 (cap $0.40) | $0.20 (cap $0.40) |
| 6. set-T check | — | $0.12 (cap $0.20) |
| 7. judged dev run | $0.42 (cap $0.50) | $0.85 (cap $1.05) |
| **estimate (caps)** | **$0.62 ($0.90)** | **$1.17 ($1.65)** |
| optional: D3 Yes/No re-parse with v12 (biased; measures (b), (c), D1) | $0.42 (cap $0.55) | does not fit under the caps with v6 ($2.20) |

- Each cap is set when its step runs, so the caps never sum past $2.00.
- **The private run is not in this budget,** as D6 was outside round 2. If the owner means the $2.00 to cover it too, then:
  - the plan is the no-v6 profile;
  - the private run is fallback off, about $1.20 at final2's $0.0082 per question on 146 questions.

## 7. Decisions for the owner

- **O1, scene v6** (R.411 directions, lights, markings):
  - yes: dev +3, D3 +2, about $0.55 more, and a set-T check;
  - or no: ranks 1–8 only.
  - Recommendation: **yes, for R.411 alone if the owner wants to keep the prompt small** (dev +2 of the 3). Lights and markings each have 1–2 questions.
- **O2, fines:** KB-9 only (recommended), or Decree 168 amounts as well.
- **O3, H3:** answer `meaning only` over several signs by listing them all, or keep unknown (recommended: keep unknown; the accuracy risk is unmeasured).
- **O4, KB-9 and KB-10:** approve as drafted, or drop.
- **O5, the optional D3 re-parse** (no-v6 profile only).
- **O6, the budget:** does the $2.00 include the private run?
