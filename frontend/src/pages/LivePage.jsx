import Globe3D from "../components/Globe3D.jsx";
import StatsPanel from "../components/StatsPanel.jsx";
import EventFeed from "../components/EventFeed.jsx";

export default function LivePage({ events, stats }) {
  return (
    <div className="dashboard-grid">
      <Globe3D events={events} />
      <StatsPanel stats={stats} />
      <EventFeed events={events} />
    </div>
  );
}
