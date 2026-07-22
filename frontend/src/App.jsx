import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import AboutPanel from "./components/AboutPanel.jsx";
import { WS_URL, fetchEvents, fetchStats } from "./api.js";
import "./App.css";

// Route-level code splitting: LivePage pulls in react-globe.gl/three,
// MetricsPage pulls in recharts - keep each out of the other's bundle.
const LivePage = lazy(() => import("./pages/LivePage.jsx"));
const MetricsPage = lazy(() => import("./pages/MetricsPage.jsx"));

const FLUSH_INTERVAL_MS = 400;

function withDisplayTime(event) {
  return { ...event, displayTime: new Date(event.ts).toLocaleTimeString() };
}

export default function App() {
  const [events, setEvents] = useState([]);
  const [stats, setStats] = useState(null);
  const [status, setStatus] = useState("connecting");
  const [showAbout, setShowAbout] = useState(false);
  const statsTimerRef = useRef(null);
  const eventQueueRef = useRef([]);

  // Debounce stats refreshes so a burst of live events (e.g. an attacker
  // running several commands in a row) doesn't hammer /api/stats.
  const refreshStats = useCallback(() => {
    if (statsTimerRef.current) return;
    statsTimerRef.current = setTimeout(() => {
      statsTimerRef.current = null;
      fetchStats().then(setStats).catch(() => {});
    }, 1500);
  }, []);

  useEffect(() => {
    fetchEvents(200).then((data) => setEvents(data.map(withDisplayTime))).catch(() => {});
    fetchStats().then(setStats).catch(() => {});
  }, []);

  // Drain queued WebSocket events into React state on a fixed cadence, so a
  // burst of incoming traffic causes one render instead of one per message.
  useEffect(() => {
    const timer = setInterval(() => {
      const queued = eventQueueRef.current.splice(0);
      if (!queued.length) return;
      setEvents((prev) => [...queued.reverse(), ...prev].slice(0, 200));
      refreshStats();
    }, FLUSH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refreshStats]);

  useEffect(() => {
    let ws;
    let reconnectTimer;
    let attempt = 0;
    let unmounted = false;

    const connect = () => {
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        attempt = 0;
        setStatus("connected");
        // We may have missed events while disconnected - backfill.
        fetchEvents(200).then((data) => setEvents(data.map(withDisplayTime))).catch(() => {});
        fetchStats().then(setStats).catch(() => {});
      };

      ws.onclose = () => {
        if (unmounted) return;
        setStatus("disconnected");
        const baseDelay = Math.min(1000 * 2 ** attempt, 10000);
        const delay = baseDelay + Math.random() * 500; // jitter so clients don't reconnect in lockstep
        attempt += 1;
        reconnectTimer = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        setStatus("error");
        ws.close();
      };

      ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data);
          eventQueueRef.current.push(withDisplayTime(event));
        } catch (err) {
          console.error("Invalid WebSocket event", err);
        }
      };
    };

    connect();

    return () => {
      unmounted = true;
      clearTimeout(reconnectTimer);
      ws.close();
    };
  }, [refreshStats]);

  return (
    <BrowserRouter>
      <div className="dashboard">
        <header>
          <div className="header-left">
            <h1>Live Honeypot Attack Map</h1>
            <nav className="main-nav">
              <NavLink to="/" end className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
                Live
              </NavLink>
              <NavLink to="/metrics" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
                Metrics
              </NavLink>
            </nav>
          </div>
          <div className="header-right">
            <button className="about-button" onClick={() => setShowAbout(true)}>
              About
            </button>
            <span className={`ws-status ${status}`}>
              WebSocket: {status === "disconnected" ? "reconnecting…" : status}
            </span>
          </div>
        </header>
        <Suspense fallback={<div className="route-loading">Loading…</div>}>
          <Routes>
            <Route path="/" element={<LivePage events={events} stats={stats} />} />
            <Route path="/metrics" element={<MetricsPage />} />
          </Routes>
        </Suspense>
        {showAbout && <AboutPanel onClose={() => setShowAbout(false)} />}
      </div>
    </BrowserRouter>
  );
}
