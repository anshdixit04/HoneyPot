"""
Per-session aggregation: credentials tried + commands typed, keyed by
Cowrie's session_id (see docs/02-design-doc.md section 3). Upserted as
events arrive so the `sessions` table stays current without a batch job -
this is what makes attacker session replay possible later.
"""
from datetime import datetime, timezone
from typing import Optional

from app.db import connect


def record_event(event: dict) -> None:
    session_id = event.get("session_id")
    if not session_id:
        return

    now = datetime.now(timezone.utc).isoformat()
    cred = None
    if event["event_type"] == "login_attempt":
        cred = f"{event.get('username') or ''}:{event.get('password') or ''}"
    command = event.get("command") if event["event_type"] == "command_input" else None

    with connect() as conn:
        row = conn.execute(
            "SELECT credentials, commands FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()

        if row is None:
            conn.execute(
                """INSERT INTO sessions
                   (session_id, src_ip, first_seen, last_seen, event_count, credentials, commands)
                   VALUES (?, ?, ?, ?, 1, ?, ?)""",
                (session_id, event.get("src_ip"), now, now, cred or "", command or ""),
            )
        else:
            conn.execute(
                """UPDATE sessions SET last_seen = ?, event_count = event_count + 1,
                   credentials = ?, commands = ? WHERE session_id = ?""",
                (now, _append(row["credentials"], cred), _append(row["commands"], command), session_id),
            )


SESSION_METADATA_COLUMNS = {"ttylog_path", "client_version", "hassh"}


def record_ttylog(session_id: str, ttylog_filename: str) -> None:
    """Attaches the session's ttylog filename once Cowrie closes it out
    (see parser.parse_log_closed)."""
    record_metadata(session_id, "ttylog_path", ttylog_filename)


def record_metadata(session_id: str, column: str, value: str) -> None:
    """Sets one per-session metadata column (ttylog, client fingerprint).
    May arrive before the session row exists if log lines are processed out
    of order, so upsert rather than assume."""
    if column not in SESSION_METADATA_COLUMNS:  # column name is interpolated below
        raise ValueError(f"not a session metadata column: {column}")
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        row = conn.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            conn.execute(
                f"""INSERT INTO sessions
                   (session_id, src_ip, first_seen, last_seen, event_count, credentials, commands, {column})
                   VALUES (?, '', ?, ?, 0, '', '', ?)""",
                (session_id, now, now, value),
            )
        else:
            conn.execute(f"UPDATE sessions SET {column} = ? WHERE session_id = ?", (value, session_id))


def _append(existing: str, new: Optional[str]) -> str:
    if not new:
        return existing
    return f"{existing}\n{new}" if existing else new
