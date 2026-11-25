"""Application settings, read from environment variables (prefix DOTASENSE_)."""
from __future__ import annotations

import os
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FROZEN = bool(getattr(sys, "frozen", False))


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_data_dir() -> Path:
    """Writable folder for the database, GSI token and live state.

    The installed Windows app keeps its data in %LOCALAPPDATA%\\DotaSenseAI; a source
    checkout keeps it in the repo root as before.
    """
    if os.getenv("DOTASENSE_DATA_DIR"):
        return Path(os.environ["DOTASENSE_DATA_DIR"])
    if FROZEN:
        base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "DotaSenseAI"
    return ROOT_DIR


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=_default_data_dir)
    db_path: Path = field(default_factory=lambda: Path(os.getenv("DOTASENSE_DB_PATH", _default_data_dir() / "dotasense.db")))
    mock_scenarios_dir: Path = ROOT_DIR / "config" / "mock_scenarios"
    opendota_base_url: str = os.getenv("DOTASENSE_OPENDOTA_URL", "https://api.opendota.com/api")
    opendota_api_key: str | None = os.getenv("OPENDOTA_API_KEY")
    # Offline mode: never call OpenDota, use the bundled snapshot only.
    offline: bool = _bool("DOTASENSE_OFFLINE", False)
    cache_ttl_seconds: int = int(os.getenv("DOTASENSE_CACHE_TTL", str(24 * 3600)))
    # Live Game State Integration: Valve's documented, read-only HTTP push from the Dota 2 client.
    live_integration_enabled: bool = _bool("DOTASENSE_LIVE_GSI", True)
    gsi_auth_token: str | None = os.getenv("DOTASENSE_GSI_TOKEN")
    gsi_host: str = os.getenv("DOTASENSE_GSI_HOST", "127.0.0.1")
    gsi_port: int = int(os.getenv("DOTASENSE_GSI_PORT", "47690"))
    # Seconds without a GSI push before live data is shown as stale.
    gsi_stale_seconds: int = int(os.getenv("DOTASENSE_GSI_STALE", "45"))

    @property
    def live_state_path(self) -> Path:
        return self.data_dir / "live_gsi_latest.json"

    @property
    def gsi_url(self) -> str:
        return f"http://{self.gsi_host}:{self.gsi_port}/gsi"


settings = Settings()


def gsi_token() -> str:
    """Token Dota 2 sends with every GSI push: DOTASENSE_GSI_TOKEN, else one generated once and kept."""
    if settings.gsi_auth_token:
        return settings.gsi_auth_token
    path = settings.data_dir / ".dotasense_gsi_token"
    try:
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    except OSError:
        pass
    token = secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8")
    return token
