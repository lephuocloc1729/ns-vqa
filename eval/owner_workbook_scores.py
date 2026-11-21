"""The owner's hand-graded scores from the V1 and V2 workbooks (owner, 2026-11-21). Aggregates only.

For the owner to run in their own terminal: the assistant never reads the grading sheets or the
workbooks (CLAUDE.md). It reads only the grade and bookkeeping columns of `Chi tiet` (Lượt, Loại câu
hỏi, AI chấm, Người chấm, Trả lời bởi), never the question, gold or answer columns, and prints totals
per run, the three-run mean and spread, and how the hand grades moved the judge's. Nothing per question
is printed; paste the output back.

    python3 eval/owner_workbook_scores.py                       # ~/UNIVERSITY/Capstone/owner_workbooks
    python3 eval/owner_workbook_scores.py --dir <folder with V1_/V2_private_benchmark.xlsx>
"""

from __future__ import annotations

import argparse
import statistics
from collections import Counter
from pathlib import Path

POINTS = {"Đúng": 1.0, "Một phần": 0.5, "Sai": 0.0}
DEFAULT_DIR = Path.home() / "UNIVERSITY" / "Capstone" / "owner_workbooks"
# Chi tiet columns (0-based), as eval/owner_workbooks.py writes them
RUN, QTYPE, AI, HUMAN, BY = 1, 4, 8, 9, 13


def rows(path: Path) -> list[tuple]:
    from openpyxl import load_workbook
    ws = load_workbook(path, read_only=True)["Chi tiet"]
    out = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[RUN] is None:
            continue
        out.append((int(r[RUN]), r[QTYPE], r[AI], r[HUMAN], r[BY]))
    return out


def score(rs: list[tuple], col: int) -> float | None:
    return sum(POINTS.get(r[col], 0.0) for r in rs) / len(rs) if rs else None


def pct(x: float | None) -> str:
    return "–" if x is None else f"{100 * x:.1f}%"


def summarize(name: str, rs: list[tuple]) -> list[str]:
    lines = [f"== {name}: {len(rs)} rows; human grade blank or not Đúng/Một phần/Sai: "
             f"{sum(r[3] not in POINTS for r in rs)}"]
    human, ai, human_rules = [], [], []
    for n in sorted({r[0] for r in rs}):
        rr = [r for r in rs if r[0] == n]
        dec = [r for r in rr if r[4] == "rules"]
        rag = [r for r in rr if r[4] == "rag_live"]
        moved = Counter(f"{a}→{h}" for _, _, a, h, _ in rr if a != h)
        h, a, hd = score(rr, 3), score(rr, 2), score(dec, 3)
        human.append(h), ai.append(a), human_rules.append(hd)
        types = ", ".join(f"{t} {pct(score([r for r in rr if r[1] == t], 3))}" for t in ("Yes/No", "Natural QA"))
        part = f"; RAG part ({len(rag)}) {pct(score(rag, 3))}" if rag else ""
        lines.append(f"  run {n}: human {pct(h)} (judge {pct(a)}); changed {sum(moved.values())} "
                     f"{dict(moved)}; rules-decided ({len(dec)}) human {pct(hd)} (judge {pct(score(dec, 2))})"
                     f"{part}; by type: {types}")
    if len(human) > 1:
        sd = lambda xs: statistics.stdev(xs) * 100   # noqa: E731
        lines.append(f"  mean: human {pct(statistics.mean(human))} (sd {sd(human):.1f}), judge "
                     f"{pct(statistics.mean(ai))} (sd {sd(ai):.1f}), rules-decided human "
                     f"{pct(statistics.mean(human_rules))} (sd {sd(human_rules):.1f})")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    a = ap.parse_args()
    for v in ("V1", "V2"):
        p = a.dir / f"{v}_private_benchmark.xlsx"
        if not p.exists():
            print(f"== {v}: {p} not found")
            continue
        print("\n".join(summarize(v, rows(p))))


if __name__ == "__main__":
    main()
