"""Latency, step 2: time the live question embedding, one question at a time.

Loads the F2LLM encoder once (as a running service would), then embeds each question's
representation (question + its live caption) on its own and records the wall time. Writes
the vectors in the runner's query-embedding cache format, so the answer step can use these
live embeddings instead of the old cache, and one timing line per question.

    python experiments/latency/embed_timing.py --captions outputs/latency/captions \
        --out outputs/latency/query_embeddings --split public_test
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from text_based_rag import inference as qa
from text_based_rag import natural_qa_runner as runner

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--captions", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--split", default="public_test")
    ap.add_argument("--dataset-root", type=Path, default=ROOT / "data/raw/VLSP2025-MLQA-Natural/dataset")
    ap.add_argument("--ids", type=Path, default=None, help="embed only these question ids (the runner's --ids)")
    a = ap.parse_args()
    if a.ids:
        runner.set_id_filter(a.ids)
    runner.np = np                                   # the runner sets this global in main()
    _, rows = runner.load_rows(a.dataset_root.resolve(), a.split)
    mapping = {m["query_id"]: m for m in map(json.loads, (a.captions / "query_image_mapping.jsonl").read_text(
        encoding="utf-8-sig").splitlines()) if m}
    t0 = time.perf_counter()
    encoder = runner.NaturalEncoder("f2llm-v2-0.6b", "bf16")
    load_seconds = time.perf_counter() - t0
    encoder.encode(["khởi động"], role="query")      # one warm-up call, not timed
    a.out.mkdir(parents=True, exist_ok=True)
    timings = []
    for row in rows:
        caption = json.loads((a.captions / mapping[row["id"]]["caption_file"]).read_text(encoding="utf-8-sig"))
        rep = qa.query_representation(row["question"].strip(), caption, row["id"], allow_incomplete=True)
        start = time.perf_counter()
        vector = encoder.encode([rep["text"]], role="query")[0]
        seconds = time.perf_counter() - start
        timings.append({"id": row["id"], "embed_seconds": seconds, "vector": vector.tolist(),
                        "representation": rep})
    with open(a.out / "embed_timing.jsonl", "w", encoding="utf-8") as f:
        for t in timings:
            f.write(json.dumps({"id": t["id"], "embed_seconds": t["embed_seconds"]}) + "\n")
    with open(a.out / "live_vectors.jsonl", "w", encoding="utf-8") as f:
        for t in timings:
            f.write(json.dumps({"id": t["id"], "representation": t["representation"], "vector": t["vector"]},
                               ensure_ascii=False) + "\n")
    s = sorted(t["embed_seconds"] for t in timings)
    print(json.dumps({"questions": len(s), "model_load_seconds": round(load_seconds, 2),
                      "embed_mean_s": round(sum(s) / len(s), 4), "embed_p50_s": round(s[len(s) // 2], 4),
                      "embed_max_s": round(s[-1], 4)}, indent=2))


if __name__ == "__main__":
    main()
