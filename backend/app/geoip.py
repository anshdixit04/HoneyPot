"""
GeoIP enrichment via IP-API.com (free, no key, rate-limited to 45 req/min).

Lookups are cached in the `geoip_cache` SQLite table (see db.py) instead of
an in-memory dict so the cache survives restarts - most bot traffic re-hits
the same IP ranges repeatedly, so a warm cache matters after day one.
"""
from datetime import datetime, timezone
from typing import Optional

import requests

from app.db import connect

GEOIP_URL = "http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,lat,lon,as"


def lookup(ip: str) -> dict:
    empty = {"country": None, "city": None, "lat": None, "lon": None, "asn": None}
    if not ip:
        return empty

    cached = _get_cached(ip)
    if cached is not None:
        return cached

    result = empty
    try:
        resp = requests.get(GEOIP_URL.format(ip=ip), timeout=2)
        data = resp.json()
        if data.get("status") == "success":
            result = {
                "country": data.get("countryCode"),
                "city": data.get("city"),
                "lat": data.get("lat"),
                "lon": data.get("lon"),
                "asn": data.get("as"),
            }
    except requests.RequestException:
        pass  # never let GeoIP failures block the live event pipeline

    # Cache failures too (as `empty`) so a down/rate-limited API doesn't get
    # re-hit for the same IP on every subsequent event.
    _set_cached(ip, result)
    return result


def _get_cached(ip: str) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute(
            "SELECT country, city, lat, lon, asn FROM geoip_cache WHERE ip = ?", (ip,)
        ).fetchone()
    return dict(row) if row else None


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
