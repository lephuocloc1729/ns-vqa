"""Download services/rag's pinned files (assets_manifest.json "downloads"), checked by sha256.

    python scripts/fetch.py llama            # llama.cpp b11624 (+ CUDA runtime), unpacked for the runner
    python scripts/fetch.py models [--bf16]  # Qwen3.5-9B Q4_K_M + mmproj (and the BF16 file)

Large files are fetched over several connections at once (some hosts limit each connection
to ~100 KB/s from GitHub), and a partial download resumes. A file whose sha256 differs from
the manifest is refused. Unpacked llama.cpp gets a marker with the tarball's sha256, so a
second run (or the GPU image, which unpacks it at build time) skips it.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "assets_manifest.json").read_text(encoding="utf-8"))
PARTS = 16


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, out: Path, size: int) -> None:
    """Parallel ranged download straight into `out`: each connection writes its own byte range
    in place, so the disk never holds more than the file itself. `<out>.progress` records each
    range's progress, so an interrupted download resumes where it stopped."""
    import threading
    out.parent.mkdir(parents=True, exist_ok=True)
    progress = out.with_name(out.name + ".progress")
    if out.exists() and out.stat().st_size == size and not progress.exists():
        return
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD",
                                                       headers={"User-Agent": "ns-vqa-fetch"})) as r:
        final = r.geturl()
    n = PARTS if size > 64 * 1024 * 1024 else 1
    step = -(-size // n)
    done = json.loads(progress.read_text()) if progress.exists() else [0] * n
    if len(done) != n or not out.exists() or out.stat().st_size != size:
        done = [0] * n
        with open(out, "wb") as f:            # a sparse file of the final size
            f.truncate(size)
    lock = threading.Lock()

    def save() -> None:
        with lock:
            progress.write_text(json.dumps(done))

    def part(i: int) -> None:
        lo, hi = i * step, min(size, (i + 1) * step) - 1
        start = lo + done[i]
        if start > hi:
            return
        req = urllib.request.Request(final, headers={"Range": f"bytes={start}-{hi}", "User-Agent": "ns-vqa-fetch"})
        with urllib.request.urlopen(req, timeout=60) as r, open(out, "r+b") as f:
            f.seek(start)
            since = 0
            while chunk := r.read(1 << 16):
                f.write(chunk)
                done[i] += len(chunk)
                since += len(chunk)
                if since >= 64 << 20:
                    f.flush()
                    save()
                    since = 0
            f.flush()
        save()

    save()
    for attempt in range(30):
        try:
            with cf.ThreadPoolExecutor(n) as ex:
                list(ex.map(part, range(n)))
            break
        except OSError as e:
            print(f"  retry {attempt + 1}: {e}", flush=True)
    else:
        sys.exit(f"download failed: {url}")
    progress.unlink()


def get(entry: dict) -> Path:
    p = ROOT / entry["path"]
    unfinished = p.with_name(p.name + ".progress").exists()      # the file has its final size from the start
    if unfinished or not (p.is_file() and p.stat().st_size == entry["bytes"]):
        print(f"downloading {entry['url']}", flush=True)
        download(entry["url"], p, entry["bytes"])
    got = sha256(p)
    if got != entry["sha256"]:
        sys.exit(f"refusing {p}: sha256 {got}, the manifest pins {entry['sha256']}")
    print(f"ok {entry['path']}", flush=True)
    return p


def unpack(entry: dict, tarball: Path) -> None:
    dest = ROOT / entry["unpack_to"]
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball) as t:
        for m in t.getmembers():
            name = m.name.split("/", 1)[1] if m.name.startswith(entry["strip"] + "/") else m.name
            if not name or name.startswith(("/", "..")) or "/../" in name:
                continue
            m.name = name
            t.extract(m, dest, filter="tar")
    (dest / f".verified-{entry['sha256'][:16]}").write_text(entry["sha256"] + "\n")
    print(f"unpacked into {entry['unpack_to']}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("llama", "models"))
    ap.add_argument("--bf16", action="store_true", help="also the BF16 GGUF (17.9 GB, Q4 vs BF16 only)")
    ap.add_argument("--keep-tarballs", action="store_true")
    a = ap.parse_args()
    for d in MANIFEST["downloads"]:
        is_llama = "unpack_to" in d
        if (a.what == "llama") != is_llama or (d.get("optional") and not a.bf16):
            continue
        if is_llama:
            marker = ROOT / d["unpack_to"] / f".verified-{d['sha256'][:16]}"
            if marker.exists():
                print(f"ok {d['unpack_to']} (already unpacked from {d['sha256'][:16]})", flush=True)
                continue
            tarball = get(d)
            unpack(d, tarball)
            if not a.keep_tarballs:
                tarball.unlink()
        else:
            get(d)
    server = ROOT / ".venv/tools/llama.cpp-b11624/llama-server"
    if a.what == "llama" and server.exists():
        os.chmod(server, 0o755)


if __name__ == "__main__":
    main()
