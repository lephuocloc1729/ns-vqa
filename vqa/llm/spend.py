"""Spend guard and usage log.

Every run gets a SpendGuard with a USD limit (default $2, or VQA_SPEND_LIMIT, or a
--max-spend flag in the scripts). Before a request is sent its worst-case cost is
checked against what is left; the run stops instead of going over. Every request
is appended to logs/api_calls.jsonl (or $VQA_LOG_DIR/api_calls.jsonl).
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_LIMIT_USD = 2.0


class SpendLimitExceeded(RuntimeError):
    pass


def default_limit() -> float:
    v = os.environ.get("VQA_SPEND_LIMIT")
    return float(v) if v else DEFAULT_LIMIT_USD


class SpendGuard:
    def __init__(self, limit_usd: float | None = None) -> None:
        self.limit = default_limit() if limit_usd is None else float(limit_usd)
        self.spent = 0.0

    @property
    def remaining(self) -> float:
        return self.limit - self.spent

    def check(self, worst_case_usd: float, what: str = "request") -> None:
        if self.spent + worst_case_usd > self.limit:
            raise SpendLimitExceeded(
                f"{what} could cost up to ${worst_case_usd:.4f}; spent ${self.spent:.4f} of "
                f"the ${self.limit:.2f} limit. Raise it with --max-spend / VQA_SPEND_LIMIT.")

    def add(self, cost_usd: float) -> None:
        self.spent += cost_usd


def log_path() -> Path:
    root = Path(os.environ.get("VQA_LOG_DIR", Path(__file__).resolve().parents[2] / "logs"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "api_calls.jsonl"


def log_call(record: dict[str, Any]) -> None:
    rec = {"time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **record}
    with open(log_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
