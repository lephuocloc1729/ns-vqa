"""Latency, summary: per-question end-to-end time from the live run's own records.

total_i = caption_i (live caption file) + embed_i (one-at-a-time timer) + retrieval (runner
log, stage time / questions) + answer_i (prediction's elapsed_seconds). Reports mean, p50,
p95 and max for public_dev (the ids in --dev-ids) and the whole public test, plus how many
live answers match the cached config-C answers.

    python experiments/latency/summarize.py --live outputs/latency \
        --cached artifacts/experiments/text_based_rag/natural_qa/answer_comparison/public_configs_C \
        --dev-ids ../NewNeuroSymbolic/eval/runs/kb_articles/public_dev_phase4.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p * (len(xs) - 1)))]


def stats(xs: list[float]) -> dict:
    return {"mean": round(sum(xs) / len(xs), 2), "p50": round(pct(xs, 0.5), 2),
            "p95": round(pct(xs, 0.95), 2), "max": round(max(xs), 2), "n": len(xs)}


def jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", type=Path, required=True)
    ap.add_argument("--cached", type=Path, required=True)
    ap.add_argument("--dev-ids", type=Path, required=True)
    ap.add_argument("--log", type=Path, default=None)
    a = ap.parse_args()
    caps = {}
    for f in (a.live / "captions" / "captions").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        caps[d["query_id"]] = d["elapsed_seconds"]
    emb = {r["id"]: r["embed_seconds"] for r in jsonl(a.live / "embed_timing" / "embed_timing.jsonl")}
    live = {r["id"]: r for r in jsonl(a.live / "answers" / "public_test" / "predictions.jsonl")}
    cached = {r["id"]: r for r in jsonl(a.cached / "public_test" / "predictions.jsonl")}
    retrieval = None
    if a.log and a.log.exists():
        hits = re.findall(r"\[gated-hybrid-natural-bank\] (\d+)/(\d+) \S+ elapsed=(\d+)s", a.log.read_text())
        if hits:
            done, total, secs = map(int, hits[-1])
            retrieval = secs / max(done, 1)
    dev = [json.loads(l)["id"] for l in a.dev_ids.read_text(encoding="utf-8").splitlines() if l.strip()]
    report = {"retrieval_seconds_per_question": round(retrieval, 3) if retrieval is not None else None}
    for name, ids in (("public_dev", dev), ("public_test", list(live))):
        c = [caps[i] for i in ids]
        e = [emb[i] for i in ids]
        an = [live[i]["elapsed_seconds"] for i in ids]
        tot = [caps[i] + emb[i] + (retrieval or 0.0) + live[i]["elapsed_seconds"] for i in ids]
        report[name] = {"caption": stats(c), "embed": stats(e), "answer": stats(an), "total": stats(tot),
                        "answers_identical_to_cached": sum(live[i]["answer"].strip() == cached[i]["answer"].strip()
                                                           for i in ids)}
    print(json.dumps(report, indent=2))
    (a.live / "latency_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
