"""Live settings: changed on the admin site, or by `rag-session.sh`, applied from the next question on.

The .env values (Settings) are the defaults. The app_setting table holds overrides. Before each
answer, the runner reads them and, if they differ from what the pipeline runs with, swaps the
pipeline's answer fallback, its `answer_fallback` switch and its spend limit. This is done in
app/ code only: the pipeline (vqa/) is unchanged and still decides exactly as frozen.
Questions already being answered finish with the settings they started with.

    python -m app.api.live show
    python -m app.api.live set answer_fallback=rag rag_url=http://rag-tunnel:8100
    python -m app.api.live reset [KEY ...]        # back to the .env values

Not live (they need a restart): the answer slots, the pipeline profile, passwords and keys.
"""

from __future__ import annotations

import dataclasses
import sys
from typing import Any

from app.api.settings import FALLBACK_MODES, Settings

KEYS = ("answer_fallback", "rag_url", "rag_cache", "spend_limit", "followup")


@dataclasses.dataclass(frozen=True)
class Live:
    answer_fallback: str
    rag_url: str
    rag_cache: bool
    spend_limit: float | None       # None: the spend guard's own default
    followup: bool = True           # rewrite follow-up questions (app/api/followup.py)

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def defaults(settings: Settings) -> Live:
    return Live(answer_fallback=settings.answer_fallback, rag_url=settings.rag_url,
                rag_cache=settings.rag_cache, spend_limit=settings.max_spend, followup=settings.followup)


def _bool(v: str) -> bool:
    s = v.strip().lower()
    if s in ("on", "1", "true", "yes"):
        return True
    if s in ("off", "0", "false", "no"):
        return False
    raise ValueError(f"not on/off: {v!r}")


def parse(key: str, value: str) -> Any:
    """A stored or given text value, checked. Raises ValueError for a bad one."""
    if key == "answer_fallback":
        v = value.strip().lower()
        if v not in FALLBACK_MODES:
            raise ValueError(f"answer_fallback must be one of {FALLBACK_MODES}")
        return v
    if key == "rag_url":
        v = value.strip().rstrip("/")
        if not v.startswith(("http://", "https://")) or len(v) > 200 or any(c.isspace() for c in v):
            raise ValueError("rag_url must be an http(s) URL")
        return v
    if key in ("rag_cache", "followup"):
        return _bool(value)
    if key == "spend_limit":
        f = float(value)
        if not 0 < f <= 1000:
            raise ValueError("spend_limit must be between 0 and 1000 USD")
        return f
    raise ValueError(f"unknown setting {key!r}; one of {KEYS}")


def to_text(key: str, value: Any) -> str:
    if key in ("rag_cache", "followup"):
        return "on" if value else "off"
    return str(value)


def effective(settings: Settings, overrides: dict[str, str]) -> Live:
    """The .env defaults with the stored overrides on top. A bad stored value is ignored."""
    values = defaults(settings).as_dict()
    for k, v in overrides.items():
        if k in KEYS:
            try:
                values[k] = parse(k, v)
            except ValueError:
                pass
    return Live(**values)


def main(argv: list[str]) -> None:
    from app.api.storage import Store
    settings = Settings.from_env()
    store = Store(settings.database_url)
    cmd, args = (argv[0] if argv else "show"), argv[1:]
    if cmd == "set":
        values: dict[str, str | None] = {}
        for a in args:
            k, sep, v = a.partition("=")
            if not sep:
                raise SystemExit(f"expected KEY=VALUE, got {a!r}")
            values[k] = to_text(k, parse(k, v))
        store.set_overrides(values)
    elif cmd == "reset":
        store.set_overrides({k: None for k in (args or KEYS)})
    elif cmd != "show":
        raise SystemExit("usage: python -m app.api.live show | set KEY=VALUE ... | reset [KEY ...]")
    over = store.settings_overrides()
    live = effective(settings, over)
    for k in KEYS:
        print(f"{k}={to_text(k, getattr(live, k))}" + ("  (live setting)" if k in over else "  (.env)"))


if __name__ == "__main__":
    main(sys.argv[1:])
