# Live Honeypot Attack Map

![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-07405E?logo=sqlite&logoColor=white)
![Three.js](https://img.shields.io/badge/Three.js-black?logo=three.js&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![Cowrie](https://img.shields.io/badge/Cowrie-Honeypot-critical)

> A production-deployed SSH and Telnet honeypot that captures real attacker
> behaviour, enriches events with GeoIP information, stores them in SQLite,
> and streams them to an interactive React and Three.js dashboard.

A real SSH/Telnet honeypot using Cowrie, with live attacker traffic streamed to
a public dashboard: world map pins, connection attempts, credentials tried, and
commands typed by actual attackers rather than synthetic data.

Built as a portfolio project to demonstrate Linux hardening, real-time systems
design, WebSocket streaming, event pipelines, and SIEM-style log analysis.

## Status

Phases 0-4 are complete: local prototype, GeoIP/dashboard enrichment, container
hardening, and a live VPS deployment with an egress-filtered honeypot behind
HTTPS. Phase 5 (recruiter polish) is in progress.

## Live Demo

**[honeypot-map.xyz](https://honeypot-map.xyz)**

Served over HTTPS via a named Cloudflare Tunnel from the VPS, backed by a
permanent domain rather than a free quick-Tunnel URL that changes on restart.

## Docs

- [`docs/01-build-steps.md`](docs/01-build-steps.md) - phased build plan
- [`docs/02-design-doc.md`](docs/02-design-doc.md) - architecture, data flow, and threat model
- [`docs/03-prototype-spec.md`](docs/03-prototype-spec.md) - original local prototype scope
- [`docs/04-vps-deployment.md`](docs/04-vps-deployment.md) - Phase 4 VPS deployment runbook
- [`docs/05-visual-redesign-prompt.md`](docs/05-visual-redesign-prompt.md) - Phase 5 build prompt: 3D globe, metrics dashboard, report generator

## Architecture

```text
Attacker -> Cowrie (Docker, hardened) -> Cowrie JSON logs
         -> FastAPI backend (GeoIP, SQLite, WebSocket)
         -> React dashboard (map, feed, stats)
```

In production, the React dashboard is served by Nginx, which proxies `/api`,
`/healthz`, and `/ws` to the private backend container.

## Repo Layout

```text
honeypot/       Future Cowrie config and fake environment files
backend/        FastAPI app: log tailer, GeoIP, SQLite, REST, WebSocket
frontend/       React dashboard served by Vite locally and Nginx in production
infra/          Docker Compose files, env examples, and VPS firewall helpers
docs/           Build plan, design doc, prototype spec, deployment runbook
data/           Local runtime logs/database, ignored except for .gitkeep
```

## Running The Local Prototype

```bash
docker compose -f infra/docker-compose.yml up -d cowrie
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

Then from another terminal:

```bash
ssh -p 2222 root@localhost
```

Try fake credentials and watch the event appear on the dashboard.

## Phase 4 Deployment

Start with the runbook:

```bash
cp infra/.env.prod.example infra/.env.prod
docker compose --env-file infra/.env.prod -f infra/docker-compose.prod.yml up -d --build
sudo bash infra/iptables-honeypot-egress.sh
```

Do this only on a single-purpose VPS, never your home network.

## Performance & UX Decisions

The live dashboard batches incoming WebSocket events and flushes them to React
state on a fixed ~400ms cadence instead of re-rendering on every message, so a
burst of attacker activity causes one render instead of dozens. The 3D globe
throttles camera-follow to at most one focus every few seconds (only for
higher-value `login_attempt`/`command_input` events), caps arcs/rings, and
exposes a **Visual mode: Full/Performance** toggle that automatically defaults
to the lighter mode on narrow or low-core-count devices. These were deliberate
trade-offs between "looks alive" and "stays smooth," not overlooked defaults.

## Known Limitations

- **Single instance, no HA**: this is a portfolio demo, not production
  infrastructure - see [`docs/02-design-doc.md`](docs/02-design-doc.md) Section 4.
- **GeoIP accuracy**: enrichment relies on free-tier GeoIP providers
  (city-level at best, sometimes only country-level) and is subject to their
  rate limits.
- **Unbounded raw log growth**: the JSON event log and the SQLite `events`
  table don't yet have a retention/pruning policy (ttylog session recordings
  do - see [`docs/02-design-doc.md`](docs/02-design-doc.md) Section 9.5).
- **Local prototype egress gap**: without host-level `iptables` egress
  filtering (a Phase 4/VPS-only step), a fully-compromised Cowrie container in
  the local Docker Desktop prototype can still reach the open internet - see
  the [Security Note](#security-note) and the design doc's threat model.

## Privacy & GeoIP Disclaimer

Usernames, passwords, and commands shown on the dashboard are real values
submitted by attackers against Cowrie's simulated shell - not real credentials
to any actual system, and not personal data belonging to the attackers
(automated scanners generate the large majority of this traffic). Source IPs
are geolocated approximately (city/region level, sometimes only country) via
free third-party GeoIP APIs for both the live pipeline and the on-demand
"Look up IP" feature; this is not precise personal-location tracking. The
honeypot's own displayed server location is intentionally coarsened for the
same reason arcs converge on one fixed point regardless of exact host.

## Security Note

This project intentionally runs a real honeypot. Do not expose it publicly until
the Phase 4 VPS checklist is complete, including host firewall rules and the
Cowrie egress block in `infra/iptables-honeypot-egress.sh`.
