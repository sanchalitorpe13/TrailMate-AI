"""Application configuration. No secrets are required to run TrailMate AI."""

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    """Minimal .env loader: KEY=value lines; real environment variables win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    ollama_url: str
    ollama_model: str
    ollama_timeout_seconds: float
    database_path: Path
    static_dir: Path


def _float_env(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, default))
        return value if value > 0 else default
    except ValueError:
        return default


def get_settings() -> Settings:
    db_path = Path(os.environ.get("TRAILMATE_DB_PATH", "data/trailmate.db"))
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path
    return Settings(
        ollama_url=os.environ.get("TRAILMATE_OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        ollama_model=os.environ.get("TRAILMATE_OLLAMA_MODEL", "gemma3:4b"),
        ollama_timeout_seconds=_float_env("TRAILMATE_OLLAMA_TIMEOUT", 90.0),
        database_path=db_path,
        static_dir=BASE_DIR / "static",
    )