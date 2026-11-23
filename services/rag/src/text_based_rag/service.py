"""One question at a time through the pinned configuration C (ns-vqa plan F2).

The batch runner (`natural_qa_runner`) reads whole splits and writes run folders. The
service answers one image + question with the models loaded once:

1. caption: the query-caption request of `experiments/latency/caption_live.py` (same
   prompt, schema, sampling and llama-server flags), on a warm caption server;
2. representation: `query_representation`, as the runner builds it;
3. embedding: `NaturalEncoder` (f2llm-v2-0.6b, BF16), as the runner's live path;
4. retrieval: `retrieve_user_query` with config C's settings, over the corpus index and
   the train example bank, loaded at start-up exactly as the runner loads them with
   `--reuse-precomputed-embeddings --fresh-captions`;
5. few-shot choice: `select_fewshot_neighbors` (5, question-type matched);
6. answer: `answer_one`, the per-row body of the runner's `answer_rows` with the answer
   server kept warm (`tests/test_service.py` checks the two give the same prediction),
   optionally streaming the `final_answer` text as it is generated.

Nothing here changes the runner. GPU only (llama.cpp CUDA, PyTorch CUDA); on a Mac the
module imports and its tests run with fake servers and encoders.
"""

from __future__ import annotations

import base64
import hashlib
import json
import socket
import subprocess
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np
import requests

from text_based_rag import inference as qa
from text_based_rag import natural_qa_runner as runner
from text_based_rag import query_image_captioning as cap
from text_based_rag.corpus_embedding import REVISION, embed_batch, file_hash, load_encoder
from text_based_rag.query_retrieval import TOP_K, retrieve_user_query

# The runner's helpers read these module globals, which its main() binds at run time.
for _name, _value in {"np": np, "requests": requests, "qa": qa, "cap": cap, "file_hash": file_hash,
                      "load_encoder": load_encoder, "embed_batch": embed_batch, "REVISION": REVISION}.items():
    setattr(runner, _name, _value)

ROOT = qa.ROOT
DATASET = ROOT / "data/raw/VLSP2025-MLQA-Natural/dataset"
CORPUS_CHUNKS = ROOT / "artifacts/experiments/text_based_rag/natural_qa/t768_o64/f2llm-v2-0.6b/train"
TRAIN_EMBEDDINGS = ROOT / "artifacts/experiments/text_based_rag/natural_qa/query_embeddings/f2llm-v2-0.6b"
# the caption settings the RAG was evaluated with, kept beside the code so the service reads no
# test-split file (copied from the public-test caption manifest; tests/test_service.py checks it)
CAPTION_SETTINGS = Path(__file__).with_name("caption_settings.json")

# Configuration C: the README run command, the saved runs and the live private run.
CONFIG_C = {
    "embedding_model": "f2llm-v2-0.6b", "embedding_dtype": "bf16", "answer_model": "qwen3.5-9b-gguf",
    "fewshot_k": 5, "answer_with_images": True, "context_size": 65536, "current_context_budget": 20000,
    "answer_max_tokens": 2048, "fresh_captions": True, "allow_incomplete_captions": True,
    "retrieval": {"corpus_k": 5, "examples_k": 4, "high_examples_k": 3, "low_threshold": 0.70,
                  "high_threshold": 0.7835, "weight_high": 0.87, "weight_middle": 0.05, "weight_low": 0.40},
    "model_sha256": "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8",
    "projector_sha256": "f70dc3509053962b0d0d3ee8a7eacebf5d60aa560cad78254ae8698516ae029f",
    "llama_cpp": "b11624",
}
CONFIG_VERSION = "rag-c@" + hashlib.sha256(json.dumps(CONFIG_C, sort_keys=True).encode()).hexdigest()[:12]
ANSWER_SCHEMA = {"type": "object", "additionalProperties": False, "required": list(qa.FIELDS),
                 "properties": {k: {"type": "string", "minLength": 1} for k in qa.FIELDS}}

Emit = Callable[[str, dict[str, Any]], None]


class _NoProgress:
    def set(self, *a, **k): pass
    def advance(self, *a, **k): pass


