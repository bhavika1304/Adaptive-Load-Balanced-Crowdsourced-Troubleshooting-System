# websocket_manager.py
from typing import Dict, Any
from fastapi import WebSocket
import json

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        print(f"✅ WebSocket connected: {user_id}")

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)

    async def send_event(self, user_id: str, event: str, data: Any = None):
        ws = self.active_connections.get(user_id)
        if ws:
            message = {
                "event": event,
                "data": data
            }
            await ws.send_text(json.dumps(message))

# ✅ Don't create in main.py — create globally here!
ws_manager = WebSocketManager()
