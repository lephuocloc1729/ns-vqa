"""Phase 4.7 coverage matrix (owner, 2026-11-17): the 80 stage-A signs and the general rule
topics against the question taxonomy. Cells are derived from the catalog, kb/sign_info.yaml and
the DSL, so the matrix can be re-run after each step. Free: no API call, no image, no dataset
question except the wording check, which reads train questions outside the validation set.

    .venv/bin/python eval/coverage_matrix.py matrix   # writes docs/plans/phase-4.7-coverage-matrix.md
    .venv/bin/python eval/coverage_matrix.py wording  # taxonomy check on train wording (counts)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vqa.kb import load_catalog  # noqa: E402
from vqa.reasoning import sign_info as si  # noqa: E402
from vqa import schemas  # noqa: E402

STAGE_A = ROOT / "docs/plans/phase-4.5-stageA-signs.md"
OUT = ROOT / "docs/plans/phase-4.7-coverage-matrix.md"

M, B, NA, OUTC = "modelled", "to build", "n/a", "out"
COLUMNS = [
    ("identity", "identity, meaning, group"),
    ("applies", "who it applies to, exceptions"),
    ("pfr", "permitted / forbidden / required"),
    ("speed", "speed"),
    ("time", "time"),
    ("lane", "lane"),
    ("scope", "where it takes effect / ends"),
    ("placement", "where it is placed"),
    ("conduct", "driver conduct"),
    ("guide", "guide-board content"),
    ("values", "weight and height limits"),
    ("photo", "vehicles in the photo"),
    ("compound", "compound and explain"),
]
# Counting and presence is one intent for every row (owner, 2026-11-17), so it is reported once in
# the summary, not per sign.
INTENT_LEVEL = [("count", "counting and presence", ("count",), "present exists; count / count_is to build")]


def stage_a_codes() -> list[str]:
    codes = []
    for line in STAGE_A.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\| (\d+) \| ([^|]+?) \|", line)
        if m:
            codes.append(m.group(2).strip())
    assert len(codes) == 80, len(codes)
    return codes


def _intents() -> set[str]:
    out = set()
    for name in dir(schemas):
        obj = getattr(schemas, name)
        f = getattr(obj, "model_fields", {}).get("intent")
        if f is not None and isinstance(f.default, str):
            out.add(f.default)
    return out


_ENGINE = None


def _probe(code: str, program):
    """The engine's answer for a scene holding just this sign (look from the catalog row)."""
    global _ENGINE
    from vqa.reasoning.engine import Engine
    from vqa.schemas import Position, SceneGraph, Sign
    _ENGINE = _ENGINE or Engine()
    row = _ENGINE.catalog.get(code)
    vis = row.visual
    from vqa.schemas import LaneSpec
    lanes = [LaneSpec(lane=1, max_speed=60)] if row.effect.lane_board else []
    sign = Sign(id="s1", code=code, confidence="high", shape=vis.shape, border=vis.border,
                background=vis.background, position=Position(rank_top_down=1, side="right"), lanes=lanes)
    return _ENGINE.answer(SceneGraph(scene_id="probe", signs=[sign]), program)


def _stem(cat, code: str) -> bool:
    try:
        return bool(cat.codes_matching(code))
    except KeyError:
        return False


