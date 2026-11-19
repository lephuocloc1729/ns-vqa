"""The end-to-end pipeline (docs/plans/phase-4.md, item 3).

    answer(image_path, question) -> PipelineAnswer

Stages:
1. perception: Haiku 5.5, prompt v4, plus the two-pass fallback, through the scene
   cache;
2. the parser: Sonnet 5.5, prompt v6. It sees the question only (D7);
3. the rule engine;
4. the answer writer and the faithfulness guard (prompt answer/v3);
5. the answer-level fallback (Sonnet 5.5), when one of its triggers fires (D3).

`answer()` takes an image path and a question string, nothing else. The run's
settings (models, prompt versions, the scene cache directory, cache-only mode, the
spend guard) are fixed when the Pipeline is built, never per question.

**Cache-only mode** is for development runs on a warmed cache: an image with no
pass-1 record is an error (`CacheMissError`), and no perception call is ever made.
A missing re-run or region record is treated like a refused call (the reading
stands, the region is skipped), exactly as the warm step's rebuild check does.

When the fallback itself fails, the engine's own answer ships through the writer
(P3); with no engine answer (the parse failed, or there was no scene), the writer
gets an `unknown` answer that says so.

**Guide reading** (`guide_reading=True`, phase 4.5 B6; default off, the frozen behaviour):
after perception, an image whose scene lists a guide board gets the guide-board call
(`vqa/perception/guide.py`, cached like a fallback region); its boards go into the scene
(schema 1.3) and its speed discs become P.127 / R.306 signs. In cache-only mode a missing
record is a refused call: the scene stays as it was.

**Fallback off** (`answer_fallback=False`, phase 4.5): a question that would go to the
fallback is not decided. No fallback or writer call is made; the answer is the
deterministic template of the engine's answer (or of an `unknown` that says why), and
`answered_by` is `not_decided`. Decided answers are exactly as with the fallback on, so
rules-only figures are the same either way; the switch only saves the calls.

**Parallel calls (latency only; answers unchanged).** The parser sees the question only (D7),
so it runs on the calling thread while perception runs in a worker thread; Prolog (the
parser's dry run, the engine) stays on the calling thread. Inside perception the uncached
tile and crop replies are fetched in parallel (`vqa/perception/fallback.py`, `REGION_WORKERS`).
When perception fails, the parse it no longer needs was already paid: its cost is counted
and its trace is kept with `"used": false`, and the answer is the same as before.
"""

from __future__ import annotations

import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from vqa.answer.asked import prune_unasked
from vqa.answer.digest import build as build_digest
from vqa.answer.fallback import AnswerFallback, trigger
from vqa.answer.template import template_answer
from vqa.answer.writer import AnswerWriter
from vqa.llm.client import LLMClient, LLMRefusal
from vqa.llm.spend import SpendGuard
from vqa.parsing.claude_parser import ClaudeParser
from vqa.perception import prompt as scene_prompt
from vqa.perception.cache import SceneCache
from vqa.perception.fallback import FallbackConfig, config_for as fallback_config_for
from vqa.perception.guide import apply as apply_boards, needs_boards, prompt_id as guide_prompt_id, read_boards
from vqa.perception.image import prepare_file
from vqa.perception.scene import perceive
from vqa.reasoning.engine import Engine, EngineError
from vqa.schemas import Answer, Verdict


_NO_ANSWER = {"perception_failed": "the scene could not be read",
              "out_of_scope": "the question is outside what the rules model",
              "parse_failed": "the question could not be parsed",
              "program_cannot_run": "the question could not be checked on this scene"}


class CacheMissError(RuntimeError):
    """Cache-only mode: the image has no pass-1 record in the scene cache."""


@dataclass(frozen=True)
class PipelineConfig:
    perception_model: str = "claude-haiku-5-5"
    scene_version: str = "v4"
    scene_fallback: bool = True                 # the two-pass fallback (phase 3, policy (d))
    cache_dir: Path | None = None               # None: the default scene cache
    cache_only: bool = False
    parser_model: str = "claude-sonnet-5-5"
    parser_effort: str | None = "medium"
    parser_version: str = "v6"
    context_year: int | None = 2025             # the dataset's questions are from 2025
    writer_version: str = "v3"
    answer_fallback_version: str = "v2"
    answer_fallback: bool = True                # False: non-decided questions get no fallback (phase 4.5)
    guide_reading: bool = False                 # phase 4.5 B6: the guide-board call (vqa/perception/guide.py)
    reading_policy: str = "all"                 # phase 4.6 D1: "higher_confidence" = policy A (Engine)
    scene_rerun: bool = True                    # the low-confidence re-run (docs/plans/rerun-removal.md)
    max_spend: float | None = None              # None: the spend guard's default


