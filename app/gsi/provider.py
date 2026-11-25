"""Game-state providers: live Dota 2 GSI and hand-written MOCK scenarios."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Protocol

from app.config import settings
from app.gsi.parser import parse_gsi
from app.models import DataSource, GameState


class GameStateProvider(Protocol):
    def current_state(self) -> GameState: ...

    def status(self) -> dict: ...


class MockProvider:
    """Serves hand-written MOCK scenarios from config/mock_scenarios/*.json.

    Every state it returns has is_mock=True. These are not real matches.
    """

    def __init__(self, scenarios_dir: Path | None = None, scenario: str | None = None):
        self.scenarios_dir = scenarios_dir or settings.mock_scenarios_dir
        names = self.scenario_names()
        if not names:
            raise FileNotFoundError(f"No mock scenarios in {self.scenarios_dir}")
        self.scenario = scenario if scenario in names else names[0]

    def scenario_names(self) -> list[str]:
        return sorted(p.stem for p in self.scenarios_dir.glob("*.json"))

    def load(self, name: str) -> dict:
        with open(self.scenarios_dir / f"{name}.json", encoding="utf-8") as fh:
            return json.load(fh)

    def current_state(self) -> GameState:
        return parse_gsi(self.load(self.scenario), source=DataSource.MOCK)

    def status(self) -> dict:
        return {"source": DataSource.MOCK.value, "connected": True, "is_mock": True,
                "detail": f"Mock scenario '{self.scenario}' (not a real match)"}


class LiveGSIProvider:
    """Latest payload pushed by the Dota 2 client to the GSI receiver.

    The payload is kept in a JSON file in the data folder so the API process and the
    dashboard (which may run separately) see the same live state.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.live_state_path

    def push(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v for k, v in payload.items() if k not in {"auth", "previously", "added"}}
        tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"received_at": time.time(), "payload": payload}), encoding="utf-8")
        os.replace(tmp, self.path)

    def _read(self) -> tuple[dict | None, float | None]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data.get("payload"), data.get("received_at")
        except (OSError, ValueError):
            return None, None

    def received_at(self) -> float | None:
        return self._read()[1]

    def age_seconds(self) -> float | None:
        received_at = self.received_at()
        return None if received_at is None else max(0.0, time.time() - received_at)

    def current_state(self) -> GameState:
        payload, _ = self._read()
        if not settings.live_integration_enabled or payload is None:
            return GameState(source=DataSource.NONE, missing_fields=["live_data"])
        return parse_gsi(payload, source=DataSource.LIVE_GSI)

    def status(self) -> dict:
        base = {"source": DataSource.LIVE_GSI.value, "is_mock": False}
        if not settings.live_integration_enabled:
            return {**base, "connected": False, "detail": "Live GSI turned off (DOTASENSE_LIVE_GSI=false)"}
        age = self.age_seconds()
        if age is None:
            return {**base, "connected": False, "detail": "Waiting for Dota 2 (start a match or demo hero)"}
        if age > settings.gsi_stale_seconds:
            return {**base, "connected": False, "detail": f"No data for {int(age)} s (Dota 2 closed?)"}
        return {**base, "connected": True, "detail": f"Receiving · last update {int(age)} s ago"}
