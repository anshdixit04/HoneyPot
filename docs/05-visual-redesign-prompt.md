# Build Prompt — Phase 5 Visual Redesign

Purpose: a self-contained prompt to hand to an AI coding tool (Claude Code, Cursor, etc.) to implement the Phase 5 redesign described in `docs/02-design-doc.md` Section 8. Paste the block below as-is; it carries enough repo context to work without the assistant re-deriving the project from scratch.

---

## Prompt

You're working in a live SSH/Telnet honeypot dashboard: React 18 + Vite frontend (`frontend/`), FastAPI + SQLite backend (`backend/`), real-time events over WebSocket. This is a portfolio project meant to impress recruiters visually as well as technically — treat this as a design-forward task, not just a functional one.

**Do not change the backend event/stats contract.** `GET /api/events`, `GET /api/stats?range=`, and `wss://<host>/ws/events` already stream normalized events shaped like:

```json
{
  "id": "uuid", "ts": "2026-07-13T18:32:01Z",
  "src_ip": "203.0.113.42", "country": "RO", "city": "Bucharest",
  "lat": 44.43, "lon": 26.10, "protocol": "ssh",
  "event_type": "login_attempt | command_input | connection",
  "username": "root", "password": "123456", "command": null,
  "session_id": "cowrie-session-id"
}
```

Build against this shape. Only add the one new backend route described in Task 4 if you take the server-rendered PDF path.

### Current frontend state
- `frontend/src/App.jsx` — single page, grid layout: map, stats panel, event feed.
- `frontend/src/components/WorldMap.jsx` — flat 2D map via `react-simple-maps`, plain circle pins, no zoom/animation beyond a CSS keyframe pop-in.
- `frontend/src/components/StatsPanel.jsx` — top countries / top credentials / connections-per-hour as plain CSS div bars.
- Design tokens already in use (`frontend/src/App.css`) — reuse these, don't invent a new palette:
  - Background `#0b1220`, panels `#111a2b`, borders `#1f2c42`
  - Text `#d7e0ee`, muted text `#93a4bf`
  - Accent blue `#60a5fa`, amber `#fbbf24` (login attempts), red `#f87171`/`#ff4d4f` (command input/critical), green `#4ade80` (connected/healthy)
  - Monospace for IPs/credentials/timestamps, system sans for UI chrome

### Task 1 — Replace the flat map with a 3D globe
Swap `WorldMap.jsx` for a new `Globe3D.jsx` using `react-globe.gl` (Three.js-based, React-idiomatic, single new dependency).

- Dark globe texture matching the existing palette (night-lights or dark vector style, not the default blue-marble look).
- Each event becomes an animated arc/ping from its `lat`/`lon` to the honeypot's fixed location. Color by `event_type` using the palette above.
- Idle state: slow continuous auto-rotation.
- On new event: smoothly zoom/tilt the camera toward that event's origin (~400-600ms ease), then ease back out to the global view. Use the library's built-in `pointOfView()` transition — don't hand-roll a Three.js camera rig.
- Keep manual orbit/zoom/pan enabled so the globe is explorable, not just a passive animation.
- Cap live arcs at ~50 concurrent (mirror the existing 200-event cap pattern in `App.jsx`) so a burst of bot traffic doesn't kill frame rate.

### Task 1b — Globe refinement pass (rotation speed, realism, arcs, IP lookup)
`Globe3D.jsx` already exists and implements the baseline above. This task is a polish/feature pass on top of it — read the existing file first, don't rewrite it from scratch.

