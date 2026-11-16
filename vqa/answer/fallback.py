"""The answer-level fallback (docs/plans/phase-4.md, item 2; D3).

When the rules can't answer, one Sonnet 5.5 vision call answers from:
- the image,
- the question,
- the pass-1 scene graph (or null when perception failed).

Nothing else: no law articles, no retrieval, no train QA beyond the prompt's fixed
style examples. The reply is one plain JSON object `{"verdict", "answer"}`,
checked in Python, with one retry that sends only the error. The answer is
marked `basis: ["fallback"]` and carries no rule citation, so it is never shown
as a rule-engine conclusion.

`trigger()` decides whether the fallback runs. The triggers (D3) are:
- `out_of_scope`: the parser returned out_of_scope;
- `parse_failed`: the parser failed after its retry;
- `unreadable_sign`: the engine answered unknown because of an unreadable sign;
- `program_cannot_run`: a selector finds no sign (or not exactly one), or the
  engine raised on the program;
- `uncertain`: alternative sign readings disagree;
- `unknown`: every other unknown verdict;
- `perception_failed`: there is no scene at all. Not in the plan's list: a reading
  made while building the pipeline, for the owner to confirm.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from vqa.answer.faithfulness import is_true_false, leading_polarity
from vqa.llm.client import LLMBadJSON, LLMClient, LLMError
from vqa.llm.spend import SpendGuard, SpendLimitExceeded
from vqa.perception.image import prepare_file
from vqa.perception.wire import retry_messages
from vqa.schemas import Answer, SceneGraph, Verdict

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "answer_fallback"
DEFAULT_VERSION = "v1"
VERDICTS = ("yes", "no", "value", "unknown")
TRIGGERS = ("perception_failed", "out_of_scope", "parse_failed", "program_cannot_run",
            "unreadable_sign", "uncertain", "unknown")

# Engine notes that mean the program could not run on this scene.
_CANNOT_RUN_NOTES = ("no sign in the scene matches the selector", "expected exactly one sign")


def trigger(*, scene_ok: bool, parse_status: str | None, answer: Answer | None,
            engine_error: bool = False) -> str | None:
    """Which fallback trigger fires, or None when the rules' answer ships."""
    if not scene_ok:
        return "perception_failed"
    if parse_status == "out_of_scope":
        return "out_of_scope"
    if parse_status != "ok":
        return "parse_failed"
    if engine_error or answer is None:
        return "program_cannot_run"
    if answer.verdict == Verdict.uncertain:
        return "uncertain"
    if answer.verdict == Verdict.unknown:
        if answer.uncertain_signs:
            return "unreadable_sign"
        if answer.note and any(n in answer.note for n in _CANNOT_RUN_NOTES):
            return "program_cannot_run"
        return "unknown"
    return None


# ---------------------------------------------------------------- prompt

def _dir(version: str) -> Path:
    d = PROMPTS_DIR / version
    if not d.is_dir():
        raise FileNotFoundError(f"no answer-fallback prompt {version!r} under {PROMPTS_DIR}")
    return d


@lru_cache(maxsize=4)
def config(version: str = DEFAULT_VERSION) -> dict[str, Any]:
    return yaml.safe_load((_dir(version) / "config.yaml").read_text(encoding="utf-8")) or {}


def examples(version: str = DEFAULT_VERSION) -> list[dict[str, Any]]:
    path = _dir(version) / "examples.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


@lru_cache(maxsize=4)
def system_prompt(version: str = DEFAULT_VERSION) -> str:
    spec = (_dir(version) / "spec.md").read_text(encoding="utf-8").strip()
    shots = [f"Question: {e['question']}\nTrue/false question: {'yes' if e['true_false'] else 'no'}\n"
             f"Reply: {json.dumps(e['reply'], ensure_ascii=False, separators=(',', ':'))}"
             for e in examples(version)]
    return spec + "\n\n" + "\n\n".join(shots)


def prompt_hash(version: str = DEFAULT_VERSION) -> str:
    cfg = (_dir(version) / "config.yaml").read_text(encoding="utf-8")
    return hashlib.sha256((system_prompt(version) + "\n--config--\n" + cfg).encode("utf-8")).hexdigest()


