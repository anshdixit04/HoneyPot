"""
Backend for the live honeypot dashboard (see docs/02-design-doc.md).

Tails the local Cowrie JSON log, parses relevant events, enriches them with
GeoIP + session tracking, persists them to SQLite, and broadcasts them to
every connected WebSocket client. Also serves REST history/stats endpoints
for the dashboard's initial load (see docs/02-design-doc.md section 2).
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv

# Must run before `from app import db, ...` - db.py reads HONEYPOT_DB_PATH
# from the environment at import time. See backend/.env (gitignored) for
# the machine-specific override used when the repo lives under a
# cloud-sync folder (see infra/docker-compose.yml for why).
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app import db, geoip, sessions, store
from app.log_tailer import tail_file
from app.parser import parse_line

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("honeypot-backend")

# Matches the bind mount in infra/docker-compose.yml. Override with the
# COWRIE_LOG_PATH env var (backend/.env) if your local layout differs.
COWRIE_LOG_PATH = os.environ.get(
    "COWRIE_LOG_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "cowrie-logs", "cowrie.json"),
)


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info("Dashboard client connected (%d total)", len(self.active))

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        logger.info("Dashboard client disconnected (%d total)", len(self.active))

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def event_pump():
    """Background task: tails the Cowrie log forever, parses, enriches, broadcasts."""
    logger.info("Watching Cowrie log at %s", COWRIE_LOG_PATH)
    async for raw_line in tail_file(COWRIE_LOG_PATH):
        event = parse_line(raw_line)
        if event is None:
            continue
        geo = await asyncio.to_thread(geoip.lookup, event["src_ip"])
        event.update(geo)
        await asyncio.to_thread(sessions.record_event, event)
        await asyncio.to_thread(store.insert_event, event)
        logger.info("Event: %s from %s (%s)", event["event_type"], event["src_ip"], event.get("country"))
        await manager.broadcast(event)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    task = asyncio.create_task(event_pump())
    yield
    task.cancel()


app = FastAPI(title="Honeypot Attack Map - Backend", lifespan=lifespan)

# Prototype/local-dev CORS: the Vite dev server runs on a different origin
# than the API. Tighten this to the deployed dashboard's origin in Phase 4.
allowed_origins = [
    origin.strip()
    for origin in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/api/events")
async def api_events(limit: int = 100, before: Optional[str] = None):
    events = await asyncio.to_thread(store.get_events, limit, before)
    return {"events": events}


@app.get("/api/stats")
async def api_stats(range: str = "24h"):
    stats = await asyncio.to_thread(store.get_stats, _parse_range_hours(range))
    return stats


def _parse_range_hours(range_str: str) -> int:
    try:
        if range_str.endswith("h"):
            return int(range_str[:-1])
        if range_str.endswith("d"):
            return int(range_str[:-1]) * 24
    except ValueError:
        pass
    return 24


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We don't expect inbound messages from the dashboard right
            # now - just keep the connection alive and detect disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