1. **Rotation speed.** `controls.autoRotateSpeed` is currently `0.35` (a multi-minute orbit). Change it so a full rotation takes about 4-5 seconds. `OrbitControls` speed maps to time as `orbit_seconds ≈ 30 * (2.0 / speed)`, so use `speed ≈ 60 / orbit_seconds` — set `autoRotateSpeed` to roughly **12-15** (13 ≈ 4.6s/rotation). Leave the `prefers-reduced-motion` branch that disables `autoRotate` entirely untouched.
2. **Make it read as a "real" globe.** Keep the existing `earth-night.jpg` + `earth-topology.png` bump map — don't switch to a daytime texture, the night-lights look already fits the dark theme and looks realistic. Add a starfield `backgroundImageUrl` (three-globe ships one, e.g. `night-sky.png`) so the globe sits in space instead of a flat transparent panel. A slowly-rotating semi-transparent cloud layer (second Three.js sphere via `globeRef.current.scene()`, independent rotation speed) is a nice-to-have — only add it if you've confirmed a real, reachable cloud texture URL; skip it rather than shipping a broken/missing texture.
3. **Make the arcs look cool.** The attack lines (`arcsData`) already animate; upgrade them from a flat color to a two-stop gradient (`arcColor: [attackerColor, honeypotGreen]`) so each line visibly travels toward the honeypot. Tighten `arcDashAnimateTime` from 1400ms to roughly 900-1100ms and nudge `arcStroke` up slightly for a more visible beam. **Important: only render arcs for real events from the `events` prop — do not add fake/ambient/demo traffic to keep the globe visually busy.** This project's whole pitch is that the data is real; fabricated traffic undermines that if anyone asks how it works.
4. **Add an IP location lookup.** New button on the globe panel (style it like the existing `.about-button`), opening a small popover with:
   - A dropdown of recent locations built from `events` already in memory — dedupe by `src_ip`, label `"<ip> — <city>, <country>"`. This needs no new network calls or dependencies.
   - A free-text IP input that, on submit, does a client-side fetch to a free HTTPS/CORS-enabled GeoIP API (e.g. `https://ipapi.co/<ip>/json/` or `https://ipwho.is/<ip>`) — verify the provider's current CORS/HTTPS/rate-limit terms before wiring it in, since free GeoIP APIs change these often.
   - On selecting either, reuse the existing zoom pattern from the live-event effect: pause `autoRotate`, `globe.pointOfView({ lat, lng, altitude: 0.5-0.8 }, ~600ms)`, drop a temporary marker, and show a label with city/region/country + rounded lat/lon. **Never claim street-level precision** — that's not what free GeoIP data provides, and the user explicitly wants "whereabouts," not an exact address.
   - Add a clearly visible "Return to live view" button that clears the marker, resumes rotation, and eases back to `IDLE_VIEW` — unlike the automatic return-after-a-few-seconds behavior used for live events, a manual lookup should stay put until the user dismisses it.

### Task 2 — Add a separate metrics dashboard route
Add `react-router-dom`. Two routes:
- `/` — today's live view (globe + event feed), largely as-is structurally.
- `/metrics` — new dedicated dashboard, not a panel bolted onto `/`.

`/metrics` pulls from the existing `/api/stats?range=` endpoint with a range selector (24h / 7d / 30d). Replace the CSS-bar charts with real ones:
- Use `recharts` (or `visx`) for the bulk of the charts — connections-over-time as a line/area chart, top-countries/top-credentials as bar charts. Prioritize legibility here.
- Add exactly one or two "hero" 3D visuals for visual impact — e.g. a tilted 3D column chart (CSS 3D transforms or a small Three.js scene) for top countries, and/or a static rotating globe-heatmap (reuse `react-globe.gl` in non-live mode) showing cumulative attack density. Do not make every chart 3D — it hurts readability past one or two centerpieces.
- Animate tiles in on mount/refresh (fade + slide, ~200-300ms). Respect `prefers-reduced-motion` — check it and fall back to instant state changes.

### Task 3 — Navigation
Add a small header nav between `/` and `/metrics` consistent with the existing header bar in `App.jsx` (same font, same button style as the existing "About" button).

### Task 4 — Report generator
Add a "Generate Report" button on `/metrics` with a date-range input, producing a downloadable PDF: `honeypot-report-<range>-<date>.pdf`.

Two acceptable implementations, pick based on time budget:
- **Preferred:** new backend route `GET /api/report?range=7d&format=pdf` in `backend/`, querying the existing SQLite store and rendering a templated PDF server-side (`weasyprint` or `reportlab`) with summary stats, top countries/credentials, a rendered chart image, and a couple of notable-session callouts.
- **Fallback (frontend-only, faster):** client-side PDF via `jspdf` + `html2canvas`, snapshotting the `/metrics` view directly. No backend changes. Use this if you need something working today; note it as a known simplification.

### Task 5 — Design polish pass (do this last)
Once the above works functionally, do a pass applying the design tokens and motion rules consistently everywhere — globe, charts, feed, nav. Nothing should loop forever except the globe's idle rotation. Every state change (new event, route change, data refresh) should animate, but should read as "alive," not "busy" or distracting.

### Suggested build order
1. Router + empty `/metrics` route.
2. Globe3D: static globe → live arcs → zoom-on-event camera behavior.
3. `/metrics` with `recharts` first, then the 1-2 hero 3D visuals.
4. Report generator (fallback first if time-constrained, upgrade to backend PDF after).
5. Final design/motion consistency pass.

### New dependencies
Frontend: `react-globe.gl`, `three` (peer dep), `react-router-dom`, `recharts`, and `jspdf` + `html2canvas` only if using the report fallback.
Backend: `weasyprint` or `reportlab` only if using the server-rendered report path.

---

Reference: full architecture, data flow, and trade-off rationale for Phase 5 live in `docs/02-design-doc.md`, Section 8.
