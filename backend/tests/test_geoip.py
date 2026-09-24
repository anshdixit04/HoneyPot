"""Run: cd backend && python3 -m tests.test_geoip  (needs `requests` installed)"""
import os
import tempfile

os.environ["HONEYPOT_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "honeypot.db")

import requests  # noqa: E402

from app import db, geoip  # noqa: E402


class FakeResp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.ok = status < 400

    def json(self):
        if self._body is None:
            raise requests.exceptions.JSONDecodeError("no body", "", 0)
        return self._body


def demo():
    db.init_db()
    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        return responses.pop(0)

    geoip.requests.get = fake_get
    ok = {"status": "success", "countryCode": "CN", "city": "Beijing", "lat": 1.0, "lon": 2.0, "as": "AS1"}

    # Rate-limited (429, non-JSON body): empty, NOT cached, and no more calls until the window resets.
    responses = [FakeResp(429, None, {"X-Ttl": "30"})]
    assert geoip.lookup("1.1.1.1")["country"] is None
    assert geoip.lookup("2.2.2.2")["country"] is None and len(calls) == 1
    assert geoip._get_cached("1.1.1.1") is None

    # Window over: the IP is looked up for real and cached.
    geoip._blocked_until = 0
    responses = [FakeResp(200, ok, {"X-Rl": "44"})]
    assert geoip.lookup("1.1.1.1")["country"] == "CN"
    assert geoip.lookup("1.1.1.1")["city"] == "Beijing" and len(calls) == 2  # served from cache

    # Private range ("fail") is a permanent answer: cached as empty...
    responses = [FakeResp(200, {"status": "fail"})]
    assert geoip.lookup("10.0.0.1")["country"] is None
    assert geoip._get_cached("10.0.0.1") is not None
    # ...but an empty row older than a day (e.g. an old cached rate-limit) is retried.
    with db.connect() as conn:
        conn.execute("UPDATE geoip_cache SET fetched_at = '2026-01-01T00:00:00+00:00' WHERE ip = '10.0.0.1'")
    assert geoip._get_cached("10.0.0.1") is None

    # Batch prefetch caches everything it gets back and skips cached IPs.
    posted = []
    geoip.requests.post = lambda url, json, timeout: posted.append(json) or FakeResp(
        200, [dict(ok, query=ip) for ip in json])
    assert geoip.prefetch(["1.1.1.1", "3.3.3.3", "3.3.3.3", "4.4.4.4"]) == 2
    assert posted == [["3.3.3.3", "4.4.4.4"]]
    assert geoip._get_cached("4.4.4.4")["country"] == "CN"
    print("ok")


if __name__ == "__main__":
    demo()
