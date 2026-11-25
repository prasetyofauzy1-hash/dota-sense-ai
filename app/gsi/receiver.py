"""FastAPI router for receiving GSI POSTs from the Dota 2 client.

GSI is Valve's documented, read-only push of the player's own game state. Every push
must carry the token written into the Dota 2 config file (see app/gsi/dota_cfg.py).
Set DOTASENSE_LIVE_GSI=false to reject all pushes.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, Request

from app.config import gsi_token, settings
from app.gsi.provider import LiveGSIProvider

router = APIRouter(prefix="/gsi", tags=["gsi"])
live_provider = LiveGSIProvider()


@router.post("")
async def receive(request: Request) -> dict:
    if not settings.live_integration_enabled:
        raise HTTPException(status_code=403, detail="Live GSI integration is turned off.")
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="GSI payload must be a JSON object")
    token = str((payload.get("auth") or {}).get("token") or "")
    if not hmac.compare_digest(token, gsi_token()):
        raise HTTPException(status_code=401, detail="Invalid GSI auth token")
    live_provider.push(payload)
    return {"ok": True}


@router.get("/status")
def status() -> dict:
    return live_provider.status()
