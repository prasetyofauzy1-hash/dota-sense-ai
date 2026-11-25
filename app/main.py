"""FastAPI backend: `uvicorn app.main:app --reload`."""
from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Query

from app.config import settings
from app.data.opendota import OpenDotaClient, OpenDotaError
from app.database import models as db
from app.database.connection import connect
from app.gsi import receiver
from app.gsi.provider import MockProvider
from app.services import analyze

app = FastAPI(title="DotaSense AI", version="0.1.0",
              description="Read-only Dota 2 companion. Mock data unless live GSI is enabled.")
app.include_router(receiver.router)
conn = connect()
client = OpenDotaClient(conn)
mock = MockProvider()


def _provider():
    return receiver.live_provider if settings.live_integration_enabled else mock


def _require_live_token(x_dotasense_token: str | None = Header(None)) -> None:
    """Live match state is private: when live GSI is on, reading it needs DOTASENSE_GSI_TOKEN."""
    if not settings.live_integration_enabled:
        return
    if not settings.gsi_auth_token:
        raise HTTPException(503, "Set DOTASENSE_GSI_TOKEN to read live match state")
    if x_dotasense_token != settings.gsi_auth_token:
        raise HTTPException(401, "Invalid or missing X-DotaSense-Token header")


def _mock_for(scenario: str) -> MockProvider:
    if scenario not in mock.scenario_names():
        raise HTTPException(404, "Unknown scenario")
    return MockProvider(scenario=scenario)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "live_integration_enabled": settings.live_integration_enabled,
            "provider": _provider().status()}


@app.get("/mock/scenarios")
def scenarios() -> list[str]:
    return mock.scenario_names()


@app.get("/state")
def state(scenario: str | None = None, x_dotasense_token: str | None = Header(None)) -> dict:
    if scenario:
        return _mock_for(scenario).current_state().model_dump()
    _require_live_token(x_dotasense_token)
    return _provider().current_state().model_dump()


@app.get("/analysis")
def analysis(scenario: str | None = None, history: bool = True,
             x_dotasense_token: str | None = Header(None)) -> dict:
    if scenario:
        provider = _mock_for(scenario)
    else:
        _require_live_token(x_dotasense_token)
        provider = _provider()
    result = analyze(provider.current_state(), conn, client, use_history=history)
    return {k: (v.model_dump() if hasattr(v, "model_dump") else
                [x.model_dump() if hasattr(x, "model_dump") else x for x in v] if isinstance(v, list) else v)
            for k, v in result.items()}


@app.get("/coach/{match_id}")
def coach(match_id: int, account_id: int | None = Query(None), hero_id: int | None = Query(None)) -> dict:
    from app.engine.coach import coach_match

    try:
        report = coach_match(client, match_id, account_id=account_id, hero_id=hero_id)
    except OpenDotaError as exc:
        raise HTTPException(502, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    db.save_report(conn, report)
    return report


@app.get("/reports")
def reports() -> list[dict]:
    return db.list_reports(conn)
