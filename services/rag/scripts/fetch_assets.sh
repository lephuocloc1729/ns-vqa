#!/usr/bin/env bash
# Get services/rag's runtime assets, every file checked against assets_manifest.json.
#
#   bash scripts/fetch_assets.sh --bundle rag_assets.tar   # index, caches, train file (private bundle)
#   bash scripts/fetch_assets.sh --links                   # dataset links into ns-vqa's copy
#   bash scripts/fetch_assets.sh --cuda [--bf16]           # weights + llama.cpp (CUDA machines only)
#
# The dataset itself is not downloaded: ns-vqa expects it at VLSP2025-MLQA-Natural/
# (or $VQA_DATASET_DIR), and the links point there.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python3}

want_bundle=""; want_links=0; want_cuda=0; want_bf16=0
while [ $# -gt 0 ]; do
  case "$1" in
    --bundle) want_bundle="$2"; shift 2 ;;
    --links) want_links=1; shift ;;
    --cuda) want_cuda=1; shift ;;
    --bf16) want_bf16=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ -n "$want_bundle" ]; then
  echo "== unpacking $want_bundle"
  tar -xf "$want_bundle" -C .
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
  "$PY" - "$want_bf16" <<'EOF'
import hashlib, json, subprocess, sys, tarfile
from pathlib import Path
want_bf16 = sys.argv[1] == "1"
m = json.loads(Path("assets_manifest.json").read_text(encoding="utf-8"))
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""): h.update(c)
    return h.hexdigest()
for d in m["downloads"]:
    if d.get("optional") and not want_bf16:
        continue
    p = Path(d["path"]); p.parent.mkdir(parents=True, exist_ok=True)
    if not (p.is_file() and p.stat().st_size == d["bytes"]):
        print("  downloading", d["url"])
        subprocess.run(["curl", "-fL", "-C", "-", "-o", str(p), d["url"]], check=True)
    got = sha(p)
    if got != d["sha256"]:
        sys.exit(f"refusing: {p} has sha256 {got}, the manifest pins {d['sha256']}")
    print("  ok:", p)
    if "unpack_to" in d:
        dest = Path(d["unpack_to"]); dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(p) as t:
            for member in t.getmembers():
                name = member.name.split("/", 1)[1] if member.name.startswith(d["strip"] + "/") else member.name
                if not name or name.startswith(("/", "..")) or "/../" in name:
                    continue
                member.name = name
                t.extract(member, dest, filter="tar")
        print("  unpacked into", dest)
EOF
fi

"$PY" scripts/verify_assets.py $([ "$want_cuda" = 1 ] && echo --cuda)
