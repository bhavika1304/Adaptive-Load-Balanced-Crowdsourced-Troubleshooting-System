from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from app.routes import user, expert
from app.auth import auth_router
from app.routes import admin
from app.routes import profile
from app.routes import ratings
from app.routes import chat
from app.routes import status
from fastapi.middleware.cors import CORSMiddleware
from app.websocket_manager import ws_manager  # ✅ Import the singleton

app = FastAPI()

# ✅ Enable CORS for all origins (for dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ API Routers
app.include_router(user.router)
app.include_router(expert.router)
app.include_router(auth_router.router)
app.include_router(admin.router)
app.include_router(profile.router)
app.include_router(ratings.router)
app.include_router(status.router)
app.include_router(chat.router)

# ✅ WebSocket Endpoint
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id)
