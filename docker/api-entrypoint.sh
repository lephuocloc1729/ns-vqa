#!/bin/sh
# VQA_PIPELINE=fake (the default): the real API code with a fake pipeline. No API key, no
#   law_db figure copies, no Claude spend: what a clean machine runs.
# VQA_PIPELINE=real: the frozen phase52 pipeline. Needs ANTHROPIC_API_KEY and the scene prompt's
#   pictogram copies mounted at prompts/scene/v5/pictograms (see docs/deploy.md).
# API_WORKERS (default 1): server processes. Each process answers one question at a time.
set -e
case "${VQA_PIPELINE:-fake}" in
  fake) exec python web/e2e/fake_api.py --host 0.0.0.0 --port 8000 --workers "${API_WORKERS:-1}" ;;
  real)
    if [ -z "$ANTHROPIC_API_KEY" ]; then echo "VQA_PIPELINE=real needs ANTHROPIC_API_KEY" >&2; exit 1; fi
    if [ ! -f prompts/scene/v5/pictograms.yaml ] || [ -z "$(ls -A prompts/scene/v5/pictograms 2>/dev/null)" ]; then
      echo "VQA_PIPELINE=real needs the pictogram copies mounted at prompts/scene/v5/pictograms" >&2; exit 1
    fi
    exec uvicorn --factory app.api.main:create_app --host 0.0.0.0 --port 8000 --workers "${API_WORKERS:-1}" --proxy-headers \
      --forwarded-allow-ips '*' --timeout-graceful-shutdown 30 ;;
  *) echo "VQA_PIPELINE must be fake or real" >&2; exit 1 ;;
esac
