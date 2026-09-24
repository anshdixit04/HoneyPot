"""
Parses raw Cowrie JSON log lines into the normalized event shape used
throughout the rest of the pipeline (see docs/02-design-doc.md, section 2,
for the WebSocket event contract).

Cowrie event types we care about for the prototype:
  - cowrie.session.connect   -> event_type "connection"
  - cowrie.login.failed      -> event_type "login_attempt" (success=False)
  - cowrie.login.success     -> event_type "login_attempt" (success=True)
  - cowrie.command.input     -> event_type "command_input"
  - cowrie.session.file_download[.failed] -> event_type "file_download" (detail = url + sha256)
  - cowrie.session.file_upload            -> event_type "file_upload"   (detail = filename + sha256)
  - cowrie.direct-tcpip.request           -> event_type "tunnel_request" (detail = dst_ip:dst_port)

Client fingerprints (cowrie.client.version / cowrie.client.kex) are session
metadata, not events - see parse_client_info().
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
    "cowrie.session.file_download",
    "cowrie.session.file_download.failed",
    "cowrie.session.file_upload",
    "cowrie.direct-tcpip.request",
}

EVENT_TYPE_MAP = {
    "cowrie.session.connect": "connection",
    "cowrie.login.failed": "login_attempt",
    "cowrie.login.success": "login_attempt",
    "cowrie.command.input": "command_input",
    "cowrie.session.file_download": "file_download",
    "cowrie.session.file_download.failed": "file_download",
    "cowrie.session.file_upload": "file_upload",
    "cowrie.direct-tcpip.request": "tunnel_request",
}


def _detail(eventid: str, raw: dict) -> Optional[str]:
    """The one interesting value for the non-login/command event types."""
    sha = f" sha256:{raw['shasum']}" if raw.get("shasum") else ""
    if eventid.startswith("cowrie.session.file_download"):
        return f"{raw.get('url') or '?'}{sha}"
    if eventid == "cowrie.session.file_upload":
        return f"{raw.get('filename') or '?'}{sha}"
    if eventid == "cowrie.direct-tcpip.request":
        return f"{raw.get('dst_ip') or '?'}:{raw.get('dst_port') or '?'}"
    return None


def parse_line(raw_line: str) -> Optional[dict]:
    """Parse one Cowrie JSON log line. Returns None if not a relevant event
    or if the line fails to parse (malformed/partial lines happen during
    rotation - caller should just skip them, not crash)."""
    raw_line = raw_line.strip()
    if not raw_line:
        return None

    try:
        raw = json.loads(raw_line)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
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
        # Derived from the raw line, so replaying a log (backfill) inserts
        # each event once - store.insert_event is INSERT OR IGNORE.
        "id": str(uuid.uuid5(uuid.NAMESPACE_OID, raw_line)),
        "ts": parsed_ts.isoformat(),
        "src_ip": raw.get("src_ip"),
        # Filled in by geoip.py - placeholders here so the contract shape
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
        "detail": _detail(eventid, raw),
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

    if not isinstance(raw, dict) or raw.get("eventid") != "cowrie.log.closed":
        return None

    session_id = raw.get("session")
    ttylog = raw.get("ttylog")
    if not session_id or not ttylog:
        return None

    return {"session_id": session_id, "ttylog_filename": ttylog.rsplit("/", 1)[-1]}


def parse_client_info(raw_line: str) -> Optional[dict]:
    """`cowrie.client.version` (SSH client banner) and `cowrie.client.kex`
    (HASSH fingerprint) identify the attacker's tooling across IPs. They fire
    on every SSH connection, so they're stored on the session row rather
    than flooding the events feed."""
    try:
        raw = json.loads(raw_line)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict) or not raw.get("session"):
        return None

    eventid = raw.get("eventid")
    if eventid == "cowrie.client.version" and raw.get("version"):
        return {"session_id": raw["session"], "column": "client_version", "value": raw["version"]}
    if eventid == "cowrie.client.kex" and raw.get("hassh"):
        return {"session_id": raw["session"], "column": "hassh", "value": raw["hassh"]}
    return None