def sign_cells(code: str, cat, intents: set[str]) -> dict[str, tuple[str, str]]:
    """(status, note) per column for one stage-A row."""
    if not cat.has(code):
        # a stem the stage-A list names on its own ("R.415"): its variant rows; the one not already a
        # stage-A row stands for it (R.415b "Kết thúc làn đường theo phương tiện", D.16)
        rows = [c for c in cat.codes_matching(code) if c not in stage_a_codes()] if _stem(cat, code) else []
        if not rows:
            return {c: (B, "no catalog row") for c, _ in COLUMNS}
        code = rows[0]
    e = cat.get(code)
    eff = e.effect
    has_rule = bool(eff.prohibits or eff.max_speed or eff.min_speed or eff.lane_board or eff.lane_reserved
                    or eff.only_directions or eff.placement or eff.zone or eff.permits or eff.ends
                    or eff.pass_side or eff.yield_from)
    cells: dict[str, tuple[str, str]] = {}
    cells["identity"] = (M, "is_sign / meaning name, group, article")

    # who it applies to: probed on a one-sign scene with the engine (applies_to)
    if e.category == "end_of_restriction":
        cells["applies"] = (NA, "an end sign lifts another sign's effect")
    else:
        a = _probe(code, schemas.AppliesTo()) if "applies_to" in intents else None
        cells["applies"] = (M, "applies_to / sign_applies") if a is not None and a.verdict.value == "value" \
            else (B, "applies_to not decided" if a is not None else "applies_to to build")

    # permitted / forbidden / required
    if code.startswith("R.411"):
        cells["pfr"] = (M, "lane arrows read by scene v6 (kb/rules/signals47.pl, D.13)")
    elif e.effect_unmodelled:
        cells["pfr"] = (B, "effect_unmodelled")
    elif eff.prohibits or eff.only_directions or eff.placement or eff.lane_reserved or eff.zone \
            or eff.permits or eff.pass_side or eff.yield_from or eff.ends or eff.min_speed or eff.max_speed \
            or eff.lane_board:
        cells["pfr"] = (M, "catalog effect + rules")
    elif e.category == "warning":
        cells["pfr"] = (NA, "a warning bans nothing (art. 27)")
    elif eff.informational:
        cells["pfr"] = (NA, "guide sign orders nothing (KB-3, art. 35)")
    elif eff.conduct:
        cells["pfr"] = (NA, "conduct only")
    else:
        cells["pfr"] = (B, "meaning-only row")

    # speed
    if eff.max_speed or eff.min_speed or eff.lane_board:
        cells["speed"] = (M, "speed_limit / speed_ok / lanes_where")
    elif eff.zone:
        cells["speed"] = (M, "zone speeds (Circular 38, interpretation)")
    elif code.startswith("W.245"):
        cells["speed"] = (NA, "'đi chậm' gives no number")
    else:
        cells["speed"] = (NA, "no speed effect")

    # time
    if eff.prohibits or eff.days or eff.only_directions or eff.max_speed or eff.lane_reserved:
        cells["time"] = (M, "S.508 plates, when, day_parity")
    elif e.effect_unmodelled and not code.startswith("R.411"):
        cells["time"] = (B, "follows pfr")
    else:
        cells["time"] = (NA, "no timed effect")

    # lane
    if eff.lane_board or eff.lane_reserved:
        cells["lane"] = (M, "per-lane rows / reserved lane")
    elif code.startswith("R.411"):
        cells["lane"] = (M, "per-lane arrows (scene v6)")
    elif eff.prohibits or eff.max_speed:
        cells["lane"] = (M, "sign over lanes (S.504, position.lane)")
    else:
        cells["lane"] = (NA, "no lane effect")

    # scope / end, placement
    for kind in ("scope", "placement"):
        hit = si.lookup(kind, e.code, e.category, extended=True)
        cells[kind] = (M, f"{hit[1].article_id}") if hit else (B, "no sign_info line")

    items, _ = si.conduct_items(e, cat, extended=True)
    if getattr(si, "conduct_out", None) and si.conduct_out(e.code):
        cells["conduct"] = (OUTC, si.conduct_out(e.code))
    elif items:
        cells["conduct"] = (M, f"{len(items)} items")
    elif eff.informational:
        cells["conduct"] = (B, "guide sign: follow the indicated direction (art. 35 to check)")
    else:
        cells["conduct"] = (B, "no conduct items")

    # guide-board content (phase 4.5 B6 / 4.6 I2: guide asks and guide_claim)
    if eff.informational or eff.zone or code.startswith(("I.414", "I.415", "I.444", "IE.4", "I.419", "I.449")):
        cells["guide"] = (M, "guide / guide_claim")
    else:
        cells["guide"] = (NA, "not a guide board")
    # weight and height limits (value conditions on the number read on the sign)
    cells["values"] = (M, f"value: {eff.value.attr}") if eff.value else (NA, "no dimension or weight limit")
    # vehicles in the photo (exists_violation)
    if code.startswith("R.411"):
        cells["photo"] = (M, "exists_violation: a pictured vehicle's lane and turn against the arrows (D.13)")
    elif e.effect_unmodelled:
        cells["photo"] = (B, "effect not modelled")
    elif eff.prohibits or eff.max_speed or eff.min_speed or eff.lane_reserved or eff.only_directions \
            or eff.placement or eff.lane_board:
        cells["photo"] = (M, "exists_violation")
    elif eff.zone and eff.zone.at == "start" and eff.zone.kind == "expressway":
        cells["photo"] = (M, "exists_violation: a pictured vehicle driving into the expressway (Law 36 art. 25)")
    elif eff.zone and eff.zone.at == "start":
        cells["photo"] = (M, "exists_violation: a pictured vehicle's speed against the zone default (Circular 38)")
    elif eff.zone:
        cells["photo"] = (NA, "an end-of-zone sign: nothing a pictured vehicle can break")
    else:
        cells["photo"] = (NA, "nothing a pictured vehicle can break")
    cells["compound"] = (M, "multi / explain / choose")
    return cells


