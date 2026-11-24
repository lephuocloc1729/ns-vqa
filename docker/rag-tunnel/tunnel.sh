#!/bin/sh
# The rag-tunnel service: one SSH connection from this server to a rented GPU, forwarding the RAG's
# port (8100) to the stack's internal network only (http://rag-tunnel:8100; nothing is published).
#
# It runs all the time and follows the target the API writes (docs/plans/admin-page.md, PR 2):
#   $DIR/target   "host port", written by the API (admin site → Cài đặt → GPU, or rag-session.sh);
#                 empty or missing: no connection (standby)
#   $DIR/state    what it is doing, for the API: standby | no_key | connecting | connected | error
#                 (one line: state|target|detail)
#   $DIR/server_key.pub   the server's public key, to add to the GPU provider once
# The API never controls Docker; this loop is the only thing that starts or stops the connection.
#
# The key is the server's own (secrets/rag_tunnel_ed25519, made by `rag-session.sh key`). vast.ai gives
# each machine new host keys, so a new target's key is accepted on first use (known hosts are per target).
set -u
DIR=${TUNNEL_DIR:-/run/signcite-gpu}
KEY=${TUNNEL_KEY:-/run/rag-secrets/rag_tunnel_ed25519}
PORT=${TUNNEL_PORT:-8100}

state() {   # state <state> [detail]
  printf '%s|%s|%s\n' "$1" "$cur" "${2:-}" > "$DIR/.state.tmp" && mv "$DIR/.state.tmp" "$DIR/state"
}

stop_ssh() {
  if [ -n "$pid" ]; then kill "$pid" 2> /dev/null; wait "$pid" 2> /dev/null; fi
  pid=""
}

mkdir -p "$DIR"
chmod 1777 "$DIR" 2> /dev/null || true   # the API (another user) writes the target here
command -v ssh > /dev/null || apk add --no-cache openssh-client > /dev/null 2>&1 || true
[ -f "$KEY.pub" ] && cp "$KEY.pub" "$DIR/server_key.pub"
touch /tmp/alive
trap 'stop_ssh; exit 0' TERM INT

pid=""; cur=""; tries=0; next=0
while :; do
  want=$(head -n 1 "$DIR/target" 2> /dev/null | tr -s ' ' | sed 's/^ //; s/ $//')
  if [ "$want" != "$cur" ]; then        # a new target, or none: drop the old connection at once
    stop_ssh; cur=$want; tries=0; next=0
    rm -f /tmp/known_hosts
  fi
  if [ -z "$cur" ]; then state standby; sleep 2; continue; fi
  if ! command -v ssh > /dev/null; then state error "no ssh client (apk add failed)"; sleep 10
    apk add --no-cache openssh-client > /dev/null 2>&1 || true; continue; fi
  if [ ! -f "$KEY" ]; then state no_key "no server key: run docker/rag-session.sh key"; sleep 5; continue; fi
  host=${cur% *}; port=${cur#* }
  if [ -z "$pid" ] || ! kill -0 "$pid" 2> /dev/null; then
    if [ -n "$pid" ]; then              # it ended: say why, then retry with a growing pause
      wait "$pid" 2> /dev/null; pid=""
      state error "$(tail -n 1 /tmp/ssh.log 2> /dev/null | cut -c1-200)"
      tries=$((tries + 1)); next=$(( $(date +%s) + (tries < 6 ? tries * 5 : 30) ))
    fi
    if [ "$(date +%s)" -ge "$next" ]; then
      state connecting
      ssh -N -i "$KEY" -p "$port" \
        -o BatchMode=yes -o ConnectTimeout=15 \
        -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/tmp/known_hosts \
        -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
        -o GatewayPorts=yes -L "0.0.0.0:$PORT:127.0.0.1:$PORT" "root@$host" 2> /tmp/ssh.log &
      pid=$!
    fi
  elif wget -q -T 3 -O /dev/null "http://127.0.0.1:$PORT/health" 2> /dev/null; then
    state connected; tries=0
  else
    state connecting "the SSH connection is up; waiting for the RAG to answer /health"
  fi
  sleep 3
done
