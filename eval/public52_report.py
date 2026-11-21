"""One report for the whole public test on phase52 (owner, 2026-11-21): public_dev and
public_holdout together, rules only (V1), rules + RAG fallback (V2) and RAG alone, from the two
runs of `eval/e2e_public_dev52.py` and their merges. No API call: it reads the runs' records
(`records.jsonl`) and merge records (`merge_records.jsonl`) and recomputes the figures.

Both halves may be read question by question (CLAUDE.md, owner 2026-11-21). The rules' grades
come from each run, the RAG's from each merge; nothing is re-judged.

    .venv/bin/python eval/public52_report.py --dev eval/runs/public_dev52/<run_id> \\
        --holdout eval/runs/public_holdout52/<run_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import e2e_private as ep  # noqa: E402
from eval import e2e_private_rag as er  # noqa: E402

OUT = ROOT / "eval" / "runs" / "public52_report.json"
HALVES = ("public_dev", "public_holdout")


def jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def _strict(question_type: str, correct: float | None, label: str | None) -> float | None:
    if correct is None:
        return None
    if question_type == "Yes/No":
        return float(correct)
    return 1.0 if label == "correct" else 0.0


def half(folder: Path) -> dict[str, Any]:
    """One half's rows: the run's records (V1) joined with its merge records (V2, RAG alone)."""
    folder = Path(folder)
    agg = json.loads((folder / "aggregate.json").read_text(encoding="utf-8"))
    if not (folder / "merge_records.jsonl").exists():
        raise SystemExit(f"{folder.name}: no merge records yet; run the merge for this half first")
    recs = {r["id"]: r for r in jsonl(folder / "records.jsonl")}
    merged = {r["id"]: r for r in jsonl(folder / "merge_records.jsonl")}
    if set(recs) != set(merged):
        raise SystemExit(f"{folder.name}: the run and its merge cover different questions")
    v1, v2, b2 = [], [], []
    for i in sorted(recs):
        r, m = recs[i], merged[i]
        v1.append({k: r.get(k) for k in ep._KEEP})
        base = {"question_type": r["question_type"], "trigger": r["trigger"]}
        rag = {**base, "correct": m["rag_correct"], "judge_label": m.get("rag_judge_label"),
               "strict": _strict(r["question_type"], m["rag_correct"], m.get("rag_judge_label"))}
        b2.append(rag)
        if r["trigger"] is None:
            v2.append({**base, "source": "rules", "correct": r["correct"], "strict": r["strict"],
                       "judge_label": r.get("judge_label")})
        else:
            v2.append({**rag, "source": "rag"})
    return {"split": agg.get("split", "public_dev"), "run_id": agg["run_id"], "git_commit": agg.get("git_commit"),
            "spent_usd": agg.get("spent_usd"), "v1": v1, "v2": v2, "b2": b2}


def _clean(v1_agg: dict) -> dict:
    v1_agg.pop("by_images", None)
    v1_agg.get("rules_only", {}).pop("by_images", None)
    return v1_agg


def figures(v1: list[dict], v2: list[dict], b2: list[dict]) -> dict[str, Any]:
    ro = _clean(ep.aggregate(v1))["rules_only"]
    rag = er.aggregate(v2, b2)
    return {"questions": len(v1),
            "v1_rules_only": {k: ro[k] for k in ro if k not in ("by_images",)},
            "v2_rules_plus_rag_fallback": rag["v2_rules_plus_rag_fallback"],
            "b2_rag_alone": rag["b2_rag_alone"], "same_questions": rag["same_questions"]}


def build(dev: Path, holdout: Path, out: Path = OUT) -> Path:
    halves = [half(dev), half(holdout)]
    if [h["split"] for h in halves] != list(HALVES):
        raise SystemExit(f"expected a public_dev run then a public_holdout run, got {[h['split'] for h in halves]}")
    report = {"what": "phase52 on the whole public test: public_dev + public_holdout, V1, V2 and RAG alone",
              "runs": {h["split"]: {"run_id": h["run_id"], "git_commit": h["git_commit"], "spent_usd": h["spent_usd"]}
                       for h in halves},
              "public_test": figures(*(sum((h[k] for h in halves), []) for k in ("v1", "v2", "b2"))),
              **{h["split"]: figures(h["v1"], h["v2"], h["b2"]) for h in halves}}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return Path(out)


def table(report: dict) -> str:
    """The headline table, as Markdown."""
    pct = lambda x: "–" if x is None else f"{100 * x:.1f}%"   # noqa: E731
    lines = ["| | " + " | ".join(("public_test", *HALVES)) + " |", "|---|---|---|---|"]
    cols = [report["public_test"], report["public_dev"], report["public_holdout"]]
    rows = [("questions", lambda f: str(f["questions"])),
            ("V1 decided coverage", lambda f: pct(f["v1_rules_only"]["decided_coverage"])),
            ("V1 accuracy on decided", lambda f: pct(f["v1_rules_only"]["accuracy_on_decided"])),
            ("V1 overall (non-decided wrong)", lambda f: pct(f["v1_rules_only"]["overall_non_decided_wrong"])),
            ("**V2 rules + RAG fallback**", lambda f: pct(f["v2_rules_plus_rag_fallback"]["overall"])),
            ("RAG alone", lambda f: pct(f["b2_rag_alone"]["overall"])),
            ("rules vs RAG on decided", lambda f: f"{pct(f['same_questions']['rules_decided']['v2_rules']['overall'])} vs "
                                                  f"{pct(f['same_questions']['rules_decided']['rag_alone']['overall'])}"),
            ("V2 vs RAG alone, McNemar p", lambda f: "–" if f["same_questions"]["all"]["paired"]["mcnemar_exact_p"] is None
                                                     else f"{f['same_questions']['all']['paired']['mcnemar_exact_p']:.2f}")]
    for name, fn in rows:
        lines.append(f"| {name} | " + " | ".join(fn(c) for c in cols) + " |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", type=Path, required=True)
    ap.add_argument("--holdout", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    out = build(a.dev, a.holdout, a.out)
    print(table(json.loads(out.read_text(encoding="utf-8"))))
    print(f"\nreport -> {out}")


if __name__ == "__main__":
    main()
