# Phase 4.5 stage A: the 80 signs, family templates and knowledge-based rules (proposal)

**Status: proposed for the owner's OK (2026-11-17). Nothing is written to `kb/` yet.** Counts come from `eval/sign_popularity.py` (train only; the validation set's questions excluded; no private or public data).

## 1. The 80 most popular sign codes in train

Sources:
- codes written in train question and answer text (420 questions: train minus the validation set);
- set-T gold labels;
- perception readings of train images in 24 stored runs (one count per image).

A question "touches" a code when its text names it, or its image has it in gold or in a perception reading. 90 codes appear in all; the top 80 are listed.

**Train text almost never names a code:** at most 2 mentions per code, after the owner's rewrite. The ranking rests mostly on gold and perception readings.

**Status of the 80 today:** 38 modelled, 37 meaning-only, 4 effect_unmodelled (R.420, R.302(a,b,c), R.411, R.303), 1 missing (R.415).

| # | code | name | status today | questions touched | text / gold / perception | proposed family |
|---|---|---|---|---|---|---|
| 1 | I.414(a,b,c,d) | Chỉ hướng đường | meaning_only | 30 | 0 / 11 / 14 | F7 guide, no restriction |
| 2 | P.127 | Tốc độ tối đa cho phép | modelled | 27 | 1 / 6 / 17 | — (already modelled; unchanged) |
| 3 | P.130 | Cấm dừng xe và đỗ xe | modelled | 22 | 0 / 6 / 10 | — (already modelled; unchanged) |
| 4 | P.131a | Cấm đỗ xe | modelled | 22 | 1 / 5 / 10 | — (already modelled; unchanged) |
| 5 | P.103a | Cấm xe ô tô | modelled | 16 | 0 / 4 / 4 | — (already modelled; unchanged) |
| 6 | P.124a | Cấm quay đầu xe | modelled | 16 | 0 / 0 / 6 | — (already modelled; unchanged) |
| 7 | P.127c | Biển ghép tốc độ tối đa cho phép theo phương tiện, trên từng làn đường | modelled | 15 | 0 / 3 / 4 | — (already modelled; unchanged) |
| 8 | I.444(a,b,c,d,e,f,g,h,i,j,k,l,m) | Biển báo chỉ dẫn địa điểm | meaning_only | 15 | 0 / 0 / 6 | F7 guide, no restriction |
| 9 | W.245a | Đi chậm | meaning_only | 14 | 0 / 6 / 7 | F5 warning conduct |
| 10 | IE.452 | Chỉ dẫn bắt đầu đường cao tốc | meaning_only | 14 | 0 / 1 / 9 | F4 zone start |
| 11 | P.125 | Cấm vượt | modelled | 14 | 0 / 4 / 5 | — (already modelled; unchanged) |
| 12 | P.102 | Cấm đi ngược chiều | modelled | 13 | 0 / 3 / 7 | — (already modelled; unchanged) |
| 13 | P.111b | Cấm xe ba bánh loại có động cơ | modelled | 13 | 0 / 4 / 3 | — (already modelled; unchanged) |
| 14 | P.123b | Cấm rẽ phải | modelled | 13 | 0 / 3 / 4 | — (already modelled; unchanged) |
| 15 | I.415 | Mũi tên chỉ hướng đi | meaning_only | 13 | 0 / 1 / 5 | F7 guide, no restriction |
| 16 | P.105 | Cấm xe ô tô và xe máy | modelled | 13 | 0 / 0 / 4 | — (already modelled; unchanged) |
| 17 | R.420 | Bắt đầu khu đông dân cư | effect_unmodelled | 12 | 0 / 1 / 6 | F4 zone start |
| 18 | P.104 | Cấm xe máy | modelled | 12 | 0 / 0 / 5 | — (already modelled; unchanged) |
| 19 | P.127b | Biển ghép tốc độ tối đa cho phép trên từng làn đường | modelled | 12 | 0 / 2 / 3 | — (already modelled; unchanged) |
| 20 | P.123a | Cấm rẽ trái | modelled | 12 | 0 / 0 / 3 | — (already modelled; unchanged) |
| 21 | R.306 | Tốc độ tối thiểu cho phép | modelled | 11 | 0 / 4 / 7 | — (already modelled; unchanged) |
| 22 | IE.465 | Chỉ dẫn địa điểm và khoảng cách | meaning_only | 11 | 0 / 2 / 5 | F7 guide, no restriction |
| 23 | P.124b | Cấm ô tô quay đầu xe | modelled | 11 | 0 / 0 / 3 | — (already modelled; unchanged) |
| 24 | W.227 | Công trường | meaning_only | 8 | 0 / 3 / 4 | F5 warning conduct |
| 25 | P.115 | Hạn chế trọng tải toàn bộ xe | modelled | 8 | 0 / 2 / 4 | — (already modelled; unchanged) |
| 26 | R.404a | Hết đoạn đường dành cho xe ô tô | modelled | 8 | 0 / 2 / 1 | — (already modelled; unchanged) |
| 27 | W.203(a,b,c) | Đường bị thu hẹp | meaning_only | 6 | 0 / 4 / 4 | F5 warning conduct |
| 28 | IE.466 | Chỉ dẫn sơ đồ lối ra một chiều tại tất cả các nút giao trên đường cao tốc | meaning_only | 6 | 0 / 3 / 4 | F7 guide, no restriction |
| 29 | P.106a | Cấm xe ô tô tải | modelled | 6 | 0 / 2 / 5 | — (already modelled; unchanged) |
| 30 | P.131c | Cấm đỗ xe ngày chẵn | modelled | 6 | 0 / 2 / 4 | — (already modelled; unchanged) |
| 31 | I.423(a,b) | Vị trí người đi bộ sang ngang | meaning_only | 6 | 0 / 1 / 4 | F5 conduct (information sign) |
| 32 | IE.454 | Chỉ dẫn khoảng cách đến lối ra phía trước | meaning_only | 6 | 0 / 0 / 5 | F7 guide, no restriction |
| 33 | I.409 | Chỗ quay xe | meaning_only | 6 | 0 / 1 / 2 | F6 information that permits / orders |
| 34 | IE.464 | Chỉ dẫn địa điểm và phương hướng | meaning_only | 5 | 0 / 1 / 4 | F7 guide, no restriction |
| 35 | R.302(a,b,c) | Hướng phải đi vòng chướng ngại vật | effect_unmodelled | 5 | 0 / 2 / 3 | F3b pass side |
| 36 | P.107 | Cấm xe ô tô khách và xe ô tô tải | modelled | 5 | 0 / 1 / 3 | — (already modelled; unchanged) |
| 37 | R.415a | Biển gộp làn đường theo phương tiện | modelled | 5 | 0 / 1 / 3 | — (already modelled; unchanged) |
| 38 | I.407(a,b,c) | Đường một chiều | meaning_only | 4 | 0 / 4 / 3 | F6 information that permits / orders |
| 39 | P.106b | Cấm xe ô tô tải có khối lượng chuyên chở lớn hơn giá trị ghi trên biển | modelled | 4 | 0 / 3 / 3 | — (already modelled; unchanged) |
| 40 | R.403a | Đường dành cho xe ô tô | modelled | 4 | 0 / 3 / 3 | — (already modelled; unchanged) |
| 41 | P.110a | Cấm xe đạp | modelled | 4 | 1 / 2 / 2 | — (already modelled; unchanged) |
| 42 | R.411 | Hướng đi trên mỗi làn đường phải theo | effect_unmodelled | 4 | 0 / 2 / 3 | stays effect_unmodelled (lane directions need schema 1.3); returns unknown |
| 43 | W.224 | Đường người đi bộ cắt ngang | meaning_only | 4 | 0 / 1 / 3 | F5 warning conduct |
| 44 | P.101 | Đường cấm | modelled | 4 | 0 / 0 / 3 | — (already modelled; unchanged) |
| 45 | P.103b | Cấm xe ô tô rẽ phải | modelled | 4 | 0 / 0 / 3 | — (already modelled; unchanged) |
| 46 | W.233 | Nguy hiểm khác | meaning_only | 4 | 0 / 0 / 3 | F5 warning conduct |
| 47 | IE.451b | Chỉ dẫn lối vào đường cao tốc | meaning_only | 3 | 0 / 3 / 3 | F4 zone start |
| 48 | P.112 | Cấm người đi bộ | modelled | 3 | 0 / 2 / 2 | — (already modelled; unchanged) |
| 49 | IE.474 | Chỉ dẫn lối ra | meaning_only | 3 | 0 / 0 / 3 | F7 guide, no restriction |
| 50 | P.124c | Cấm rẽ trái và quay đầu xe | modelled | 3 | 0 / 1 / 2 | — (already modelled; unchanged) |
| 51 | P.131b | Cấm đỗ xe ngày lẻ | modelled | 3 | 0 / 1 / 2 | — (already modelled; unchanged) |
| 52 | R.303 | Nơi giao nhau chạy theo vòng xuyến | effect_unmodelled | 3 | 0 / 1 / 2 | F3c roundabout yield |
| 53 | W.207(a,b,c,d,e,f,g,h,i,k,l) | Giao nhau với đường không ưu tiên (đường nhánh) | meaning_only | 3 | 0 / 1 / 2 | F5 warning conduct |
| 54 | I.449 | Biển tên đường | meaning_only | 3 | 0 / 0 / 2 | F7 guide, no restriction |
| 55 | R.412b | Làn đường dành cho xe ô tô con | modelled | 3 | 0 / 0 / 2 | — (already modelled; unchanged) |
| 56 | W.239a | Đường cáp điện ở phía trên | meaning_only | 3 | 0 / 0 / 2 | F5 warning conduct |
| 57 | I.408 | Nơi đỗ xe | meaning_only | 2 | 0 / 1 / 2 | F6 information that permits / orders |
| 58 | W.205(a,b,c,d,e) | Đường giao nhau | meaning_only | 2 | 0 / 1 / 2 | F5 warning conduct |
| 59 | I.419a | Chỉ dẫn địa giới | meaning_only | 2 | 0 / 0 / 2 | F7 guide, no restriction |
| 60 | IE.460 | Chỉ dẫn cột kilômét trên đường cao tốc | meaning_only | 2 | 0 / 0 / 2 | F7 guide, no restriction |
| 61 | IE.464b | Chỉ dẫn hướng ra tại lối ra | meaning_only | 2 | 0 / 0 / 2 | F7 guide, no restriction |
| 62 | IE.467 | Chỉ dẫn vị trí nhập làn | meaning_only | 2 | 0 / 0 / 2 | F7 guide, no restriction |
| 63 | IE.471 | Chỉ dẫn giữ khoảng cách lái xe an toàn | meaning_only | 2 | 0 / 0 / 2 | F5 conduct (information sign) |
| 64 | P.117 | Hạn chế chiều cao | modelled | 2 | 0 / 1 / 1 | — (already modelled; unchanged) |
| 65 | R.415 | (missing) | missing | 2 | 2 / 0 / 0 | F3 lanes: missing row (D.16) |
| 66 | I.401 | Bắt đầu đường ưu tiên | meaning_only | 2 | 0 / 0 / 1 | F6 information that permits / orders |
| 67 | I.417(a,b,c) | Chỉ hướng đường phải đi cho từng loại xe | meaning_only | 2 | 0 / 0 / 1 | F7 guide, no restriction |
| 68 | IE.453b | Chỉ dẫn điểm kết thúc đường cao tốc | meaning_only | 2 | 0 / 0 / 1 | F4 zone end |
| 69 | IE.453c | Hết đường cao tốc | meaning_only | 2 | 0 / 0 / 1 | F4 zone end |
| 70 | P.118 | Hạn chế chiều ngang xe | modelled | 2 | 0 / 0 / 1 | — (already modelled; unchanged) |
| 71 | R.301b | Hướng đi phải theo (chỉ được rẽ phải) | modelled | 2 | 0 / 0 / 1 | — (already modelled; unchanged) |
| 72 | R.412f | Làn đường dành cho xe ô tô | modelled | 2 | 0 / 0 / 1 | — (already modelled; unchanged) |
| 73 | W.209 | Giao nhau có tín hiệu đèn | meaning_only | 2 | 0 / 0 / 1 | F5 warning conduct |
| 74 | W.246(a,b,c) | Chú ý chướng ngại vật | meaning_only | 2 | 0 / 0 / 1 | F5 warning conduct |
| 75 | DP.134 | Hết tốc độ tối đa cho phép | modelled | 1 | 0 / 1 / 1 | — (already modelled; unchanged) |
| 76 | P.103c | Cấm xe ô tô rẽ trái | modelled | 1 | 0 / 1 / 1 | — (already modelled; unchanged) |
| 77 | P.111a | Cấm xe gắn máy | modelled | 1 | 0 / 1 / 1 | — (already modelled; unchanged) |
| 78 | W.201b | Chỗ ngoặt nguy hiểm vòng bên phải | meaning_only | 1 | 0 / 1 / 1 | F5 warning conduct |
| 79 | W.210 | Giao nhau với đường sắt có rào chắn | meaning_only | 1 | 0 / 1 / 1 | F5 warning conduct |
| 80 | I.434a | Bến xe buýt | meaning_only | 1 | 0 / 0 / 1 | F7 guide, no restriction |

