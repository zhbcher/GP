from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.config import get_settings
from app.auth import verify_ws_key
from app.services.realtime_service import connection_manager

router = APIRouter()
settings = get_settings()


@router.websocket("/ws/quote")
async def ws_quote(ws: WebSocket):
    # Auth check for WebSocket
    if settings.auth_enabled:
        key = ws.query_params.get("key") or ws.query_params.get("token") or ""
        if not key or not verify_ws_key(key):
            await ws.close(code=4001, reason="Unauthorized")
            return
    await connection_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "subscribe":
                await connection_manager.subscribe(ws, data.get("codes", []))
            elif data.get("type") == "unsubscribe":
                await connection_manager.unsubscribe(ws, data.get("codes", []))
    except WebSocketDisconnect:
        connection_manager.disconnect(ws)
