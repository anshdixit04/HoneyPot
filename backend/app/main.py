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
from datetime import datetime, timezone
from typing import Optional

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*_args, **_kwargs):
        return False

# Must run before `from app import db, ...` — db.py reads HONEYPOT_DB_PATH
# from the environment at import time. See backend/.env (gitignored) for
# the machine-specific override used when the repo lives under a
# cloud-sync folder (see infra/docker-compose.yml for why).
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app import db, geoip, replay, report, sessions, store
from app.log_tailer import tail_file
from app.parser import parse_line, parse_log_closed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("honeypot-backend")

# Matches the bind mount in infra/docker-compose.yml. Override with the
# COWRIE_LOG_PATH env var (backend/.env) if your local layout differs.
COWRIE_LOG_PATH = os.environ.get(
    "COWRIE_LOG_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "cowrie-logs", "cowrie.json"),
)

# Ttylogs are binary and accumulate forever otherwise (docs/02-design-doc.md
# section 9.5). Files older than this get deleted by retention_loop().
TTYLOG_RETENTION_DAYS = int(os.environ.get("TTYLOG_RETENTION_DAYS", "14"))
RETENTION_INTERVAL_SECONDS = 24 * 60 * 60


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
        log_closed = parse_log_closed(raw_line)
        if log_closed is not None:
            await asyncio.to_thread(
                sessions.record_ttylog, log_closed["session_id"], log_closed["ttylog_filename"]
            )
            continue

        event = parse_line(raw_line)
        if event is None:
            continue
        geo = await asyncio.to_thread(geoip.lookup, event["src_ip"])
        event.update(geo)
        await asyncio.to_thread(sessions.record_event, event)
        await asyncio.to_thread(store.insert_event, event)
        logger.info("Event: %s from %s (%s)", event["event_type"], event["src_ip"], event.get("country"))
        await manager.broadcast(event)


async def retention_loop():
    """Background task: once a day, deletes ttylog files older than
    TTYLOG_RETENTION_DAYS and clears the DB references to them."""
    while True:
        deleted = await asyncio.to_thread(replay.prune_old_ttylogs, TTYLOG_RETENTION_DAYS)
        cleared = await asyncio.to_thread(store.clear_missing_ttylogs)
        if deleted or cleared:
            logger.info("Ttylog retention: deleted %d file(s), cleared %d session reference(s)", deleted, cleared)
        await asyncio.sleep(RETENTION_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    task = asyncio.create_task(event_pump())
    retention_task = asyncio.create_task(retention_loop())
    yield
    task.cancel()
    retention_task.cancel()


app = FastAPI(title="Honeypot Attack Map — Backend", lifespan=lifespan)

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


@app.get("/api/sessions")
async def api_sessions(range: str = "24h", limit: int = 8):
    hours = _parse_range_hours(range)
    rows = await asyncio.to_thread(store.get_top_sessions, hours, limit)
    return {
        "sessions": [
            {
                "session_id": r["session_id"],
                "src_ip": r["src_ip"],
                "country": r["country"],
                "city": r["city"],
                "first_seen": r["first_seen"],
                "last_seen": r["last_seen"],
                "event_count": r["event_count"],
                "commands": [c for c in (r["commands"] or "").split("\n") if c],
                "has_replay": bool(r["ttylog_path"]),
            }
            for r in rows
        ]
    }


@app.get("/api/sessions/{session_id}/replay")
async def api_session_replay(session_id: str):
    session = await asyncio.to_thread(store.get_session, session_id)
    if session is None or not session["ttylog_path"]:
        raise HTTPException(status_code=404, detail="No recording available for this session")

    cast = await asyncio.to_thread(replay.build_asciicast, session["ttylog_path"])
    if cast is None:
        raise HTTPException(status_code=404, detail="Recording could not be read")

    return Response(content=cast, media_type="text/plain; charset=utf-8")


@app.get("/api/sessions/{session_id}/replay/steps")
async def api_session_replay_steps(session_id: str):
    """Powers the guided "inject the next command" replay UI: the same
    recording as /replay, but pre-grouped into one step per command
    instead of raw timed frames (see replay.build_command_steps)."""
    session = await asyncio.to_thread(store.get_session, session_id)
    if session is None or not session["ttylog_path"]:
        raise HTTPException(status_code=404, detail="No recording available for this session")

    steps = await asyncio.to_thread(replay.build_command_steps, session["ttylog_path"])
    if steps is None:
        raise HTTPException(status_code=404, detail="Recording could not be read")

    return steps


@app.get("/api/report")
async def api_report(range: str = "24h", format: str = "pdf"):
    hours = _parse_range_hours(range)
    pdf_bytes = await asyncio.to_thread(report.build_report_pdf, range, hours)
    filename = f"honeypot-report-{range}-{datetime.now(timezone.utc).date()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
            # now — just keep the connection alive and detect disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
