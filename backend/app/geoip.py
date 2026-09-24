"""
GeoIP enrichment via IP-API.com (free, no key, rate-limited to 45 req/min).

Lookups are cached in the `geoip_cache` SQLite table (see db.py) instead of
an in-memory dict so the cache survives restarts - most bot traffic re-hits
the same IP ranges repeatedly, so a warm cache matters after day one.

ip-api bans clients that keep calling after hitting the limit, so we honour
its X-Rl (requests left) / X-Ttl (seconds until reset) headers and skip
lookups until the window resets. Skipped/failed lookups are NOT cached, so
the IP gets a real location on a later event instead of staying blank forever.
"""
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import requests

from app.db import connect

FIELDS = "status,query,country,countryCode,city,lat,lon,as"
GEOIP_URL = "http://ip-api.com/json/{ip}?fields=" + FIELDS
BATCH_URL = "http://ip-api.com/batch?fields=" + FIELDS
BATCH_SIZE = 100  # ip-api batch limit: 100 IPs per request, 15 requests/min
# Empty rows written by older versions (which cached rate-limit failures)
# are retried once they're this old.
EMPTY_RETRY_AFTER = timedelta(days=1)

EMPTY = {"country": None, "city": None, "lat": None, "lon": None, "asn": None}

_blocked_until = 0.0  # time.monotonic() before which we don't call ip-api


def lookup(ip: str) -> dict:
    if not ip:
        return dict(EMPTY)

    cached = _get_cached(ip)
    if cached is not None:
        return cached

    if time.monotonic() < _blocked_until:
        return dict(EMPTY)  # rate-limited: skip, and don't cache

    try:
        resp = requests.get(GEOIP_URL.format(ip=ip), timeout=2)
        _note_rate_limit(resp)
        # A non-2xx (e.g. HTTP 429) usually has a non-JSON body.
        data = resp.json() if resp.ok else None
    except (requests.RequestException, ValueError):
        # Network error/timeout or a garbage body. Never let a GeoIP hiccup
        # crash the live event pipeline - and don't cache it, it's transient.
        return dict(EMPTY)
    if not isinstance(data, dict):
        return dict(EMPTY)

    # status "fail" means private/reserved range - a permanent answer, cache it.
    result = _to_result(data)
    _set_cached(ip, result)
    return result


def prefetch(ips: Iterable[str]) -> int:
    """Warms the cache for many IPs via ip-api's batch endpoint (100 IPs per
    request, 15 requests/min - ~33x faster than single lookups). Used by the
    backfill so historical events get locations. Returns IPs cached."""
    todo = [ip for ip in dict.fromkeys(ips) if ip and _get_cached(ip) is None]
    done = 0
    for i in range(0, len(todo), BATCH_SIZE):
        chunk = todo[i:i + BATCH_SIZE]
        while True:
            wait = _blocked_until - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                resp = requests.post(BATCH_URL, json=chunk, timeout=15)
                _note_rate_limit(resp)
            except requests.RequestException:
                time.sleep(10)
                continue
            if resp.status_code == 429:
                continue  # _note_rate_limit set the wait
            break
        try:
            rows = resp.json() if resp.ok else []
        except ValueError:
            rows = []
        for data in rows:
            if isinstance(data, dict) and data.get("query"):
                _set_cached(data["query"], _to_result(data))
                done += 1
    return done


def _to_result(data: dict) -> dict:
    if data.get("status") != "success":
        return dict(EMPTY)
    return {
        "country": data.get("countryCode"),
        "city": data.get("city"),
        "lat": data.get("lat"),
        "lon": data.get("lon"),
        "asn": data.get("as"),
    }


def _note_rate_limit(resp: requests.Response) -> None:
    global _blocked_until
    if resp.status_code == 429 or resp.headers.get("X-Rl") == "0":
        try:
            ttl = int(resp.headers.get("X-Ttl", "60"))
        except ValueError:
            ttl = 60
        _blocked_until = time.monotonic() + ttl + 1


def _get_cached(ip: str) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute(
            "SELECT country, city, lat, lon, asn, fetched_at FROM geoip_cache WHERE ip = ?", (ip,)
        ).fetchone()
    if row is None:
        return None
    result = {k: row[k] for k in EMPTY}
    if result["country"] is None and _older_than(row["fetched_at"], EMPTY_RETRY_AFTER):
        return None  # stale empty answer - look it up again
    return result


def _older_than(ts: str, age: timedelta) -> bool:
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(ts) > age
    except (TypeError, ValueError):
        return True


def _set_cached(ip: str, result: dict) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO geoip_cache (ip, country, city, lat, lon, asn, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(ip) DO UPDATE SET
                 country=excluded.country, city=excluded.city, lat=excluded.lat,
                 lon=excluded.lon, asn=excluded.asn, fetched_at=excluded.fetched_at""",
            (
                ip,
                result["country"],
                result["city"],
                result["lat"],
                result["lon"],
                result["asn"],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
