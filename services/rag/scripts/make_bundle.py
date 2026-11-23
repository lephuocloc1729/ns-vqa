"""Pack what a GPU machine needs from this folder into compressed files.

    python scripts/make_bundle.py              # -> dist/rag_bundle.* and dist/rag_eval_bundle.*

Two bundles (paths relative to services/rag/, unpacked in place by gpu_setup.sh):
- **rag_bundle** (every session; what the RAG service needs, and no test-split file):
  - every runtime file of assets_manifest.json except the test-split caches;
  - the train images, the law file, and the RAG's own original train questions;
  - the train images and the law file are stored as real files (here they are links into
    ns-vqa's copy of the dataset).
- **rag_eval_bundle** (only with `gpu_setup.sh --eval`): the public-test caches and the public
  test data, for evaluation runs of the batch runner (`--split public_test`) and the runbook's
  comparison checks.

No private-test file goes in either: neither its questions, images, captions nor embeddings.
The weights and llama.cpp are not in them either; they come from their own pinned sources.
dist/<bundle>.json lists every member with its size and sha256, and the bundle's sha256.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NATURAL = "data/raw/VLSP2025-MLQA-Natural/dataset"
SERVICE_DIRS = [f"{NATURAL}/train data/train_images"]
SERVICE_FILES = [f"{NATURAL}/law_db/vlsp2025_law.json"]
EVAL_DIRS = [f"{NATURAL}/public_test data"]
TEST_WORDS = ("private", "public", "test")   # no service member may have these in its path


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def files_in(dirs: list[str]) -> list[str]:
    out = []
    for d in dirs:
        base = ROOT / d
        out += sorted(str((base / f.relative_to(base.resolve())).relative_to(ROOT))
                      for f in base.resolve().rglob("*") if f.is_file() and f.name != ".DS_Store")
    return out


def members(which: str) -> list[str]:
    m = json.loads((ROOT / "assets_manifest.json").read_text(encoding="utf-8"))
    if which == "service":
        paths = [e["path"] for e in m["files"] if e["kind"] not in ("cache-private", "cache-public")]
        paths += files_in(SERVICE_DIRS) + SERVICE_FILES
        out = sorted(set(paths))
        leaked = [p for p in out if any(w in p.lower() for w in TEST_WORDS)]
        if leaked:
            sys.exit(f"refusing: test-split paths would go into the service bundle: {leaked[:3]}")
    else:
        paths = [e["path"] for e in m["files"] if e["kind"] == "cache-public"] + files_in(EVAL_DIRS)
        out = sorted(set(paths))
    private = [p for p in out if "private" in p.lower()]
    if private:
        sys.exit(f"refusing: private-test paths would go into the {which} bundle: {private[:3]}")
    return out


def pack(name: str, paths: list[str]) -> dict:
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / f"{name}.tar.gz"
    listing = []
    with tarfile.open(out, "w:gz", compresslevel=6) as tar:
        for rel in paths:
            src = (ROOT / rel).resolve()                    # follow the dataset links: store real files
            info = tar.gettarinfo(str(src), arcname=rel)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with open(src, "rb") as f:
                tar.addfile(info, f)
            listing.append({"path": rel, "bytes": src.stat().st_size, "sha256": sha256(src)})
    record = {"bundle": out.name, "bytes": out.stat().st_size, "sha256": sha256(out),
              "members": len(listing), "unpacked_bytes": sum(e["bytes"] for e in listing), "files": listing}
    (dist / f"{name}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{out.relative_to(ROOT)}: {record['members']} files, {record['unpacked_bytes'] / 1e6:.1f} MB -> "
          f"{record['bytes'] / 1e6:.1f} MB, sha256 {record['sha256'][:16]}")
    return record


def main() -> None:
    pack("rag_bundle", members("service"))
    pack("rag_eval_bundle", members("eval"))


if __name__ == "__main__":
    main()
