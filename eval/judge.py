"""The Natural-QA judge (docs/plans/phase-4.md, item 4; D4). Eval only: it never
lives in vqa/ and inference never imports it.

Opus 5.5 compares a predicted answer with the gold answer on the key facts and
returns correct / partial / wrong, scored 1 / 0.5 / 0. The strict score counts
partial as 0. The prompt (eval/prompts/judge/<version>/) and the model are pinned
by a test before the first phase-4 result. One retry that sends only the error;
a second failure is recorded as `error` and scored 0.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqa.llm.client import LLMBadJSON, LLMClient, LLMError  # noqa: E402
from vqa.llm.spend import SpendGuard, SpendLimitExceeded  # noqa: E402
from vqa.perception.wire import retry_messages  # noqa: E402

PROMPTS = ROOT / "eval" / "prompts" / "judge"
DEFAULT_VERSION = "v1"
SCORES = {"correct": 1.0, "partial": 0.5, "wrong": 0.0, "error": 0.0}
STRICT = {"correct": 1.0, "partial": 0.0, "wrong": 0.0, "error": 0.0}


@lru_cache(maxsize=4)
def config(version: str = DEFAULT_VERSION) -> dict[str, Any]:
    return yaml.safe_load((PROMPTS / version / "config.yaml").read_text(encoding="utf-8"))


def system_prompt(version: str = DEFAULT_VERSION) -> str:
    return (PROMPTS / version / "spec.md").read_text(encoding="utf-8").strip()


def prompt_hash(version: str = DEFAULT_VERSION) -> str:
    text = system_prompt(version) + "\n--config--\n" + (PROMPTS / version / "config.yaml").read_text("utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_id(version: str = DEFAULT_VERSION) -> str:
    return f"judge/{version}@{prompt_hash(version)[:12]}"


def user_text(question: str, gold: str, prediction: str) -> str:
    return f"Question: {question.strip()}\nGold answer: {gold.strip()}\nPredicted answer: {prediction.strip()}"


def check(reply: Any) -> list[str]:
    if not isinstance(reply, dict):
        return ["the reply must be a JSON object"]
    errs = []
    if reply.get("label") not in ("correct", "partial", "wrong"):
        errs.append("label must be correct, partial or wrong")
    if extra := sorted(set(reply) - {"label", "reason"}):
        errs.append(f"unexpected keys: {', '.join(extra)}")
    return errs


@dataclass
class Verdict:
    label: str                 # correct | partial | wrong | error
    reason: str = ""
    cost_usd: float = 0.0

    @property
    def score(self) -> float:
        return SCORES[self.label]

    @property
    def strict(self) -> float:
        return STRICT[self.label]


class Judge:
    def __init__(self, *, llm: LLMClient | None = None, version: str = DEFAULT_VERSION,
                 guard: SpendGuard | None = None) -> None:
        cfg = config(version)
        self.llm = llm or LLMClient(model=cfg["model"], guard=guard or SpendGuard())
        self.effort, self.max_tokens = cfg.get("effort"), int(cfg.get("max_tokens", 1500))
        self.system = system_prompt(version)
        self.prompt_id = prompt_id(version)

    def grade(self, question: str, gold: str, prediction: str) -> Verdict:
        if not prediction.strip():
            return Verdict("wrong", "empty prediction")
        user, extra, cost = user_text(question, gold, prediction), [], 0.0
        for _ in (1, 2):
            try:
                call = self.llm.json_reply(system=self.system, user=user, max_tokens=self.max_tokens,
                                           effort=self.effort, purpose="judge", extra_messages=extra)
            except SpendLimitExceeded:
                raise
            except LLMBadJSON as e:
                cost += getattr(e, "cost_usd", 0.0)
                errs = [str(e)]
            except LLMError as e:
                return Verdict("error", str(e), cost + getattr(e, "cost_usd", 0.0))
            else:
                cost += call.cost_usd
                errs = check(call.data)
                if not errs:
                    return Verdict(call.data["label"], str(call.data.get("reason", "")), cost)
            extra = retry_messages(errs)
        return Verdict("error", "; ".join(errs), cost)
