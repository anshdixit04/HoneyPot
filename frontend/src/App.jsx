import { useCallback, useEffect, useRef, useState } from "react";
import WorldMap from "./components/WorldMap.jsx";
import EventFeed from "./components/EventFeed.jsx";
import StatsPanel from "./components/StatsPanel.jsx";
import AboutPanel from "./components/AboutPanel.jsx";
import { WS_URL, fetchEvents, fetchStats } from "./api.js";
import "./App.css";

export default function App() {
  const [events, setEvents] = useState([]);
  const [stats, setStats] = useState(null);
  const [status, setStatus] = useState("connecting");
  const [showAbout, setShowAbout] = useState(false);
  const statsTimerRef = useRef(null);

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
    fetchEvents(200).then(setEvents).catch(() => {});
    fetchStats().then(setStats).catch(() => {});
  }, []);

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
        // We may have missed events while disconnected — backfill.
        fetchEvents(200).then(setEvents).catch(() => {});
        fetchStats().then(setStats).catch(() => {});
      };

      ws.onclose = () => {
        if (unmounted) return;
        setStatus("disconnected");
        const delay = Math.min(1000 * 2 ** attempt, 10000);
        attempt += 1;
        reconnectTimer = setTimeout(connect, delay);
      };

      ws.onerror = () => setStatus("error");

      ws.onmessage = (msg) => {
        const event = JSON.parse(msg.data);
        setEvents((prev) => [event, ...prev].slice(0, 200));
        refreshStats();
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
    <div className="dashboard">
      <header>
        <h1>Live Honeypot Attack Map</h1>
        <div className="header-right">
          <button className="about-button" onClick={() => setShowAbout(true)}>
            About
          </button>
          <span className={`ws-status ${status}`}>WebSocket: {status}</span>
        </div>
      </header>
      <div className="dashboard-grid">
        <WorldMap events={events} />
        <StatsPanel stats={stats} />
        <EventFeed events={events} />
      </div>
      {showAbout && <AboutPanel onClose={() => setShowAbout(false)} />}
    </div>
  );
}
