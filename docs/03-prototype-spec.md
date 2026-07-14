# Prototype Spec — Weekend 0 (local, no public exposure)

Purpose: the smallest possible slice that proves the whole idea works, that we can build and run together in this session, entirely on localhost. No VPS, no public IP, no real risk — this is Phase 0 from `01-build-steps.md`.

## Scope (in)
1. Cowrie running in Docker, bound to `127.0.0.1` only.
2. A Python script that tails Cowrie's JSON log, parses `cowrie.login.failed`, `cowrie.login.success`, `cowrie.command.input`, and `cowrie.session.connect` events.
3. A minimal FastAPI backend with one WebSocket endpoint (`/ws/events`) that broadcasts parsed events to any connected client.
4. A single-page React (or even plain HTML+JS) client that connects to the WebSocket and prints incoming events to a live-updating list — no map, no styling polish yet.
5. Manual test: open a second terminal, `ssh -p 2222 root@localhost` into the local Cowrie instance, try a fake password, run a command like `ls` or `whoami` in the fake shell — watch it appear on the page within ~1 second.

## Scope (out, deliberately deferred)
- GeoIP enrichment (Phase 1)
- World map visualization (Phase 2)
- Persistent storage / history (Phase 2)
- Isolation hardening beyond "bound to localhost" (Phase 3 — required before any public exposure, not needed for a local-only prototype)
- Public deployment (Phase 4)

## Definition of done for this session
- `docker compose up` starts Cowrie locally.
- Running the shipper script shows parsed JSON events printed to the terminal as you type them into a fake SSH session.
- The React/HTML page shows the same events appear live, in order, without a page refresh.
- You've personally "attacked" your own honeypot at least once and watched it show up on screen — this is the moment that proves the concept before any time is spent on deployment or polish.

## Why this scope
Everything riskier (public exposure, isolation hardening, GeoIP rate limits) is deferred until after the core pipeline is proven. This matches how you'd actually want to explain the project in an interview: "I proved the pipeline locally first, then layered on hardening before ever exposing it publicly" — that ordering is itself good engineering practice to point to.
