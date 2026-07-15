const BAR_COLOR = "#60a5fa";

export default function HeroCountryChart({ data }) {
  const top = data.slice(0, 8);
  const max = Math.max(1, ...top.map((d) => d.count));

  return (
    <div className="panel metrics-tile tile-wide fade-in hero-tile">
      <h2>Top Countries - 3D</h2>
      {top.length === 0 ? (
        <p className="empty">No data yet</p>
      ) : (
        <div className="hero-3d">
          <div className="hero-3d-stage">
            {top.map((d) => {
              const heightPx = Math.max(6, (d.count / max) * 140);
              return (
                <div
                  key={d.label}
                  className="hero-bar3d"
                  style={{ "--h": `${heightPx}px`, "--c": BAR_COLOR }}
                  title={`${d.label}: ${d.count}`}
                >
                  <span className="hero-bar3d-count">{d.count}</span>
                  <span className="hero-bar3d-label">{d.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
