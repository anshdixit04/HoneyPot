"""
One-off import of rotated Cowrie logs into the database, for periods the
live pump missed (e.g. 2026-07-25 -> 2026-09-24, when ingestion was dead).

Runs every line through the same path as the live pump (main._process_line),
so events, sessions and fingerprints come out identical. Event ids are
derived from the raw line (parser.parse_line), so re-running is safe.

    docker exec -d honeypot-backend python -m app.backfill \
        --after 2026-07-25T05:11:12 --before 2026-09-24T01:03 \
        /var/log/cowrie/cowrie.json.2026-07-25 /var/log/cowrie/cowrie.json.2026-07-26 ...

--after/--before bound Cowrie's own `timestamp` field (ISO strings compare
correctly as text), so events the live pump already stored are skipped.
"""
import argparse
import asyncio
import json
import logging
import sys

from app import db, geoip
from app.main import _process_line
from app.parser import RELEVANT_EVENTS


def _in_window(raw_line: str, after: str, before: str):
    """Returns the parsed line if its timestamp is inside the window."""
    try:
        raw = json.loads(raw_line)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    ts = raw.get("timestamp") or ""
    return raw if after <= ts < before else None


async def backfill(paths: list, after: str, before: str) -> None:
    db.init_db()

    # Pass 1: warm the GeoIP cache in batches - one lookup per event would
    # take days at ip-api's 45 req/min limit.
    ips = set()
    for path in paths:
        with open(path, errors="replace") as fh:
            for line in fh:
                raw = _in_window(line, after, before)
                if raw and raw.get("eventid") in RELEVANT_EVENTS and raw.get("src_ip"):
                    ips.add(raw["src_ip"])
    print(f"{len(ips)} unique IPs; prefetching GeoIP...", flush=True)
    print(f"cached {geoip.prefetch(sorted(ips))} IPs", flush=True)

    # Pass 2: replay.
    count = failed = 0
    for path in paths:
        with open(path, errors="replace") as fh:
            for line in fh:
                if _in_window(line, after, before) is None:
                    continue
                try:
                    await _process_line(line)
                except Exception as exc:  # same policy as the live pump: skip the line
                    failed += 1
                    print(f"skip ({exc!r}): {line[:120]}", file=sys.stderr, flush=True)
                count += 1
                if count % 10000 == 0:
                    print(f"{path}: {count} lines replayed", flush=True)
        print(f"done {path} ({count} lines so far)", flush=True)
    print(f"finished: {count} lines replayed, {failed} failed", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--after", required=True, help="ISO timestamp, inclusive")
    ap.add_argument("--before", required=True, help="ISO timestamp, exclusive")
    ap.add_argument("paths", nargs="+")
    args = ap.parse_args()
    logging.getLogger("honeypot-backend").setLevel(logging.WARNING)  # no per-event log line
    asyncio.run(backfill(args.paths, args.after, args.before))


if __name__ == "__main__":
    main()
