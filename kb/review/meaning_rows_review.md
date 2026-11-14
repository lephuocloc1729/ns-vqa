# Meaning-only rows: review list

148 rows drafted (58 W, 51 I, 39 IE). 26 flagged, plus a random 10% sample (12) of the unflagged rows (seed 1611) to spot-check.

## Flagged rows

| Code | Name (vi) | Cited | Why flagged |
| --- | --- | --- | --- |
| W.201(c,d) | Chỗ ngoặt nguy hiểm có nguy cơ lật xe | C.1a | variant letters c,d are not described one by one in the text |
| W.202(a,b) | Nhiều chỗ ngoặt nguy hiểm liên tiếp | C.2 | variant letters a,b are not described one by one in the text |
| W.203(a,b,c) | Đường bị thu hẹp | C.3 | variant letters a,b,c are not described one by one in the text |
| W.205(a,b,c,d,e) | Đường giao nhau | C.5 | variant letters a,b,c,d,e are not described one by one in the text |
| W.207(a,b,c,d,e,f,g,h,i,k,l) | Giao nhau với đường không ưu tiên (đường nhánh) | C.7 | variant letters a,b,c,d,e,f,g,h,i,k,l are not described one by one in the text |
| W.223(a,b) | Vách núi nguy hiểm | C.23 | variant letters a,b are not described one by one in the text |
| W.228(a,b) | Đá lở | C.28 | variant letters a,b are not described one by one in the text |
| W.242(a,b) | Nơi đường sắt giao vuông góc với đường bộ | C.42 | variant letters a,b are not described one by one in the text |
| W.243(a,b,c) | Nơi đường sắt giao không vuông góc với đường bộ | C.43 | variant letters a,b,c are not described one by one in the text |
| W.246(a,b,c) | Chú ý chướng ngại vật | C.46 | variant letters a,b,c are not described one by one in the text |
| I.405(a,b,c) | Đường cụt | E.5 | variant letters a,b,c are not described one by one in the text |
| I.407(a,b,c) | Đường một chiều | E.7 | variant letters a,b,c are not described one by one in the text |
| I.413(b,c) | Rẽ ra đường có làn đường dành cho ô tô khách | E.13 | variant letters b,c are not described one by one in the text |
| I.414(a,b,c,d) | Chỉ hướng đường | E.14 | variant letters a,b,c,d are not described one by one in the text |
| I.417(a,b,c) | Chỉ hướng đường phải đi cho từng loại xe | E.17 | variant letters a,b,c are not described one by one in the text |
| I.423(a,b) | Vị trí người đi bộ sang ngang | E.23a | variant letters a,b are not described one by one in the text |
| I.424(a,b) | Cầu vượt qua đường cho người đi bộ | E.24 | variant letters a,b are not described one by one in the text |
| I.424(c,d) | Hầm chui qua đường cho người đi bộ | E.25 | variant letters c,d are not described one by one in the text |
| I.433(b,c,d) | Báo hiệu nơi cắm trại, nhà nghỉ lưu động | E.35b | variant letters b,c,d are not described one by one in the text |
| I.441(a,b,c) | Báo hiệu phía trước có công trường thi công | E.44 | variant letters a,b,c are not described one by one in the text |
| I.444(a,b,c,d,e,f,g,h,i,j,k,l,m) | Biển báo chỉ dẫn địa điểm | E.47 | variant letters a,b,c,d,e,f,g,h,i,j,k,l,m are not described one by one in the text |
| I.445(a,b,c,d,e,f,g,h) | Biển báo kiểu mô tả tình trạng đường | E.48 | variant letters a,b,c,d,e,f,g,h are not described one by one in the text |
| I.447(a,b,c,d) | Cầu vượt liên thông | E.50 | variant letters a,b,c,d are not described one by one in the text |
| IE.464b | Chỉ dẫn hướng ra tại lối ra | 47 | name from figure caption Hình 11', which prints the code as 'E.464b' |
| IE.472(a,b) | Chỉ dẫn khoảng cách đến trạm thu phí | 47 | variant letters a,b are shown only in figure Hình 31 |
| IE.473 | Cảnh báo cho người điều khiển phương tiện chú ý lái xe và giảm tốc độ tại khu vực có | 47 | name cut from a longer sentence |

