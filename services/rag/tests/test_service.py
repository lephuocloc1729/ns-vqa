"""The RAG service (ns-vqa plan F2), on any machine: fake llama-servers and encoders, the real
index and train bank (skipped when services/rag's runtime files are absent, as in CI).

    cd services/rag && .venv/bin/python -m pytest -q tests
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from text_based_rag import inference as qa
from text_based_rag import natural_qa_runner as runner
from text_based_rag import service as svc

ROOT = Path(__file__).resolve().parent.parent
ASSETS = (svc.CORPUS_CHUNKS / "corpus_vectors.npy").is_file() and (svc.DATASET / "train data").exists()
needs_assets = pytest.mark.skipif(not ASSETS, reason="services/rag runtime files not present")
PUBLIC_IDS = ["public_natural_0001", "public_natural_0002", "public_natural_0005", "public_natural_0026",
              "public_natural_0043", "public_natural_0097"]
FLAGS_C = ["--embedding-model", "f2llm-v2-0.6b", "--embedding-dtype", "bf16", "--answer-model", "qwen3.5-9b-gguf",
           "--corpus-chunks", str(svc.CORPUS_CHUNKS), "--reuse-precomputed-embeddings", "--fresh-captions",
           "--allow-incomplete-captions", "--fewshot-k", "5", "--context-size", "65536",
           "--current-context-budget", "20000", "--answer-max-tokens", "2048", "--corpus-k", "5", "--examples-k", "4",
           "--high-examples-k", "3", "--gate-low", "0.70", "--gate-high", "0.7835", "--weight-high", "0.87",
           "--weight-middle", "0.05", "--weight-low", "0.40"]


@pytest.fixture(scope="module")
def engine():
    e = svc.RagEngine()
    e.load_bank()
    return e


@pytest.fixture(scope="module")
def public(engine):
    """Public rows with their cached captions and query embeddings (the saved runs' inputs)."""
    _, rows = runner.load_rows(engine.root, "public_test")
    args = SimpleNamespace(split="public_test", caption_dir=None, train_caption_dir=None,
                           allow_incomplete_captions=True)
    captions, _ = runner.load_fresh_caption_artifacts(rows, engine.root, "public_test", args, qa)
    rows = [r for r in rows if r["id"] in PUBLIC_IDS]       # the caption check needs the whole split first
    path = ROOT / "artifacts/public-test/text_based_rag/natural_qa/query_embeddings/f2llm-v2-0.6b/embeddings.jsonl"
    cached = {r["id"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r["id"] in PUBLIC_IDS}
    return rows, captions, cached


# ---------------------------------------------------------------------- retrieval = the runner's
@needs_assets
def test_retrieval_matches_the_runners_own_run(engine, public, tmp_path):
    rows, captions, cached = public
    subprocess.run([sys.executable, "-m", "text_based_rag.natural_qa_runner", "--dataset-root", str(svc.DATASET),
                    "--split", "public_test", "--output-dir", str(tmp_path / "out"), *FLAGS_C, "--retrieval-only"],
                   cwd=ROOT, check=True, capture_output=True)
    expected = {r["id"]: r["retrieval"] for r in map(
        json.loads, (tmp_path / "out/public_test/retrievals.jsonl").read_text(encoding="utf-8").splitlines())}
    assert set(PUBLIC_IDS) <= set(expected)
    for row in rows:
        rep = engine.represent(row["question"], captions[row["id"]], row["id"])
        assert rep == cached[row["id"]]["representation"]
        got = engine.retrieve(np.asarray(cached[row["id"]]["vector"], dtype=np.float32), rep["text"],
                              row["question"], row["id"])
        assert len(got.pop("fewshot_neighbors")) == 5
        assert got == expected[row["id"]], row["id"]


# ---------------------------------------------------------------------- answer = answer_rows
class FakeAnswerServer:
    """apply-template/tokenize count characters; generate returns a reply derived from the messages."""
    url = "http://fake"

    def __init__(self):
        self.calls = []

    def launch(self, *a, **k): pass
    def close(self): pass

    def post(self, endpoint, payload):
        if endpoint == "/apply-template":
            return {"prompt": json.dumps(payload["messages"], ensure_ascii=False)}
        return {"tokens": list(range(len(payload["content"]) // 4))}

    def generate(self, messages, schema, max_tokens):
        self.calls.append(messages)
        h = hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()[:8]
        return {k: f"{k} {h}" for k in qa.FIELDS}, {"completion_tokens": 7}


@needs_assets
def test_answer_one_gives_the_runners_prediction(engine, public):
    rows, captions, cached = public
    engine.answer_server = FakeAnswerServer()
    for row in rows[:3]:
        rep = engine.represent(row["question"], captions[row["id"]], row["id"])
        vec = np.asarray(cached[row["id"]]["vector"], dtype=np.float32)
        retrieval = engine.retrieve(vec, rep["text"], row["question"], row["id"])
        mine = engine.answer_one(row, rep["text"], retrieval)
        theirs = runner.answer_rows(svc.MemoryRun(), [row], {row["id"]: rep}, {row["id"]: {"retrieval": retrieval}},
                                    engine.registry, FakeAnswerServer(), svc._NoProgress(), 65536, 2048,
                                    engine.fewshot_data, 20000, True)[row["id"]]
        for k in ("elapsed_seconds",):
            mine.pop(k), theirs.pop(k)
        theirs = {k: v for k, v in theirs.items() if k not in ("id", "image_id", "question", "image")}
        assert mine == theirs, row["id"]
        assert mine["fewshot_used_ids"] and mine["answer"].startswith("final_answer")


# ---------------------------------------------------------------------- streaming = generate
REPLY = {"visual_matching": "Biển tròn", "legal_rule_extraction": "B.31", "option_evaluation": "đúng",
         "final_answer": 'Đây là biển "cấm đỗ xe ngày chẵn".\nÁp dụng 24 giờ.'}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        text = json.dumps(REPLY, ensure_ascii=True)
        if not body.get("stream"):
            out = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": text}}],
                              "usage": {"completion_tokens": 40}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        pieces = [text[i:i + 3] for i in range(0, len(text), 3)]
        for p in pieces:
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': p}, 'finish_reason': None}]})}\n\n".encode())
        self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})}\n\n".encode())
        self.wfile.write(f"data: {json.dumps({'choices': [], 'usage': {'completion_tokens': 40}})}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


@pytest.fixture
def llama():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s = runner.Server()
    s.url = f"http://127.0.0.1:{srv.server_address[1]}"
    yield s
    srv.shutdown()


def test_streaming_gives_the_same_payload_as_generate(llama):
    plain, usage = llama.generate([{"role": "user", "content": "x"}], svc.ANSWER_SCHEMA, 100)
    deltas = []
    streamed, usage2 = svc.generate_streaming(llama, [{"role": "user", "content": "x"}], svc.ANSWER_SCHEMA, 100,
                                              deltas.append)
    assert streamed == plain == REPLY and usage2 == usage
    fs = svc.FinalAnswerStream()
    assert "".join(fs.feed(d) for d in deltas) == REPLY["final_answer"]


# ---------------------------------------------------------------------- the HTTP API
class FakeEngine:
    def close(self): pass

    def ask(self, image, question, emit=None, stream=False):
        if question == "boom":
            raise RuntimeError("model down")
        if emit:
            emit("caption", {"status": "COMPLETED"})
            emit("retrieval", {"gate": "high", "laws": [{"law_id": "QCVN 41:2024/BGTVT", "article_id": "B.31"}]})
            if stream:
                for t in ("Đây là ", "biển cấm đỗ."):
                    emit("token", {"text": t})
        return svc.RagResult(answer="Đây là biển cấm đỗ.", analysis={}, citations=[], retrieved=[], gate="high",
                             s_max=0.9, fewshot_used_ids=[], caption_status="COMPLETED", timings={"total": 1.0},
                             usage=None)


def png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (200, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def test_the_api_answers_and_streams():
    from fastapi.testclient import TestClient
    from text_based_rag.service_api import create_app
    with TestClient(create_app(lambda: FakeEngine(), start=False)) as c:
        assert c.get("/health").json()["status"] == "ok"
        assert c.get("/version").json()["config_version"] == svc.CONFIG_VERSION
        r = c.post("/answer", files={"image": ("a.png", png(), "image/png")}, data={"question": "Biển gì?"})
        assert r.status_code == 200 and r.json()["answer"] == "Đây là biển cấm đỗ."
        s = c.post("/answer/stream", files={"image": ("a.png", png(), "image/png")}, data={"question": "Biển gì?"})
        names = [ln[7:] for ln in s.text.splitlines() if ln.startswith("event: ")]
        assert names == ["caption", "retrieval", "token", "token", "answer", "done"]
        assert c.post("/answer", files={"image": ("a.png", b"xx", "image/png")}, data={"question": "q"}).status_code == 415
        e = c.post("/answer", files={"image": ("a.png", png(), "image/png")}, data={"question": "boom"})
        assert e.status_code == 500 and "model down" in e.json()["detail"]


def test_health_reports_a_failed_start():
    from fastapi.testclient import TestClient
    from text_based_rag.service_api import create_app

    def broken():
        raise FileNotFoundError("no llama-server")
    with TestClient(create_app(broken)) as c:
        h = c.get("/health").json()
        assert h["status"] == "error" and "llama-server" in h["error"]
        r = c.post("/answer", files={"image": ("a.png", png(), "image/png")}, data={"question": "q"})
        assert r.status_code == 503
