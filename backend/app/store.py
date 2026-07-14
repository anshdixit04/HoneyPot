"""
Event persistence + read queries backing the REST API (see
docs/02-design-doc.md section 2 for the /api/events and /api/stats
contracts). Uses the `events` table defined in db.py.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.db import connect


def insert_event(event: dict) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO events
               (id, ts, src_ip, country, city, lat, lon, asn, protocol,
                event_type, username, password, command, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event["id"], event["ts"], event.get("src_ip"), event.get("country"),
                event.get("city"), event.get("lat"), event.get("lon"), event.get("asn"),
                event.get("protocol"), event["event_type"], event.get("username"),
                event.get("password"), event.get("command"), event.get("session_id"),
            ),
        )


def get_events(limit: int = 100, before: Optional[str] = None) -> list:
    query = "SELECT * FROM events"
    params: list = []
    if before:
        query += " WHERE ts < ?"
        params.append(before)
    query += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_stats(hours: int = 24) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with connect() as conn:
        top_countries = [
            dict(r) for r in conn.execute(
                """SELECT country, COUNT(*) as count FROM events
                   WHERE ts >= ? AND country IS NOT NULL
                   GROUP BY country ORDER BY count DESC LIMIT 10""",
                (since,),
            )
        ]
        top_credentials = [
            dict(r) for r in conn.execute(
                """SELECT username, password, COUNT(*) as count FROM events
                   WHERE ts >= ? AND event_type = 'login_attempt'
                   GROUP BY username, password ORDER BY count DESC LIMIT 10""",
                (since,),
            )
        ]
        connections_by_hour = [
            dict(r) for r in conn.execute(
                """SELECT strftime('%Y-%m-%dT%H:00:00Z', ts) as hour, COUNT(*) as count
                   FROM events WHERE ts >= ? AND event_type = 'connection'
                   GROUP BY hour ORDER BY hour""",
                (since,),
            )
        ]
    return {
        "top_countries": top_countries,
        "top_credentials": top_credentials,
        "connections_by_hour": connections_by_hour,
    }


_SESSION_COLUMNS = """
    s.session_id, s.src_ip, s.first_seen, s.last_seen, s.event_count,
    s.credentials, s.commands, s.ttylog_path,
    (SELECT country FROM events e WHERE e.session_id = s.session_id AND e.country IS NOT NULL LIMIT 1) AS country,
    (SELECT city FROM events e WHERE e.session_id = s.session_id AND e.city IS NOT NULL LIMIT 1) AS city
"""


def get_top_sessions(hours: int = 24, limit: int = 8) -> list:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT {_SESSION_COLUMNS} FROM sessions s WHERE s.last_seen >= ?
               ORDER BY s.event_count DESC LIMIT ?""",
            (since, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_session(session_id: str) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute(
            f"SELECT {_SESSION_COLUMNS} FROM sessions s WHERE s.session_id = ?",
            (session_id,),
        ).fetchone()
    return dict(row) if row else None
