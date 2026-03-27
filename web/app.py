"""
RyTorr Web UI - FastAPI Backend with WebSocket support
Uses original RyTorr modules via downloader.py
"""

import os
import asyncio
import json
from pathlib import Path
from typing import List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from downloader import DownloadManager


app = FastAPI(title="RyTorr", description="BitTorrent Client Web UI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"
UPLOAD_DIR = WEB_DIR.parent / "torrents"

os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

manager = DownloadManager()


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        dead_connections = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.add(connection)

        for conn in dead_connections:
            self.active_connections.discard(conn)


ws_manager = ConnectionManager()


async def broadcast_loop():
    """Periodically broadcast torrent states to all connected clients."""
    while True:
        await asyncio.sleep(0.5)

        if ws_manager.active_connections:
            states = manager.get_all_states()
            global_stats = manager.get_global_stats()

            message = {
                "type": "update",
                "torrents": states,
                "global_stats": global_stats,
            }

            await ws_manager.broadcast(message)


@app.on_event("startup")
async def startup():
    asyncio.create_task(broadcast_loop())


@app.on_event("shutdown")
async def shutdown():
    manager.shutdown()


@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = TEMPLATES_DIR / "index.html"
    return FileResponse(str(index_path))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()

            action = data.get("action")

            if action == "add_torrent":
                torrent_path = data.get("path")
                if torrent_path and os.path.exists(torrent_path):
                    torrent_id = manager.add_torrent(torrent_path)
                    await websocket.send_json({
                        "type": "torrent_added",
                        "id": torrent_id,
                    })

            elif action == "pause":
                torrent_id = data.get("id")
                if torrent_id:
                    manager.pause_torrent(torrent_id)

            elif action == "resume":
                torrent_id = data.get("id")
                if torrent_id:
                    manager.resume_torrent(torrent_id)

            elif action == "remove":
                torrent_id = data.get("id")
                delete_files = data.get("delete_files", False)
                if torrent_id:
                    manager.remove_torrent(torrent_id, delete_files)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.post("/api/upload")
async def upload_torrent(file: UploadFile = File(...)):
    """Upload a .torrent file and start downloading."""
    if not file.filename.endswith(".torrent"):
        raise HTTPException(status_code=400, detail="File must be a .torrent file")

    try:
        file_path = UPLOAD_DIR / file.filename
        content = await file.read()

        with open(file_path, "wb") as f:
            f.write(content)

        torrent_id = manager.add_torrent(str(file_path))

        return {"id": torrent_id, "message": "Torrent added successfully"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/torrents")
async def get_torrents():
    """Get all torrent states."""
    return {
        "torrents": manager.get_all_states(),
        "global_stats": manager.get_global_stats(),
    }


@app.post("/api/torrents/{torrent_id}/pause")
async def pause_torrent(torrent_id: str):
    manager.pause_torrent(torrent_id)
    return {"status": "paused"}


@app.post("/api/torrents/{torrent_id}/resume")
async def resume_torrent(torrent_id: str):
    manager.resume_torrent(torrent_id)
    return {"status": "resumed"}


@app.delete("/api/torrents/{torrent_id}")
async def remove_torrent(torrent_id: str, delete_files: bool = False):
    manager.remove_torrent(torrent_id, delete_files)
    return {"status": "removed"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
