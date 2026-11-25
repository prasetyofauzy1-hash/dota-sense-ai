"""OpenDota API client (public, read-only) with SQLite caching and an offline snapshot fallback.

Docs: https://docs.opendota.com/  — free tier is rate limited (about 60 requests/min,
2000/day without a key). Set OPENDOTA_API_KEY for higher limits.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests

from app.config import settings
from app.database import models as db

log = logging.getLogger(__name__)
SNAPSHOT_DIR = Path(__file__).parent / "snapshot"

PARSED_MATCH_TTL = 7 * 24 * 3600
UNPARSED_MATCH_TTL = 300  # 5 minutes so newly parsed matches are picked up
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_MATCH_URL_RE = re.compile(r"^https?://(?:www\.)?(?:opendota|dotabuff)\.com/matches/(\d+)(?:[/?#].*)?$")


class OpenDotaError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, timed_out: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.timed_out = timed_out


def parse_match_id(raw: int | str) -> int:
    """Parse a positive Dota 2 match ID from an int, numeric string, or OpenDota/Dotabuff URL."""
    if isinstance(raw, bool):
        raise ValueError("Enter a valid positive numeric match ID (or an OpenDota/Dotabuff match URL).")
    if isinstance(raw, int):
        if raw <= 0:
            raise ValueError("Match ID must be a positive number.")
        return raw
    text = str(raw).strip()
    if text.isdigit():
        mid = int(text)
        if mid <= 0:
            raise ValueError("Match ID must be a positive number.")
        return mid
    m = _MATCH_URL_RE.match(text)
    if m:
        mid = int(m.group(1))
        if mid > 0:
            return mid
    raise ValueError("Enter a valid positive numeric match ID (or an OpenDota/Dotabuff match URL).")


def _is_match_parsed(match: Any) -> bool:
    return isinstance(match, dict) and any(
        bool(p.get("purchase_log")) for p in (match.get("players") or []) if isinstance(p, dict)
    )


class OpenDotaClient:
    def __init__(self, conn: sqlite3.Connection | None = None, *, base_url: str | None = None,
                 api_key: str | None = None, offline: bool | None = None, timeout: float = 10.0,
                 http: requests.Session | None = None, max_retries: int = 2, backoff_base: float = 1.0):
        self.conn = conn
        self.base_url = (base_url or settings.opendota_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.opendota_api_key
        self.offline = settings.offline if offline is None else offline
        self.timeout = timeout
        self.http = http or requests.Session()
        self.max_retries = max(0, max_retries)
        self.backoff_base = max(0.0, backoff_base)

    def _retry_delay(self, resp: requests.Response, attempt: int) -> float:
        if self.backoff_base == 0:
            return 0.0
        retry_after = resp.headers.get("Retry-After") if getattr(resp, "headers", None) else None
        if retry_after:
            try:
                return min(5.0, max(0.0, float(retry_after)))
            except ValueError:
                pass
        return min(5.0, self.backoff_base * (2 ** attempt))

    def _error_for_status(self, path: str, status_code: int) -> OpenDotaError:
        if status_code == 404:
            if path.startswith("/matches/"):
                return OpenDotaError(
                    "Match not found on OpenDota (HTTP 404). Check the match ID and make sure public match data is enabled.",
                    status_code=404,
                )
            return OpenDotaError(f"OpenDota resource not found: {path} (HTTP 404).", status_code=404)
        if status_code == 429:
            return OpenDotaError(
                "OpenDota rate limit reached (HTTP 429). Wait a minute and try again, or set OPENDOTA_API_KEY.",
                status_code=429,
            )
        if 500 <= status_code < 600:
            return OpenDotaError(
                f"OpenDota is temporarily unavailable (HTTP {status_code}). Try again in a moment.",
                status_code=status_code,
            )
        return OpenDotaError(f"OpenDota {path} returned HTTP {status_code}.", status_code=status_code)

    def _get(self, path: str, *, max_age: float | None = None, force_refresh: bool = False) -> Any:
        key = f"opendota:{path}"
        ttl = settings.cache_ttl_seconds if max_age is None else max_age
        if self.conn is not None and not force_refresh:
            cached = db.cache_get(self.conn, key, ttl)
            if cached is not None:
                return cached
        if self.offline:
            raise OpenDotaError(f"Offline mode: {path} not cached")
        params = {"api_key": self.api_key} if self.api_key else None
        last_err: OpenDotaError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.http.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
            except requests.Timeout as exc:
                last_err = OpenDotaError(
                    f"OpenDota timed out after {self.timeout:.0f}s. The API may be slow — try again in a moment.",
                    timed_out=True,
                )
                if attempt < self.max_retries:
                    delay = min(5.0, self.backoff_base * (2 ** attempt))
                    if delay > 0:
                        time.sleep(delay)
                    continue
                raise last_err from exc
            except requests.RequestException as exc:
                raise OpenDotaError(f"Could not reach OpenDota ({type(exc).__name__}).") from exc

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError as exc:
                    raise OpenDotaError(
                        f"OpenDota returned an unexpected non-JSON response for {path}.",
                        status_code=resp.status_code,
                    ) from exc
                if self.conn is not None:
                    db.cache_put(self.conn, key, data)
                return data

            last_err = self._error_for_status(path, resp.status_code)
            if resp.status_code in RETRYABLE_STATUSES and attempt < self.max_retries:
                delay = self._retry_delay(resp, attempt)
                log.warning("OpenDota %s returned HTTP %s; retrying in %.1fs", path, resp.status_code, delay)
                if delay > 0:
                    time.sleep(delay)
                continue
            raise last_err
        assert last_err is not None
        raise last_err

    # --- Live endpoints ---------------------------------------------------
    def hero_item_popularity(self, hero_id: int) -> dict[str, dict[str, int]]:
        """Item purchase counts per game phase for a hero (recent public matches)."""
        return self._get(f"/heroes/{hero_id}/itemPopularity")

    def hero_matchups(self, hero_id: int) -> list[dict[str, int]]:
        """Games played / wins of this hero against each other hero."""
        return self._get(f"/heroes/{hero_id}/matchups")

    def match(self, match_id: int | str, *, force_refresh: bool = False) -> dict:
        """Full match details. Parsed fields (purchase_log) exist only for parsed matches."""
        mid = parse_match_id(match_id)
        path = f"/matches/{mid}"
        key = f"opendota:{path}"
        stale_unparsed: dict | None = None
        if self.conn is not None:
            cached = db.cache_get(self.conn, key, PARSED_MATCH_TTL)
            if cached is not None:
                if _is_match_parsed(cached):
                    return cached
                if not force_refresh:
                    fresh_unparsed = db.cache_get(self.conn, key, UNPARSED_MATCH_TTL)
                    if fresh_unparsed is not None:
                        return fresh_unparsed
                    stale_unparsed = cached
        try:
            data = self._get(path, max_age=PARSED_MATCH_TTL, force_refresh=True)
        except OpenDotaError:
            if stale_unparsed is not None:
                return stale_unparsed
            raise
        if not isinstance(data, dict) or not data.get("players"):
            raise OpenDotaError(
                f"Match {mid} returned incomplete data from OpenDota (no players found).",
                status_code=404,
            )
        return data


@lru_cache(maxsize=None)
def _load_snapshot(name: str) -> dict:
    with open(SNAPSHOT_DIR / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def snapshot_meta() -> dict:
    return _load_snapshot("meta")
