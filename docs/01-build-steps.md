# Build Steps - Live Honeypot Attack Map

Simple phase-by-phase breakdown. Each phase ends with something runnable, so
you never go more than a weekend without a visible result.

## Phase 0 - Local Prototype

Goal: prove the pipeline end-to-end on your own laptop before anything touches
the internet.

1. Run Cowrie in Docker locally, bound only to localhost.
2. Point a small Python shipper at Cowrie's JSON log file, tail it, and parse events.
3. Push parsed events over a WebSocket to a bare-bones React page.
4. Manually SSH into your own local Cowrie instance and watch the event show up live.

Deliverable: attack the local honeypot from a second terminal and see it appear
on screen within a second. See `03-prototype-spec.md`.

## Phase 1 - Enrichment

1. Add GeoIP lookup to tag each event with country, city, latitude/longitude,
   and ASN where available.
2. Add a lightweight local cache so repeat IPs do not re-hit the GeoIP API.
3. Track credentials tried and commands typed per Cowrie session ID.

## Phase 2 - Dashboard v1

1. World map component with pins that animate in as events arrive.
2. Live scrolling feed panel: timestamp, source IP, country, protocol, command,
   or credential attempted.
3. Aggregate panels: top attacking countries, top credentials tried, and
   connection count over time.

## Phase 3 - Container Hardening

1. Put Cowrie on its own Docker network so no app container shares a network path with it.
2. Run Cowrie with a read-only root filesystem, writable `tmpfs` only where
   needed, dropped Linux capabilities, `no-new-privileges`, and resource caps.
3. Verify the local attack pipeline still works with those restrictions enabled.
4. Document the remaining egress-filtering gap and why it belongs on the real
   Linux VPS, not Docker Desktop on Windows.

## Phase 4 - Public Deployment

1. Rent a small single-purpose VPS from a reputable provider. Do not expose this
   from your home network or ISP.
2. Deploy the production Docker Compose stack: Cowrie, private FastAPI backend,
   and Nginx-served React dashboard.
3. Apply host-level iptables egress filtering in the Docker `DOCKER-USER` chain
   so Cowrie can answer inbound honeypot sessions but cannot start new outbound
   connections.
4. Smoke-test that real source IPs are preserved, backend port `8000` is private,
   and the dashboard receives live events.
5. Add HTTPS/domain routing and basic uptime monitoring.

Runbook: `docs/04-vps-deployment.md`.

## Phase 5 - Polish For Recruiters

1. Add a short About panel on the dashboard explaining what the project is.
2. Record a 30-60 second screen capture as a fallback if the live demo is down.
3. Write the GitHub README with architecture diagram, screenshots, and a clear
   explanation of what this demonstrates.
4. Add the live link and repo link to resume and LinkedIn.

## Effort Estimate

- Phase 0-2: about 2 weekends.
- Phase 3: about 2-4 hours.
- Phase 4: about 2-4 hours for VPS setup, firewall, egress rules, and DNS/HTTPS.
- Phase 5: about 2-3 hours.
