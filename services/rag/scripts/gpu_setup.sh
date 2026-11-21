#!/usr/bin/env bash
# Set up the RAG service on a fresh GPU machine, in one command.
#
#   export RAG_ASSETS_REPO=<hf-user>/ns-vqa-rag-assets     # the private dataset repo with the bundle
#   hf auth login                                         # once, on the machine (or export HF_TOKEN)
#   bash scripts/gpu_setup.sh [--bf16]
#
# Works in the GPU image (ghcr.io/<owner>/ns-vqa-rag, packages and llama.cpp already in it)
# and on a plain CUDA machine (packages installed with uv, llama.cpp downloaded).
# Steps, overlapped where they can be:
#   background: the Qwen weights (Hugging Face) and llama.cpp (GitHub), sha256-checked
#   foreground: Python packages if missing, then the asset bundle from the private repo
#   then: unpack, check every file against assets_manifest.json, report GPU and timing
set -euo pipefail
cd "$(dirname "$0")/.."
: "${RAG_ASSETS_REPO:?set RAG_ASSETS_REPO to the private Hugging Face dataset repo, e.g. user/ns-vqa-rag-assets}"
BF16=""
[ "${1:-}" = "--bf16" ] && BF16="--bf16"
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

echo "== asset bundle from $RAG_ASSETS_REPO"
"$PY" - "$RAG_ASSETS_REPO" <<'EOF'
import hashlib, json, sys
from huggingface_hub import hf_hub_download
repo = sys.argv[1]
paths = {n: hf_hub_download(repo, n, repo_type="dataset", local_dir="dist") for n in ("rag_bundle.json", "rag_bundle.tar.gz")}
record = json.load(open(paths["rag_bundle.json"]))
h = hashlib.sha256()
with open(paths["rag_bundle.tar.gz"], "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
        h.update(chunk)
if h.hexdigest() != record["sha256"]:
    sys.exit(f"refusing the bundle: sha256 {h.hexdigest()} != {record['sha256']}")
print(f"   ok: {record['members']} files, sha256 {record['sha256'][:16]}")
EOF
tar -xzf dist/rag_bundle.tar.gz -C .

echo "== waiting for the background downloads"
wait $MODELS || { echo "weights failed; see logs/fetch_models.log"; exit 1; }
wait $LLAMA || { echo "llama.cpp failed; see logs/fetch_llama.log"; exit 1; }

echo "== checking every file"
"$PY" scripts/verify_assets.py --cuda --no-private
echo "== ready in $((SECONDS - t0)) s. Start the service with:"
echo "   uvicorn --factory text_based_rag.service_api:create_app --host 0.0.0.0 --port 8100"
