"""The scene call: one Claude vision call per image (docs/plans/phase-3.md, item 3).

perceive(image_path) -> PerceptionResult

- The image is prepared (vqa/perception/image.py) and sent with the cached system
  prompt (vqa/perception/prompt.py). The reply is one plain JSON object; no JSON
  schema is sent.
- The reply is converted by vqa/perception/wire.py in strict mode. Malformed JSON
  or a failed check gets exactly one retry. The retry sends only the error: the
  rejected reply is not echoed back (the assistant turn is a placeholder). The
  retry's reply is converted in final mode (invalid codes become UNKNOWN).
- A refusal or a reply cut off at max_tokens is an error, with no retry.
- Every request goes through the spend guard and the usage log (LLMClient).
- The scene cache (vqa/perception/cache.py) is keyed by image sha256 + model +
  effort + prompt id. A hit makes no call: the scene is rebuilt from the cached
  reply by the current code. Only replies that gave a scene are cached.
- The scene id is the first 12 hex digits of the image hash, never a file name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vqa.llm.client import LLMBadJSON, LLMClient, LLMRefusal, LLMTruncated, parse_json_reply
from vqa.llm.spend import SpendGuard
from vqa.perception import prompt as scene_prompt
from vqa.perception.cache import CacheRecord, SceneCache
from vqa.perception.image import PreparedImage, prepare_file
from vqa.perception.wire import WireResult, to_scene
from vqa.schemas import SceneGraph

DEFAULT_MODEL = "claude-haiku-5-5"
PLACEHOLDER = "[previous reply not shown]"


@dataclass
class PerceptionResult:
    scene: SceneGraph | None
    image_sha256: str
    model: str
    effort: str | None
    prompt_id: str
    error: str | None = None                 # refusal, truncation, or no valid reply after the retry
    retried: bool = False
    cache_hit: bool = False
    cost_usd: float = 0.0
    raw_codes: dict[str, str] = field(default_factory=dict)   # sign id -> invalid code as read
    dropped: list[str] = field(default_factory=list)          # parts the final conversion left out
    issues: list[str] = field(default_factory=list)           # verification (item 4)
    replies: list[dict[str, Any]] = field(default_factory=list)
    image: PreparedImage | None = None

    @property
    def ok(self) -> bool:
        return self.scene is not None and self.error is None


def _retry_messages(errors: list[str]) -> list[dict[str, Any]]:
    msg = ("That reply was not valid: " + "; ".join(errors[:12])
           + ". Reply again with only the corrected JSON object.")
    return [{"role": "assistant", "content": PLACEHOLDER}, {"role": "user", "content": msg}]


def _reply_record(pass_: str, res) -> dict[str, Any]:
    return {"pass": pass_, "raw_text": res.raw_text, "stop_reason": "end_turn",
            "usage": res.usage, "cost_usd": res.cost_usd, "request_id": res.request_id}


def _convert(text: str, scene_id: str, final: bool) -> tuple[WireResult | None, list[str]]:
    try:
        data = parse_json_reply(text)
    except LLMBadJSON as e:
        return None, [str(e)]
    w = to_scene(data, scene_id, final=final)
    return w, w.errors


def perceive(image_path: str | Path, *, model: str = DEFAULT_MODEL, version: str = "v1",
             client: LLMClient | None = None, cache: SceneCache | None = None,
             use_cache: bool = True, guard: SpendGuard | None = None) -> PerceptionResult:
    img = prepare_file(image_path)
    effort = scene_prompt.effort_for(model, version)
    pid = scene_prompt.prompt_id(version)
    scene_id = img.sha256[:12]
    cache = cache if cache is not None else SceneCache()
    base = dict(image_sha256=img.sha256, model=model, effort=effort, prompt_id=pid, image=img)

    if use_cache and (rec := cache.get(img.sha256, model, effort, pid)) is not None:
        last = rec.replies[-1]
        w, errs = _convert(last["raw_text"], scene_id, final=len(rec.replies) > 1)
        if w is not None and w.scene is not None:
            return PerceptionResult(scene=w.scene, cache_hit=True, retried=len(rec.replies) > 1,
                                    raw_codes=w.raw_codes, dropped=w.dropped,
                                    replies=rec.replies, **base)

    client = client or LLMClient(model=model, guard=guard or SpendGuard())
    system = scene_prompt.system_prompt(version)
    user = [img.content_block(), {"type": "text", "text": scene_prompt.user_text()}]
    max_tokens = scene_prompt.config(version)["max_tokens"]
    replies, cost = [], 0.0

    def call(extra=None):
        return client.json_reply(system=system, user=user, max_tokens=max_tokens, effort=effort,
                                 purpose="scene", extra_messages=extra)

    def fail(msg: str, retried: bool) -> PerceptionResult:
        return PerceptionResult(scene=None, error=msg, retried=retried, cost_usd=cost,
                                replies=replies, **base)

    try:
        res = call()
    except (LLMRefusal, LLMTruncated) as e:
        cost += getattr(e, "cost_usd", 0.0)
        return fail(f"{type(e).__name__}: {e}", False)
    except LLMBadJSON as e:
        cost += getattr(e, "cost_usd", 0.0)
        errors = [str(e)]
        replies.append({"pass": "first", "raw_text": getattr(e, "raw_text", ""), "stop_reason": "end_turn",
                        "usage": client.last_usage or {}, "cost_usd": getattr(e, "cost_usd", 0.0),
                        "request_id": None})
    else:
        cost += res.cost_usd
        replies.append(_reply_record("first", res))
        w, errors = _convert(res.raw_text, scene_id, final=False)
        if w is not None and w.ok:
            cache.put(CacheRecord(img.sha256, model, effort, pid, replies=replies))
            return PerceptionResult(scene=w.scene, cost_usd=cost, raw_codes=w.raw_codes,
                                    dropped=w.dropped, replies=replies, **base)

    # one retry, sending only the error
    try:
        res = call(_retry_messages(errors))
    except (LLMRefusal, LLMTruncated, LLMBadJSON) as e:
        cost += getattr(e, "cost_usd", 0.0)
        return fail(f"after the retry: {type(e).__name__}: {e}", True)
    cost += res.cost_usd
    replies.append(_reply_record("retry", res))
    w, errors = _convert(res.raw_text, scene_id, final=True)
    if w is None or w.scene is None:
        return fail("after the retry: " + "; ".join(errors), True)
    cache.put(CacheRecord(img.sha256, model, effort, pid, replies=replies))
    return PerceptionResult(scene=w.scene, retried=True, cost_usd=cost, raw_codes=w.raw_codes,
                            dropped=w.dropped, replies=replies, **base)