## Random sample of unflagged rows

| Code | Name (vi) | Cited |
| --- | --- | --- |
| W.233 | Nguy hiểm khác | C.33 |
| W.234 | Giao nhau với đường hai chiều | C.34 |
| W.235 | Đường đôi | C.35 |
| I.432 | Khách sạn | E.34 |
| I.434b | Bến xe tải | E.37 |
| I.442 | Chợ | E.45 |
| I.449 | Biển tên đường | E.52 |
| IE.451a | Chỉ dẫn khoảng cách đến lối vào đường cao tốc | 47 |
| IE.453a | Chỉ dẫn khoảng cách đến điểm kết thúc đường cao tốc | 47 |
| IE.463c | Chỉ lối vào Công trình kiểm soát tải trọng xe | 47 |
| IE.471 | Chỉ dẫn giữ khoảng cách lái xe an toàn | 47 |
| IE.474 | Chỉ dẫn lối ra | 47 |

## Review results — 2026-11-14

Reviewed all **26 flagged rows and 12 sample rows** against the local QCVN
41:2024/BGTVT article text and the actual figure images in
`VLSP2025-MLQA-Natural/dataset/law_db/`. All 38 entries above also match the
current `kb/sign_catalog_meaning.yaml` names, variant lists and citations.

**Name/code outcome:** 25 flagged rows retain valid family names/code sets;
**IE.473 needs its name corrected**. All **12/12 sample names and codes pass**.
The requested threshold of two sample errors is not reached, so this review
was not expanded to the other 110 rows. A passing sample is evidence, not
verification of those remaining rows.

This is an assistant review, not human sign-off. Catalog data and review status
were left unchanged. In particular, a family-level name is accepted here when
it matches QCVN's heading/caption; that does not make it a complete description
of every lettered variant.

### Correction and qualifications

- **IE.473 — incorrect, incomplete name.** Replace the dangling sentence
  “Cảnh báo cho người điều khiển phương tiện chú ý lái xe và giảm tốc độ tại khu
  vực có” with **“Chỉ dẫn giảm tốc độ”**, matching article 47.24, Hình 32,
  `image078.jpg` (the sign reads “GIẢM TỐC ĐỘ / SLOW DOWN”). The current key is
  also mechanically truncated; if correcting the catalog, use a corresponding
  stable key such as `chi_dan_giam_toc_do` and update the drafting tool so the
  correction survives regeneration.
- **IE.472(a,b) — valid QCVN family caption, with a specificity caveat.** Hình 31
  calls the family “Chỉ dẫn khoảng cách đến trạm thu phí”; a (`image074.jpg`)
  includes “750 m”, whereas b (`image076.jpg`) says only “TRẠM THU PHÍ”. Thus
  the current family title is source-faithful, but a meaning answer specifically
  for b should not claim that its face displays a distance.
- **IE.464b — retain IE, not E.** Article 47.5 explicitly uses IE.464b; Hình 11’
  prints E.464b in its caption. The exit-direction figure (`image034.jpg`) and
  article 47.15 support the current code and name. This is a source caption typo.
- **I.447c — retain 447c, not 445c.** E.50 twice prints I.445c in its prose;
  Hình E.57 (`image454.jpg`) explicitly labels I.447c and I.447d. The catalog's
  a,b,c,d set is correct.

### Flagged-row evidence

Image filenames below are relative to `law_db/images.fld/`. “Pass” concerns the
requested name and letter set; variant distinctions are recorded to avoid
mistaking a shared family name for a variant-specific description.

