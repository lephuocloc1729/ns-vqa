"""The owner's hand-grading workbooks for V1 and V2 on the private test (owner, 2026-11-21).

Builds two workbooks in the layout of the RAG repo's `reports/Natural_Private_Benchmark.xlsx`,
from the six grading sheets the private runs and the RAG merges wrote (`owner_grading.csv` and
`owner_grading_rag.csv` in each run's replay folder) plus the run records (image id, seconds)
and the live RAG files (seconds):

- `V1_private_benchmark.xlsx`: V1, rules only, 3 runs x 146 questions;
- `V2_private_benchmark.xlsx`: V2, rules + live RAG fallback, 3 runs x 146 questions.

Each has a summary sheet (`Tong hop`, formulas over the detail sheet, so the owner's grades in
"Người chấm" update it), the detail sheet (`Chi tiet`, one row per run and question, with a
Đúng / Một phần / Sai list in "Người chấm", initialised to the judge's grade unless the CSV
already holds a human score) and the method sheet (`Phuong phap`).

The sheets hold private questions and gold answers. This is owner-only material, like the CSVs:
the workbooks go into the gitignored replay folder, nothing from them is printed (counts only),
and the assistant does not open them.

    python3 eval/owner_workbooks.py          # needs openpyxl
"""

from __future__ import annotations

import csv
import json
import statistics
import subprocess
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "cache" / "private_run"
OUT = REPLAY / "owner_workbooks"
SENTINELS = [ROOT / "eval" / n for n in ("private_ran.json", "private_ran_2.json", "private_ran_3.json")]
LIVE = [REPLAY / "a51605785ace" / "rag_live.jsonl", REPLAY / "live_rest" / "rag_live.jsonl"]

NAVY = "FF243B53"
HEAD_FONT = Font(bold=True, color="FFFFFFFF")
HEAD_FILL = PatternFill("solid", fgColor=NAVY)
WRAP_TOP = Alignment(wrap_text=True, vertical="top")
LABELS = {"correct": "Đúng", "partial": "Một phần", "wrong": "Sai", "error": "Sai"}
HUMAN = {1.0: "Đúng", 0.5: "Một phần", 0.0: "Sai"}

DETAIL = [("Cấu hình", 16), ("Lượt", 6), ("ID", 18), ("Ảnh", 15), ("Loại câu hỏi", 11), ("Câu hỏi", 40),
          ("Đáp án tham chiếu", 30), ("Câu trả lời", 50), ("AI chấm", 10), ("Người chấm", 14),
          ("Điểm AI (0–1)", 10), ("Nhận xét giám khảo", 50), ("Latency (giây/câu)", 11), ("Trả lời bởi", 11),
          ("Trigger", 17), ("Ghi chú người chấm", 30)]
SUMMARY = [("Cấu hình", 22), ("Lượt", 8), ("Người chấm đúng", 12), ("Người chấm một phần", 14),
           ("Người chấm sai", 12), ("Người chấm tỷ lệ đúng", 14), ("Điểm người chấm TB", 14),
           ("Latency TB (giây)", 12), ("Latency trung vị", 12), ("Tổng thời gian (phút)", 12),
           ("Số câu", 9), ("AI đúng", 9), ("AI một phần", 10), ("AI sai", 9), ("AI tỷ lệ đúng", 11),
           ("AI điểm TB", 11), ("Câu rules quyết định", 12), ("Người chấm điểm TB (câu rules)", 16),
           ("AI điểm TB (câu rules)", 14)]


def ignored(path: Path) -> bool:
    return subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", str(path)]).returncode == 0


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def ai_label(row: dict) -> str:
    if row["judge_label"]:
        return LABELS.get(row["judge_label"], "Sai")
    return "Đúng" if float(row["auto_correct"] or 0) == 1.0 else "Sai"       # Yes/No: by polarity


def human_label(row: dict) -> str:
    s = (row.get("human_score") or "").strip().replace(",", ".")
    try:
        return HUMAN.get(float(s), ai_label(row))
    except ValueError:
        return ai_label(row)


def live_seconds() -> dict[str, float]:
    out = {}
    for path in LIVE:
        meta = json.loads(path.with_name("rag_live_meta.json").read_text(encoding="utf-8"))
        retrieval = meta.get("retrieval_seconds_per_question") or 0.0
        for r in jsonl(path):
            out[r["id"]] = sum(r.get(k) or 0.0 for k in ("caption_seconds", "embed_seconds", "answer_seconds")) + retrieval
    return out


