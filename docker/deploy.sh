#!/usr/bin/env bash
# Runs on the server (from CD, over SSH): install a commit's files, switch `api` and `web` to its
# images, check the stack, and roll back files and images together if the check fails.
#
#   APP_DIR=/opt/signcite bash deploy.sh <api image> <web image> [<files.tar>]
#
# <files.tar> is `git archive` of the commit. Its files replace the ones in APP_DIR; the files they
# replace are saved first, so a rollback restores them (and removes files the commit added). .env
# and the pictogram copies are not in git, so they are never touched.
# The images are recorded in .env (API_IMAGE, WEB_IMAGE), so a manual `docker compose up -d` keeps
# them. The registry login, if one is needed, is done by the caller before this script.
set -euo pipefail
cd "${APP_DIR:-$(dirname "$0")/..}"
API_NEW=$1
WEB_NEW=$2
FILES=${3:-}

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
  # every service except the GPU tunnel, whose health depends on a rented machine being up
  local core
  core=$(docker compose config --services | grep -vx rag-tunnel | tr '\n' ' ')
  # shellcheck disable=SC2086
  docker compose up -d --no-build --wait --wait-timeout 180 $core || return 1
  # Caddy reads its Caddyfile (a mounted file) only at start or on reload: a changed one needs this
  if echo " $core " | grep -q " caddy "; then
    docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile || return 1
  fi
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

# the commit's files: save the ones they replace, note the ones they add, then unpack
SAVE=$(mktemp -d)
trap 'rm -rf "$SAVE"' EXIT
if [ -n "$FILES" ]; then
  tar -tf "$FILES" | grep -v '/$' > "$SAVE/all"
  : > "$SAVE/existing"; : > "$SAVE/added"
  while IFS= read -r f; do
    if [ -e "$f" ]; then echo "$f" >> "$SAVE/existing"; else echo "$f" >> "$SAVE/added"; fi
  done < "$SAVE/all"
  tar -cf "$SAVE/old.tar" --files-from "$SAVE/existing"
  cp -p DEPLOYED_COMMIT "$SAVE/DEPLOYED_COMMIT" 2>/dev/null || true
  tar -xf "$FILES"
  echo "${API_NEW##*:}" > DEPLOYED_COMMIT
  echo "deploy: $(wc -l < "$SAVE/all") files installed ($(wc -l < "$SAVE/added") new)"
fi
envset API_IMAGE "$API_NEW"
envset WEB_IMAGE "$WEB_NEW"

if check; then
  echo "deploy: ok"
  docker image prune -f > /dev/null   # dangling layers only; tagged images (the rollback target) stay
  exit 0
fi

echo "deploy: the check failed; rolling back" >&2
docker compose logs --no-color --tail=80 api web >&2 || true
if [ -n "$FILES" ]; then
  xargs -r -d '\n' rm -f < "$SAVE/added"
  tar -xf "$SAVE/old.tar"
  if [ -f "$SAVE/DEPLOYED_COMMIT" ]; then cp -p "$SAVE/DEPLOYED_COMMIT" DEPLOYED_COMMIT; fi
  echo "deploy: restored the previous files" >&2
fi
envset API_IMAGE "$API_OLD"
envset WEB_IMAGE "$WEB_OLD"
if check; then echo "deploy: rolled back to the previous files and images" >&2; else echo "deploy: ROLLBACK FAILED TOO" >&2; fi
exit 1
