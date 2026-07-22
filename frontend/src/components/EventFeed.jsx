import { memo, useEffect, useRef, useState } from "react";

const MAX_ROWS = 50;

function EventFeed({ events }) {
  const [paused, setPaused] = useState(false);
  const [frozenEvents, setFrozenEvents] = useState(events);
  const wasPausedRef = useRef(false);

  useEffect(() => {
    if (paused) {
      if (!wasPausedRef.current) setFrozenEvents(events);
    }
    wasPausedRef.current = paused;
  }, [paused, events]);

  const rows = (paused ? frozenEvents : events).slice(0, MAX_ROWS);

  return (
    <div className="panel event-feed">
      <div className="event-feed-header">
        <h2>Live Feed</h2>
        <button className="about-button" onClick={() => setPaused((v) => !v)}>
          {paused ? "Resume" : "Pause"}
        </button>
      </div>
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Source IP</th>
            <th>Country</th>
            <th>Type</th>
            <th>Username</th>
            <th>Password</th>
            <th>Command</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.id}>
              <td>{e.displayTime ?? new Date(e.ts).toLocaleTimeString()}</td>
              <td>{e.src_ip}</td>
              <td>{e.country ?? "?"}</td>
              <td className={`event-type ${e.event_type}`}>{e.event_type}</td>
              <td>{e.username ?? ""}</td>
              <td>{e.password ?? ""}</td>
              <td>{e.command ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default memo(EventFeed);
