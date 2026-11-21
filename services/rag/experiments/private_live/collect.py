"""The live private run, step 4: one file of answers and per-stage seconds for the rules repo.

Reads the live run's own records (caption files, the embedding timer, the runner's
predictions and run_config.json) and writes, in the run folder:

- `rag_live.jsonl`: one row per question: id, status, answer, caption/embed/answer seconds;
- `rag_live_meta.json`: the run's configuration fingerprint and the retrieval seconds per question.

Model outputs only: the private answers are never read here.

    python experiments/private_live/collect.py --live outputs/private_live --log outputs/private_live/answers.log
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

# run_config.json fields that pin the configuration (plan F1); kept in the meta file.
CONFIG_KEYS = ("embedding_model", "embedding_dtype", "answer_model", "answer_model_id", "answer_dtype",
               "answer_model_file_sha256", "answer_projector_sha256", "fewshot_k", "answer_image_policy",
               "answer_context", "current_context_budget", "answer_max_tokens", "retrieval", "id_filter",
               "corpus_chunk_file_sha256", "example_bank_fingerprint", "gpu")


def jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def retrieval_seconds(log: Path | None) -> float | None:
    if not log or not log.exists():
        return None
    hits = re.findall(r"\[gated-hybrid-natural-bank\] (\d+)/(\d+) \S+ elapsed=(\d+)s", log.read_text())
    if not hits:
        return None
    done, _total, secs = map(int, hits[-1])
    return secs / max(done, 1)


def collect(live: Path, log: Path | None = None) -> tuple[Path, Path]:
    ids = json.loads((live / "ids.json").read_text(encoding="utf-8-sig"))
    caps = {}
    for f in (live / "captions" / "captions").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        caps[d["query_id"]] = (d["elapsed_seconds"], d["status"])
    emb = {r["id"]: r["embed_seconds"] for r in jsonl(live / "embed_timing" / "embed_timing.jsonl")}
    answers_dir = live / "answers" / "private_test"
    preds = {r["id"]: r for r in jsonl(answers_dir / "predictions.jsonl")}
    if set(preds) != set(ids) or set(caps) != set(ids) or set(emb) != set(ids):
        raise SystemExit(f"the live run is incomplete: {len(ids)} ids, {len(caps)} captions, {len(emb)} embeddings, "
                         f"{len(preds)} answers")
    out = live / "rag_live.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for i in ids:
            p = preds[i]
            f.write(json.dumps({"id": i, "status": p["status"], "answer": p.get("answer", ""),
                                "caption_status": caps[i][1], "caption_seconds": round(caps[i][0], 3),
                                "embed_seconds": round(emb[i], 4),
                                "answer_seconds": round(p.get("elapsed_seconds", 0.0), 3)},
                               ensure_ascii=False) + "\n")
    cfg_path = answers_dir / "run_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    meta = {"what": "live RAG fallback run on the triggered private questions (config C, no per-question cache)",
            "status": cfg.get("status"), "questions": len(ids),
            "run_config_sha256": hashlib.sha256(cfg_path.read_bytes()).hexdigest(),
            "config": {k: cfg[k] for k in CONFIG_KEYS if k in cfg},
            "caption_manifest": {k: v for k, v in json.loads((live / "captions" / "manifest.json").read_text(
                encoding="utf-8")).items() if k in ("status", "incomplete_queries", "model_load_seconds",
                                                    "elapsed_seconds", "scope")},
            "retrieval_seconds_per_question": retrieval_seconds(log)}
    meta_path = live / "rag_live_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"questions": len(ids), "completed": sum(preds[i]["status"] == "COMPLETED" for i in ids),
                      "out": str(out)}, indent=2))
    return out, meta_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", type=Path, required=True)
    ap.add_argument("--log", type=Path, default=None)
    a = ap.parse_args()
    collect(a.live.resolve(), a.log)


if __name__ == "__main__":
    main()
