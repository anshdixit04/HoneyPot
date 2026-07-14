import { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { fetchStats } from "../api.js";
import HeroCountryChart from "../components/HeroCountryChart.jsx";
import ReportButton from "../components/ReportButton.jsx";

const RANGES = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
];

const TOOLTIP_STYLE = {
  background: "#111a2b",
  border: "1px solid #1f2c42",
  borderRadius: 6,
  color: "#d7e0ee",
  fontSize: 12,
};

function formatHour(hour) {
  const d = new Date(hour);
  return Number.isNaN(d.getTime()) ? hour : d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit" });
}

export default function MetricsPage() {
  const [range, setRange] = useState("24h");
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchStats(range)
      .then((data) => {
        if (cancelled) return;
        setStats(data);
        setLoading(false);
        setRefreshKey((k) => k + 1);
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [range]);

  const { top_countries = [], top_credentials = [], connections_by_hour = [] } = stats || {};

  const connectionSeries = connections_by_hour.map((h) => ({ hour: formatHour(h.hour), count: h.count }));
  const countrySeries = top_countries.map((c) => ({ label: c.country, count: c.count }));
  const credentialSeries = top_credentials.map((c) => ({
    label: `${c.username || ""}:${c.password || ""}`,
    count: c.count,
  }));

  return (
    <div className="metrics-page">
      <div className="metrics-toolbar">
        <div className="range-selector">
          {RANGES.map((r) => (
            <button
              key={r.value}
              className={`range-button${range === r.value ? " active" : ""}`}
              onClick={() => setRange(r.value)}
            >
              {r.label}
            </button>
          ))}
        </div>
        <ReportButton range={range} />
      </div>

      {loading && !stats && <p className="empty">Loading…</p>}

      <div className="metrics-grid" key={refreshKey}>
        <div className="panel metrics-tile tile-wide fade-in">
          <h2>Connections Over Time</h2>
          {connectionSeries.length === 0 ? (
            <p className="empty">No data yet</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={connectionSeries}>
                <defs>
                  <linearGradient id="connGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.5} />
                    <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#1f2c42" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="hour" stroke="#93a4bf" tick={{ fontSize: 11 }} />
                <YAxis stroke="#93a4bf" tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Area type="monotone" dataKey="count" stroke="#60a5fa" fill="url(#connGradient)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="panel metrics-tile fade-in">
          <h2>Top Countries</h2>
          {countrySeries.length === 0 ? (
            <p className="empty">No data yet</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={countrySeries} layout="vertical" margin={{ left: 8 }}>
                <CartesianGrid stroke="#1f2c42" strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" stroke="#93a4bf" tick={{ fontSize: 11 }} allowDecimals={false} />
                <YAxis type="category" dataKey="label" stroke="#93a4bf" tick={{ fontSize: 11 }} width={40} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="count" fill="#60a5fa" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="panel metrics-tile fade-in">
          <h2>Top Credentials</h2>
          {credentialSeries.length === 0 ? (
            <p className="empty">No data yet</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={credentialSeries} layout="vertical" margin={{ left: 8 }}>
                <CartesianGrid stroke="#1f2c42" strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" stroke="#93a4bf" tick={{ fontSize: 11 }} allowDecimals={false} />
                <YAxis
                  type="category"
                  dataKey="label"
                  stroke="#93a4bf"
                  tick={{ fontSize: 10, fontFamily: "monospace" }}
                  width={110}
                />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="count" fill="#fbbf24" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <HeroCountryChart data={countrySeries} />
      </div>
    </div>
  );
}