**Two codes outside the 80, proposed as additions:** R.122 "Dừng lại" (D.1) and S.501 "Phạm vi tác dụng của biển" (F.1). Neither can reach the top 80: perception can't name a code the catalog doesn't have (STOP signs are read UNKNOWN). The dev analysis found 2 STOP questions and 1 S.501 plate question.

## 2. Family templates

New effect keys are marked **new**. Every rule built on them cites the sign's own article and the law article named here.

| family | applies to (of the 80) | effect | source | what it decides in stage A (no parser change) |
|---|---|---|---|---|
| F1–F2 prohibitory bans, limits, speeds | 38 already modelled (P.1xx, R.306, R.403a, R.404a, R.412, R.415a, DP.134) | unchanged | their own B/D articles | — |
| F3 mandatory lanes | **R.415** (missing row): add R.415(a,b) as one family row, a = lanes by vehicle (as R.415a today), b = end of a lane | `lane_board` (a), `ends` (b) | QCVN 41 D.16 | the code resolves (2 train questions name "R.415") |
| F3b pass side (**new** `pass_side: left / right / either`) | R.302(a,b,c) | vehicles must pass the obstacle on the shown side | D.2: "Biển có hiệu lực bắt buộc các loại xe phải đi vòng chướng ngại vật theo hướng …" | no longer effect_unmodelled: direction and speed claims near R.302 decide (KB-1 below) |
| F3c roundabout (**new** `yield_from: left`) | R.303 | at the roundabout, yield to vehicles coming from the left | Law 36 art. 22.3: "Tại nơi đường giao nhau có báo hiệu đi theo vòng xuyến, phải nhường đường cho xe đi đến từ bên trái"; QCVN 41 art. 32 | no longer effect_unmodelled (KB-2) |
| F4 zones (**new** `zone: {kind: expressway / residential, at: start / end}`) | IE.452, IE.451b (expressway start, entrance); IE.453b, IE.453c (expressway end); R.420 (residential start); R.421 (residential end, not in the 80 but its pair) | expressway: entry banned for four-wheel motor vehicles, motorcycles, mopeds and similar, rudimentary vehicles, pedestrians, and slow special machines; stopping and parking only where permitted. Residential: no horn 22:00–05:00 except priority vehicles | Law 36 art. 25.3, 25.2; art. 21.2; QCVN 41 D.17, D.18, P.3 and the IE rows' own articles | expressway entry and stopping claims decide (dev 81 becomes right); R.420 no longer blocks closed-world claims |
| F5 warning conduct (**new** `conduct: [...]`) | 12 W rows (W.245a, W.227, W.203, W.224, W.233, W.207, W.239a, W.205, W.209, W.246, W.201b, W.210) + I.423, IE.471 | slow down as needed, observe, be ready (all warnings); plus the sign's own wording: W.227 "tốc độ xe chạy phải giảm cho thích hợp"; W.224 and I.423 "giảm tốc độ, nhường ưu tiên cho người đi bộ"; W.245 "giảm tốc độ đi chậm"; IE.471 keep a safe distance | QCVN 41 art. 27 ("phải giảm tốc độ đến mức cần thiết, chú ý quan sát và chuẩn bị sẵn sàng xử lý"); C.27, C.24, C.45, E.23a; Law 36 art. 12.1 (IE.471) | nothing yet: warnings never bear on closed-world claims. Used by stage B's `conduct` intent |
| F6 information that permits or orders (**new** `permits`) | I.409, I.408, I.407(a,b,c), I.401 | I.409: U-turns permitted at this place (E.9 "vị trí được phép quay đầu xe"). I.408: parking permitted (E.8). I.407: only in the arrow's direction, no U-turn back, except priority vehicles (E.7 b). I.401: vehicles on this road go first; side roads stop and yield (E.1) | E.9, E.8, E.7, E.1 | "Được quay đầu / đỗ ở đây không" decide **yes** with a positive citation; I.407 decides U-turn claims **no** |
| F7 guide, no restriction (**new** `informational: true`) | 15 rows: I.414, I.444, I.415, IE.465, IE.466, IE.454, IE.464, I.449, I.419a, IE.460, IE.464b, IE.467, IE.474, I.417, I.434a | carries no ban or obligation, so closed-world claims ignore it (as today, now stated with a citation) | QCVN 41 art. 11 (guide signs "chỉ dẫn hoặc thông báo"); each row's own article | nothing changes (KB-3). Their content (destinations, distances) is stage B rank 9 |
| — R.411 | R.411 | stays effect_unmodelled: lane directions need direction fields on lane rows (scene schema 1.3 + perception) | D.13 | rank-1 fix: no rows → unknown, not "all false" |

