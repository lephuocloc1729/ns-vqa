#!/usr/bin/env bash
# Runs on the server (from CD, over SSH): switch `api` and `web` to the given images, check the
# stack, and roll back to the previous images if the check fails.
#
#   bash docker/deploy.sh <api image> <web image>
#
# The images are recorded in .env (API_IMAGE, WEB_IMAGE), so a manual `docker compose up -d` keeps
# them. The registry login, if one is needed, is done by the caller before this script.
set -euo pipefail
cd "$(dirname "$0")/.."
API_NEW=$1
WEB_NEW=$2

envget() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
envset() {   # replace or add KEY=VALUE in .env, keeping its permissions
  sed -i "/^$1=/d" .env
  echo "$1=$2" >> .env
}

API_OLD=$(envget API_IMAGE); API_OLD=${API_OLD:-signcite-api:local}
WEB_OLD=$(envget WEB_IMAGE); WEB_OLD=${WEB_OLD:-signcite-web:local}
DOMAIN=$(envget DOMAIN)
echo "deploy: api $API_OLD -> $API_NEW"
echo "deploy: web $WEB_OLD -> $WEB_NEW"

check() {   # the stack is healthy: containers, the API's own health, and the public HTTPS entry
  docker compose up -d --no-build --wait --wait-timeout 180 || return 1
  docker compose exec -T api python -c "
import json, urllib.request
h = json.load(urllib.request.urlopen('http://127.0.0.1:8000/health'))
assert h['status'] == 'ok' and h['database'], h
print('api health', h)" || return 1
  if [ -n "$DOMAIN" ]; then
    curl -fsS --max-time 15 "https://$DOMAIN/healthz" > /dev/null || return 1
    echo "https://$DOMAIN/healthz ok"
  fi
}

# pull first: if the registry fails, nothing on the server has changed (tags are commit shas,
# so an image already on the server is the right one)
for img in "$API_NEW" "$WEB_NEW"; do
  docker image inspect "$img" > /dev/null 2>&1 || docker pull --quiet "$img"
done
envset API_IMAGE "$API_NEW"
envset WEB_IMAGE "$WEB_NEW"

if check; then
  echo "deploy: ok"
  docker image prune -f > /dev/null   # dangling layers only; tagged images (the rollback target) stay
  exit 0
fi

echo "deploy: the check failed; rolling back" >&2
docker compose logs --no-color --tail=80 api web >&2 || true
envset API_IMAGE "$API_OLD"
envset WEB_IMAGE "$WEB_OLD"
if check; then echo "deploy: rolled back to the previous images" >&2; else echo "deploy: ROLLBACK FAILED TOO" >&2; fi
exit 1
