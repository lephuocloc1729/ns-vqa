#!/usr/bin/env bash
# Latency without per-question caches (config C, public test, warm models).
# 1. live captions (Qwen, llama.cpp), each caption file records its generation time
# 2. live question embeddings: the runner's embedding-only mode (cache format) + a one-at-a-time timer
# 3. retrieval + answer: the runner, reading only the live captions and live embeddings
# The offline index (law-corpus and train-bank vectors) is reused, as a deployment would.
set -euo pipefail
cd /workspace/rag
PY=.venv-run/bin/python
OUT=outputs/latency
QE=artifacts/public-test/text_based_rag/natural_qa/query_embeddings/f2llm-v2-0.6b
mkdir -p "$OUT"

echo "== 1 live captions"
start=$(date +%s)
$PY experiments/latency/caption_live.py --split public_test --out "$OUT/captions"
echo "captions_wall_seconds=$(( $(date +%s) - start ))"

echo "== 2a live embeddings, one question at a time (timing)"
$PY experiments/latency/embed_timing.py --captions "$OUT/captions" --out "$OUT/embed_timing"

echo "== 2b live embeddings in the runner's cache format"
[ -d "$QE" ] && [ ! -d "$QE.cached_before_latency" ] && mv "$QE" "$QE.cached_before_latency"
start=$(date +%s)
$PY -m text_based_rag.natural_qa_runner --dataset-root data/raw/VLSP2025-MLQA-Natural/dataset \
  --split public_test --embedding-only --embedding-model f2llm-v2-0.6b --embedding-dtype bf16 \
  --caption-dir "$OUT/captions" --output-dir "$QE" --allow-incomplete-captions
echo "embedding_wall_seconds=$(( $(date +%s) - start ))"

echo "== 3 retrieval + answer, config C, live captions and embeddings"
start=$(date +%s)
$PY -m text_based_rag.natural_qa_runner \
  --dataset-root data/raw/VLSP2025-MLQA-Natural/dataset --split public_test \
  --output-dir "$OUT/answers" --embedding-model f2llm-v2-0.6b --embedding-dtype bf16 \
  --answer-model qwen3.5-9b-gguf \
  --corpus-chunks artifacts/experiments/text_based_rag/natural_qa/t768_o64/f2llm-v2-0.6b/train \
  --reuse-precomputed-embeddings --fresh-captions --allow-incomplete-captions \
  --caption-dir "$OUT/captions" \
  --fewshot-k 5 --answer-with-images \
  --context-size 65536 --current-context-budget 20000 --answer-max-tokens 2048 \
  --corpus-k 5 --examples-k 4 --high-examples-k 3 \
  --gate-low 0.70 --gate-high 0.7835 \
  --weight-high 0.87 --weight-middle 0.05 --weight-low 0.40
echo "answer_wall_seconds=$(( $(date +%s) - start ))"
echo LATENCY_DONE
