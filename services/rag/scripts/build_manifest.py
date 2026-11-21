"""Build assets_manifest.json: every runtime file config C needs, with its size and sha256.

    python scripts/build_manifest.py runtime_list.txt      # run from services/rag/

runtime_list.txt holds the paths (relative to services/rag/) that a traced config C
run opened, outside src/, experiments/ and the dataset. The dataset layout, the
downloads and the environment are fixed below. Writes assets_manifest.json.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NATURAL = "data/raw/VLSP2025-MLQA-Natural/dataset"
# Links into ns-vqa's own copy of the dataset (identical files). The train questions
# are not linked: the RAG index was built from the original train file (2026-11-05),
# and ns-vqa holds the owner's rewrite of 2026-11-15.
DATASET_LINKS = {
    f"{NATURAL}/law_db": "../../../../../../VLSP2025-MLQA-Natural/dataset/law_db",
    f"{NATURAL}/public_test data": "../../../../../../VLSP2025-MLQA-Natural/dataset/public_test data",
    f"{NATURAL}/private_test data (post submission)":
        "../../../../../../VLSP2025-MLQA-Natural/dataset/private_test data (post submission)",
    f"{NATURAL}/train data/train_images":
        "../../../../../../../VLSP2025-MLQA-Natural/dataset/train data/train_images",
}
DATASET_OWN = [f"{NATURAL}/train data/vlsp_2025_train.json"]

QWEN = "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/3885219b6810b007914f3a7950a8d1b469d598a5"
LLAMA = "https://github.com/ggml-org/llama.cpp/releases/download/b11624"
DOWNLOADS = [
    {"path": "models/huggingface/Qwen3.5-9B-GGUF/Qwen3.5-9B-Q4_K_M.gguf", "url": f"{QWEN}/Qwen3.5-9B-Q4_K_M.gguf",
     "bytes": 5680522464, "sha256": "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8"},
    {"path": "models/huggingface/Qwen3.5-9B-GGUF/mmproj-F16.gguf", "url": f"{QWEN}/mmproj-F16.gguf",
     "bytes": 918166080, "sha256": "f70dc3509053962b0d0d3ee8a7eacebf5d60aa560cad78254ae8698516ae029f"},
    {"path": "models/huggingface/Qwen3.5-9B-GGUF/Qwen3.5-9B-BF16.gguf", "url": f"{QWEN}/Qwen3.5-9B-BF16.gguf",
     "bytes": 17920697312, "sha256": "daebe40eeea7057c1cdf35ac56d13f507d8bf12171bbb7a6b6b0d3f05439159a",
     "optional": "only for the Q4 vs BF16 comparison"},
    {"path": "downloads/llama-b11624-bin-ubuntu-cuda-12.8-x64.tar.gz",
     "url": f"{LLAMA}/llama-b11624-bin-ubuntu-cuda-12.8-x64.tar.gz",
     "bytes": 171630261, "sha256": "a63b56fceb6002c6ce4f3bc0d887a37b7962fe257891a5ba9ae1d105bad74baa",
     "unpack_to": ".venv/tools/llama.cpp-b11624", "strip": "llama-b11624"},
    {"path": "downloads/cudart-llama-b11624-bin-ubuntu-cuda-12.8-x64.tar.gz",
     "url": f"{LLAMA}/cudart-llama-b11624-bin-ubuntu-cuda-12.8-x64.tar.gz",
     "bytes": 594377811, "sha256": "a2f14f43ff0081052933874af8be0bd2cb74f7fb68b840d1fd06ea7d0af070d0",
     "unpack_to": ".venv/tools/llama.cpp-b11624", "strip": "cudart-llama-b11624-bin-ubuntu-cuda-12.8-x64"},
]

NOTES = [
    "Config C (README run command) reads only the files listed under 'files', the dataset and, on CUDA "
    "machines, the downloads. Checked by tracing file opens (2026-11-21).",
    "The query/ caches pinned in some run_config.json files (artifacts/experiments/text_based_rag/query/...) are "
    "provenance only: config C runs with --fresh-captions and never reads them. The older non-fresh pipelines "
    "(load_existing_captions, query_embedding.py, query_retrieval.py) cannot be re-run from these assets.",
    "The f2llm-v2-0.6b encoder (codefuse-ai/F2LLM-v2-0.6B) is loaded without a pinned revision, so the revision "
    "used by the saved runs is unknown; it matters only for live query embeddings, not for runs that reuse the "
    "cached embeddings listed here.",
    "Weights and llama.cpp are needed on CUDA machines only; scripts/fetch_assets.sh downloads and checks them.",
]

ENVIRONMENT = {
    "gpu": {"python": "3.12.3", "torch": "2.14.1+cu130 (https://download.pytorch.org/whl/cu130)",
            "numpy": "2.5.4", "Pillow": "13.0.0", "requests": "2.34.2", "llama.cpp": "b11624",
            "driver": "580.178.04 (RTX 5090), as recorded by the saved runs"},
    "mac": {"python": "3.11", "packages": "numpy, requests, pillow (no PyTorch): retrieval-only and checks"},
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def kind(path: str) -> str:
    if path.startswith("artifacts/private_test/"):
        return "cache-private"
    if path.startswith("artifacts/public-test/"):
        return "cache-public"
    if path.startswith("artifacts/"):
        return "index"
    if path.startswith("data/"):
        return "law"
    return "other"


def main(listing: str) -> None:
    paths = sorted({ln.strip() for ln in Path(listing).read_text(encoding="utf-8").splitlines() if ln.strip()})
    files = []
    for p in paths + DATASET_OWN:
        f = ROOT / p
        files.append({"path": p, "bytes": f.stat().st_size, "sha256": sha256(f),
                      "kind": "dataset" if p in DATASET_OWN else kind(p)})
    manifest = {
        "version": 1,
        "root": "services/rag",
        "config": "C (pinned F1 flags; README run command)",
        "notes": NOTES,
        "files": files,
        "dataset_links": DATASET_LINKS,
        "downloads": DOWNLOADS,
        "environment": ENVIRONMENT,
    }
    out = ROOT / "assets_manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{out.name}: {len(files)} files, {sum(f['bytes'] for f in files)} bytes, "
          f"{len(DATASET_LINKS)} dataset links, {len(DOWNLOADS)} downloads")


if __name__ == "__main__":
    main(sys.argv[1])
