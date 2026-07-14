import { ComposableMap, Geographies, Geography, Marker } from "react-simple-maps";

const GEO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

export default function WorldMap({ events }) {
  const pins = events.filter((e) => e.lat != null && e.lon != null);

  return (
    <div className="panel world-map">
      <h2>Live Attack Map</h2>
      <ComposableMap projectionConfig={{ scale: 140 }} style={{ width: "100%", height: "auto" }}>
        <Geographies geography={GEO_URL}>
          {({ geographies }) =>
            geographies.map((geo) => (
              <Geography
                key={geo.rsmKey}
                geography={geo}
                fill="#1b2635"
                stroke="#2c3b52"
                strokeWidth={0.5}
              />
            ))
          }
        </Geographies>
        {pins.map((e) => (
          <Marker key={e.id} coordinates={[e.lon, e.lat]}>
            <circle r={4} className="attack-pin" fill="#ff4d4f" stroke="#fff" strokeWidth={0.5} />
          </Marker>
        ))}
      </ComposableMap>
    </div>
  );
}