# General rule topics: hand-filled; the source column names the law_db article.
TOPICS = [
    ("speed by road type", "Circular 38/2024 art. 6-9 (interpretation, r_c38_*); Law 36 art. 12",
     {"applies": (M, "rule_permitted: Circular 38 vehicle groups"),
      "speed": (M, "expressway / residential (zones); outside residential (rule_permitted, area)"),
      "conduct": (M, "duties speed_and_distance (art. 12)"), "compound": (M, "")}),
    ("lane use", "Law 36 art. 13", {"applies": (M, "13.3 rudimentary vehicles (rule_permitted)"),
     "pfr": (M, "13.4 reserved lanes (R.412, lane_block); 13.3 (rule_permitted)"),
     "speed": (OUTC, "13.1 'tốc độ thấp hơn phải đi về bên phải' gives no number to check"),
     "lane": (M, "13.3 rightmost lane"), "conduct": (M, "duties lane_change (13.2)"),
     "photo": (M, "exists_violation: a pictured vehicle crossing a line (G.1)"), "compound": (M, "")}),
    ("overtaking", "Law 36 art. 14; QCVN 41 B.25 (P.125)", {"applies": (NA, "every vehicle (art. 14)"),
     "pfr": (M, "14.6 places (rule_permitted); P.125 signs"), "lane": (NA, "multi-lane roads follow art. 13 (14.1)"),
     "conduct": (M, "duties overtaking (14.2-14.5)"), "compound": (M, "")}),
    ("turning, U-turns, reversing", "Law 36 art. 15, 16; QCVN 41 6.2.2",
     {"pfr": (M, "15.4 U-turn places, 16.2 reversing places (rule_permitted); P.123/P.124 signs"),
     "lane": (M, "choose over lanes with permitted(lane) and R.411 arrows (D.13)"), "conduct": (M, "duties turning (15.2-15.3)"),
     "compound": (M, "")}),
    ("stopping and parking", "Law 36 art. 18, 25.2, 26.2", {"applies": (NA, "every vehicle (art. 18)"),
     "pfr": (M, "18.4 places, 26.2 tunnels, 25.2 emergency lane (rule_permitted); P.130/P.131 signs"),
     "photo": (OUTC, "a pictured vehicle stopped at a listed place: perception reads no places (bridge, crossing ...)"),
     "conduct": (M, "duties stopping_parking (18.3, 18.5)"), "compound": (M, "")}),
    ("priority vehicles", "Law 36 art. 27; QCVN 41 art. 7",
     {"applies": (OUTC, "27.2's order matters only between priority vehicles; no question form"),
      "pfr": (M, "27.4 'không phụ thuộc vào tín hiệu đèn' (rule_permitted with a light)"),
      "speed": (M, "27.4 'không bị hạn chế tốc độ' (rule_permitted)"),
      "conduct": (M, "duties priority_vehicle_signal (27.5)"), "compound": (M, "")}),
    ("expressways", "Law 36 art. 25", {"applies": (M, "zone entry ban (KB-4)"),
     "pfr": (M, "25.1 c emergency lane, 25.2 stopping (rule_permitted)"), "speed": (M, "Circular 38 defaults"),
     "lane": (M, "emergency lane"), "scope": (M, "IE.452 to IE.453"),
     "conduct": (M, "duties expressway (25.1 a-c)"), "compound": (M, "")}),
    ("traffic lights", "QCVN 41 art. 4, 6, 8", {"identity": (M, "signal_meaning (art. 6.3, 6.4; scene v6)"),
     "applies": (M, "27.4 priority vehicles on duty (rule_permitted)"),
     "pfr": (M, "6.3 green go, yellow stop (past the line: 6.3.2), red no go; 6.4 arrows (rule_permitted)"),
     "lane": (M, "arrow lights per direction (6.4)"),
     "scope": (OUTC, "art. 8 says where a light takes effect; no question form beyond pfr"),
     "placement": (OUTC, "art. 9 heights: no question form"),
     "conduct": (M, "signal_meaning: 6.3.1 yield to pedestrians, 6.3.2 flashing yellow"),
     "photo": (M, "exists_violation over signals: unknown at red (6.3.2 stop-line timing), no at green"), "compound": (M, "")}),
    ("road markings", "QCVN 41 art. 48-51, G.1-G.4", {"identity": (M, "marking_meaning, marking_is (G.1; scene v6)"),
     "applies": (NA, "the reserved lane's sign (R.412, D.14) says who; line 2.3 adds no addressee"), "pfr": (M, "cross_center / change_lane by pattern (rule_permitted)"),
     "lane": (M, "lane lines by `between`"), "scope": (M, "marking_meaning states art. 51 (alone / with lights and signs, art. 4 order)"),
     "placement": (OUTC, "dimensions: no question form"), "conduct": (M, "marking_meaning: 3.1 yield to rudimentary"),
     "photo": (M, "exists_violation: crossing_line against G.1"), "compound": (M, "")}),
    # parser v13 (owner, 2026-11-18): kb/rules/v13_47.pl
    ("officer's signals", "Law 36 art. 11.3", {"identity": (M, "officer_signal (a, b, c by side)"),
     "pfr": (M, "officer_permits; an obligation asked yes/no is verify(..., expect=false)"),
     "conduct": (M, "officer_signal for the driver's side"),
     "photo": (OUTC, "perception reads no officer; the gesture and side come from the question"),
     "compound": (M, "")}),
    ("signal precedence", "Law 36 art. 11.2, 11.12; QCVN 41 art. 4", {"identity": (M, "precedence, precedence_is"),
     "pfr": (M, "rule_permitted: a green arrow for the action over a sign's ban; a round green overrides nothing"),
     "compound": (M, "")}),
    ("right of way at intersections", "Law 36 art. 22; QCVN 41 D.1, C.7, C.8, E.1",
     {"pfr": (M, "must_yield from R.122 / W.208 / I.401 / W.207, else 22.2-22.3; unknown under a light (E.1 b)"),
      "conduct": (M, "right_of_way; duties joining_road (22.1, 25.1 a)"),
      "photo": (OUTC, "perception reads no approach of the vehicles in the photo"), "compound": (M, "")}),
    ("size and axle limits", "QCVN 41 B.15-B.19", {"pfr": (M, "permitted / forbidden by the vehicle's stated size"),
     "values": (M, "P.115 gross_t, P.116 axle_t (new; not a stage-A row), P.117 height_m, P.118 width_m, P.119 length_m"),
     "compound": (M, "")}),
    ("vehicle classes", "Law 36 art. 34", {"identity": (M, "vehicle_class, vehicle_class_is (34.1 g moped by design speed, cc, kW)"),
     "compound": (M, "")}),
]


