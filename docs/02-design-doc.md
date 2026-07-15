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

## 8. Phase 5: Visual Redesign — 3D Globe, Metrics Dashboard, Report Generator

Status: Draft v1, planned. This is the "recruiter polish" phase referenced in the README. Goal: replace the flat SVG map and CSS-bar stats with a visually stronger, animated frontend, without touching the backend contract (`/api/events`, `/api/stats`, `wss://<host>/ws/events` stay as-is — this is a frontend-only phase).

### 8.1 Current state (baseline)
- `frontend/src/components/WorldMap.jsx` — flat 2D map via `react-simple-maps` (`ComposableMap`/`Geography`/`Marker`), static pins, no zoom/pan, no animation beyond a CSS pin pop-in.
- `frontend/src/components/StatsPanel.jsx` — top countries / top credentials / connections-per-hour rendered as plain CSS div bars, one page, no charts library.
- `frontend/src/App.jsx` — single-page grid layout (`dashboard-grid`): map, stats, and event feed all on one screen.
- Visual language: dark theme (`#0b1220` background, `#111a2b` panels, `#60a5fa` blue accent, `#ff4d4f`/`#4ade80`/`#f87171` status colors), monospace for data, no motion design beyond the pin keyframe.
- No PDF/export capability of any kind exists yet.

### 8.2 New capability 1 — 3D attack globe
**Library:** `react-globe.gl` (Three.js under the hood, React-idiomatic API, actively maintained, fits the existing React 18 + Vite stack with a single new dependency — no build tooling changes needed).

- Replace `WorldMap.jsx` with a `Globe3D.jsx` component rendering a rotating dark-textured Earth (night-lights or dark vector texture to match the existing `#0b1220`/`#111a2b` palette).
- Each incoming event becomes an animated arc or ping from the attacker's `lat`/`lon` to the honeypot's fixed VPS location — reuses the exact same event shape already on the wire (`lat`, `lon`, `country`, `event_type`), no backend changes.
- Idle state: slow auto-rotation. On new event: camera does a short (400-600ms) ease-in-out zoom/tilt toward the new arc's origin, then eases back to the global view — this is the "zoom in and zoom out" behavior, driven by `react-globe.gl`'s built-in `pointOfView()` camera control on a `requestAnimationFrame`-friendly transition, not a custom Three.js camera rig (keeps this a days-not-weeks addition).
- Manual zoom/pan/rotate stays enabled via the library's built-in OrbitControls passthrough so a recruiter can explore the globe themselves.
- Color-code arcs/points by `event_type` (login_attempt / command_input / connection) using the existing status palette, so the globe carries the same meaning as today's pin colors.
- Performance guard: cap simultaneous animated arcs (e.g. keep last ~50 live, same pattern as the existing 200-event cap in `App.jsx`) so a burst of bot traffic doesn't tank frame rate.

**Implementation status:** `frontend/src/components/Globe3D.jsx` exists and does the above (earth-night texture + bump map, arcs/rings/points off the live event stream, zoom-on-event via `pointOfView()`). The `HONEYPOT` point (green dot) is the fixed VPS location arcs converge on — this is already correct behavior, not a bug. The subsections below are a refinement pass on top of that baseline, not a rewrite.