def runs() -> list[tuple[int, str]]:
    out = []
    for n, s in enumerate(SENTINELS, 1):
        mark = json.loads(s.read_text(encoding="utf-8"))
        if mark.get("status") != "finished":
            raise SystemExit(f"private run {n} has not finished")
        out.append((n, mark["run_id"]))
    return out


def header(ws, row: int, cols: list[tuple[str, int]]) -> None:
    for j, (name, width) in enumerate(cols, 1):
        c = ws.cell(row=row, column=j, value=name)
        c.font, c.fill, c.alignment = HEAD_FONT, HEAD_FILL, WRAP_TOP
        ws.column_dimensions[c.column_letter].width = width
    ws.row_dimensions[row].height = 43.5


def detail_rows(system: str) -> list[list]:
    live = live_seconds() if system == "v2" else {}
    rows = []
    for n, rid in runs():
        folder = REPLAY / rid
        recs = {r["id"]: r for r in jsonl(folder / "records.jsonl")}
        if system == "v1":
            sheet = [r for r in read_csv(folder / "owner_grading.csv") if r["system"] == "v1_rules_only"]
        else:
            sheet = [r for r in read_csv(folder / "owner_grading_rag.csv") if r["system"] == "v2_rules_plus_rag"]
        if len(sheet) != 146:
            raise SystemExit(f"run {n}: {len(sheet)} {system} rows, expected 146")
        name = f"{system.upper()} — lần {n}"
        for r in sheet:
            rec = recs[r["id"]]
            secs = rec.get("seconds") or 0.0
            if r["answered_by"] == "rag_live":
                secs += live[r["id"]]
            ai, human, score = ai_label(r), human_label(r), float(r["auto_correct"] or 0)
            reason = r["judge_reason"] or ("Yes/No: chấm theo Đúng/Sai (polarity)" if not r["judge_label"] else "")
            if system == "v1" and r["answered_by"] != "rules":
                # V1's definition: a question the rules did not decide counts as wrong, whatever the judge said
                note = "Luật không quyết định → V1 tính Sai."
                reason = f"{note} {reason}".strip() if ai != "Sai" else (reason or note)
                ai, score = "Sai", 0.0
                if not (r.get("human_score") or "").strip():
                    human = "Sai"
            rows.append([name, n, r["id"], rec["image_id"], r["question_type"], r["question"], r["gold_answer"],
                         r["system_answer"], ai, human, score, reason,
                         round(secs, 2), r["answered_by"], r["trigger"] or "", r.get("human_note") or ""])
    return rows


