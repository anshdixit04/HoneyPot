import { useEffect, useState } from "react";
import { API_BASE } from "../api.js";
import ReplayModal from "./ReplayModal.jsx";

export default function SessionsPanel({ range }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [replaySessionId, setReplaySessionId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`${API_BASE}/api/sessions?range=${range}&limit=8`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        setSessions(data.sessions || []);
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [range]);

  return (
    <div className="panel metrics-tile tile-wide fade-in">
      <h2>Notable Sessions</h2>
      {loading && <p className="empty">Loading…</p>}
      {!loading && sessions.length === 0 && <p className="empty">No sessions yet</p>}
      {sessions.length > 0 && (
        <table className="sessions-table">
          <thead>
            <tr>
              <th>Source IP</th>
              <th>Location</th>
              <th>Events</th>
              <th>Commands</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.session_id}>
                <td>{s.src_ip}</td>
                <td>{[s.city, s.country].filter(Boolean).join(", ") || "—"}</td>
                <td>{s.event_count}</td>
                <td className="sessions-commands">{s.commands.slice(0, 3).join(", ") || "—"}</td>
                <td>
                  {s.has_replay ? (
                    <button className="about-button" onClick={() => setReplaySessionId(s.session_id)}>
                      Replay
                    </button>
                  ) : (
                    <span className="empty">no recording</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {replaySessionId && (
        <ReplayModal sessionId={replaySessionId} onClose={() => setReplaySessionId(null)} />
      )}
    </div>
  );
}
