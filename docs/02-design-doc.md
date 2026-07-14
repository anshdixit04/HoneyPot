# Design Document — Live Honeypot Attack Map

Status: Draft v1
Owner: Ansh Dixit
Purpose: portfolio project demonstrating Linux hardening, network/SIEM-style log analysis, and real-time systems design to recruiters, via a public dashboard showing live attacker activity against a real honeypot.

## 1. Requirements

### Functional
- Run a real, internet-facing honeypot that emulates SSH/Telnet services (and optionally a fake IoT device banner).
- Capture every connection attempt, login attempt (credentials tried), and command an attacker types in a fake shell session.
- Enrich each event with geolocation (country, city, lat/lon) and ASN/organization where available.
- Stream events to a public web dashboard in real time (sub-second to few-second latency is fine — this is not a trading system).
- Show: live world map with pins, live scrolling event feed, aggregate stats (top countries, top credentials, connections over time).
- Persist history so the dashboard isn't empty right after a restart, and so you can pull "coolest attacks" for a portfolio write-up later.

### Non-functional
- Availability: best-effort. This is a portfolio demo, not production infra — a few minutes of downtime is acceptable, but it shouldn't silently die for days.
- Latency: event-to-dashboard under ~3 seconds is plenty.
- Scale: single honeypot, expect tens to low hundreds of connection attempts/day from internet background-noise scanning (this is realistic — you don't need to advertise the IP for bots to find it within hours).
- Cost: should run on the cheapest VPS tier (~$4-6/month) or a port-forwarded Raspberry Pi if you want $0 hosting cost (trade-off: home IP exposure, see Section 6).
- Security: the honeypot must be unable to reach anything else — your LAN, the backend, or the wider internet for outbound abuse — even if fully compromised beyond its intended emulation layer.

### Constraints
- Solo developer, portfolio timeline (~2-3 weekends for MVP).
- Existing skills to lean on: Linux administration/hardening, Python, React, WebSocket API design (from the ARES capstone), Docker.
- Must be safe to link from a public resume — no real credentials, no path from honeypot to anything sensitive.

## 2. High-Level Design

### Component diagram
```
                 ┌────────────────────────────────────────────┐
                 │              VPS (public IP)                │
                 │                                              │
  Attacker  ───► │  ┌───────────┐   tail    ┌───────────────┐  │
  (internet)     │  │  Cowrie    │──log────►│  Log Shipper   │  │
                 │  │  (Docker,  │  (JSON)  │  (Python)      │  │
                 │  │  isolated  │           │  - parse       │  │
                 │  │  network)  │           │  - GeoIP       │  │
                 │  └───────────┘           │  - dedupe/cache │  │
                 │                          └──────┬─────────┘  │
                 │                                 │ events      │
                 │                          ┌──────▼─────────┐  │
                 │                          │  Backend API    │  │
                 │                          │  (FastAPI)      │  │
                 │                          │  - WebSocket    │  │
                 │                          │    broadcast    │  │
                 │                          │  - REST history │  │
                 │                          │  - SQLite store │  │
                 │                          └──────┬─────────┘  │
                 │                                 │ WS + REST   │
                 │                          ┌──────▼─────────┐  │
                 │                          │  React Dashboard│  │
                 │                          │  (static build, │  │
                 │                          │   served here   │  │
                 │                          │   or on Vercel) │  │
                 │                          └────────┬────────┘  │
                 └───────────────────────────────────┼───────────┘
                                                      │ HTTPS
                                                Recruiter's browser
```

### Data flow
1. Attacker connects to Cowrie's exposed SSH/Telnet port (or scans it — most traffic is automated bots, and that's fine, it's still real).
2. Cowrie logs the session as structured JSON (`cowrie.json.<date>`) — connection metadata, auth attempts, TTY input if a shell is opened.
3. The log shipper tails the file (or reads Cowrie's internal event bus — see Section 3), parses each line into a normalized event, looks up GeoIP, and writes to SQLite + pushes to the backend.
4. The backend fans the event out over WebSocket to every connected dashboard client and appends it to the persistent store for REST history queries (e.g. "top countries this month").
5. The dashboard renders the pin, appends to the feed, updates aggregate counters — all client-side, no polling needed for live events (WebSocket push), REST only used for initial page load / historical range queries.

### API / contract sketch
**WebSocket** `wss://<host>/ws/events`
```json
{
  "id": "uuid",
  "ts": "2026-07-13T18:32:01Z",
  "src_ip": "203.0.113.42",
  "country": "RO",
  "city": "Bucharest",
  "lat": 44.43, "lon": 26.10,
  "protocol": "ssh",
  "event_type": "login_attempt | command_input | connection",
  "username": "root",
  "password": "123456",
  "command": null,
  "session_id": "cowrie-session-id"
}
```

**REST** `GET /api/stats?range=24h` → top countries, top creds, connection counts bucketed by hour
**REST** `GET /api/events?limit=100&before=<ts>` → paginated history for initial load / scrollback

### Storage
SQLite is enough here — single writer (the shipper/backend), read-mostly, low volume (hundreds of rows/day). No need for Postgres unless you want to reuse CalmVault patterns for resume-consistency; either is a reasonable, defensible choice, and note that trade-off explicitly if asked in an interview.

## 3. Deep Dive

### Data model
`events` table: id, ts, src_ip, country, city, lat, lon, asn, protocol, event_type, username, password, command, session_id.
`sessions` table (derived view or separate table): session_id, src_ip, first_seen, last_seen, event_count, commands (joined text) — this is what makes the "attacker session replay" feature possible later (nice interview talking point: "I reconstructed attacker sessions from raw log events").

### Getting events out of Cowrie: two options
- **Log tailing (simpler, recommended for MVP):** tail `cowrie.json.<date>`, parse each line as JSON, one event per line. Cowrie rotates this file daily — the shipper needs to detect rotation (watch for file recreation, not just EOF).
- **Cowrie's internal Twisted log/event system (advanced):** write a custom Cowrie output plugin that pushes events directly, skipping the file round-trip. More "correct" but more integration work — good Phase 2+ upgrade, not needed for MVP.
Start with log tailing. It's simpler, decoupled (shipper crash doesn't affect Cowrie), and still real-time enough (Cowrie flushes per-line).

### GeoIP caching
IP-API.com is free for non-commercial use, no key required, but has a rate limit (45 req/min). Cache lookups in a local dict/SQLite table keyed by IP — most bot traffic re-hits from the same ranges repeatedly, so cache hit rate will be high after the first day.

### Production deployment shape
Phase 4 runs three containers on a single-purpose VPS:
- **Cowrie:** public SSH/Telnet honeypot with published ports and Phase 3 container hardening.
- **Backend:** private FastAPI container with no published port; reads the Cowrie log volume and writes SQLite to a separate data volume.
- **Frontend:** Nginx container that serves the built React dashboard and reverse-proxies `/api`, `/healthz`, and `/ws` to the private backend.

The browser uses same-origin API/WebSocket paths in production, which avoids hardcoded localhost URLs and lets HTTPS automatically upgrade the live feed to WSS.

### Error handling / retry
- Shipper loses connection to backend → buffer events locally (append to a small file or in-memory queue), retry with backoff, replay on reconnect. Don't drop data on a blip.
- Backend restarts → dashboard WebSocket reconnects automatically (standard reconnect-with-backoff on the client), re-fetches recent history via REST to backfill the gap.
- GeoIP API down/rate-limited → log event anyway with `country: "unknown"`, backfill geolocation later via a retry queue. Never block the live pipeline on an enrichment step.

## 4. Scale and Reliability
This system is intentionally small-scale — the "load" is internet background scanning, not user traffic. Realistic estimate: 10-200 connection attempts/day, spiking if the IP gets listed by scanners like Shodan/Censys (which will happen within days of exposure). Single-instance deployment is correct here; horizontal scaling would be over-engineering for a portfolio piece and worth explicitly saying so if asked ("I chose not to over-build this — here's why").

Monitoring: a simple healthcheck endpoint (`/healthz`) + uptime pinger (UptimeRobot free tier or a cron job you control) so you know if the demo silently dies before a recruiter finds out for you.

## 5. Trade-off Analysis

| Decision | Choice | Trade-off |
|---|---|---|
| Honeypot interaction level | Cowrie (medium interaction) | Easier/safer than a real vulnerable VM; less "realistic" than high-interaction honeypots, but far lower risk — correct choice for a public portfolio demo |
| Hosting | Cheap VPS vs. home Pi + port-forward | VPS: small monthly cost, keeps your home network/IP out of it. Pi: free, but exposes your home ISP IP and requires router config — recommend VPS |
| Database | SQLite vs. Postgres | SQLite: zero-ops, fine at this scale. Postgres: consistent with CalmVault, marginally more "production" looking on a resume, more setup. Either defensible; SQLite recommended for speed of delivery |
| Event ingestion | Log tailing vs. custom Cowrie plugin | Tailing: simpler, decoupled, ships this weekend. Plugin: more elegant, more work — good v2 upgrade |
| GeoIP provider | IP-API.com | Free, no key, rate-limited — caching mitigates; fine for this traffic volume |

## 6. Threat Model (do not skip — this is also your interview story)
- **Assumption:** the honeypot container will eventually be compromised beyond its intended emulation (this is the point — attackers "win" the fake shell).
- **Containment — implemented now (Phase 3, local prototype):** the Cowrie container runs with a read-only root filesystem (a `tmpfs` covers the one directory — `/tmp` — it actually needs to write to, so nothing persists there across a restart), all Linux capabilities dropped (`cap_drop: ALL`), `no-new-privileges` set, and hard resource caps (256MB memory, 0.5 CPU, 128 PIDs) so it can't be repurposed as a cheap compute/DDoS node even if fully compromised. It also sits on its own dedicated Docker network, isolated from any other container on the host (there are none right now, but this is the right default). All of this is verified working: `docker inspect` confirms every flag applied, and a live attack still flows through the full pipeline correctly with these restrictions on.
- **Containment — deliberately deferred to Phase 4 (network egress):** we tried adding true network isolation (a Docker `internal: true` network with no route out at all) behind a small TCP relay to keep the published ports working, since Docker won't publish ports on an internal-only network. That worked for isolation but broke something more important: a plain TCP relay terminates and re-originates the connection, so Cowrie only ever saw the relay's own container IP as `src_ip` — which silently kills GeoIP enrichment and the map, the actual point of this project. We verified this empirically (before the relay: Cowrie could reach both the open internet and the backend's `/healthz` via `host.docker.internal`; with a naive relay: real attacker IPs were lost). Preserving the real source IP through a port-forward requires kernel-level DNAT (which is what Docker's native `ports:` publishing already uses, and what Cowrie's own bundled config assumes — see the `reported_port` comment in `cowrie.cfg.dist`, "useful if you use iptables to forward ports to Cowrie"), not an application-level proxy. The correct way to get egress-filtering without this trade-off is host-level `iptables` rules on the real Linux VPS in Phase 4 (DNAT preserves source IP; a separate OUTPUT/FORWARD rule can still block the container's own outbound traffic). Docker Desktop on Windows doesn't offer an equivalent that doesn't sacrifice source-IP capture, so this is explicitly a Phase 4 deployment step, not a gap in the local prototype's design.
- **Residual gap in the local prototype:** without network-level egress filtering, a fully-compromised Cowrie container can currently reach the open internet and (via Docker Desktop's `host.docker.internal`) the backend's `/healthz`. This is scoped and acceptable for a local, non-public prototype; it must be closed via the Phase 4 iptables approach above before any public exposure.
- **Blast radius if fully broken out (defense in depth, assume containment fails):** VPS is single-purpose, holds no other data, credentials are unique to it, can be destroyed and redeployed from the Docker Compose file in minutes.
- **What you tell a recruiter:** "I designed this assuming the honeypot itself gets compromised — the interesting engineering problem wasn't 'catch attackers,' it was 'make sure catching them can't hurt me.'" And if pushed on the egress-filtering gap: "I actually tried the network-isolated approach first, found it silently broke source-IP capture — the entire point of the map — and made a deliberate call to defer true egress-filtering to the real Linux deployment where it's a solved problem (iptables DNAT), rather than ship a fix that quietly broke the product." That's a stronger interview answer than pretending the trade-off doesn't exist.

## 7. What we'd revisit as this grows
- Phase 4 production artifact status: `infra/docker-compose.prod.yml` now runs Cowrie, a private backend, and an Nginx-served dashboard. `infra/iptables-honeypot-egress.sh` is the VPS-only egress control that preserves source IPs while blocking new outbound traffic from Cowrie.
- Move from log-tailing to a native Cowrie output plugin for lower latency and less brittle parsing.
- Add a second honeypot type (fake HTTP/IoT device, e.g. mimicking a router login page) to diversify attack data and story.
- Add session replay UI (scrub through an attacker's actual typed commands like a terminal recording).
- If traffic grows enough to matter, move SQLite to Postgres and add a proper message queue between shipper and backend — not needed at current scale.