## 3. Knowledge-based rules (no `law_db` article says this; for review first)

Each is marked `law_id: interpretation` with a `basis` note, shown in proofs, never counted as a law citation, and checked against `law_db` for contradiction.

| id | rule | basis (believed) | why it's needed |
|---|---|---|---|
| KB-1 | R.302 governs only how to pass the obstacle; it doesn't restrict turns or U-turns at the next intersection | QCVN 41:2024 D.2 (scope of the sign's effect) | otherwise R.302 keeps direction claims unknown |
| KB-2 | R.303 orders only who yields at the roundabout; it doesn't ban an exit or a direction | QCVN 41:2024 art. 32; Law 36/2024 art. 22.3 | otherwise R.303 keeps direction claims unknown |
| KB-3 | guide and information boards with no ordering wording (F7) impose no ban or obligation | QCVN 41:2024 art. 11 (definition of the guide group) | states today's behaviour with a source |
| KB-4 | IE.452 / IE.451b in the photo means the road being entered is an expressway, from the sign on, until IE.453b/c | QCVN 41:2024 P.3 and the IE rows' articles; Law 36/2024 art. 25 | links the sign to art. 25's rules |
| KB-5 | an R.415a board's row count is the road's lane count when the scene gives none | QCVN 41:2024 D.16 a ("biết số lượng làn đường") | rank 3: lane questions under R.415a (dev 421) |
| KB-6 | with lane-specific speed signs and no lane in the question, a speed claim is decided when every lane gives the same verdict | engine policy (signs over lanes apply per lane, CLAUDE.md); no law sentence says it | rank 3 (dev 381) |
| KB-7 | a `choose` / `which` answer is unknown when an option it needs is unknown | engine policy (three-valued logic), no law | rank 1 (dev 352, 381) |
| KB-8 (optional) | at an I.434a bus stop, vehicles other than buses may not park | Law 36/2024 art. 18 (the list of places where parking is banned); the exact clause is to be checked in `law_db` at build time. If it isn't there, the rule is dropped rather than kept as knowledge | 1 train question touches I.434a |