HEADER = """# Phase 4.7 coverage matrix

Generated by `eval/coverage_matrix.py matrix` (free; no API call). The sign rows are derived from
the catalog (`kb/sign_catalog*.yaml`), `kb/sign_info.yaml` and the DSL intents in
`vqa/schemas.py`, so re-running it after a step shows the cells that step filled. The topic rows
are hand-filled. Rows come from the law (QCVN 41:2024, Law 36/2024, Circular 38/2024), not from
dev failures; dev, D3 and train are checks only (owner, 2026-11-17).

- **modelled**: every question form in the column can be asked in the DSL and the engine decides it
  from a cited rule.
- **to build**: part or all of the column is missing (the note says what).
- **n/a**: the sign has no such effect in law (e.g. a warning sign bans nothing, art. 27).
- **out**: a form with no question or no law text (reason in the notes).

"""


def matrix() -> str:
    cat = load_catalog()
    intents = _intents()
    rows = [(c, sign_cells(c, cat, intents)) for c in stage_a_codes()]
    abbrev = {M: "M", B: "**B**", NA: "–", OUTC: "out"}
    lines = ["| # | row | " + " | ".join(h for _, h in COLUMNS) + " |",
             "|---|---|" + "---|" * len(COLUMNS)]
    totals = {c: Counter() for c, _ in COLUMNS}
    notes = []
    for i, (code, cells) in enumerate(rows, 1):
        shown = f"{code} (as R.415b)" if code == "R.415" else code
        lines.append(f"| {i} | {shown} | " + " | ".join(abbrev[cells[c][0]] for c, _ in COLUMNS) + " |")
        for c, _ in COLUMNS:
            totals[c][cells[c][0]] += 1
            if cells[c][0] in (B, OUTC):
                notes.append(f"- {code}, {c}: {cells[c][1]}")
    tl = ["| | topic | source | " + " | ".join(h for _, h in COLUMNS) + " |",
          "|---|---|---|" + "---|" * len(COLUMNS)]
    for i, (name, src, cells) in enumerate(TOPICS, 1):
        cells = {c: cells.get(c, (NA, "")) for c, _ in COLUMNS}
        tl.append(f"| T{i} | {name} | {src} | " + " | ".join(abbrev[cells[c][0]] for c, _ in COLUMNS) + " |")
        for c, _ in COLUMNS:
            totals[c][cells[c][0]] += 1
            if cells[c][0] in (B, OUTC) and cells[c][1]:
                notes.append(f"- topic {name}, {c}: {cells[c][1]}")
    grand = Counter()
    for c in totals.values():
        grand.update(c)
    tot = ["| column | modelled | to build | n/a | out |", "|---|---|---|---|---|"]
    for c, h in COLUMNS:
        t = totals[c]
        tot.append(f"| {h} | {t[M]} | {t[B]} | {t[NA]} | {t[OUTC]} |")
    for _, h, need, note in INTENT_LEVEL:
        st = M if all(n in intents for n in need) else B
        tot.append(f"| {h} (one intent for every row) | {int(st == M)} | {int(st == B)} | 0 | 0 |")
        grand[st] += 1
    tot.append(f"| **all cells ({sum(grand.values())})** | **{grand[M]}** | **{grand[B]}** | **{grand[NA]}** | **{grand[OUTC]}** |")
    return "\n".join(["## Totals", "", *tot, "", "## Signs (80 rows)", "",
                      "M = modelled, **B** = to build, – = not applicable, out = out (reason in the notes).", "",
                      *lines, "", "## General rule topics", "", *tl, "", "## Cell notes (to build / out)", "", *notes, ""])