def prompt_id(version: str = DEFAULT_VERSION) -> str:
    return f"answer_fallback/{version}@{prompt_hash(version)[:12]}"


def user_text(question: str, scene: SceneGraph | None, true_false: bool) -> str:
    sg = (json.dumps(scene.model_dump(mode="json", by_alias=True, exclude_none=True),
                     ensure_ascii=False, separators=(",", ":")) if scene is not None else "null")
    return (f"Question: {question.strip()}\n"
            f"True/false question: {'yes' if true_false else 'no'}\n"
            f"Scene graph: {sg}")


# ---------------------------------------------------------------- reply check

def check_reply(reply: Any, question: str) -> list[str]:
    """Shape and opening-word checks (the fallback has no proof to be faithful to)."""
    if not isinstance(reply, dict):
        return ["the reply must be a JSON object"]
    errs = []
    if missing := [k for k in ("verdict", "answer") if k not in reply]:
        errs.append(f"missing keys: {', '.join(missing)}")
    if extra := sorted(set(reply) - {"verdict", "answer"}):
        errs.append(f"unexpected keys: {', '.join(extra)}")
    verdict, text = reply.get("verdict"), reply.get("answer")
    if verdict not in VERDICTS:
        errs.append(f"verdict must be one of {', '.join(VERDICTS)}")
    if not isinstance(text, str) or not text.strip():
        return errs + ["`answer` must be a non-empty string"]
    pol = leading_polarity(text)
    if verdict in ("yes", "no"):
        want = verdict == "yes"
        if is_true_false(question):
            first = "đúng" if want else "sai"
            if not text.strip().lower().startswith(first):
                errs.append(f"a true/false question is answered starting with {first.capitalize()!r}")
        elif pol is None or pol != want:
            errs.append("a yes/no answer starts with a word of its verdict "
                        + ("(Có / Được / Đúng)" if want else "(Không / Sai)"))
    elif verdict == "unknown" and pol is not None:
        errs.append("an 'unknown' answer must not open with a yes or no word")
    return errs


# ---------------------------------------------------------------- the call

@dataclass
class FallbackAnswer:
    status: str                      # ok | failed
    verdict: str | None = None
    text: str = ""
    attempts: int = 0
    errors: list[list[str]] = field(default_factory=list)
    cost_usd: float = 0.0
    raw: list[str] = field(default_factory=list)
    prompt_id: str = ""


class AnswerFallback:
    def __init__(self, *, llm: LLMClient | None = None, version: str = DEFAULT_VERSION,
                 guard: SpendGuard | None = None) -> None:
        cfg = config(version)
        self.version = version
        self.llm = llm or LLMClient(model=cfg["model"], guard=guard or SpendGuard())
        self.effort = cfg.get("effort")
        self.max_tokens = int(cfg.get("max_tokens", 1500))
        self._system = system_prompt(version)
        self.prompt_id = prompt_id(version)

    def answer(self, image_path: str | Path, question: str, scene: SceneGraph | None) -> FallbackAnswer:
        img = prepare_file(image_path)
        user = [img.content_block(),
                {"type": "text", "text": user_text(question, scene, is_true_false(question))}]
        res = FallbackAnswer(status="failed", prompt_id=self.prompt_id)
        extra: list[dict] = []
        for attempt in (1, 2):
            res.attempts = attempt
            try:
                call = self.llm.json_reply(system=self._system, user=user, max_tokens=self.max_tokens,
                                           effort=self.effort, purpose="answer fallback",
                                           extra_messages=extra)
            except SpendLimitExceeded:
                raise
            except LLMBadJSON as e:
                res.cost_usd += getattr(e, "cost_usd", 0.0)
                res.raw.append(getattr(e, "raw_text", ""))
                errs = [str(e)]
            except LLMError as e:            # refusal or max_tokens: no retry
                res.cost_usd += getattr(e, "cost_usd", 0.0)
                res.raw.append(getattr(e, "raw_text", ""))
                res.errors.append([str(e)])
                return res
            else:
                res.cost_usd += call.cost_usd
                res.raw.append(call.raw_text)
                errs = check_reply(call.data, question)
                if not errs:
                    res.status, res.verdict = "ok", call.data["verdict"]
                    res.text = call.data["answer"].strip()
                    return res
            res.errors.append(errs)
            extra = retry_messages(errs)
        return res
