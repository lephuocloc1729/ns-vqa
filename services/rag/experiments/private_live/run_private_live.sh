#!/usr/bin/env bash
# The live RAG fallback run on the private test (NewNeuroSymbolic docs/plans/rag-fallback.md, F4.3).
#
# Runs the pinned configuration C (Qwen3.5-9B Q4_K_M, f2llm-v2-0.6b, 5 image few-shots) live on
# the private questions the neuro-symbolic rules left undecided (their ids only, exported by
# the rules repo). No cache is used for the private questions (owner, 2026-11-21): they are
# captioned and embedded live. The offline index stays as a deployment would have it: the law
# corpus chunks and vectors, the train example bank's captions and embeddings.
#   1. live captions for the triggered private questions (one warm llama-server, each timed)
#   2. live question embeddings: a one-at-a-time timer, then the runner's cache format
#   3. retrieval + answer: the runner, reading the live private captions and embeddings
#      (--query-embeddings-dir) and the hash-verified offline index
#   4. collect: one rag_live.jsonl (answers + per-stage seconds) for the rules repo's merge
#
#   bash experiments/private_live/run_private_live.sh <triggered_ids.json> [out_dir]
set -euo pipefail
IDS=$(realpath "$1")
cd "$(dirname "$0")/../.."
PY=${PY:-.venv/bin/python}
OUT=${2:-outputs/private_live}
DATA=data/raw/VLSP2025-MLQA-Natural/dataset
if [ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then
  echo "refusing: $OUT is not empty (the live run happens once; choose a new folder)" >&2
  exit 1
fi
mkdir -p "$OUT"
cp "$IDS" "$OUT/ids.json"

echo "== 1 live captions, triggered private questions"
$PY experiments/latency/caption_live.py --split private_test --ids "$OUT/ids.json" --out "$OUT/captions"

echo "== 2a live embeddings, one question at a time (timing)"
$PY experiments/latency/embed_timing.py --split private_test --ids "$OUT/ids.json" \
  --captions "$OUT/captions" --out "$OUT/embed_timing"

echo "== 2b live embeddings in the runner's cache format"
$PY -m text_based_rag.natural_qa_runner --dataset-root "$DATA" \
  --split private_test --ids "$OUT/ids.json" --embedding-only \
  --embedding-model f2llm-v2-0.6b --embedding-dtype bf16 \
  --caption-dir "$OUT/captions" --output-dir "$OUT/query_embeddings" --allow-incomplete-captions

echo "== 3 retrieval + answer, config C, live private captions and embeddings"
$PY -m text_based_rag.natural_qa_runner \
  --dataset-root "$DATA" --split private_test --ids "$OUT/ids.json" \
  --output-dir "$OUT/answers" --embedding-model f2llm-v2-0.6b --embedding-dtype bf16 \
  --answer-model qwen3.5-9b-gguf \
  --corpus-chunks artifacts/experiments/text_based_rag/natural_qa/t768_o64/f2llm-v2-0.6b/train \
  --reuse-precomputed-embeddings --query-embeddings-dir "$OUT/query_embeddings" \
  --fresh-captions --allow-incomplete-captions --caption-dir "$OUT/captions" \
  --fewshot-k 5 --answer-with-images \
  --context-size 65536 --current-context-budget 20000 --answer-max-tokens 2048 \
  --corpus-k 5 --examples-k 4 --high-examples-k 3 \
  --gate-low 0.70 --gate-high 0.7835 \
  --weight-high 0.87 --weight-middle 0.05 --weight-low 0.40 2>&1 | tee "$OUT/answers.log"

echo "== 4 collect"
$PY experiments/private_live/collect.py --live "$OUT" --log "$OUT/answers.log"
echo PRIVATE_LIVE_DONE