class MemoryRun:
    """The part of the runner's Run that its helpers use, kept in memory (no run folder)."""

    def __init__(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="rag_service_"))
        self.config: dict[str, Any] = {}
        self.previous: dict[str, Any] = {}
        self.records: dict[str, list[dict[str, Any]]] = {}

    def read(self, name, rows):
        return {}

    def append(self, name, row, record):
        out = {**record, "id": row["id"]}
        self.records.setdefault(name, []).append(out)
        return out


def caption_valid(description: str) -> bool:
    """caption_live.valid: the query caption JSON is complete and well-formed."""
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


def png_data_url(path: Path) -> str:
    """caption_live's image encoding: RGB, PNG, base64 data URL."""
    from PIL import Image
    with Image.open(path) as original, BytesIO() as buf:
        with original.convert("RGB") as im:
            im.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def llama_parallel() -> int:
    """RAG_LLAMA_PARALLEL (default 1): requests each llama-server runs at once. Each slot keeps
    the full context (the server gets context x slots), so no answer is shortened by it; the
    cost is KV-cache memory. With more than 1, also set RAG_WORKERS (service_api)."""
    return max(1, int(os.environ.get("RAG_LLAMA_PARALLEL", "1")))


def slot_context(context: int) -> int:
    """RAG_LLAMA_SLOT_CONTEXT (default: the configured context): tokens per slot. Smaller saves
    KV-cache memory for more slots; a prompt longer than it fails instead of being shortened."""
    return int(os.environ.get("RAG_LLAMA_SLOT_CONTEXT", str(context)))


_ENCODE_LOCK = threading.Lock()   # the query encoder (PyTorch, GPU) runs one call at a time


class CaptionServer:
    """A warm llama-server with caption_live's exact command line."""

    def __init__(self, context_size: int) -> None:
        self.context_size, self.process, self.url = context_size, None, None

    def launch(self, log_dir: Path) -> None:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        log = (log_dir / "caption_server.log").open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            [str(cap.SERVER), "-m", str(cap.CORPUS_MODEL), "--mmproj", str(cap.PROJECTOR), "--host", "127.0.0.1",
             "--port", str(port), "-c", str(slot_context(self.context_size) * llama_parallel()), "-ngl", "all",
             "--parallel", str(llama_parallel()), "--jinja",
             "--reasoning", "off"], stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("caption llama-server stopped; see caption_server.log")
            try:
                if requests.get(self.url + "/health", timeout=2).status_code == 200:
                    return
            except requests.ConnectionError:
                pass
            time.sleep(1)
        raise TimeoutError("caption model not ready after 180 s")

    def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        r = requests.post(self.url + "/v1/chat/completions", json=payload, timeout=(10, 900))
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=20)