#### 8.2.1 Refinement — faster rotation, more realistic globe, cooler arcs
- **Rotation speed:** current idle `controls.autoRotateSpeed = 0.35` is too slow (roughly a 3-minute orbit). Target a full rotation every 4-5 seconds. `OrbitControls.autoRotateSpeed` follows `orbit_seconds ≈ 30 * (2.0 / speed)`, so `speed ≈ 60 / orbit_seconds` — set `autoRotateSpeed` to roughly **12-15** (13 ≈ 4.6s/rotation). Keep the existing `prefers-reduced-motion` check that disables `autoRotate` entirely — a fast-spinning globe is exactly the kind of motion that setting exists to suppress.
- **More realistic globe:** keep the existing `earth-night.jpg` + `earth-topology.png` bump map (a real night-lights texture already reads as "a real globe," and matches the dark theme better than a daytime blue-marble look). Add a starfield background (`backgroundImageUrl`, e.g. `three-globe`'s bundled `night-sky.png`) so the globe sits in a black starfield rather than the flat transparent panel background — this is the single highest-impact realism change for the least effort. A rotating semi-transparent cloud layer is a reasonable stretch goal (Three.js: a second sphere slightly larger than the globe, rotating at its own independent speed via `globeRef.current.scene()`), but only take it on if a reliable cloud texture asset is confirmed reachable first — don't ship a broken/missing-texture globe chasing this detail.
- **Cooler arcs:** the arc lines already exist (`arcsData`) but should read as more of a "signal" than a thin line. Use a two-stop gradient color per arc (`arcColor` as `[originColor, honeypotColor]` rather than a flat color) so each line visibly travels from the attacker's color toward the honeypot's green. Shorten `arcDashAnimateTime` slightly (from 1400ms toward ~900-1100ms) and increase `arcStroke` a touch for a more visible "beam" without turning it into a thick blob. **Do not fabricate ambient/demo arcs when there's no live traffic** — this dashboard's entire value proposition is that the data is real attacker activity, not a simulation; an idle globe with occasional real arcs is honest and still reads as "live," a globe that's always busy with fake traffic undermines the project's credibility if a recruiter asks about it.

#### 8.2.2 New sub-feature — IP location lookup
A "Look up IP" affordance on the globe panel, separate from the passive live-event zoom already described above.

- **UI:** a button (styled like the existing `.about-button`) opens a small popover/panel with two ways to pick a location:
  1. **Recent locations dropdown** — populated straight from `events` already in memory (dedupe by `src_ip`, label each option `"<ip> — <city>, <country>"`). Zero new dependencies or network calls; always populated once any traffic has been seen.
  2. **Free-text IP field** — user types an arbitrary IP address; on submit, do a client-side GeoIP lookup against a free, HTTPS, CORS-enabled provider (e.g. `ipapi.co/<ip>/json/` or `ipwho.is/<ip>` — confirm current CORS/HTTPS/rate-limit behavior before wiring this up, since providers change terms). This is a separate, ad-hoc lookup path — it does not touch the honeypot's own server-side GeoIP pipeline (Section 3) or the `/api/events` contract.
- **Zoom behavior:** on selecting a location (from either path), reuse the existing per-event zoom pattern in `Globe3D.jsx` (`controls.autoRotate = false` → `globe.pointOfView({ lat, lng, altitude: ~0.5-0.8 }, ~600ms)`), drop a temporary marker at that point, and show a small label with city/region/country and rounded lat/lon — explicitly **not** street-level detail, matching what a free GeoIP lookup can honestly provide. Add a visible "Return to live view" control that clears the marker, resumes `autoRotate`, and eases the camera back to `IDLE_VIEW`, mirroring the existing `RETURN_DELAY_MS` auto-return behavior used for live events (except lookups should wait for the user to dismiss rather than auto-returning on a timer, since the user asked to look at that spot on purpose).

### 8.3 New capability 2 — separate 3D metrics dashboard
A second route/view (`/metrics`), not a panel bolted onto the main screen — the existing single-page grid stays as the "live" view; this is a distinct dashboard for aggregate stats.

- Add client-side routing (`react-router-dom`, the one other new dependency needed) with two views: `/` (today's live map + feed) and `/metrics` (new).
- Metrics view consumes the same `GET /api/stats?range=` REST endpoint already defined in Section 2, just requesting more ranges (24h / 7d / 30d) via a range selector.
- Visuals: replace the flat CSS bars in `StatsPanel.jsx` with real charts — recommend `recharts` or `visx` for the 2D charts (connections-over-time line/area, top-countries bar) plus one or two 3D-styled centerpieces for visual impact:
  - A 3D-tilted bar/column chart (CSS 3D transforms or a lightweight Three.js scene) for top countries or top credentials — the "3D outputs on metrics" ask — rather than every chart being literally 3D, which usually hurts readability. Keep this to 1-2 hero visuals, not the whole dashboard, so the numbers stay legible.
  - Consider a small rotating "globe heatmap" (reuse `react-globe.gl` in a static/summary mode, no live ticking) showing cumulative attack density by country as a second callback to the main globe's visual language.
- Each metrics tile animates in on mount/data-refresh (fade + slide, ~200-300ms, respecting `prefers-reduced-motion`).

### 8.4 New capability 3 — report generator
On-demand PDF summary report, generated client-side or backend-side from existing data — no new external/paid data source required; "some other source" in the original ask is satisfied by the existing `/api/stats` and `/api/events` endpoints, just parameterized by a date range.

- New UI: a "Generate Report" button on the `/metrics` view with a date-range picker (reuses the same range param as the stats endpoint).
- **Recommended approach:** new backend endpoint `GET /api/report?range=7d&format=pdf` that queries the existing SQLite store, renders a templated PDF (e.g. via `weasyprint` or `reportlab` server-side, since the backend already owns the data and this avoids shipping a heavy PDF-rendering library to the browser) containing: summary stats, top countries/credentials, a static rendered chart image, and a few "notable session" callouts (ties into the session-replay idea in Section 7).
- **Alternative (no backend change):** generate the PDF client-side from data already in memory using `jspdf` + `html2canvas` to snapshot the metrics view — faster to ship, less polished, no new backend route. Recommended as a fallback if backend time is tight, not as the primary path.
- Output is a downloadable file (`honeypot-report-<range>-<date>.pdf`), suitable for attaching to a portfolio/resume email.

### 8.5 New dependencies summary
| Package | Purpose | Added to |
|---|---|---|
| `react-globe.gl` | 3D globe + arcs/points + camera zoom | frontend |
| `react-router-dom` | `/` vs `/metrics` routing | frontend |
| `recharts` (or `visx`) | 2D charts on metrics view | frontend |
| `three` | peer dep of `react-globe.gl`; also backs any custom 3D chart | frontend |
| `weasyprint` or `reportlab` | server-rendered PDF report | backend |
| `jspdf` + `html2canvas` (fallback only) | client-rendered PDF report | frontend |

### 8.6 Visual design system (make it "look attractive")
Keep the existing dark theme as the base — it already reads as a credible security-tool aesthetic — but tighten it into an explicit system rather than ad-hoc CSS:
- **Palette:** background `#0b1220`, panel `#111a2b`, border `#1f2c42`, text `#d7e0ee`, muted text `#93a4bf`; accent blue `#60a5fa` for primary data, amber `#fbbf24` for login attempts, red `#f87171`/`#ff4d4f` for command input/critical, green `#4ade80` for healthy/connected status. Reuse these exact tokens across the new globe/charts instead of introducing a second palette.
- **Typography:** keep system sans for UI chrome, monospace for anything data-like (IPs, credentials, timestamps) — already established, extend it to the new metrics view.
- **Motion principles:** every state change animates (event arrival, route change, chart refresh), but nothing loops forever except the globe's idle rotation — recruiters should feel "alive," not "busy." Respect `prefers-reduced-motion` throughout.
- **Hierarchy:** the globe is the visual centerpiece of `/`; the hero 3D chart is the centerpiece of `/metrics`. Everything else (feed, bars, tables) is supporting detail, sized and positioned accordingly.

### 8.7 Suggested build order
1. `react-router-dom` + empty `/metrics` route (low risk, unlocks everything else).
2. Swap `WorldMap.jsx` → `Globe3D.jsx` with static globe, then live arcs, then zoom-on-event camera behavior.
3. Build out `/metrics` with `recharts` first (fast, functional), then layer in the 1-2 hero 3D visuals.
4. Add the report generator, starting with the client-side `jspdf` fallback if a quick demo is needed, upgrading to the backend PDF endpoint when time allows.
5. Pass over the whole app applying Section 8.6's design tokens/motion consistently, last — polish after function.

## 9. Session Replay

Status: Implemented. Turns the "notable sessions" data already used by the PDF report into an interactive, guided walkthrough — the visitor clicks (or presses Enter) to inject each of the attacker's real commands one at a time and see Cowrie's simulated-shell response, rather than passively watching a recording.

### 9.1 Why Cowrie's own ttylog, not our parsed events
Our own `command_input` events only capture completed commands, missing backspaces, tab-completion, and the shell's actual responses. Cowrie already records the full raw session per connection as a binary "ttylog" file (referenced by the `cowrie.log.closed` event's `ttylog` field). Replaying that directly is strictly richer than reconstructing a weaker version from our own event log, and required no changes to Cowrie itself.

### 9.2 Ttylog format
Each ttylog is a sequence of frames: a 24-byte little-endian header (`struct` format `<iLiiLL`: op, tty, length, direction, sec, usec) followed by `length` bytes of raw payload. `op` is `OP_WRITE` (3) for data frames or `OP_CLOSE` (2) to end the session; `direction` distinguishes `TYPE_INPUT` (1, raw keystrokes) from `TYPE_OUTPUT` (2, the shell's echoed/produced output). Only `OP_WRITE` frames matching the *first* direction seen in the session are kept — in practice always the output stream, since a real PTY echoes typed characters back as part of its own output, so a viewer never needs the separate input stream to see what was typed. Format confirmed against Cowrie's own `src/cowrie/scripts/asciinema.py`, not reverse-engineered. Confirmed against real captured production data: Cowrie logs character-by-character (one frame per keystroke), not line-buffered — significant for how playback is chunked (see 9.3).

### 9.3 Pipeline
- **Infra**: `var/lib/cowrie/tty` (previously unmounted — Cowrie was writing there via an implicit, ephemeral, container-anonymous location) is now an explicit volume, shared with the backend (read-write, so the retention loop in 9.5 can delete from its side).
- **Capture**: `parser.parse_log_closed()` extracts `{session_id, ttylog_filename}` from `cowrie.log.closed` lines, handled as session metadata (`sessions.record_ttylog()`) — separate from the normal event pipeline, since it's not an attack event for the live feed/map.
- **Command-level chunking**: character-by-character frames are grouped into one step per command by `replay.build_command_steps()`, using Cowrie's IRM (insert-mode) ANSI markers (`\x1b[4h` right before a prompt, `\x1b[4l` right after the typed line is echoed) as step boundaries. This is a structural marker, not dependent on knowing the fake hostname/prompt string, so it holds regardless of session content. Each step comes out as `{prompt, command, output}`. (`replay.build_asciicast()` — full timed asciicast v2 output — is kept for API completeness but unused by the current UI.)
- **API**: `GET /api/sessions?range=&limit=` lists recent sessions (src IP, location, event/command counts, `has_replay`); `GET /api/sessions/{id}/replay/steps` returns `{banner, steps: [{prompt, command, output}, ...]}` for a given session.
- **UI**: a custom terminal-styled component (`ReplayModal.jsx`) reveals `banner` immediately, then one step at a time on click or Enter (native browser button-focus behavior, not a global keydown listener — see the callout below). No third-party terminal-player library; a plain `<pre>` is enough since there's no need to render real-time timing or ANSI color, and it avoids depending on a library's internal click-handling working reliably across browsers.

**Design note — earlier passive-playback version:** the first implementation used `asciinema-player` with the full timed asciicast and `autoPlay: true` (after its click-to-start overlay proved unreliable — reproducible even with accurate, trusted synthetic clicks). That approach worked but was replaced with the guided injector described above per explicit direction: a visitor actively driving the session command-by-command is a better fit for a portfolio piece than a video-like passive recording.

**Bug caught during testing:** the first injector draft used a global `window` keydown listener for the "press Enter" hint. That's too broad — it fires on *any* Enter keypress anywhere on the page while the modal is open, which both a browser automation tool's accessibility-tree scan and, plausibly, a real user's unrelated interaction elsewhere could trigger unintentionally (observed firsthand: it double-advanced steps during testing). Fixed by auto-focusing the inject button instead and relying on the browser's native focused-button Enter/Space activation — standard behavor, not a custom global listener.

### 9.4 Honesty framing
The replay modal states explicitly that this is real attacker input against Cowrie's *simulated* shell, not a real compromised system — consistent with the project's broader stance of never fabricating or embellishing attack data.

### 9.5 Retention
Ttylogs are binary and would otherwise accumulate indefinitely (same class of problem as the JSON event log). `replay.prune_old_ttylogs()` deletes files whose mtime is older than `TTYLOG_RETENTION_DAYS` (default 14, configurable in `infra/.env.prod`); `store.clear_missing_ttylogs()` reconciles the DB afterward so a session whose recording was pruned correctly shows "no recording" instead of a dead link. Both run from a background loop (`retention_loop()` in `main.py`) once every 24h. Requires the backend's `cowrie_tty` volume mount to be read-write (not `:ro`), unlike the JSON log mount.

Known remaining gap: no equivalent retention exists yet for the JSON event log or the SQLite `events` table itself, both of which also grow unboundedly. Not addressed here — same fix shape (age-based pruning) would apply if it becomes a problem.