**What can't be added, even as knowledge:** speed limits by road type (residential area, divided road, default expressway limits). They come from Circular 38/2024/TT-BGTVT, which is neither QCVN 41:2024 nor Law 36/2024, so the owner's rule excludes them. The 4 dev questions after R.420 and the 2 speed-range questions stay out.

## 4. One correction to the approved rank 1

**"P.127 covers every vehicle" would contradict `law_db`.** B.27 b says the sign bans "các loại xe cơ giới" (motor vehicles) from exceeding the number. Dev 272 failed because the parser gave the patrol car class `vehicle` (unknown kind). **Proposed instead:** drop this item from stage A. In stage B, parser v7 maps "xe cảnh sát" (and other named service vehicles) to `motor_vehicle` / `car` with `priority` as the question states. The other rank-1 fixes stand.

## 5. Changes this makes outside `kb/`

- `vqa/kb.py` `Effect`: new keys `zone`, `conduct`, `permits`, `pass_side`, `yield_from`, `informational`; Prolog facts for each; new rules in `kb/rules/` (zones, permits, conduct facts). No cuts.
- **The catalog listing changes** (new rows R.415(a,b), R.122, S.501; new effect keys don't alter listing lines, but new rows do). So the scene prompt becomes **`scene/v5`** (catalog-only change) and the parser prompt hash changes too. That needs a set-T perception check (about $0.06) and a dev re-perception (about $0.17), priced in step 6. The stage-A engine-only replay runs first on the stored v4 scenes: it measures everything except the new rows.
