"""Application settings, read from environment variables (prefix DOTASENSE_)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.getenv("DOTASENSE_DB_PATH", ROOT_DIR / "dotasense.db")))
    mock_scenarios_dir: Path = ROOT_DIR / "config" / "mock_scenarios"
    opendota_base_url: str = os.getenv("DOTASENSE_OPENDOTA_URL", "https://api.opendota.com/api")
    opendota_api_key: str | None = os.getenv("OPENDOTA_API_KEY")
    # Offline mode: never call OpenDota, use the bundled snapshot only.
    offline: bool = _bool("DOTASENSE_OFFLINE", False)
    cache_ttl_seconds: int = int(os.getenv("DOTASENSE_CACHE_TTL", str(24 * 3600)))
    # Live Game State Integration stays OFF until its use is reviewed against
    # current Valve policy (see docs in README "Compliance").
    live_integration_enabled: bool = _bool("DOTASENSE_LIVE_GSI", False)
    gsi_auth_token: str | None = os.getenv("DOTASENSE_GSI_TOKEN")


settings = Settings()