MISSED = """
## Taxonomy check on train wording

`eval/coverage_matrix.py wording` matches each train question to the columns by wording only (no
image, no per-image lookup). **The 110 validation questions are excluded** (CLAUDE.md: aggregate
only), so 420 of the 530 are checked. A question may match several columns.

| column (by wording) | questions |
|---|---|
| permitted / forbidden / required | 231 |
| identity, meaning, group | 120 |
| guide-board content (places, distances, directions, route) | 147 |
| where it takes effect / ends (incl. "phía trước", distances) | 73 |
| speed | 65 |
| who it applies to | 48 |
| counting and presence | 48 |
| compound and explain | 42 |
| time | 38 |
| lane | 38 |
| limit values other than speed (weight, height, width, length) | 30 |
| driver conduct | 24 |
| vehicles in the photo (violation by a pictured vehicle) | 15 |
| road markings | 9 |
| where it is placed | 7 |
| symbols and letters on a sign | 5 |
| traffic lights | 3 |

**Question forms the owner's first taxonomy missed.** Items 1-3 are matrix columns since the owner's
OK (2026-11-17); counting and presence is reported once, as one intent for every row:
1. **Guide-board content** (147 by wording): places, distances, arrow directions, route codes and
   what a board says lies ahead. Modelled since phase 4.5/4.6 (`guide`, `guide_claim`); it has no
   column in the taxonomy because it is not a sign-row property.
2. **Limit values other than speed** (30): "giới hạn trọng tải / chiều cao ... ở mức bao nhiêu"
   (196, 441). Modelled for P.115-P.119 through `value` conditions; the taxonomy's "speed, time and
   lane" has no slot for them, so they are counted under speed here.
3. **Vehicles in the photo** (15): "các xe trong ảnh có đỗ đúng chỗ không" (464, 338). Modelled
   through `exists_violation` when perception lists vehicles; it depends on the scene, not a row.
4. **Symbols and letters on a sign** (5): "chữ P ... viết tắt của từ tiếng Anh nào" (86),
   "trạm dừng nghỉ có mấy dịch vụ" (363). **Out:** no law_db text gives the letters' source word,
   and service pictograms on IE boards are not read by perception.
5. **The zone the road is in** ("đang vào khu vực nào", 88): asked of the scene, answered by the
   zone rows (F4) under "where it takes effect".

Four questions match no column: 65 and 199 (guide-board places; covered by `guide`), 361 (the
place beside a sign; `meaning`), 459 (a summary of stopping and overtaking rules; compound).
"""


