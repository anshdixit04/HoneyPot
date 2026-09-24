"""Run: cd backend && python -m tests.test_parser"""
import json
import os
import sqlite3
import tempfile

os.environ["HONEYPOT_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "honeypot.db")

from app import db, sessions, store  # noqa: E402
from app.parser import parse_client_info, parse_line  # noqa: E402


def line(**kw):
    return json.dumps({"session": "s1", "src_ip": "1.2.3.4", "timestamp": "2026-09-23T10:00:00Z", **kw})


def demo():
    e = parse_line(line(eventid="cowrie.session.file_download", url="http://x/bot.sh", shasum="abc"))
    assert (e["event_type"], e["detail"]) == ("file_download", "http://x/bot.sh sha256:abc")
    e = parse_line(line(eventid="cowrie.session.file_download.failed", url="http://x/m"))
    assert (e["event_type"], e["detail"]) == ("file_download", "http://x/m")
    e = parse_line(line(eventid="cowrie.session.file_upload", filename="a.bin", shasum="def"))
    assert (e["event_type"], e["detail"]) == ("file_upload", "a.bin sha256:def")
    e = parse_line(line(eventid="cowrie.direct-tcpip.request", dst_ip="8.8.8.8", dst_port=53))
    assert (e["event_type"], e["detail"]) == ("tunnel_request", "8.8.8.8:53")
    assert parse_line(line(eventid="cowrie.command.input", input="ls"))["detail"] is None
    # Same line -> same id (backfill idempotency); JSON that isn't an object is skipped.
    same = line(eventid="cowrie.command.input", input="ls")
    assert parse_line(same)["id"] == parse_line(same)["id"] != parse_line(line(eventid="cowrie.command.input", input="id"))["id"]
    assert parse_line('"just a string"') is None and parse_line("123") is None
    assert parse_line(line(eventid="cowrie.client.version", version="SSH-2.0-Go")) is None

    ver = parse_client_info(line(eventid="cowrie.client.version", version="SSH-2.0-Go"))
    kex = parse_client_info(line(eventid="cowrie.client.kex", hassh="h4ssh"))
    assert parse_client_info(line(eventid="cowrie.command.input", input="ls")) is None
    assert parse_client_info("not json") is None

    # Old-schema DB (pre-migration) must gain the new columns on init.
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute("CREATE TABLE events (id TEXT PRIMARY KEY, ts TEXT NOT NULL, src_ip TEXT, country TEXT,"
                     " city TEXT, lat REAL, lon REAL, asn TEXT, protocol TEXT, event_type TEXT NOT NULL,"
                     " username TEXT, password TEXT, command TEXT, session_id TEXT)")
    db.init_db()

    for info in (ver, kex):  # before any event: metadata upsert creates the row
        sessions.record_metadata(info["session_id"], info["column"], info["value"])
    event = parse_line(line(eventid="cowrie.session.file_download", url="http://x/bot.sh"))
    assert store.insert_event(event)
    sessions.record_event(event)
    assert not store.insert_event(event)  # replayed line: ignored, not duplicated
    assert [e["detail"] for e in store.get_events()] == ["http://x/bot.sh"]
    s = store.get_session("s1")
    assert (s["client_version"], s["hassh"]) == ("SSH-2.0-Go", "h4ssh")
    # Session times come from the event (so a backfill doesn't make July look like today).
    assert s["last_seen"].startswith("2026-09-23T10:00:00") and s["first_seen"] == s["last_seen"]
    assert s["src_ip"] == "1.2.3.4" and s["event_count"] == 1
    try:
        sessions.record_metadata("s1", "src_ip; DROP TABLE events", "x")
        raise AssertionError("unknown column accepted")
    except ValueError:
        pass
    print("ok")


if __name__ == "__main__":
    demo()