| Row | Result | Source figure(s) / image(s) | Letter check and observations |
| --- | --- | --- | --- |
| W.201(c,d) | Pass | C.1a; Hình C.1a; image190.jpg | c: curve left, overturning risk to right; d: curve right, overturning risk to left. Both letters appear. |
| W.202(a,b) | Pass | C.2; Hình C.2; image192.jpg | a: first bend left; b: first bend right. |
| W.203(a,b,c) | Pass | C.3; Hình C.3; image194.jpg | a: narrows both sides; b: left side; c: right side. |
| W.205(a,b,c,d,e) | Pass | C.5; Hình C.5; image198.jpg | All five labels present: a crossroad, b branch right, c branch left, d T junction, e Y junction; equal-priority intersections. |
| W.207(a,b,c,d,e,f,g,h,i,k,l) | Pass | C.7; Hình C.7–C.9; image202.jpg, image204.jpg, image206.jpg | All eleven labels present; no j. Thick strokes identify the priority road; thin strokes identify minor branches. Family name matches the article. |
| W.223(a,b) | Pass | C.23; Hình C.25; image238.jpg | a: cliff on left; b: cliff on right. |
| W.228(a,b) | Pass | C.28; Hình C.30; image248.jpg | a: falling rocks from left; b: from right. c (loose stones) and d (weak roadbed) are different meanings, correctly excluded from this row. |
| W.242(a,b) | Pass | C.42; Hình C.44; image280.jpg | a: one railway track; b: two or more tracks. Crossbuck shapes, not triangular signs. |
| W.243(a,b,c) | Pass | C.43; Hình C.45; image282.jpg | a,b,c have one,two,three red stripes respectively; text assigns 50,100,150 m. Rectangular markers. |
| W.246(a,b,c) | Pass | C.46; Hình C.48; image288.jpg | a: pass either side; b: pass left; c: pass right. |
| I.405(a,b,c) | Pass | E.5; Hình E.5; image350.jpg | a: dead-end branch right; b: left; c: dead end ahead. |
| I.407(a,b,c) | Pass | E.7; Hình E.7; image354.jpg | a: straight arrow; b: right arrow; c: left arrow. |
| I.413(b,c) | Pass | E.13; Hình E.13; image364.jpg | Both b,c are turns onto a road with a bus lane: b right, c left. a is a separate approach sign, correctly excluded. |
| I.414(a,b,c,d) | Pass | E.14; Hình E.14; image366.jpg | All four labels present; a,b schematic junction directions, c,d multiple destination panels. Heading matches. |
| I.417(a,b,c) | Pass | E.17; Hình E.17; image372.jpg | All three labels present; a,b show truck/semitrailer directions (right/straight), c a different vehicle restriction/direction example. |
| I.423(a,b) | Pass | E.23a; Hình E.23a; image384.jpg | Mirrored pedestrian-crossing figures; both letters present. |
| I.424(a,b) | Pass | E.24; Hình E.24; image388.jpg | Mirrored footbridge stair signs. |
| I.424(c,d) | Pass | E.25; Hình E.25; image390.jpg | Mirrored pedestrian underpass stair signs; c,d are not bridge variants. |
| I.433(b,c,d) | Pass | E.35b; Hình E.35b; image412.jpg | b camping; c caravans/mobile homes; d both. Shared family title is valid but loses this distinction. |
| I.441(a,b,c) | Pass | E.44; Hình E.44; image430.jpg | a 500 m, b 100 m, c 50 m before works. |
| I.444(a,b,c,d,e,f,g,h,i,j,k,l,m) | Pass | E.47; Hình E.47–E.51; image436.jpg, image438.jpg, image440.jpg, image442.jpg | All thirteen labels present: a rail station, b airport, c parking, d coach station, e first aid, f passenger wharf, g tourism, h fuel, i wash, j ferry, k metro, l traveler services, m repair. Hình E.47 is embedded in image436.jpg above E.48. |
| I.445(a,b,c,d,e,f,g,h) | Pass | E.48; Hình E.52–E.54; image444.jpg, image446.jpg, image448.jpg | a slippery road, b steep road, c fog, d weak roadbed, e large vehicles keep right, f crosswind, g accident risk, h continuous descent. Family title matches but individual meanings differ. |
| I.447(a,b,c,d) | Pass; source typo | E.50; Hình E.56–E.57; image452.jpg, image454.jpg | All four interchange diagrams labeled 447a–d. Prose's 445c is contradicted by the figure label. |
| IE.464b | Pass; source typo | 47.5, 47.15; Hình 11’; image034.jpg | Exit-direction arrow sign. IE.464b is explicit in the text despite E.464b in the caption. |
| IE.472(a,b) | Pass as family title; qualify b | 47.23; Hình 31; image074.jpg, image076.jpg | Both letters explicit; only a displays distance. See qualification above. |
| IE.473 | Correct name required | 47.24; Hình 32; image078.jpg | No variant letter. Current name ends mid-sentence; use “Chỉ dẫn giảm tốc độ”. |

