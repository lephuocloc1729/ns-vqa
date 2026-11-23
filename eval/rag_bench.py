"""How many questions the RAG service answers at once on one GPU (owner, 2026-11-23).

Sends public_dev questions with their photos to a running RAG service (through the SSH tunnel)
with C requests in flight, and records answers per minute, time per answer and per stage, the
prompt sizes, the GPU's peak memory and use, and, against a baseline run (C = 1 on the
benchmarked settings), how many answers are identical.

    .venv/bin/python eval/rag_bench.py --label p1 --concurrency 1
    .venv/bin/python eval/rag_bench.py --label p4 --concurrency 4 --baseline p1 \\
        --gpu-ssh "ssh -i ~/.ssh/vast_gpu_ed25519 -p <port> root@<host>"

The service's settings (RAG_LLAMA_PARALLEL, RAG_WORKERS) are set on the GPU machine; this script
only sends questions. Records stay local in eval/runs/rag_bench/ (gitignored).
"""

from __future__ import annotations

import argparse
import json
import shlex
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.e2e_holdout import image_file  # noqa: E402
from eval.e2e_public_dev52 import load_public  # noqa: E402

OUT = ROOT / "eval" / "runs" / "rag_bench"


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else 0.0


class GpuSampler(threading.Thread):
    """nvidia-smi every 2 s over SSH: memory used (MiB) and GPU use (%)."""

    def __init__(self, ssh: str) -> None:
        super().__init__(daemon=True)
        self.cmd = shlex.split(ssh) + ["nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu "
                                       "--format=csv,noheader,nounits"]
        self.samples: list[tuple[int, int, int]] = []
        self.stop = threading.Event()

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                out = subprocess.run(self.cmd, capture_output=True, text=True, timeout=10).stdout.strip()
                used, total, util = (int(float(x)) for x in out.splitlines()[0].split(","))
                self.samples.append((used, total, util))
            except Exception:
                pass
            self.stop.wait(2)


def ask(url: str, q: dict) -> dict:
    path = image_file(q["image_id"])
    t0 = time.monotonic()
    try:
        r = requests.post(url + "/answer", data={"question": q["question"]},
                          files={"image": (path.name, path.read_bytes(), "application/octet-stream")},
                          timeout=900)
        ok = r.status_code == 200
        body = r.json() if ok else {"error": r.text[:300]}
    except Exception as e:
        ok, body = False, {"error": f"{type(e).__name__}: {e}"}
    usage = body.get("usage") or {}
    return {"id": q["id"], "ok": ok, "seconds": round(time.monotonic() - t0, 3), "answer": body.get("answer"),
            "timings": body.get("timings"), "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"), "error": body.get("error")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8100")
    ap.add_argument("--label", required=True)
    ap.add_argument("--concurrency", type=int, required=True)
    ap.add_argument("--n", type=int, default=24, help="questions (public_dev, in id order)")
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--baseline", help="label of a run to compare answers with")
    ap.add_argument("--gpu-ssh", help="ssh command for the GPU machine, to sample nvidia-smi")
    a = ap.parse_args()

    version = requests.get(a.url + "/version", timeout=10).json()
    qs = load_public("public_dev")[: a.n]
    for q in qs[: a.warmup]:                                   # warm caches and kernels, untimed
        ask(a.url, q)
    gpu = GpuSampler(a.gpu_ssh) if a.gpu_ssh else None
    if gpu:
        gpu.start()
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        records = list(ex.map(lambda q: ask(a.url, q), qs))
    wall = time.monotonic() - t0
    if gpu:
        gpu.stop.set()
        gpu.join(5)

    ok = [r for r in records if r["ok"]]
    secs = [r["seconds"] for r in ok]
    stage = {}
    for k in ("caption", "embedding", "retrieval", "answer", "total"):
        xs = [r["timings"][k] for r in ok if r.get("timings") and k in r["timings"]]
        if xs:
            stage[k] = round(statistics.mean(xs), 2)
    summary = {
        "label": a.label, "concurrency": a.concurrency, "questions": len(qs), "answered": len(ok),
        "failed": len(records) - len(ok), "wall_seconds": round(wall, 1),
        "answers_per_minute": round(60 * len(ok) / wall, 2) if wall else 0.0,
        "seconds_p50": round(pct(secs, 50), 2), "seconds_p95": round(pct(secs, 95), 2),
        "seconds_max": round(max(secs), 2) if secs else 0.0, "stage_means": stage,
        "prompt_tokens_max": max((r["prompt_tokens"] or 0) for r in ok) if ok else 0,
        "gpu_mem_peak_mib": max((s[0] for s in gpu.samples), default=None) if gpu else None,
        "gpu_mem_total_mib": gpu.samples[0][1] if gpu and gpu.samples else None,
        "gpu_util_mean": round(statistics.mean(s[2] for s in gpu.samples), 1) if gpu and gpu.samples else None,
        "service_config_version": version.get("config_version"),
    }
    if a.baseline:
        base = {r["id"]: r["answer"] for r in json.loads((OUT / f"{a.baseline}.json").read_text())["records"]}
        same = [r["id"] for r in ok if base.get(r["id"]) is not None and base[r["id"]] == r["answer"]]
        summary["identical_to_baseline"] = f"{len(same)}/{len(ok)}"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.label}.json").write_text(json.dumps({"summary": summary, "records": records},
                                                    ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
