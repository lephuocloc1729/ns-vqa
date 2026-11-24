#!/usr/bin/env bash
# Connect the demo server's API to the RAG on a rented GPU, and back (docs/runbooks/gpu-session.md).
#
#   bash docker/rag-session.sh key               # once: the server's own SSH key; prints its public half
#   bash docker/rag-session.sh on <host> <port>  # the GPU's SSH address, as vast.ai shows it
#   bash docker/rag-session.sh status
#   bash docker/rag-session.sh off               # after the session, before destroying the GPU
#
# The rag-tunnel service runs all the time, in standby (docker/rag-tunnel/tunnel.sh). `on` gives it the
# GPU's address (app/api/gpu.py: one SSH connection, nothing published on the server) and waits for
# the RAG to answer /health through it. Only then it sets the live settings answer_fallback=rag and
# rag_url=http://rag-tunnel:8100 (app/api/live.py). They apply from the next question, without
# restarting the API, so answers in progress are never cut off. `off` sets the fallback back to off
# and puts the tunnel back in standby. The admin site (Cài đặt → Máy GPU) does the same with buttons.
set -euo pipefail
cd "$(dirname "$0")/.."
KEY=secrets/rag_tunnel_ed25519

envdel() { sed -i "/^$1=/d" .env; }

live() {      # live settings in the API's database: applied from the next question, no restart
  docker compose exec -T api python -m app.api.live "$@"
}

gpu() {       # the tunnel's target and state (app/api/gpu.py; the admin site shows the same)
  docker compose exec -T api python -m app.api.gpu "$@"
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
    gpu connect "$host" "$port"           # the rag-tunnel service picks the target up by itself
    echo "waiting for the RAG through the tunnel (the GPU's service must already be up)..."
    ok=""
    for _ in $(seq 1 40); do
      if api_get http://rag-tunnel:8100/health 2>/dev/null | grep -q '"ok"'; then ok=1; break; fi
      sleep 3
    done
    if [ -z "$ok" ]; then
      echo "the RAG did not answer through the tunnel; disconnecting, the fallback is left as it was:"
      gpu status
      gpu disconnect > /dev/null
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
    gpu disconnect
    envdel COMPOSE_PROFILES; envdel RAG_SSH_HOST; envdel RAG_SSH_PORT    # left by older versions
    api_get http://127.0.0.1:8000/version
    echo "off: the RAG fallback is off and the tunnel is in standby"
    ;;
  status)
    gpu status
    live show
    api_get http://127.0.0.1:8000/version
    ;;
  *)
    echo "usage: rag-session.sh key | on <host> <port> | status | off"; exit 2 ;;
esac
