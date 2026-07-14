"""
Parses raw Cowrie JSON log lines into the normalized event shape used
throughout the rest of the pipeline (see docs/02-design-doc.md, section 2,
for the WebSocket event contract).

Cowrie event types we care about for the prototype:
  - cowrie.session.connect   -> event_type "connection"
  - cowrie.login.failed      -> event_type "login_attempt" (success=False)
  - cowrie.login.success     -> event_type "login_attempt" (success=True)
  - cowrie.command.input     -> event_type "command_input"

Everything else is ignored for now (Phase 1+ can widen this).
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

RELEVANT_EVENTS = {
    "cowrie.session.connect",
    "cowrie.login.failed",
    "cowrie.login.success",
    "cowrie.command.input",
}

EVENT_TYPE_MAP = {
    "cowrie.session.connect": "connection",
    "cowrie.login.failed": "login_attempt",
    "cowrie.login.success": "login_attempt",
    "cowrie.command.input": "command_input",
}


def parse_line(raw_line: str) -> Optional[dict]:
    """Parse one Cowrie JSON log line. Returns None if not a relevant event
    or if the line fails to parse (malformed/partial lines happen during
    rotation — caller should just skip them, not crash)."""
    raw_line = raw_line.strip()
    if not raw_line:
        return None

    try:
        raw = json.loads(raw_line)
    except json.JSONDecodeError:
        return None

    eventid = raw.get("eventid")
    if eventid not in RELEVANT_EVENTS:
        return None

    ts = raw.get("timestamp")
    try:
        parsed_ts = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else datetime.now(timezone.utc)
    except (ValueError, AttributeError):
        parsed_ts = datetime.now(timezone.utc)

    event = {
        "id": str(uuid.uuid4()),
        "ts": parsed_ts.isoformat(),
        "src_ip": raw.get("src_ip"),
        # Filled in by geoip.py — placeholders here so the contract shape
        # matches the design doc regardless of enrichment success/failure.
        "country": None,
        "city": None,
        "lat": None,
        "lon": None,
        "asn": None,
        "protocol": raw.get("protocol", "ssh" if "SSH" in raw.get("system", "") else "telnet"),
        "event_type": EVENT_TYPE_MAP[eventid],
        "username": raw.get("username"),
        "password": raw.get("password"),
        "command": raw.get("input") if eventid == "cowrie.command.input" else None,
        "session_id": raw.get("session"),
    }
    return event


def parse_log_closed(raw_line: str) -> Optional[dict]:
    """`cowrie.log.closed` carries the session's ttylog filename (the raw
    per-keystroke recording used for session replay). It's session
    metadata, not an attack event, so it's parsed separately from
    parse_line() and never goes through the events table/broadcast."""
    raw_line = raw_line.strip()
    if not raw_line:
        return None

    try:
        raw = json.loads(raw_line)
    except json.JSONDecodeError:
        return None

    if raw.get("eventid") != "cowrie.log.closed":
        return None

    session_id = raw.get("session")
    ttylog = raw.get("ttylog")
    if not session_id or not ttylog:
        return None

    return {"session_id": session_id, "ttylog_filename": ttylog.rsplit("/", 1)[-1]}
