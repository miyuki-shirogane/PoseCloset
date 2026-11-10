from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = ROOT / "index" / "pose_outfit_index.json"

POSE_CATEGORIES = {
    "full": {"name": "全身单人・标准系", "order": 10},
    "bust": {"name": "上半身单人", "order": 20},
}

OUTFIT_CATEGORIES = {
    "春": {"name": "春装", "order": 10},
    "夏": {"name": "夏装", "order": 20},
    "秋": {"name": "秋装", "order": 30},
    "冬": {"name": "冬装", "order": 40},
    "パーティ": {"name": "派对", "order": 50},
}

ALLOWED_POSE_SYSTEMS = frozenset(POSE_CATEGORIES)
ALLOWED_OUTFIT_CATEGORIES = frozenset(OUTFIT_CATEGORIES)

ASSET_ORIGINS = {
    "pose": "https://ai-pose-gallery.anhao.app",
    "outfit": "https://ai-costume-gallery.pages.dev",
}

ASPECT_RATIOS = ("1:1", "3:4", "4:3", "2:3", "3:2", "9:16", "16:9")
MAX_BATCH_LIMIT = 20

DEFAULT_SPEC = {
    "aspect_ratio": "3:4",
    "size": "1024x1536",
    "n": 1,
    "style": "photo",
    "watermark": False,
}


def _state_dir() -> Path:
    override = os.environ.get("POSE_STATE_DIR")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "pose-outfit"


@dataclass(frozen=True)
class Config:
    deployment: str = "personal"
    pose_library: str = "upstream"
    index_path: Path = DEFAULT_INDEX
    state_dir: Path = None  # type: ignore[assignment]
    renderer: str = "mock"
    asset_timeout: float = 20.0
    asset_max_bytes: int = 12_000_000
    subject_max_bytes: int = 10_000_000
    session_ttl_hours: float = 24.0
    session_max_batch: int = 5

    def __post_init__(self) -> None:
        if self.state_dir is None:
            object.__setattr__(self, "state_dir", _state_dir())
        object.__setattr__(self, "index_path", Path(self.index_path))
        object.__setattr__(self, "state_dir", Path(self.state_dir))
        object.__setattr__(self, "session_max_batch", max(1, min(MAX_BATCH_LIMIT, int(self.session_max_batch))))

    @property
    def commercial(self) -> bool:
        return self.deployment == "commercial"

    @classmethod
    def from_env(cls, env=None) -> "Config":
        env = os.environ if env is None else env

        def num(name: str, default):
            raw = env.get(name)
            if raw is None or raw == "":
                return default
            try:
                return type(default)(raw)
            except (TypeError, ValueError):
                return default

        return cls(
            deployment=env.get("POSE_DEPLOYMENT", "personal"),
            pose_library=env.get("POSE_LIBRARY", "upstream"),
            index_path=Path(env.get("POSE_INDEX", str(DEFAULT_INDEX))),
            state_dir=Path(env["POSE_STATE_DIR"]) if env.get("POSE_STATE_DIR") else None,
            renderer=env.get("POSE_RENDERER", "mock"),
            asset_timeout=num("POSE_ASSET_TIMEOUT", 20.0),
            asset_max_bytes=num("POSE_ASSET_MAX_BYTES", 12_000_000),
            subject_max_bytes=num("POSE_SUBJECT_MAX_BYTES", 10_000_000),
            session_ttl_hours=num("POSE_SESSION_TTL_HOURS", 24.0),
            session_max_batch=num("POSE_SESSION_MAX_BATCH", 5),
        )