def build(system: str) -> Path:
    rows = detail_rows(system)
    last = len(rows) + 1
    wb = Workbook()
    summ = wb.active
    summ.title = "Tong hop"
    det = wb.create_sheet("Chi tiet")
    meth = wb.create_sheet("Phuong phap")

    # ---------------------------------------------------------------- Chi tiet
    header(det, 1, DETAIL)
    for i, row in enumerate(rows, 2):
        for j, v in enumerate(row, 1):
            c = det.cell(row=i, column=j, value=v)
            c.alignment = WRAP_TOP
        det.cell(row=i, column=11).number_format = "0.00"
        det.cell(row=i, column=13).number_format = "0.00"
    det.freeze_panes = "D2"
    det.auto_filter.ref = f"A1:P{last}"
    dv = DataValidation(type="list", formula1='"Đúng,Một phần,Sai"', allow_blank=False)
    dv.add(f"J2:J{last}")
    det.add_data_validation(dv)
    for text, colour in (("Đúng", "FFD9EAD3"), ("Sai", "FFF4CCCC"), ("Một phần", "FFFFF2CC")):
        det.conditional_formatting.add(f"J2:J{last}", FormulaRule(formula=[f'J2="{text}"'],
                                                                   fill=PatternFill("solid", bgColor=colour)))

    # ---------------------------------------------------------------- Tong hop
    title = {"v1": "Natural private test — V1, rules only (neuro-symbolic), 3 lượt, phase52",
             "v2": "Natural private test — V2, rules + RAG fallback (live), 3 lượt, phase52"}[system]
    summ["A2"] = title
    summ["A2"].font = Font(bold=True, size=15, color=NAVY)
    header(summ, 4, SUMMARY)
    rng = lambda col: f"'Chi tiet'!${col}$2:${col}${last}"
    run_list = runs()
    secs_by_run = {n: [r[12] for r in rows if r[1] == n] for n, _ in run_list}
    for k, (n, rid) in enumerate(run_list):
        r = 5 + k
        name = f"{system.upper()} — lần {n}"
        summ.cell(row=r, column=1, value=name)
        summ.cell(row=r, column=2, value=n)
        key = f"{rng('A')},$A{r},{rng('B')},$B{r}"
        for col, lab in ((3, "Đúng"), (4, "Một phần"), (5, "Sai")):
            summ.cell(row=r, column=col, value=f'=COUNTIFS({key},{rng("J")},"{lab}")')
        summ.cell(row=r, column=6, value=f"=IFERROR(C{r}/K{r},0)")
        summ.cell(row=r, column=7, value=f"=IFERROR((C{r}+0.5*D{r})/K{r},0)")
        summ.cell(row=r, column=8, value=f"=AVERAGEIFS({rng('M')},{rng('A')},$A{r},{rng('B')},$B{r})")
        summ.cell(row=r, column=9, value=round(statistics.median(secs_by_run[n]), 2))
        summ.cell(row=r, column=10, value=round(sum(secs_by_run[n]) / 60, 2))
        summ.cell(row=r, column=11, value=f"=COUNTIFS({key})")
        for col, lab in ((12, "Đúng"), (13, "Một phần"), (14, "Sai")):
            summ.cell(row=r, column=col, value=f'=COUNTIFS({key},{rng("I")},"{lab}")')
        summ.cell(row=r, column=15, value=f"=IFERROR(L{r}/K{r},0)")
        summ.cell(row=r, column=16, value=f"=IFERROR((L{r}+0.5*M{r})/K{r},0)")
        rules = f'{key},{rng("N")},"rules"'
        summ.cell(row=r, column=17, value=f"=COUNTIFS({rules})")
        summ.cell(row=r, column=18, value=f'=IFERROR((COUNTIFS({rules},{rng("J")},"Đúng")'
                                          f'+0.5*COUNTIFS({rules},{rng("J")},"Một phần"))/Q{r},0)')
        summ.cell(row=r, column=19, value=f'=IFERROR((COUNTIFS({rules},{rng("I")},"Đúng")'
                                          f'+0.5*COUNTIFS({rules},{rng("I")},"Một phần"))/Q{r},0)')
    first, lastrun = 5, 4 + len(run_list)
    for r, label, fn in ((lastrun + 1, "Trung bình 3 lượt", "AVERAGE"), (lastrun + 2, "Độ lệch chuẩn", "STDEV")):
        summ.cell(row=r, column=1, value=label).font = Font(bold=True)
        for col in (6, 7, 8, 15, 16, 17, 18, 19):
            L = summ.cell(row=4, column=col).column_letter
            summ.cell(row=r, column=col, value=f"={fn}({L}{first}:{L}{lastrun})").font = Font(bold=True)
    for r in range(first, lastrun + 3):
        for col in (6, 7, 15, 16, 18, 19):
            summ.cell(row=r, column=col).number_format = "0.0%"
        for col in (8, 9, 10):
            summ.cell(row=r, column=col).number_format = "0.00"

    # by question type
    t0 = lastrun + 4
    summ.cell(row=t0, column=1, value="Theo loại câu hỏi").font = Font(bold=True, color=NAVY)
    header(summ, t0 + 1, [("Cấu hình", 22), ("Lượt", 8), ("Loại câu hỏi", 12), ("Số câu", 12), ("Người chấm điểm TB", 14),
                          ("AI điểm TB", 14)])
    r = t0 + 2
    for n, _ in run_list:
        for qt in ("Yes/No", "Natural QA"):
            summ.cell(row=r, column=1, value=f"{system.upper()} — lần {n}")
            summ.cell(row=r, column=2, value=n)
            summ.cell(row=r, column=3, value=qt)
            key = f'{rng("A")},$A{r},{rng("B")},$B{r},{rng("E")},$C{r}'
            summ.cell(row=r, column=4, value=f"=COUNTIFS({key})")
            summ.cell(row=r, column=5, value=f'=IFERROR((COUNTIFS({key},{rng("J")},"Đúng")'
                                             f'+0.5*COUNTIFS({key},{rng("J")},"Một phần"))/D{r},0)')
            summ.cell(row=r, column=6, value=f'=IFERROR((COUNTIFS({key},{rng("I")},"Đúng")'
                                             f'+0.5*COUNTIFS({key},{rng("I")},"Một phần"))/D{r},0)')
            for col in (5, 6):
                summ.cell(row=r, column=col).number_format = "0.0%"
            r += 1

    # info block
    info = r + 1
    header(summ, info, [("Thông tin", 22), ("Giá trị", 88)])
    ids = ", ".join(f"lần {n} = {rid}" for n, rid in run_list)
    notes = [
        ("Dữ liệu", "VLSP2025 MLQA-Natural private test: 146 câu (70 Yes/No, 76 Natural QA); 3 lượt chạy trên cùng cấu hình đóng băng phase52."),
        ("Các lượt", ids + "."),
        ("Hệ thống", {"v1": "Neuro-symbolic, chỉ luật: perception Haiku 5.5 (scene v5 + guide), parser v18, engine Prolog, writer v3; "
                             "câu không quyết định được trả lời mẫu \"Chưa xác định\" và tính Sai.",
                      "v2": "Neuro-symbolic + RAG fallback: câu luật quyết định giữ câu trả lời của luật; câu có trigger "
                             "(out of scope, unknown, unreadable sign, ...) lấy câu trả lời RAG chạy live (Qwen3.5-9B Q4_K_M, cấu hình C)."}[system]),
        ("Chấm AI", "Yes/No: theo Đúng/Sai (polarity) của câu trả lời so với đáp án. Natural QA: judge/v1, Claude Opus 5.5 "
                    "(correct / partial / wrong)."),
        ("Quy đổi điểm", "Đúng=1; Một phần=0,5; Sai=0. Tỷ lệ đúng = đúng/146; điểm TB = (đúng + 0,5×một phần)/146. "
                         "Người chấm khởi tạo giống AI chấm; sửa cột Người chấm ở sheet Chi tiet, các công thức tự cập nhật."),
        ("Câu rules", "Cột \"Trả lời bởi\" = rules: câu do luật quyết định (có proof và trích dẫn)"
                      + ("; rag_live: câu do RAG trả lời." if system == "v2" else "; not_decided: luật không quyết định.")),
        ("Latency", "Giây/câu của pipeline neuro-symbolic" + (" cộng thời gian RAG live (caption + embedding + retrieval + answer) "
                                                             "với câu do RAG trả lời." if system == "v2" else ".")),
    ]
    for k, (a, b) in enumerate(notes, 1):
        summ.cell(row=info + k, column=1, value=a).alignment = WRAP_TOP
        summ.cell(row=info + k, column=2, value=b).alignment = WRAP_TOP

    # ---------------------------------------------------------------- Phuong phap
    header(meth, 1, [("Phương pháp", 25), ("Chi tiết", 115)])
    method = [
        ("Dữ liệu", "VLSP2025 MLQA-Natural private test; 146 câu; 3 lượt chạy độc lập (scene cache mới mỗi lượt) trên bản đóng băng phase52 (eval/frozen_phase52.json)."),
        ("Hệ thống", notes[2][1]),
        ("Rubric AI", notes[3][1]),
        ("Người chấm", "Cột Người chấm ban đầu sao chép AI chấm (hoặc điểm người chấm đã có trong CSV). Chọn Đúng / Một phần / Sai trong danh sách."),
        ("Lặp lại giữa lượt", "Câu trả lời khác nhau giữa các lượt vì perception, parser và writer gọi Claude; "
                              + ("câu trả lời RAG giống nhau giữa các lượt (RAG tất định)." if system == "v2" else "mỗi lượt cần chấm riêng.")),
        ("Nguồn", "Sinh từ owner_grading.csv / owner_grading_rag.csv của từng lượt (cache/private_run/<run_id>/) bằng eval/owner_workbooks.py."),
        ("Giới hạn", "Chấm theo đáp án tham chiếu private; không mở lại ảnh để xác minh nhãn. Điểm AI là tham khảo; điểm báo cáo là điểm người chấm."),
    ]
    for k, (a, b) in enumerate(method, 2):
        meth.cell(row=k, column=1, value=a).alignment = WRAP_TOP
        meth.cell(row=k, column=2, value=b).alignment = WRAP_TOP

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{system.upper()}_private_benchmark.xlsx"
    wb.save(path)
    print(f"{system.upper()}: {len(rows)} rows ({len(run_list)} runs) -> {path}")         # counts only
    return path


def main() -> None:
    if not ignored(OUT / "probe.xlsx"):
        raise SystemExit("git does not ignore the replay folder: the workbooks must stay local")
    for system in ("v1", "v2"):
        build(system)


if __name__ == "__main__":
    sys.exit(main())
