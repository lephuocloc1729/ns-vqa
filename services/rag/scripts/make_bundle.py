"""Pack everything a GPU machine needs from this folder into one compressed file.

    python scripts/make_bundle.py              # -> dist/rag_bundle.tar.gz + dist/rag_bundle.json

Contents (paths relative to services/rag/, unpacked in place by gpu_setup.sh):
- every runtime file of assets_manifest.json except the private-test caches;
- the dataset folders the GPU run reads, stored as real files (here they are links into
  ns-vqa's copy): the train images, the public split, the law file, and the RAG's own
  original train questions.

No private-test file goes in: neither its questions, images, captions nor embeddings.
The weights and llama.cpp are not in it either; they come from their own pinned sources.
dist/rag_bundle.json lists every member with its size and sha256, and the bundle's sha256.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NATURAL = "data/raw/VLSP2025-MLQA-Natural/dataset"
DATASET_DIRS = [f"{NATURAL}/public_test data", f"{NATURAL}/train data/train_images"]
DATASET_FILES = [f"{NATURAL}/law_db/vlsp2025_law.json"]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def members() -> list[str]:
    m = json.loads((ROOT / "assets_manifest.json").read_text(encoding="utf-8"))
    paths = [e["path"] for e in m["files"] if e["kind"] != "cache-private"]
    for d in DATASET_DIRS:
        base = ROOT / d
        paths += sorted(str((base / f.relative_to(base.resolve())).relative_to(ROOT))
                        for f in base.resolve().rglob("*") if f.is_file() and f.name != ".DS_Store")
    paths += DATASET_FILES
    out = sorted(set(paths))
    leaked = [p for p in out if "private" in p.lower()]
    if leaked:
        sys.exit(f"refusing: private-test paths would go into the bundle: {leaked[:3]}")
    return out


def main() -> None:
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / "rag_bundle.tar.gz"
    listing = []
    with tarfile.open(out, "w:gz", compresslevel=6) as tar:
        for rel in members():
            src = (ROOT / rel).resolve()                    # follow the dataset links: store real files
            info = tar.gettarinfo(str(src), arcname=rel)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with open(src, "rb") as f:
                tar.addfile(info, f)
            listing.append({"path": rel, "bytes": src.stat().st_size, "sha256": sha256(src)})
    record = {"bundle": out.name, "bytes": out.stat().st_size, "sha256": sha256(out),
              "members": len(listing), "unpacked_bytes": sum(e["bytes"] for e in listing), "files": listing}
    (dist / "rag_bundle.json").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{out.relative_to(ROOT)}: {record['members']} files, {record['unpacked_bytes'] / 1e6:.1f} MB -> "
          f"{record['bytes'] / 1e6:.1f} MB, sha256 {record['sha256'][:16]}")


if __name__ == "__main__":
    main()
