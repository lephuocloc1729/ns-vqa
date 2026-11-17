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


def sign_cells(code: str, cat, intents: set[str]) -> dict[str, tuple[str, str]]:
    """(status, note) per column for one stage-A row."""
    if not cat.has(code):
        return {c: (B, "no catalog row") for c, _ in COLUMNS}
    e = cat.get(code)
    eff = e.effect
    has_rule = bool(eff.prohibits or eff.max_speed or eff.min_speed or eff.lane_board or eff.lane_reserved
                    or eff.only_directions or eff.placement or eff.zone or eff.permits or eff.ends
                    or eff.pass_side or eff.yield_from)
    cells: dict[str, tuple[str, str]] = {}
    cells["identity"] = (M, "is_sign / meaning name, group, article")

    # who it applies to
    if e.category in ("warning",) or eff.informational:
        cells["applies"] = (NA, "applies to every road user (art. 27 / guide sign)")
    elif eff.prohibits or eff.max_speed or eff.min_speed or eff.lane_reserved or eff.lane_board:
        have = "applies_to" in intents
        cells["applies"] = (M if have else B,
                            "which_vehicles exists for bans; applies_to claim, every_vehicle except, covered classes"
                            + ("" if have else " to build"))
    elif e.effect_unmodelled:
        cells["applies"] = (B, "effect not modelled")
    elif has_rule or eff.conduct:
        cells["applies"] = (B, "applies_to over the row's vehicles (art. 31 / its article)")
    else:
        cells["applies"] = (NA, "no vehicle-specific effect")

    # permitted / forbidden / required
    if e.effect_unmodelled:
        cells["pfr"] = (B, "effect_unmodelled" + (" (lane directions: scene v6)" if code.startswith("R.411") else ""))
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
    elif e.effect_unmodelled:
        cells["time"] = (B, "follows pfr")
    else:
        cells["time"] = (NA, "no timed effect")

    # lane
    if eff.lane_board or eff.lane_reserved:
        cells["lane"] = (M, "per-lane rows / reserved lane")
    elif code.startswith("R.411"):
        cells["lane"] = (B, "lane directions (scene v6)")
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
    if e.effect_unmodelled:
        cells["photo"] = (B, "effect not modelled")
    elif eff.prohibits or eff.max_speed or eff.min_speed or eff.lane_reserved or eff.only_directions \
            or eff.placement or eff.lane_board:
        cells["photo"] = (M, "exists_violation")
    elif eff.zone:
        cells["photo"] = (B, "zone entry by a pictured vehicle")
    else:
        cells["photo"] = (NA, "nothing a pictured vehicle can break")
    cells["compound"] = (M, "multi / explain / choose")
    return cells


# General rule topics: hand-filled; the source column names the law_db article.
TOPICS = [
    ("speed by road type", "Circular 38/2024 (interpretation, r_c38_*); Law 36 art. 12",
     {"identity": (NA, ""), "applies": (B, "per class at the road type"), "pfr": (NA, ""),
      "speed": (B, "expressway / residential defaults modelled; outside residential, divided roads to build"),
      "time": (NA, ""), "lane": (NA, ""), "scope": (NA, ""), "placement": (NA, ""),
      "conduct": (B, "art. 12.1 keep speed and distance"), "compound": (M, "")}),
    ("lane use", "Law 36 art. 13", {"identity": (NA, ""), "applies": (B, "13.3 rudimentary right, motor left"),
     "pfr": (B, "13.2 change lanes only where allowed; 13.4 reserved lanes"), "speed": (B, "13.1 slower keeps right"),
     "time": (NA, ""), "lane": (B, "lane sets"), "scope": (NA, ""), "placement": (NA, ""),
     "conduct": (B, "13.2 signal, observe"), "compound": (M, "")}),
    ("overtaking", "Law 36 art. 14; QCVN 41 B.25 (P.125)", {"identity": (NA, ""), "applies": (B, ""),
     "pfr": (B, "14.3 overtake on the left; 14.4 where banned"), "speed": (NA, ""), "time": (NA, ""),
     "lane": (B, "14.3 exceptions on multi-lane roads"), "scope": (NA, ""), "placement": (NA, ""),
     "conduct": (B, "14.1 signal, observe"), "compound": (M, "")}),
    ("turning and U-turns", "Law 36 art. 15; QCVN 41 6.2.2", {"identity": (NA, ""), "applies": (NA, ""),
     "pfr": (B, "15.4 no U-turn places"), "speed": (NA, ""), "time": (NA, ""), "lane": (B, "turn lanes"),
     "scope": (NA, ""), "placement": (NA, ""), "conduct": (B, "15.1-15.2 slow, signal, yield"),
     "compound": (M, "")}),
    ("stopping and parking", "Law 36 art. 18", {"identity": (NA, ""), "applies": (B, ""),
     "pfr": (B, "18.3 places where stopping / parking is banned"), "photo": (B, "a pictured vehicle stopped at a banned place"), "speed": (NA, ""), "time": (NA, ""),
     "lane": (NA, ""), "scope": (NA, ""), "placement": (NA, ""), "conduct": (B, "18.2 signal, keep right"),
     "compound": (M, "")}),
    ("priority vehicles", "Law 36 art. 27; QCVN 41 art. 7", {"identity": (NA, ""),
     "applies": (B, "27.2 the order of priority"), "pfr": (B, "27.4 not bound by lights, may go against the flow"),
     "speed": (B, "27.4 'không bị hạn chế tốc độ'"), "time": (NA, ""), "lane": (NA, ""), "scope": (NA, ""),
     "placement": (NA, ""), "conduct": (B, "27.5 others slow down, keep right, yield"), "compound": (M, "")}),
    ("expressways", "Law 36 art. 25", {"identity": (NA, ""), "applies": (M, "zone entry ban (KB-4)"),
     "pfr": (B, "25.1 c no driving in the emergency lane; 25.2 stopping"), "speed": (M, "Circular 38 defaults"),
     "time": (NA, ""), "lane": (B, "emergency lane"), "scope": (M, "IE.452 to IE.453"), "placement": (NA, ""),
     "conduct": (B, "25.1 entering, leaving"), "compound": (M, "")}),
    ("traffic lights", "QCVN 41 art. 4, 6, 8", {"identity": (B, "colour / arrow meaning (art. 6.3, 6.4)"),
     "applies": (B, "27.4 priority vehicles"), "pfr": (B, "6.3 green go, yellow stop, red no go"),
     "speed": (NA, ""), "time": (NA, ""), "lane": (B, "arrow lights per direction"), "scope": (B, "art. 8"),
     "placement": (OUTC, "art. 9 heights: no question form"), "conduct": (B, "6.3.1 yield to pedestrians"),
     "photo": (B, "a pictured vehicle against the light"), "compound": (M, "")}),
    ("road markings", "QCVN 41 art. 48-51, G.1-G.4", {"identity": (B, "line kind meaning (G.1)"),
     "applies": (B, "2.3 reserved-lane line"), "pfr": (B, "cross / change lane by line pattern"),
     "speed": (NA, ""), "time": (NA, ""), "lane": (B, "between which lanes"), "scope": (B, "art. 51"),
     "placement": (OUTC, "dimensions: no question form"), "conduct": (B, "G.1 3.1 yield to rudimentary"),
     "photo": (B, "a pictured vehicle crossing a line"), "compound": (M, "")}),
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
        lines.append(f"| {i} | {code} | " + " | ".join(abbrev[cells[c][0]] for c, _ in COLUMNS) + " |")
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
