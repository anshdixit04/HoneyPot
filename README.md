# Live Honeypot Attack Map

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

**[isa-font-apparently-surprised.trycloudflare.com](https://isa-font-apparently-surprised.trycloudflare.com)**

Served over HTTPS via a Cloudflare Tunnel from the VPS. Note: this is a free
quick Tunnel, so the URL changes if the tunnel process ever restarts - for a
permanent link, point a real domain at a named Cloudflare Tunnel instead.

## Docs

- [`docs/01-build-steps.md`](docs/01-build-steps.md) - phased build plan
- [`docs/02-design-doc.md`](docs/02-design-doc.md) - architecture, data flow, and threat model
- [`docs/03-prototype-spec.md`](docs/03-prototype-spec.md) - original local prototype scope
- [`docs/04-vps-deployment.md`](docs/04-vps-deployment.md) - Phase 4 VPS deployment runbook

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

## Security Note

This project intentionally runs a real honeypot. Do not expose it publicly until
the Phase 4 VPS checklist is complete, including host firewall rules and the
Cowrie egress block in `infra/iptables-honeypot-egress.sh`.
