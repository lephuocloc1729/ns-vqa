#!/usr/bin/env bash
# vast.ai on-start: set the machine up and start the RAG service, unattended.
#
#   template On-start script:  bash /app/scripts/onstart.sh
#   template environment:      HF_TOKEN=<read-only token>  (RAG_ASSETS_REPO optional)
#   add --bf16 through RAG_SETUP_ARGS=--bf16 for the Q4 vs BF16 measurement
#
# Progress: /app/logs/onstart.log; the service: /app/logs/service.log; ready when
#   curl localhost:8100/health   says {"status":"ok"}.
cd /app || exit 1
mkdir -p logs
{
  echo "onstart $(date -u +%FT%TZ)"
  if bash scripts/gpu_setup.sh ${RAG_SETUP_ARGS:-}; then
    nohup uvicorn --factory text_based_rag.service_api:create_app --host 0.0.0.0 --port 8100 \
      > logs/service.log 2>&1 < /dev/null &
    echo "service starting (pid $!); see logs/service.log"
  else
    echo "setup failed; the service was not started"
  fi
} >> logs/onstart.log 2>&1
