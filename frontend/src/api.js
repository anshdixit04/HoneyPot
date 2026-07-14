const configuredApiBase = import.meta.env.VITE_API_BASE ?? "";
const configuredWsUrl = import.meta.env.VITE_WS_URL;

export const API_BASE = configuredApiBase;
export const WS_URL =
  configuredWsUrl ??
  `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/events`;

export async function fetchEvents(limit = 200) {
  const res = await fetch(`${API_BASE}/api/events?limit=${limit}`);
  if (!res.ok) throw new Error(`GET /api/events failed: ${res.status}`);
  return (await res.json()).events;
}

export async function fetchStats(range = "24h") {
  const res = await fetch(`${API_BASE}/api/stats?range=${range}`);
  if (!res.ok) throw new Error(`GET /api/stats failed: ${res.status}`);
  return res.json();
}