def generate_streaming(server: Any, messages: list, schema: dict, max_tokens: int,
                       on_text: Callable[[str], None]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Server.generate with stream=true: the same request and sampling, the content passed on as it
    arrives. Returns (payload, usage) like generate; raises GenerationIncomplete the same way."""
    body = {"messages": messages, "temperature": 0, "seed": 2025, "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_object", "schema": schema},
            "stream": True, "stream_options": {"include_usage": True}}
    content, finish, usage = [], None, None
    with requests.post(server.url + "/v1/chat/completions", json=body, stream=True, timeout=(10, 900)) as r:
        r.raise_for_status()
        # llama-server sends no charset, and requests would then decode as Latin-1: decode UTF-8 ourselves
        for raw_bytes in r.iter_lines():
            raw = raw_bytes.decode("utf-8") if isinstance(raw_bytes, bytes) else raw_bytes
            if not raw or not raw.startswith("data: "):
                continue
            data = raw[6:].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            if chunk.get("usage"):
                usage = chunk["usage"]
            for ch in chunk.get("choices") or []:
                delta = (ch.get("delta") or {}).get("content")
                if delta:
                    content.append(delta)
                    try:
                        on_text(delta)
                    except Exception:
                        pass
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
    text = "".join(content)
    choice = {"finish_reason": finish, "message": {"content": text}}
    if finish != "stop":
        raise runner.GenerationIncomplete(choice, usage)
    return json.loads(text), usage


class FinalAnswerStream:
    """Decodes the "final_answer" string of the streaming JSON reply (as vqa.answer.stream does)."""

    def __init__(self) -> None:
        import re
        self._key = re.compile(r'"final_answer"\s*:\s*"')
        self._buf, self._pos, self.done = "", None, False

    def feed(self, chunk: str) -> str:
        if self.done:
            return ""
        self._buf += chunk
        if self._pos is None:
            m = self._key.search(self._buf)
            if not m:
                return ""
            self._pos = m.end()
        out, buf, i = [], self._buf, self._pos
        simple = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
        while i < len(buf):
            c = buf[i]
            if c == '"':
                self.done = True
                i += 1
                break
            if c != "\\":
                out.append(c)
                i += 1
                continue
            if i + 1 >= len(buf):
                break
            e = buf[i + 1]
            if e == "u":
                if i + 6 > len(buf):
                    break
                try:
                    out.append(chr(int(buf[i + 2:i + 6], 16)))
                except ValueError:
                    out.append("\ufffd")
                i += 6
            else:
                out.append(simple.get(e, e))
                i += 2
        self._pos = i
        return "".join(out)


@dataclass
class RagResult:
    answer: str
    analysis: dict[str, Any]
    citations: list[dict[str, Any]]            # the laws given to the answer model, in rank order
    retrieved: list[dict[str, Any]]            # the retrieval result before context packing
    gate: str | None
    s_max: float | None
    fewshot_used_ids: list[str]
    caption_status: str
    timings: dict[str, float]
    usage: dict[str, Any] | None
    config_version: str = CONFIG_VERSION
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"answer": self.answer, "analysis": self.analysis, "citations": self.citations,
                "retrieved": self.retrieved, "gate": self.gate, "s_max": self.s_max,
                "fewshot_used_ids": self.fewshot_used_ids, "caption_status": self.caption_status,
                "timings": self.timings, "usage": self.usage, "config_version": self.config_version, **self.extra}


class RagEngine:
    """Config C for one question at a time. Collaborators can be injected (tests use fakes)."""

    def __init__(self, dataset_root: Path = DATASET, *, encoder: Any = None, answer_server: Any = None,
                 caption_server: Any = None) -> None:
        self.root = Path(dataset_root).expanduser().resolve()
        self.run = MemoryRun()
        self.encoder = encoder
        self.answer_server = answer_server
        self.caption_server = caption_server
        self.caption_settings: dict[str, Any] | None = None
        self.bank: dict[str, Any] | None = None

    # ------------------------------------------------------------------ start-up
    def load_bank(self) -> None:
        """The train example bank and corpus index, as the runner builds them for config C."""
        train_source, train = runner.load_rows(self.root, "train")
        natural_law = self.root / "law_db/vlsp2025_law.json"
        if (json.loads(natural_law.read_text(encoding="utf-8-sig"))
                != json.loads(qa.LAW_SOURCE.read_text(encoding="utf-8-sig"))):
            raise ValueError("Natural law content differs from the indexed corpus.")
        corpus_root = qa.CORPUS.parent
        chunk_file, chunk_manifest_file = CORPUS_CHUNKS / "corpus_chunks.jsonl", CORPUS_CHUNKS / "run_config.json"
        chunk_manifest = json.loads(chunk_manifest_file.read_text(encoding="utf-8-sig"))
        if chunk_manifest.get("status") != "COMPLETED":
            raise ValueError(f"Chunk input not COMPLETED: {chunk_manifest_file}")
        expected = chunk_manifest.get("output_sha256", {}).get(chunk_file.name)
        if expected and file_hash(chunk_file) != expected:
            raise ValueError(f"Chunk input hash differs: {chunk_file}")
        corpus_manifest = runner.verified_run_cache(CORPUS_CHUNKS, ("corpus_vectors.npy", "corpus_chunks.jsonl"))
        train_manifest = runner.verified_run_cache(TRAIN_EMBEDDINGS, ("embeddings.jsonl",))
        model = runner.EMBEDDERS[CONFIG_C["embedding_model"]][0]
        for label, m in (("corpus", corpus_manifest), ("train", train_manifest)):
            meta = m.get("encoder", {})
            if (m.get("embedding_model") != CONFIG_C["embedding_model"] or meta.get("model") != model
                    or m.get("embedding_dtype") != CONFIG_C["embedding_dtype"] or int(meta.get("dimension", 0)) < 1):
                raise ValueError(f"Precomputed {label} embedding metadata does not match config C.")
        if train_manifest.get("split") != "train":
            raise ValueError("Precomputed training embeddings do not have split=train.")
        natural_chunks = qa.read_lines(chunk_file)
        self.registry = qa.user_corpus_registry()
        valid = {(str(c["document_id"]), str(c["id"])) for c in qa.read_lines(corpus_root / "corpus_embedding/chunks.jsonl")}
        kept = [r for r in train if all((c["law_id"], c["article_id"]) in valid for c in r["relevant_articles"])]
        if len(kept) < TOP_K:
            raise ValueError("Not enough natural train examples with valid citations.")
        train = bank_rows = kept
        args = SimpleNamespace(split="train", caption_dir=None, train_caption_dir=None,
                               allow_incomplete_captions=True)
        train_captions, _ = runner.load_fresh_caption_artifacts(train, self.root, "train", args, qa)
        bank_encoder = runner.CachedNaturalEncoder(CONFIG_C["embedding_model"], train_manifest["encoder"])
        train_repr, vectors = runner.embed_rows(self.run, train, train_captions, _NoProgress(), "train",
                                                bank_encoder, True, precomputed_path=TRAIN_EMBEDDINGS / "embeddings.jsonl",
                                                precomputed_manifest=train_manifest)
        corpus_vectors = np.load(CORPUS_CHUNKS / "corpus_vectors.npy", allow_pickle=False)
        if (corpus_vectors.shape != (len(natural_chunks), bank_encoder.dimension) or not np.isfinite(corpus_vectors).all()
                or not np.allclose(np.linalg.norm(corpus_vectors, axis=1), 1, atol=1e-5)):
            raise ValueError("Corpus embedding cache is invalid.")
        self.corpus_index = {"chunks": natural_chunks, "vectors": corpus_vectors, "encoder": bank_encoder.metadata()}
        position = {r["id"]: i for i, r in enumerate(train)}
        self.bank = {"queries": [{"query_id": r["id"], "source_image_id": r["image_id"], "question": r["question"],
                                  "vector_row": i} for i, r in enumerate(bank_rows)],
                     "labels": {r["id"]: r for r in bank_rows},
                     "vectors": vectors[[position[r["id"]] for r in bank_rows]], "encoder": bank_encoder.metadata()}
        answers = runner.load_fewshot_answers(train_source, bank_rows)
        self.fewshot_data = {}
        for r in bank_rows:
            if r["id"] not in answers:
                continue
            text, q = train_repr[r["id"]]["text"], r["question"].strip()
            prefix = "Câu hỏi:\n" + q
            if not text.startswith(prefix):
                raise ValueError(f"Unexpected train representation format: {r['id']}")
            self.fewshot_data[r["id"]] = {"question": q, "visual_description": text[len(prefix):].strip(),
                                          "answer": answers[r["id"]], "image": r["image"]}
        self.train_ids = {r["id"] for r in train}

    def start(self) -> None:
        """Load the bank, the encoder and both warm llama-servers (GPU machine)."""
        self.load_bank()
        settings = dict(json.loads(CAPTION_SETTINGS.read_text(encoding="utf-8"))["settings"])
        if settings.get("prompt") != cap.QUERY_PROMPT or settings.get("max_new_tokens") != cap.MAX_NEW_TOKENS:
            raise RuntimeError("the caption prompt or token limit differs from the reference artifacts")
        settings.update(model=str(cap.CORPUS_MODEL), projector=str(cap.PROJECTOR))
        self.caption_settings = settings
        if self.encoder is None:
            self.encoder = runner.NaturalEncoder(CONFIG_C["embedding_model"], CONFIG_C["embedding_dtype"])
        if self.caption_server is None:
            self.caption_server = CaptionServer(int(settings["context_size"]))
            self.caption_server.launch(self.run.folder)
        if self.answer_server is None:
            self.answer_server = runner.Server()
            self.answer_server.launch(self.run, CONFIG_C["answer_with_images"], CONFIG_C["context_size"])

    def close(self) -> None:
        for s in (self.caption_server, self.answer_server):
            if s is not None and hasattr(s, "close"):
                s.close()

    # ------------------------------------------------------------------ the steps
    def caption(self, image: Path, question: str, query_id: str) -> dict[str, Any]:
        """caption_live's request for one image and question; returns the caption record."""
        image_id = "sha256:" + sha256(Path(image).read_bytes()).hexdigest()
        prompt = cap.QUERY_PROMPT.replace("{question_text}", question)
        g = self.caption_server.chat({
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": png_data_url(Path(image))}},
                {"type": "text", "text": prompt}]}],
            "temperature": 0, "seed": 2025, "max_tokens": cap.MAX_NEW_TOKENS,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_object", "schema": cap.QUERY_SCHEMA}})
        choice = g["choices"][0]
        description = cap.strip_json_fence(choice["message"]["content"])
        status = "COMPLETED" if caption_valid(description) and choice.get("finish_reason") == "stop" else "INCOMPLETE"
        return {"query_id": query_id, "image_id": image_id, "question_text": question, "description": description,
                "settings": self.caption_settings, "status": status, "finish_reason": choice.get("finish_reason"),
                "generated_tokens": (g.get("usage") or {}).get("completion_tokens")}

    def represent(self, question: str, caption: dict[str, Any], query_id: str) -> dict[str, Any]:
        return qa.query_representation(question.strip(), caption, query_id, allow_incomplete=True)

    def embed(self, text: str) -> np.ndarray:
        with _ENCODE_LOCK:
            v = np.asarray(self.encoder.encode([text], role="query")[0], dtype=np.float32)
        if v.shape != (self.corpus_index["vectors"].shape[1],) or not np.isfinite(v).all():
            raise ValueError("query embedding has the wrong shape")
        return v

    def retrieve(self, vector: np.ndarray, representation_text: str, question: str, query_id: str) -> dict[str, Any]:
        retrieval = retrieve_user_query(vector, representation_text, example_bank=self.bank,
                                        corpus_index=self.corpus_index, settings=CONFIG_C["retrieval"])
        retrieval["fewshot_neighbors"] = runner.select_fewshot_neighbors(
            vector, question, self.bank, self.fewshot_data, CONFIG_C["fewshot_k"], query_id)
        return retrieval

    def answer_one(self, row: dict[str, Any], representation_text: str, retrieval: dict[str, Any],
                   on_text: Callable[[str], None] | None = None) -> dict[str, Any]:
        """The body of the runner's answer_rows for one row, with the answer server already running.
        Returns the prediction record answer_rows would append (without the row's own fields)."""
        c = CONFIG_C
        context, max_tokens, budget = c["context_size"], c["answer_max_tokens"], c["current_context_budget"]
        with_images, server = c["answer_with_images"], self.answer_server
        started = time.monotonic()
        selected = [{"query_id": n["query_id"], **self.fewshot_data[n["query_id"]]}
                    for n in retrieval.get("fewshot_neighbors", []) if n["query_id"] in self.fewshot_data]
        hits, laws = sorted(retrieval["results"], key=lambda hit: hit["rank"]), []
        retrieved_hits = list(hits)
        for hit in hits:
            text, _ = qa.resolve_citation(hit, self.registry)
            laws.append(f"[Hạng {hit['rank']}; điểm {hit['score']:.4f}]\n{text}")
        usage, nt, attempt = None, 0, 0
        truncation = {"context_truncated": False, "original_input_tokens": 0,
                      "input_token_budget": context - max_tokens - 128,
                      "current_context_budget": min(budget, context - max_tokens - 128),
                      "current_query_tokens": 0, "fewshot_requested": len(selected),
                      "fewshot_used_ids": [], "fewshot_dropped_ids": [], "dropped_citations": [], "shortened_citations": []}
        if not hits and not with_images:
            payload = {k: "" for k in qa.FIELDS}
            payload["final_answer"] = "Mình chưa tìm thấy điều luật phù hợp để trả lời câu hỏi này."
        else:
            messages, nt, laws, hits, truncation = runner.fit_answer_context(
                server, row["question"].strip(), representation_text, laws, hits, context, max_tokens,
                selected, budget, query_image=row["image"] if with_images else None, answer_with_images=with_images)
            for attempt in range(1, 4):
                try:
                    if on_text is None:
                        payload, usage = server.generate(messages, ANSWER_SCHEMA, max_tokens)
                    else:
                        payload, usage = generate_streaming(server, messages, ANSWER_SCHEMA, max_tokens, on_text)
                    if set(payload) != set(qa.FIELDS) or any(not isinstance(payload[k], str) or not payload[k].strip()
                                                             for k in qa.FIELDS):
                        raise ValueError("Invalid answer schema")
                    break
                except Exception:
                    if attempt == 3:
                        raise
        return {"status": "COMPLETED", "answer": qa.normalized(payload["final_answer"]), "analysis_summary": payload,
                "citations": hits, "gate": retrieval["gate"], "s_max": retrieval["s_max"],
                "retrieved_citations": retrieved_hits, "answer_context": context, **truncation,
                "input_tokens": nt, "usage": usage, "elapsed_seconds": time.monotonic() - started, "attempt": attempt,
                "retrieved_laws_sha256": hashlib.sha256("\n\n".join(laws).encode()).hexdigest(),
                "fewshot_requested": truncation.get("fewshot_requested", 0),
                "fewshot_used_ids": truncation.get("fewshot_used_ids", []),
                "fewshot_dropped_ids": truncation.get("fewshot_dropped_ids", []),
                "current_query_tokens": truncation.get("current_query_tokens", 0)}

    # ------------------------------------------------------------------ one question
    def ask(self, image: Path, question: str, emit: Emit | None = None, stream: bool = False) -> RagResult:
        def send(name, payload):
            if emit is not None:
                try:
                    emit(name, payload)
                except Exception:
                    pass
        qid = "service_" + sha256((str(image) + question).encode()).hexdigest()[:16]
        if qid in getattr(self, "train_ids", set()):
            raise ValueError("query id collides with the train bank")
        timings: dict[str, float] = {}
        t = time.monotonic()
        caption = self.caption(Path(image), question, qid)
        timings["caption"] = time.monotonic() - t
        send("caption", {"status": caption["status"], "seconds": round(timings["caption"], 3)})
        t = time.monotonic()
        rep = self.represent(question, caption, qid)
        vector = self.embed(rep["text"])
        timings["embedding"] = time.monotonic() - t
        t = time.monotonic()
        retrieval = self.retrieve(vector, rep["text"], question, qid)
        timings["retrieval"] = time.monotonic() - t
        send("retrieval", {"gate": retrieval["gate"], "s_max": retrieval["s_max"],
                           "laws": [{k: h.get(k) for k in ("law_id", "article_id", "rank", "score")}
                                    for h in sorted(retrieval["results"], key=lambda h: h["rank"])],
                           "seconds": round(timings["retrieval"], 3)})
        on_text = None
        if stream:
            fs = FinalAnswerStream()

            def on_text(delta: str) -> None:
                new = fs.feed(delta)
                if new:
                    send("token", {"text": new})
        t = time.monotonic()
        row = {"id": qid, "question": question, "image": str(image)}
        pred = self.answer_one(row, rep["text"], retrieval, on_text=on_text)
        timings["answer"] = time.monotonic() - t
        timings["total"] = sum(timings.values())
        cited = []
        for h in pred["citations"]:
            text, _ = qa.resolve_citation(h, self.registry)
            cited.append({"law_id": h["law_id"], "article_id": h["article_id"], "rank": h.get("rank"),
                          "score": h.get("score"), "text": text})
        return RagResult(answer=pred["answer"], analysis=pred["analysis_summary"], citations=cited,
                         retrieved=[{k: h.get(k) for k in ("law_id", "article_id", "rank", "score")}
                                    for h in pred["retrieved_citations"]],
                         gate=pred["gate"], s_max=pred["s_max"], fewshot_used_ids=pred["fewshot_used_ids"],
                         caption_status=caption["status"], timings={k: round(v, 3) for k, v in timings.items()},
                         usage=pred["usage"], extra={"context_truncated": pred["context_truncated"]})
