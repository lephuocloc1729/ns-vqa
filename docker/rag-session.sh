#!/usr/bin/env bash
# Connect the demo server's API to the RAG on a rented GPU, and back (docs/runbooks/gpu-session.md).
#
#   bash docker/rag-session.sh key               # once: the server's own SSH key; prints its public half
#   bash docker/rag-session.sh on <host> <port>  # the GPU's SSH address, as vast.ai shows it
#   bash docker/rag-session.sh status
#   bash docker/rag-session.sh off               # after the session, before destroying the GPU
#
# `on` writes the GPU's address and COMPOSE_PROFILES=rag-tunnel to .env, starts the rag-tunnel service
# (one SSH connection, nothing published on the server) and waits for the RAG to answer /health
# through it. Only then it sets the live settings answer_fallback=rag and rag_url=http://rag-tunnel:8100
# (app/api/live.py; the admin site shows and changes the same ones). They apply from the next
# question, without restarting the API, so answers in progress are never cut off. `off` sets the
# fallback back to off and stops the tunnel. The RAG answer cache follows its own live setting.
set -euo pipefail
cd "$(dirname "$0")/.."
KEY=secrets/rag_tunnel_ed25519

envget() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
envset() { sed -i "/^$1=/d" .env; echo "$1=$2" >> .env; }
envdel() { sed -i "/^$1=/d" .env; }

live() {      # live settings in the API's database: applied from the next question, no restart
  docker compose exec -T api python -m app.api.live "$@"
}

api_get() {   # api_get <url>: GET from inside the API container (the stack's internal network)
  docker compose exec -T api python -c "import sys, urllib.request; print(urllib.request.urlopen(sys.argv[1], timeout=10).read().decode())" "$1"
}

case "${1:-}" in
  key)
    if [ ! -f "$KEY" ]; then
      mkdir -p secrets && chmod 700 secrets
      ssh-keygen -q -t ed25519 -N "" -C "signcite-server rag-tunnel" -f "$KEY"
      chmod 600 "$KEY"
      echo "created $KEY"
    fi
    echo "Add this public key to vast.ai (Account > SSH keys), so every rented machine accepts it:"
    cat "$KEY.pub"
    ;;
  on)
    host=${2:?usage: rag-session.sh on <host> <port>} port=${3:?usage: rag-session.sh on <host> <port>}
    [ -f "$KEY" ] || { echo "no server key yet: run  bash docker/rag-session.sh key"; exit 1; }
    envset RAG_SSH_HOST "$host"
    envset RAG_SSH_PORT "$port"
    envset COMPOSE_PROFILES rag-tunnel
    docker compose up -d --no-build --force-recreate rag-tunnel
    echo "waiting for the RAG through the tunnel (the GPU's service must already be up)..."
    ok=""
    for _ in $(seq 1 40); do
      if docker compose exec -T rag-tunnel wget -q -O - http://127.0.0.1:8100/health 2>/dev/null | grep -q '"ok"'; then
        ok=1; break
      fi
      sleep 3
    done
    if [ -z "$ok" ]; then
      echo "the RAG did not answer through the tunnel; the API is left as it was. Tunnel log:"
      docker compose logs --no-color --tail=20 rag-tunnel
      exit 1
    fi
    live set answer_fallback=rag rag_url=http://rag-tunnel:8100
    api_get http://rag-tunnel:8100/version | head -c 160; echo
    api_get http://127.0.0.1:8000/version
    echo "on: undecided questions go to the RAG on $host:$port"
    ;;
  off)
    live set answer_fallback=off
    live reset rag_url > /dev/null
    envdel COMPOSE_PROFILES
    envdel RAG_SSH_HOST
    envdel RAG_SSH_PORT
    docker compose --profile rag-tunnel rm -sf rag-tunnel > /dev/null 2>&1 || true
    api_get http://127.0.0.1:8000/version
    echo "off: the RAG fallback is off and the tunnel is stopped"
    ;;
  status)
    echo "gpu: $(envget RAG_SSH_HOST):$(envget RAG_SSH_PORT)"
    live show
    docker compose --profile rag-tunnel ps rag-tunnel 2>/dev/null || true
    api_get http://127.0.0.1:8000/version
    ;;
  *)
    echo "usage: rag-session.sh key | on <host> <port> | status | off"; exit 2 ;;
esac
