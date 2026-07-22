import { memo } from "react";

function Bar({ label, count, max }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="bar-count">{count}</span>
    </div>
  );
}

function StatsPanel({ stats }) {
  const { top_countries = [], top_credentials = [], connections_by_hour = [] } = stats || {};
  const maxCountry = Math.max(1, ...top_countries.map((c) => c.count));
  const maxCred = Math.max(1, ...top_credentials.map((c) => c.count));
  const maxHour = Math.max(1, ...connections_by_hour.map((h) => h.count));

  return (
    <div className="panel stats-panel">
      <h2>Stats (24h)</h2>

      <h3>Top Countries</h3>
      {top_countries.length === 0 && <p className="empty">No data yet</p>}
      {top_countries.map((c) => (
        <Bar key={c.country} label={c.country} count={c.count} max={maxCountry} />
      ))}

      <h3>Top Credentials</h3>
      {top_credentials.length === 0 && <p className="empty">No data yet</p>}
      {top_credentials.map((c) => (
        <Bar
          key={`${c.username}:${c.password}`}
          label={`${c.username || ""}:${c.password || ""}`}
          count={c.count}
          max={maxCred}
        />
      ))}

      <h3>Connections / hour</h3>
      {connections_by_hour.length === 0 && <p className="empty">No data yet</p>}
      <div className="hour-chart">
        {connections_by_hour.map((h) => (
          <div
            key={h.hour}
            className="hour-bar"
            style={{ height: `${Math.max(4, (h.count / maxHour) * 60)}px` }}
            title={`${h.hour}: ${h.count}`}
          />
        ))}
      </div>
    </div>
  );
}

export default memo(StatsPanel);
