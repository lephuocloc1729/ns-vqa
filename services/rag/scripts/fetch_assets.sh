#!/usr/bin/env bash
# Get services/rag's runtime assets, every file checked against assets_manifest.json.
#
#   bash scripts/fetch_assets.sh --bundle dist/rag_bundle.tar.gz   # index, caches, train file, images
#   bash scripts/fetch_assets.sh --links                            # dataset links into ns-vqa's copy (Mac)
#   bash scripts/fetch_assets.sh --cuda [--bf16]                    # weights + llama.cpp (CUDA machines only)
#
# On a fresh GPU machine, scripts/gpu_setup.sh does all of it in one go.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python3}

want_bundle=""; want_links=0; want_cuda=0; bf16=""
while [ $# -gt 0 ]; do
  case "$1" in
    --bundle) want_bundle="$2"; shift 2 ;;
    --links) want_links=1; shift ;;
    --cuda) want_cuda=1; shift ;;
    --bf16) bf16="--bf16"; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ -n "$want_bundle" ]; then
  echo "== unpacking $want_bundle"
  tar -xzf "$want_bundle" -C .
fi

if [ "$want_links" = 1 ]; then
  echo "== dataset links"
  "$PY" - <<'EOF'
import json, os
from pathlib import Path
m = json.loads(Path("assets_manifest.json").read_text(encoding="utf-8"))
for link, target in m["dataset_links"].items():
    p = Path(link)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.is_symlink() or p.exists():
        print("  exists:", link)
        continue
    os.symlink(target, p)
    print("  linked:", link, "->", target)
EOF
fi

if [ "$want_cuda" = 1 ]; then
  echo "== weights and llama.cpp"
  "$PY" scripts/fetch.py models $bf16
  "$PY" scripts/fetch.py llama
fi

extra=""
[ "$want_cuda" = 1 ] && extra="--cuda"
[ -n "$want_bundle" ] && extra="$extra --no-private"
"$PY" scripts/verify_assets.py $extra
