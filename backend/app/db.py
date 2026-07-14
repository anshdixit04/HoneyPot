"""
SQLite persistence for the honeypot pipeline (see docs/02-design-doc.md
section 3 for the data model). One file, `data/honeypot.db`, shared by the
GeoIP cache, session tracking, and event history.
"""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get(
    "HONEYPOT_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "honeypot.db"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS geoip_cache (
    ip TEXT PRIMARY KEY,
    country TEXT,
    city TEXT,
    lat REAL,
    lon REAL,
    asn TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    src_ip TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    event_count INTEGER NOT NULL DEFAULT 0,
    credentials TEXT NOT NULL DEFAULT '',
    commands TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    src_ip TEXT,
    country TEXT,
    city TEXT,
    lat REAL,
    lon REAL,
    asn TEXT,
    protocol TEXT,
    event_type TEXT NOT NULL,
    username TEXT,
    password TEXT,
    command TEXT,
    session_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
"""


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
