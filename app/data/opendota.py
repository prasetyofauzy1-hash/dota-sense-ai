"""OpenDota API client (public, read-only) with SQLite caching and an offline snapshot fallback.

Docs: https://docs.opendota.com/  — free tier is rate limited (about 60 requests/min,
2000/day without a key). Set OPENDOTA_API_KEY for higher limits.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests

from app.config import settings
from app.database import models as db

log = logging.getLogger(__name__)
SNAPSHOT_DIR = Path(__file__).parent / "snapshot"


class OpenDotaError(RuntimeError):
    pass


class OpenDotaClient:
    def __init__(self, conn: sqlite3.Connection | None = None, *, base_url: str | None = None,
                 api_key: str | None = None, offline: bool | None = None, timeout: float = 10.0,
                 http: requests.Session | None = None):
        self.conn = conn
        self.base_url = (base_url or settings.opendota_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.opendota_api_key
        self.offline = settings.offline if offline is None else offline
        self.timeout = timeout
        self.http = http or requests.Session()

    def _get(self, path: str, *, max_age: float | None = None) -> Any:
        key = f"opendota:{path}"
        ttl = settings.cache_ttl_seconds if max_age is None else max_age
        if self.conn is not None:
            cached = db.cache_get(self.conn, key, ttl)
            if cached is not None:
                return cached
        if self.offline:
            raise OpenDotaError(f"Offline mode: {path} not cached")
        params = {"api_key": self.api_key} if self.api_key else None
        try:
            resp = self.http.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise OpenDotaError(f"OpenDota request failed ({type(exc).__name__})") from exc
        if resp.status_code != 200:
            raise OpenDotaError(f"OpenDota {path} returned HTTP {resp.status_code}")
        data = resp.json()
        if self.conn is not None:
            db.cache_put(self.conn, key, data)
        return data

    # --- Live endpoints ---------------------------------------------------
    def hero_item_popularity(self, hero_id: int) -> dict[str, dict[str, int]]:
        """Item purchase counts per game phase for a hero (recent public matches)."""
        return self._get(f"/heroes/{hero_id}/itemPopularity")

    def hero_matchups(self, hero_id: int) -> list[dict[str, int]]:
        """Games played / wins of this hero against each other hero."""
        return self._get(f"/heroes/{hero_id}/matchups")

    def match(self, match_id: int | str) -> dict:
        """Full match details. Parsed fields (purchase_log) exist only for parsed matches."""
        path = f"/matches/{int(match_id)}"
        data = self._get(path, max_age=7 * 24 * 3600)
        if not any(p.get("purchase_log") for p in data.get("players", [])):
            # Unparsed matches may get parsed later: refetch after an hour, keep the cached copy if that fails.
            try:
                data = self._get(path, max_age=3600)
            except OpenDotaError:
                pass
        return data


@lru_cache(maxsize=None)
def _load_snapshot(name: str) -> dict:
    with open(SNAPSHOT_DIR / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def snapshot_meta() -> dict:
    return _load_snapshot("meta")