### Sample-row evidence

| Row | Result | Source / image | Check |
| --- | --- | --- | --- |
| W.233 | Pass | C.33; Hình C.35; image260.jpg | “Nguy hiểm khác”; exclamation-mark warning; no letter. |
| W.234 | Pass | C.34; Hình C.36; image262.jpg | “Giao nhau với đường hai chiều”; opposing horizontal arrows; no letter. |
| W.235 | Pass | C.35; Hình C.37; image264.jpg | “Đường đôi”; divided-road diagram; no letter. |
| I.432 | Pass | E.34; Hình E.34; image408.jpg | “Khách sạn”; bed pictogram and hotel text; no letter. |
| I.434b | Pass | E.37; Hình E.37; image418.jpg | “Bến xe tải”; truck pictogram; b explicitly in title/caption. |
| I.442 | Pass | E.45; Hình E.45; image432.jpg | “Chợ”; market sign; no letter. |
| I.449 | Pass | E.52; Hình E.59; image458.jpg | “Biển tên đường”; AH112 example for an international route; no letter. |
| IE.451a | Pass | 47.2.1; Hình 8a; image024.jpg | Distance to expressway entrance, “500 m”; a explicitly under left panel. |
| IE.453a | Pass | 47.4.1; Hình 10a; image028.jpg | Distance to expressway end, “500 m”; a under left panel, b under no-distance panel. |
| IE.463c | Pass | 47.14; Hình 22; image054.jpg | Entrance to vehicle weighing facility; c under direction-arrow panel. |
| IE.471 | Pass | 47.22; Hình 30; image072.jpg | “Chỉ dẫn giữ khoảng cách lái xe an toàn”; no letter. |
| IE.474 | Pass | 47.25; Hình 33; image080.jpg | “Chỉ dẫn lối ra” matches caption; expressway exit arrow; no letter. |

### Incidental visual-metadata discrepancies (outside the name/letter sample score)

The figures also expose incorrect generic `visual` defaults in some checked
catalog rows. These do **not** count as sample name/code errors:

- W.242(a,b) is a red/white crossbuck, not a yellow triangle.
- W.243(a,b,c) comprises white rectangular markers with red diagonal stripes,
  not yellow triangles.
- IE.451a is blue in Hình 8a, whereas the catalog says green.
- IE.471 has a yellow fluorescent background and black border in 47.22/Hình 30,
  whereas the catalog says green with no border.
- IE.473 likewise has a yellow fluorescent background and black border in
  47.24/Hình 32, whereas the catalog says green with no border.

No full audit of visual metadata was performed. These five observations should
be handled separately from the requested names and variant letters.

## Applied after the owner's review (2026-11-14)

The project owner confirmed in review that the flagged rows and the 12 sample
rows are correct, with two corrections. Applied in `tools/draft_catalog_rows.py`
(so they survive regeneration) and in `kb/sign_catalog_meaning.yaml`:

- **IE.473** renamed "Chỉ dẫn giảm tốc độ" (key `chi_dan_giam_toc_do`).
- **IE.472(a,b)** split into two rows, both citing art. 47:
  - IE.472a "Chỉ dẫn khoảng cách đến trạm thu phí" (the sign shows a distance).
  - IE.472b "Chỉ dẫn trạm thu phí phía trước" (only "Toll Plaza", no distance). The row's
    `note` says QCVN names the family "distance to toll station" and that this
    variant-level meaning is our reading of the figure.
- The five visual defaults listed above (W.242, W.243, IE.451a, IE.471, IE.473) are
  corrected from the figures.
- The 39 reviewed rows (the flagged rows, with IE.472 now two rows, and the 12 sample
  rows) carry `reviewed: true`. The other 110 rows stay `reviewed: false`.
