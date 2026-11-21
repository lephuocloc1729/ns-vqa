"""Latency, step 1: caption each Natural QA question live, timing each request.

Same model, projector, prompt, schema and request settings as the caption artifacts the
runner uses (`query_image_captioning`, llama.cpp backend), but reading the Natural question
file (the existing captioning CLI reads the TSR copy, a different file). One llama-server is
started once and kept warm, as a deployed service would. Writes a caption folder in the
format the runner validates (manifest, query_image_mapping.jsonl, captions/), with each
caption's own `elapsed_seconds`.

    python experiments/latency/caption_live.py --split public_test --out outputs/latency/captions
"""

from __future__ import annotations

import argparse
import base64
import json
import socket
import subprocess
import time
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

from text_based_rag import natural_qa_runner as runner
from text_based_rag import query_image_captioning as cap
from text_based_rag.corpus_embedding import file_hash

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = {"public_test": ROOT / "artifacts/public-test/text_based_rag/natural_qa/image_captioning",
             "private_test": ROOT / "artifacts/private_test/text_based_rag/natural_qa/image_captioning",
             "train": ROOT / "artifacts/experiments/text_based_rag/natural_qa/image_captioning/train"}


def valid(description: str) -> bool:
    try:
        p = json.loads(description)
    except json.JSONDecodeError:
        return False
    return (isinstance(p, dict) and set(p) == {"image_category", "summary", "items"}
            and p["image_category"] in cap.IMAGE_CATEGORIES and isinstance(p["summary"], str) and p["summary"].strip()
            and isinstance(p["items"], list)
            and all(isinstance(s, dict) and set(s) == {*cap.ITEM_FIELDS, "is_relevant"}
                    and all(isinstance(s[k], str) and s[k].strip() for k in cap.ITEM_FIELDS)
                    and type(s["is_relevant"]) is bool for s in p["items"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="public_test", choices=sorted(REFERENCE))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dataset-root", type=Path, default=ROOT / "data/raw/VLSP2025-MLQA-Natural/dataset")
    ap.add_argument("--ids", type=Path, default=None, help="caption only these question ids (the runner's --ids)")
    a = ap.parse_args()
    id_filter = runner.set_id_filter(a.ids) if a.ids else None
    source, rows = runner.load_rows(a.dataset_root.resolve(), a.split)
    reference = json.loads((REFERENCE[a.split] / "manifest.json").read_text(encoding="utf-8-sig"))
    settings = dict(reference["settings"])
    if settings.get("prompt") != cap.QUERY_PROMPT or settings.get("max_new_tokens") != cap.MAX_NEW_TOKENS:
        raise SystemExit("the caption prompt or token limit differs from the reference artifacts")
    settings.update(model=str(cap.CORPUS_MODEL), projector=str(cap.PROJECTOR))
    out = a.out.resolve()
    (out / "captions").mkdir(parents=True, exist_ok=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    log = (out / "llama-server.log").open("w", encoding="utf-8")
    t_load = time.perf_counter()
    proc = subprocess.Popen([str(cap.SERVER), "-m", str(cap.CORPUS_MODEL), "--mmproj", str(cap.PROJECTOR),
                             "--host", "127.0.0.1", "--port", str(port), "-c", str(settings["context_size"]),
                             "-ngl", "all", "--parallel", "1", "--jinja", "--reasoning", "off"],
                            stdout=log, stderr=subprocess.STDOUT)
    started_at = datetime.now(timezone.utc).isoformat()
    mapping, incomplete = [], []
    try:
        while True:
            if proc.poll() is not None:
                raise RuntimeError("llama-server stopped; see llama-server.log")
            try:
                if requests.get(url + "/health", timeout=2).status_code == 200:
                    break
            except requests.ConnectionError:
                pass
            if time.perf_counter() - t_load > 180:
                raise TimeoutError("caption model not ready after 180 s")
            time.sleep(1)
        load_seconds = time.perf_counter() - t_load
        t_all = time.perf_counter()
        for n, row in enumerate(rows, 1):
            path = Path(row["image"])
            image_id = "sha256:" + sha256(path.read_bytes()).hexdigest()
            start = time.perf_counter()
            with Image.open(path) as original, BytesIO() as buf:
                with original.convert("RGB") as im:
                    im.save(buf, format="PNG")
                encoded = base64.b64encode(buf.getvalue()).decode("ascii")
            prompt = cap.QUERY_PROMPT.replace("{question_text}", row["question"])
            r = requests.post(url + "/v1/chat/completions", json={
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}},
                    {"type": "text", "text": prompt}]}],
                "temperature": 0, "seed": 2025, "max_tokens": cap.MAX_NEW_TOKENS,
                "chat_template_kwargs": {"enable_thinking": False},
                "response_format": {"type": "json_object", "schema": cap.QUERY_SCHEMA}}, timeout=(10, 900))
            r.raise_for_status()
            g = r.json()
            choice = g["choices"][0]
            description = cap.strip_json_fence(choice["message"]["content"])
            status = "COMPLETED" if valid(description) and choice.get("finish_reason") == "stop" else "INCOMPLETE"
            caption_file = f"captions/{row['id']}_description.json"
            result = {"query_id": row["id"], "image_id": image_id, "filename": row["image_id"] + ".jpg",
                      "question_text": row["question"], "description": description, "settings": settings,
                      "status": status, "finish_reason": choice.get("finish_reason"),
                      "generated_tokens": g["usage"]["completion_tokens"],
                      "elapsed_seconds": time.perf_counter() - start}
            (out / caption_file).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            mapping.append({"query_id": row["id"], "source_image_id": row["image_id"],
                            "filename": row["image_id"] + ".jpg", "image_id": image_id, "caption_file": caption_file})
            if status != "COMPLETED":
                incomplete.append(row["id"])
            print(f"[caption] {n}/{len(rows)} {result['elapsed_seconds']:.2f}s {status}", flush=True)
        total = time.perf_counter() - t_all
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=20)
        log.close()
    with open(out / "query_image_mapping.jsonl", "w", encoding="utf-8") as f:
        for m in mapping:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    manifest = {"status": "INCOMPLETE" if incomplete else "COMPLETED", "split": a.split, "input": str(source),
                "input_sha256": file_hash(source), "settings": settings, "queries": len(rows),
                "captioned_queries": len(rows) - len(incomplete), "incomplete_queries": incomplete,
                "resources": {"backend": "llama.cpp CUDA", "gpu_layers": "all"},
                "scope": "id_subset" if id_filter else "full_split", "id_filter": id_filter,
                "started_at": started_at, "model_load_seconds": load_seconds, "elapsed_seconds": total,
                "tool": "experiments/latency/caption_live.py (live, one warm server)"}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("status", "queries", "captioned_queries", "model_load_seconds",
                                               "elapsed_seconds")}, indent=2))


if __name__ == "__main__":
    main()