@dataclass
class PipelineAnswer:
    text: str
    verdict: str | None
    answered_by: str                            # rules | fallback | not_decided (fallback off)
    basis: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    proof: dict[str, Any] | None = None         # the engine's answer, when it ran
    trace: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    seconds: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class _RefuseCalls:
    """Cache-only perception: any call is refused (a missing re-run or region record
    behaves like a refused call). Counts the refusals for the trace."""

    def __init__(self, model: str):
        self.model, self.last_usage, self.refused = model, None, 0
        self._lock = threading.Lock()

    def json_reply(self, **kw):
        with self._lock:
            self.refused += 1
        raise LLMRefusal("cache-only mode: no perception call is made")


class Pipeline:
    def __init__(self, config: PipelineConfig | None = None, *, sdk: Any = None,
                 engine: Engine | None = None, guard: SpendGuard | None = None) -> None:
        self.config = c = config or PipelineConfig()
        self.guard = guard or SpendGuard(c.max_spend)
        self.engine = engine or Engine(reading_policy=c.reading_policy)
        self.cache = SceneCache(c.cache_dir)

        def client(model: str) -> LLMClient:
            return LLMClient(model=model, guard=self.guard, sdk=sdk)

        self._perception_client = None if c.cache_only else client(c.perception_model)
        self.parser = ClaudeParser(llm=client(c.parser_model), effort=c.parser_effort,
                                   prompt_version=c.parser_version, context_year=c.context_year,
                                   engine=self.engine)
        self.writer = AnswerWriter(llm=client("claude-haiku-5-5"), version=c.writer_version,
                                   catalog=self.engine.catalog)
        self.fallback = AnswerFallback(llm=client("claude-sonnet-5-5"), version=c.answer_fallback_version)

    # ------------------------------------------------------------------ perception
    def fallback_config(self) -> FallbackConfig | None:
        """The scene fallback for this run's scene version (v4: the frozen FallbackConfig())."""
        return fallback_config_for(self.config.scene_version) if self.config.scene_fallback else None

    def _require_pass1(self, image_path: Path) -> None:
        """Cache-only mode: raise CacheMissError when the image has no pass-1 record."""
        c = self.config
        sha = hashlib.sha256(image_path.read_bytes()).hexdigest()
        pid = scene_prompt.prompt_id(c.scene_version)
        if self.cache.get(sha, c.perception_model, scene_prompt.effort_for(c.perception_model,
                                                                          c.scene_version), pid) is None:
            raise CacheMissError(f"no pass-1 record for {image_path.name} in {self.cache.root}")

    def _perceive(self, image_path: Path, *, rerun: bool | None = None) -> tuple[Any, dict[str, Any]]:
        """Perception for one image. `rerun` overrides `config.scene_rerun` (the paired holdout check)."""
        c = self.config
        client = self._perception_client
        info: dict[str, Any] = {}
        if c.cache_only:
            self._require_pass1(image_path)
            client = _RefuseCalls(c.perception_model)
        res = perceive(image_path, model=c.perception_model, version=c.scene_version, client=client,
                       cache=self.cache, use_cache=True, rerun=c.scene_rerun if rerun is None else rerun,
                       fallback=self.fallback_config())
        info = {"ok": res.ok, "error": res.error, "cache_hit": res.cache_hit,
                "image_sha256": res.image_sha256, "prompt_id": res.prompt_id,
                "scene_id": res.scene.scene_id if res.scene else None,
                "cost_usd": res.cost_usd}
        if res.fallback is not None:
            info["scene_fallback"] = {"tiled": res.fallback.tiled, "tiles_added": res.fallback.tiles_added,
                                      "crops": res.fallback.crops, "codes_changed": res.fallback.codes_changed}
        if c.guide_reading and res.ok and res.scene is not None and needs_boards(res.scene, self.engine.catalog):
            g = read_boards(res.image if res.image is not None else prepare_file(image_path),
                            model=c.perception_model, client=client, cache=self.cache, use_cache=True)
            res.cost_usd += g.cost_usd
            if g.ok:
                res.scene = apply_boards(res.scene, g.boards)
            info["guide"] = {"prompt_id": guide_prompt_id(), "called": g.called, "cache_hit": g.cache_hit,
                             "ok": g.ok, "boards": len(g.boards), "cost_usd": g.cost_usd, "issues": g.issues}
            info["cost_usd"] = res.cost_usd
        if isinstance(client, _RefuseCalls):
            info["refused_calls"] = client.refused
        return res, info

    # ------------------------------------------------------------------ entry point
    def answer(self, image_path: str | Path, question: str) -> PipelineAnswer:
        t0 = time.monotonic()
        image_path = Path(image_path)
        trace: dict[str, Any] = {}
        cost = 0.0

        if self.config.cache_only:
            self._require_pass1(image_path)            # before the parser spends anything
        with ThreadPoolExecutor(max_workers=1) as ex:  # perception beside the parser (latency only)
            seen = ex.submit(self._perceive, image_path)
            pr = self.parser.parse(question)
            res, trace["perception"] = seen.result()
        cost += res.cost_usd
        scene = res.scene if res.ok else None

        parse_status, program, engine_answer, engine_error = None, None, None, None
        if scene is None:
            cost += pr.cost_usd
            trace["parser"] = {"status": pr.status, "attempts": pr.attempts, "errors": pr.errors,
                               "cost_usd": pr.cost_usd, "used": False}
        else:
            cost += pr.cost_usd
            parse_status = pr.status
            trace["parser"] = {"status": pr.status, "attempts": pr.attempts, "errors": pr.errors,
                               "cost_usd": pr.cost_usd}
            if pr.query is not None:
                program = pr.query.model_dump(mode="json", by_alias=True, exclude_none=True)
                trace["parser"]["program"] = program
            if pr.status == "ok":
                try:
                    engine_answer = prune_unasked(self.engine.answer(scene, pr.query), question)  # 4.8c B2
                except EngineError as e:
                    engine_error = str(e)
                trace["engine"] = {"verdict": engine_answer.verdict.value if engine_answer else None,
                                   "error": engine_error}

        why = trigger(scene_ok=scene is not None, parse_status=parse_status, answer=engine_answer,
                      engine_error=engine_error is not None)
        trace["fallback"] = {"trigger": why}

        if why is not None and not self.config.answer_fallback:
            trace["fallback"]["status"] = "off"
            if engine_answer is None:
                engine_answer = Answer(verdict=Verdict.unknown, note=_NO_ANSWER.get(why or "") or None)
            digest = build_digest(engine_answer, scene, self.engine.catalog)
            return PipelineAnswer(text=template_answer(digest, question), verdict=engine_answer.verdict.value,
                                  answered_by="not_decided", basis=["not_decided"], citations=[],
                                  proof=engine_answer.model_dump(mode="json"), trace=trace, cost_usd=cost,
                                  seconds=time.monotonic() - t0)

        if why is not None:
            fa = self.fallback.answer(image_path, question, scene)
            cost += fa.cost_usd
            trace["fallback"].update(status=fa.status, attempts=fa.attempts, errors=fa.errors,
                                     cost_usd=fa.cost_usd, prompt_id=fa.prompt_id, raw=fa.raw)
            if fa.status == "ok":
                return PipelineAnswer(text=fa.text, verdict=fa.verdict, answered_by="fallback",
                                      basis=["fallback"], citations=[],
                                      proof=engine_answer.model_dump(mode="json") if engine_answer else None,
                                      trace=trace, cost_usd=cost, seconds=time.monotonic() - t0)

        # the rules' answer (or, after a failed fallback, P3: the engine's own answer)
        if engine_answer is None:
            engine_answer = Answer(verdict=Verdict.unknown, note=_NO_ANSWER.get(why or "") or None)
        w = self.writer.write(question, engine_answer, scene)
        cost += w.cost_usd
        trace["writer"] = {"status": w.status, "attempts": w.attempts, "errors": w.errors,
                           "cost_usd": w.cost_usd, "prompt_id": w.prompt_id,
                           "cited_signs": w.cited_signs, "cited_rules": w.cited_rules,
                           "raw": w.raw}                    # T1: every attempt's reply text
        digest = build_digest(engine_answer, scene, self.engine.catalog)
        return PipelineAnswer(text=w.text, verdict=w.verdict, answered_by="rules",
                              basis=["rules", *engine_answer.basis],
                              citations=digest["citations"],
                              proof=engine_answer.model_dump(mode="json"),
                              trace=trace, cost_usd=cost, seconds=time.monotonic() - t0)


_DEFAULT: Pipeline | None = None


def answer(image_path: str | Path, question: str) -> PipelineAnswer:
    """The default pipeline's answer for one image and one question."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Pipeline()
    return _DEFAULT.answer(image_path, question)
