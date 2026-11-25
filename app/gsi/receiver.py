"""FastAPI router for receiving GSI POSTs from the Dota 2 client.

DISABLED by default. Valve documents GSI for tools such as overlays, but this project
does not assume its use is approved for live matchmaking. Until reviewed, requests are
rejected with HTTP 403 and nothing is stored.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.gsi.provider import LiveGSIProvider

router = APIRouter(prefix="/gsi", tags=["gsi"])
live_provider = LiveGSIProvider()


@router.post("")
async def receive(request: Request) -> dict:
    if not settings.live_integration_enabled:
        raise HTTPException(status_code=403, detail="Live GSI integration is disabled pending policy review.")
    payload = await request.json()
    token = (payload.get("auth") or {}).get("token")
    if settings.gsi_auth_token and token != settings.gsi_auth_token:
        raise HTTPException(status_code=401, detail="Invalid GSI auth token")
    live_provider.push(payload)
    return {"ok": True}


@router.get("/status")
def status() -> dict:
    return live_provider.status()
