"""Check services/rag's runtime files against assets_manifest.json.

    python scripts/verify_assets.py            # files and dataset links
    python scripts/verify_assets.py --cuda     # also the weights and llama.cpp
    python scripts/verify_assets.py --quick    # sizes only, no hashing
    python scripts/verify_assets.py --no-private  # a GPU machine set up from the bundle (no private-test files)

Exit code 0 when everything required is present and matches, 1 otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cuda", action="store_true", help="also check the weights and llama.cpp downloads")
    ap.add_argument("--quick", action="store_true", help="check sizes only")
    ap.add_argument("--no-private", action="store_true",
                    help="skip the private-test caches and dataset folder (the GPU bundles leave them out)")
    ap.add_argument("--with-public", action="store_true",
                    help="with --no-private: also check the public-test caches and data (rag_eval_bundle); "
                         "without it a GPU machine has the service bundle only")
    args = ap.parse_args()
    m = json.loads((ROOT / "assets_manifest.json").read_text(encoding="utf-8"))
    problems: list[str] = []

    skip = ({"cache-private"} | (set() if args.with_public else {"cache-public"})) if args.no_private else set()
    files = [e for e in m["files"] if e["kind"] not in skip]
    for e in files:
        p = ROOT / e["path"]
        if not p.is_file():
            problems.append(f"missing: {e['path']}")
        elif p.stat().st_size != e["bytes"]:
            problems.append(f"size differs: {e['path']}")
        elif not args.quick and sha256(p) != e["sha256"]:
            problems.append(f"sha256 differs: {e['path']}")

    for link, target in m["dataset_links"].items():
        if args.no_private and ("private_test" in link or ("public_test" in link and not args.with_public)):
            continue
        p = ROOT / link
        if not p.is_symlink():
            if not p.exists():
                problems.append(f"missing dataset folder: {link} (expected a link to {target})")
        elif not p.resolve().exists():
            problems.append(f"broken dataset link: {link} -> {target}")

    if args.cuda:
        for d in m["downloads"]:
            if d.get("optional"):
                continue
            target = ROOT / d["unpack_to"] / "llama-server" if "unpack_to" in d else ROOT / d["path"]
            if "unpack_to" in d:
                if not target.is_file():
                    problems.append(f"missing: {target.relative_to(ROOT)} (run scripts/fetch_assets.sh)")
                continue
            if not target.is_file():
                problems.append(f"missing: {d['path']} (run scripts/fetch_assets.sh)")
            elif target.stat().st_size != d["bytes"]:
                problems.append(f"size differs: {d['path']}")
            elif not args.quick and sha256(target) != d["sha256"]:
                problems.append(f"sha256 differs: {d['path']}")

    n = len(files)
    if problems:
        print(f"FAILED: {len(problems)} problem(s) in {n} files"
              f"{' + downloads' if args.cuda else ''}:")
        for p in problems[:50]:
            print("  " + p)
        return 1
    print(f"OK: {n} files{' (sizes only)' if args.quick else ''}, {len(m['dataset_links'])} dataset links"
          f"{', downloads' if args.cuda else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
