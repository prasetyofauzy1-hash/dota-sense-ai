"""Game-state providers. Only the mock provider is active in this version."""
from __future__ import annotations

import json
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
    """Holds the latest payload pushed to the GSI receiver. Disabled unless
    DOTASENSE_LIVE_GSI=true, pending a policy review (see README)."""

    def __init__(self) -> None:
        self._latest: dict | None = None

    def push(self, payload: dict) -> None:
        self._latest = payload

    def current_state(self) -> GameState:
        if not settings.live_integration_enabled or self._latest is None:
            return GameState(source=DataSource.NONE, missing_fields=["live_data"])
        return parse_gsi(self._latest, source=DataSource.LIVE_GSI)

    def status(self) -> dict:
        if not settings.live_integration_enabled:
            return {"source": DataSource.LIVE_GSI.value, "connected": False, "is_mock": False,
                    "detail": "Live integration disabled pending Valve policy review"}
        return {"source": DataSource.LIVE_GSI.value, "connected": self._latest is not None,
                "is_mock": False, "detail": "Waiting for data" if self._latest is None else "Receiving"}
