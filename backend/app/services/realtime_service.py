import logging
from datetime import datetime, time
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.subscriptions: Dict[str, set] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        for codes in self.subscriptions.values():
            codes.discard(websocket)
        self.subscriptions = {k: v for k, v in self.subscriptions.items() if v}

    async def subscribe(self, websocket: WebSocket, codes: List[str]):
        for code in codes:
            if code not in self.subscriptions:
                self.subscriptions[code] = set()
            self.subscriptions[code].add(websocket)

    async def unsubscribe(self, websocket: WebSocket, codes: List[str]):
        for code in codes:
            if code in self.subscriptions:
                self.subscriptions[code].discard(websocket)

    async def broadcast(self, data: dict):
        import json
        message = json.dumps(data)
        disconnected = []
        for ws in self.active_connections:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


connection_manager = ConnectionManager()


async def get_realtime_quotes(codes: List[str]) -> dict:
    from app.data_sources.tencent_source import TencentSource
    from app.data_sources.easyquotation_source import EasyquotationSource
    from app.data_sources.manager import DataSourceError

    sources = [TencentSource(), EasyquotationSource()]
    for source in sources:
        try:
            return await source.fetch_realtime(codes)
        except Exception as e:
            logger.warning(f"{source.name} realtime failed: {e}")
    return {}


async def start_polling():
    logger.info("Realtime polling task started (disabled - requires scheduler integration)")

