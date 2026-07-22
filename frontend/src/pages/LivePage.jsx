import Globe3D from "../components/Globe3D.jsx";
import StatsPanel from "../components/StatsPanel.jsx";
import EventFeed from "../components/EventFeed.jsx";

export default function LivePage({ events, stats }) {
  const recentEvents = events.slice(0, 50);
  return (
    <div className="dashboard-grid">
      <Globe3D events={recentEvents} />
      <StatsPanel stats={stats} />
      <EventFeed events={recentEvents} />
    </div>
  );
}
