"""API settings, read from environment variables once at start-up.

| Variable | Default | Meaning |
|---|---|---|
| VQA_DATABASE_URL | sqlite:///var/app.db | SQLAlchemy URL; postgresql+psycopg://... in Docker |
| VQA_UPLOAD_DIR | var/uploads | where uploaded images are kept, named by sha256 |
| VQA_PROFILE | phase52 | the frozen pipeline profile the API runs |
| VQA_ANSWER_FALLBACK | off | off: undecided questions get the rules' "not decided" answer; claude: the Sonnet answer fallback |
| VQA_SCENE_CACHE | (pipeline default) | scene cache directory |
| VQA_SPEND_LIMIT | (spend guard default) | Claude API spend limit in USD for this process |
| VQA_MAX_IMAGE_MB | 10 | largest accepted upload |
| VQA_CORS_ORIGINS | * | comma-separated origins allowed to call the API |
| VQA_HEARTBEAT_S | 15 | seconds between keep-alive comments on a quiet stream |
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FALLBACK_MODES = ("off", "claude")


@dataclass(frozen=True)
class Settings:
    database_url: str = f"sqlite:///{ROOT / 'var' / 'app.db'}"
    upload_dir: Path = ROOT / "var" / "uploads"
    profile: str = "phase52"
    answer_fallback: str = "off"
    scene_cache: Path | None = None
    max_spend: float | None = None
    max_image_bytes: int = 10 * 1024 * 1024
    cors_origins: tuple[str, ...] = ("*",)
    heartbeat_s: float = 15.0
    max_question_chars: int = 500
    extra: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.answer_fallback not in FALLBACK_MODES:
            raise ValueError(f"VQA_ANSWER_FALLBACK must be one of {FALLBACK_MODES}, not {self.answer_fallback!r}")

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        spend = env.get("VQA_SPEND_LIMIT")
        cache = env.get("VQA_SCENE_CACHE")
        return cls(
            database_url=env.get("VQA_DATABASE_URL", cls.database_url),
            upload_dir=Path(env.get("VQA_UPLOAD_DIR", str(cls.upload_dir))),
            profile=env.get("VQA_PROFILE", cls.profile),
            answer_fallback=env.get("VQA_ANSWER_FALLBACK", cls.answer_fallback),
            scene_cache=Path(cache) if cache else None,
            max_spend=float(spend) if spend else None,
            max_image_bytes=int(float(env.get("VQA_MAX_IMAGE_MB", "10")) * 1024 * 1024),
            cors_origins=tuple(o.strip() for o in env.get("VQA_CORS_ORIGINS", "*").split(",") if o.strip()),
            heartbeat_s=float(env.get("VQA_HEARTBEAT_S", "15")),
        )