# --------------------------------------------------------------------- wording check
TAXONOMY = {
    "identity": r"(là|thuộc) (biển|loại biển|nhóm)|biển (gì|nào)|tên (của )?biển|ý nghĩa|có nghĩa|cho biết|báo (hiệu|trước|gì)|thuộc nhóm|mã|số hiệu|điều nào|quy định ở|điều gì|thông tin gì|chỉ dẫn|cảnh báo",
    "applies": r"áp dụng cho|dành cho|(xe|phương tiện) nào|loại xe|ngoài xe|trừ|ngoại trừ|đối với",
    "pfr": r"được (phép )?(đi|rẽ|quay|vượt|dừng|đỗ|vào|chạy|lưu thông|đón)|cấm|bắt buộc|phải (đi|rẽ)|có được|không được|vi phạm|bị phạt|hướng nào|đi thẳng|rẽ",
    "speed": r"km/h|tốc độ|chạy (tối đa|tối thiểu|nhanh)",
    "time": r"\d+ ?(giờ|h\b|:\d\d)|giờ nào|khung giờ|ngày (chẵn|lẻ)|buổi|ban đêm|thời gian",
    "lane": r"làn",
    "scope": r"(hiệu lực|phạm vi|đến đâu|kết thúc|hết (đoạn|hiệu lực|cấm)|bắt đầu|phía trước|từ (đây|vị trí)|bao xa|cách (đây)? ?\d|còn \d|km\b)",
    "placement": r"đặt ở|được đặt|vị trí đặt|đặt (biển|tại)",
    "conduct": r"(cần|phải|nên) (làm gì|làm|xử lý|chú ý|giảm|đi như thế nào|đi thế nào)|người lái|xử lý thế nào|chú ý|yêu cầu xe làm gì",
    "count": r"bao nhiêu biển|mấy biển|đếm|có (biển|bảng)|trong ảnh có|xuất hiện",
    "compound": r"vì sao|tại sao|\?.+\?|nhận định|trường hợp nào|hay |hoặc .*\?|đúng hay sai|lý do",
    "guide": r"đường|hướng|thành phố|quốc lộ|cao tốc|lối ra|địa điểm|đến (đường|thành)",
    "values": r"trọng tải|tấn|chiều cao|cao hơn|chiều ngang|chiều dài|khối lượng|\d+[,.]?\d* ?m\b|thông số",
    "scene_vehicles": r"(xe|chiếc|người lái).{0,40}trong ảnh|các xe trong ảnh|đang (đỗ|dừng|đi|chạy)",
    "symbols": r"chữ .{1,6} (trên|viết tắt)|ký hiệu|biểu tượng|viết tắt|dịch vụ",
    "light": r"đèn",
    "marking": r"vạch",
}


def wording() -> dict:
    tr = json.loads((ROOT / "VLSP2025-MLQA-Natural/dataset/train data/vlsp_2025_train.json").read_text())
    val = json.loads((ROOT / "data/splits/train_validation.json").read_text())
    vids = set(val["question_ids"]) if "question_ids" in val else {q for q in val.get("questions", [])}
    qs = [q for q in tr if q["id"] not in vids]
    hits = Counter()
    unmatched = []
    for q in qs:
        cols = [c for c, p in TAXONOMY.items() if re.search(p, q["question"], re.I)]
        for c in cols:
            hits[c] += 1
        if not cols:
            unmatched.append((q["id"], q["question"]))
    return {"questions": len(qs), "validation_excluded": len(tr) - len(qs), "hits": dict(hits),
            "unmatched": unmatched}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "matrix"
    if cmd == "matrix":
        OUT.write_text(HEADER + matrix() + MISSED, encoding="utf-8")
        print(OUT)
    elif cmd == "wording":
        r = wording()
        print(json.dumps({k: v for k, v in r.items() if k != "unmatched"}, ensure_ascii=False, indent=1))
        for i, t in r["unmatched"]:
            print(i, "|", t)
