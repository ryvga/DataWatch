"""Authenticated browser realtime transport."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy import select

from app.auth import decode_access_token
from app.database import AsyncSessionLocal
from app.models.organization import Organization
from app.models.user import User
from app.services.realtime import realtime_manager

router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])


@router.websocket("/ws")
async def realtime_socket(websocket: WebSocket) -> None:
    """Stream org events; browsers pass their normal JWT as a query token."""
    token = websocket.query_params.get("token") or websocket.query_params.get("access_token")
    if not token:
        await websocket.close(code=1008, reason="Bearer token required")
        return

    try:
        claims = decode_access_token(token)
        if claims.get("type") != "user":
            raise JWTError("not a user token")
    except (JWTError, KeyError, TypeError):
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.id == claims.get("sub"), User.is_active.is_(True)))
        org = await db.get(Organization, claims.get("org_id"))
    if not user or not org or user.org_id != org.id:
        await websocket.close(code=1008, reason="Workspace access denied")
        return

    org_id = str(org.id)
    await realtime_manager.connect(websocket, org_id)
    try:
        while True:
            message = await websocket.receive_text()
            if message.strip().lower() in {"ping", "heartbeat"}:
                await websocket.send_json({"version": 1, "type": "realtime.pong", "payload": {}})
    except WebSocketDisconnect:
        pass
    finally:
        await realtime_manager.disconnect(websocket, org_id)
