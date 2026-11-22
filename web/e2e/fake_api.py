"""The real API (app/api) with a fake pipeline, for the web UI's end-to-end test. No Claude calls.

    python web/e2e/fake_api.py --port 8765

The fake has the stage methods the API's runner wraps (perception, parser, engine, writer,
fallback), so every stream event comes from the real runner and endpoint code:
- a question containing "RAG" goes to the fallback, which answers as the RAG service would
  (streamed text, `basis` gains "rag", the laws it used in `retrieved`);
- any other question is answered by the "rules": the writer streams a first draft, withdraws
  it (`token_reset`) and streams the final text, as on a retry.
By default each start uses a fresh temporary database and upload folder; VQA_DATABASE_URL and
VQA_UPLOAD_DIR override them (the Docker Compose stack's demo mode uses its Postgres).
`/version` reports the profile "fake-e2e", and the UI shows a warning banner for it, so the fake
is never mistaken for the real system.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

from app.api.main import create_app  # noqa: E402
from app.api.settings import Settings  # noqa: E402
from vqa.schemas import Position, SceneGraph, Sign  # noqa: E402

DELAY = 0.12   # seconds between streamed pieces, so the UI's streaming is visible

NAMES = {"P.103a": "Cấm xe ô tô", "W.207a": "Giao nhau với đường không ưu tiên"}

PROOF_NO = {
    "verdict": "no", "value": None, "uncertain_signs": [], "note": None, "basis": [],
    "citations": [{"law_id": "QCVN 41:2024/BGTVT", "article_id": "B.3"}],
    "reasons": [{
        "sign_id": "s1", "truth": "true", "detail": "biển cấm áp dụng cho ô tô",
        "proof": {"type": "rule", "rule": "forbids", "goal": "forbids(s1, car, enter)", "children": [
            {"type": "fact", "goal": "sign(s1, p103a)", "children": []},
            {"type": "rule", "rule": "covers", "goal": "covers(p103a, car)", "children": [
                {"type": "fact", "goal": "is_a(car, motor_vehicle)", "children": []}]},
            {"type": "cite", "goal": "cite(p103a)",
             "source": {"law_id": "QCVN 41:2024/BGTVT", "article_id": "B.3"}, "children": []},
        ]},
    }],
}

PROOF_PLATE = {
    **PROOF_NO, "basis": ["non_standard_plate"],
    "reasons": [{
        "sign_id": "s2", "truth": "true", "detail": "biển phụ địa phương cấm xe 2 và 3 bánh",
        "proof": {"type": "rule", "rule": "forbids", "goal": "forbids(s2, motorbike, enter)", "children": [
            {"type": "fact", "goal": "local_plate(s2,'CẤM XE 2 VÀ 3 BÁNH')", "children": []},
            {"type": "cite", "goal": "cite(r_non_standard_plate_not_in_qcvn41)", "children": []},
        ]},
    }],
}

RAG_LAWS = [
    {"law_id": "QCVN 41:2024/BGTVT", "article_id": "B.3", "rank": 1, "score": 0.812,
     "text": "Biển số P.103a \"Cấm xe ô tô\": để báo đường cấm các loại xe cơ giới bốn bánh trở lên ..."},
    {"law_id": "36/2024/QH15", "article_id": "11", "rank": 2, "score": 0.644,
     "text": "Điều 11. Chấp hành báo hiệu đường bộ ..."},
]


def stream(listener, pieces):
    for p in pieces:
        time.sleep(DELAY)
        if listener is not None:
            listener("delta", {"text": p})


class FakePipeline:
    def __init__(self) -> None:
        catalog = SimpleNamespace(get=lambda code: SimpleNamespace(name_vi=NAMES[code]))
        self.engine = SimpleNamespace(answer=self._engine_answer, catalog=catalog)
        self.parser = SimpleNamespace(parse=self._parse)
        self.writer = SimpleNamespace(write=self._write, on_event=None)
        self.fallback = SimpleNamespace(answer=self._fallback, on_event=None)

    # stage methods (the runner wraps the instance attributes)
    def _perceive(self, image_path):
        time.sleep(DELAY)
        scene = SceneGraph(scene_id="s", signs=[
            Sign(id="s1", code="P.103a", confidence="high", position=Position(box=(400, 60, 520, 180))),
            Sign(id="s2", code="W.207a", confidence="low", position=Position(box=(120, 90, 220, 180))),
        ])
        return SimpleNamespace(ok=True, scene=scene), {"cache_hit": False, "error": None}

    def _parse(self, question):
        time.sleep(DELAY)
        return SimpleNamespace(status="ok", query=None)

    def _engine_answer(self, scene, program):
        return SimpleNamespace(verdict=SimpleNamespace(value=program))

    def _write(self, question, verdict):
        listener = self.writer.on_event
        stream(listener, ["Có, ", "xe ô tô ", "được đi"])
        if listener is not None:
            listener("reset", {"reason": "retry"})
        text = "Không. Biển số 1 (P.103a) cấm xe ô tô đi vào."
        stream(listener, ["Không. ", "Biển số 1 (P.103a) ", "cấm xe ô tô đi vào."])
        return SimpleNamespace(text=text)

    def _fallback(self, question):
        text = "Theo QCVN 41:2024/BGTVT, biển P.103a cấm xe ô tô, nên xe ô tô không được đi vào."
        stream(self.fallback.on_event, ["Theo QCVN 41:2024/BGTVT, ", "biển P.103a cấm xe ô tô, ",
                                        "nên xe ô tô không được đi vào."])
        return SimpleNamespace(text=text)

    def answer(self, image_path, question):
        t0 = time.monotonic()
        res, _ = self._perceive(image_path)
        self.parser.parse(question)
        if "RAG" in question:
            self.engine.answer(res.scene, "unknown")
            fa = self.fallback.answer(question)
            raw = json.dumps({"config_version": "C", "retrieved": RAG_LAWS}, ensure_ascii=False)
            return SimpleNamespace(
                text=fa.text, verdict="no", answered_by="fallback", basis=["fallback"], citations=[],
                proof={**PROOF_NO, "verdict": "unknown", "reasons": [], "citations": []},
                trace={"fallback": {"trigger": "unknown", "status": "ok", "prompt_id": "rag-C", "raw": [raw]}},
                cost_usd=0.003, seconds=round(time.monotonic() - t0, 2))
        self.engine.answer(res.scene, "no")
        w = self.writer.write(question, "no")
        # "biển phụ": the answer rests on the low-confidence sign 2 and its local plate
        plate = "biển phụ" in question
        return SimpleNamespace(
            text=w.text, verdict="no", answered_by="rules",
            basis=["rules", "non_standard_plate"] if plate else ["rules"],
            citations=["QCVN 41:2024/BGTVT B.3"], proof=PROOF_PLATE if plate else PROOF_NO,
            trace={"writer": {"status": "retry", "cost_usd": 0.001}},
            cost_usd=0.002, seconds=round(time.monotonic() - t0, 2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="vqa-e2e-"))
    settings = dataclasses.replace(
        Settings.from_env(), profile="fake-e2e", answer_fallback="off",
        database_url=os.environ.get("VQA_DATABASE_URL") or f"sqlite:///{tmp / 'app.db'}",
        upload_dir=Path(os.environ.get("VQA_UPLOAD_DIR") or tmp / "uploads"),
        heartbeat_s=1.0)
    pipe = FakePipeline()
    uvicorn.run(create_app(settings, pipeline_factory=lambda: pipe), host=args.host, port=args.port,
                log_level="warning")


if __name__ == "__main__":
    main()
