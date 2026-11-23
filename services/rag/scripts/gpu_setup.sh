#!/usr/bin/env bash
# Set up the RAG service on a fresh GPU machine, in one command.
#
#   bash scripts/gpu_setup.sh [--bf16] [--eval]
#
# --eval also fetches rag_eval_bundle: the public-test caches and data, for evaluation runs of the
# batch runner (--split public_test) and the runbook's comparison checks. The RAG service needs
# neither; without --eval no test-split file reaches the machine.
#
# Hugging Face access, with no interactive login: set HF_TOKEN (a read-only token) when the
# container starts, e.g. in the vast.ai template's environment variables. The script also
# reads HF_TOKEN and RAG_ASSETS_REPO from the container's start environment (/proc/1/environ),
# because vast.ai passes them to the container but not always to SSH shells. A saved
# `hf auth login` works too. The token is never printed or written by this script.
# RAG_ASSETS_REPO defaults to lephuocloc/ns-vqa-rag-assets.
#
# Works in the GPU image (ghcr.io/<owner>/ns-vqa-rag, packages and llama.cpp already in it)
# and on a plain CUDA machine (packages installed with uv, llama.cpp downloaded).
# Steps, overlapped where they can be:
#   background: the Qwen weights (Hugging Face) and llama.cpp (GitHub), sha256-checked
#   foreground: Python packages if missing, then the asset bundle from the private repo
#   then: unpack, check every file against assets_manifest.json, report GPU and timing
set -euo pipefail
cd "$(dirname "$0")/.."

# Variables the container was started with (vast.ai -e / template env) that this shell lacks.
load_container_env() {
  local src=${CONTAINER_ENV_FILE:-/proc/1/environ} kv key
  [ -r "$src" ] || return 0
  while IFS= read -r -d '' kv; do
    key=${kv%%=*}
    case "$key" in
      HF_TOKEN|RAG_ASSETS_REPO) [ -z "${!key:-}" ] && export "$kv" ;;
    esac
  done < "$src"
}
load_container_env
export RAG_ASSETS_REPO=${RAG_ASSETS_REPO:-lephuocloc/ns-vqa-rag-assets}
BF16="" EVAL=""
for arg in "$@"; do
  case "$arg" in
    --bf16) BF16="--bf16" ;;
    --eval) EVAL=1 ;;
    *) echo "unknown option: $arg (expected --bf16, --eval)"; exit 2 ;;
  esac
done
PY=${PY:-python3}
# CUDA images often mark their Python as externally managed (PEP 668); torch lives there, so install into it.
export PIP_BREAK_SYSTEM_PACKAGES=1 UV_BREAK_SYSTEM_PACKAGES=1
mkdir -p logs dist
t0=$SECONDS
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || { echo "no NVIDIA GPU"; exit 1; }

echo "== background: weights and llama.cpp"
"$PY" scripts/fetch.py models $BF16 > logs/fetch_models.log 2>&1 & MODELS=$!
"$PY" scripts/fetch.py llama > logs/fetch_llama.log 2>&1 & LLAMA=$!

echo "== Python packages"
if "$PY" -c "import torch, sentence_transformers, fastapi, huggingface_hub; assert torch.__version__.startswith('2.14.1')" 2>/dev/null; then
  echo "   present (GPU image)"
else
  "$PY" -m pip install -q uv
  "$PY" -m uv pip install --system "torch==2.14.1" --index-url https://download.pytorch.org/whl/cu130
  "$PY" -m uv pip install --system -e '.[service]' "transformers==4.56.2" "sentence-transformers==5.1.1" \
    "huggingface_hub[cli]>=0.34"
fi

echo "== Hugging Face access"
if ! "$PY" -c "import sys; from huggingface_hub import get_token; sys.exit(0 if get_token() else 1)"; then
  echo "   no token: set HF_TOKEN (read-only) in the instance's environment, or run: hf auth login"
  kill $MODELS $LLAMA 2>/dev/null || true
  exit 1
fi
echo "   token found ($( [ -n "${HF_TOKEN:-}" ] && echo HF_TOKEN || echo saved login ))"

fetch_bundle() {   # fetch_bundle <name>: download, check its sha256, unpack in place
  echo "== $1 from $RAG_ASSETS_REPO"
  "$PY" - "$RAG_ASSETS_REPO" "$1" <<'EOF'
import hashlib, json, sys
from huggingface_hub import hf_hub_download
repo, name = sys.argv[1], sys.argv[2]
paths = {n: hf_hub_download(repo, n, repo_type="dataset", local_dir="dist") for n in (f"{name}.json", f"{name}.tar.gz")}
record = json.load(open(paths[f"{name}.json"]))
h = hashlib.sha256()
with open(paths[f"{name}.tar.gz"], "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
        h.update(chunk)
if h.hexdigest() != record["sha256"]:
    sys.exit(f"refusing the bundle: sha256 {h.hexdigest()} != {record['sha256']}")
print(f"   ok: {record['members']} files, sha256 {record['sha256'][:16]}")
EOF
  tar -xzf "dist/$1.tar.gz" -C .
}
fetch_bundle rag_bundle
if [ -n "$EVAL" ]; then fetch_bundle rag_eval_bundle; fi

echo "== waiting for the background downloads"
wait $MODELS || { echo "weights failed; see logs/fetch_models.log"; exit 1; }
wait $LLAMA || { echo "llama.cpp failed; see logs/fetch_llama.log"; exit 1; }

echo "== checking every file"
"$PY" scripts/verify_assets.py --cuda --no-private ${EVAL:+--with-public}
echo "== ready in $((SECONDS - t0)) s. Start the service with:"
echo "   uvicorn --factory text_based_rag.service_api:create_app --host 0.0.0.0 --port 8100"
