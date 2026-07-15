import { useEffect, useMemo, useRef, useState } from "react";
import Globe from "react-globe.gl";

// Approximate location of the honeypot VPS (NYC1 datacenter) - arcs
// converge here regardless of exact host, so this is intentionally coarse.
const HONEYPOT = { lat: 40.7128, lng: -74.006 };
const HONEYPOT_COLOR = "#4ade80";
const LOOKUP_COLOR = "#c084fc";

const GLOBE_HEIGHT = 380;
const IDLE_VIEW = { lat: 15, lng: 10, altitude: 2.2 };
const MAX_ARCS = 50;
const RETURN_DELAY_MS = 2200;
const AUTO_ROTATE_SPEED = 13; // ~4.6s per rotation

const GLOBE_IMAGE_URL = "https://unpkg.com/three-globe/example/img/earth-night.jpg";
const BUMP_IMAGE_URL = "https://unpkg.com/three-globe/example/img/earth-topology.png";
const BACKGROUND_IMAGE_URL = "https://unpkg.com/three-globe/example/img/night-sky.png";

const EVENT_COLOR = {
  connection: "#60a5fa",
  login_attempt: "#fbbf24",
  command_input: "#f87171",
};

function colorFor(eventType) {
  return EVENT_COLOR[eventType] || EVENT_COLOR.connection;
}

function roundCoord(n) {
  return Math.round(n * 100) / 100;
}

async function geoLookupIp(ip) {
  const res = await fetch(`https://ipwho.is/${encodeURIComponent(ip)}`);
  const data = await res.json();
  if (!data.success || data.latitude == null || data.longitude == null) {
    throw new Error(data.message || "Lookup failed for that IP");
  }
  return {
    lat: data.latitude,
    lng: data.longitude,
    city: data.city,
    region: data.region,
    country: data.country,
    ip: data.ip || ip,
  };
}

function formatLookupLabel(loc) {
  const place = [loc.city, loc.region, loc.country].filter(Boolean).join(", ");
  return `${loc.ip ? `${loc.ip} - ` : ""}${place || "Unknown location"} (${roundCoord(loc.lat)}, ${roundCoord(loc.lng)})`;
}

export default function Globe3D({ events }) {
  const containerRef = useRef(null);
  const globeRef = useRef(null);
  const lastEventIdRef = useRef(null);
  const returnTimerRef = useRef(null);
  const [width, setWidth] = useState(0);
  const [lookup, setLookup] = useState(null);
  const [showLookupPanel, setShowLookupPanel] = useState(false);
  const [ipInput, setIpInput] = useState("");
  const [lookupState, setLookupState] = useState("idle"); // idle | loading | error
  const [lookupError, setLookupError] = useState("");

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    setWidth(el.clientWidth);
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const pins = useMemo(
    () => events.filter((e) => e.lat != null && e.lon != null).slice(0, MAX_ARCS),
    [events]
  );

  const recentLocations = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const e of events) {
      if (e.lat == null || e.lon == null || !e.src_ip || seen.has(e.src_ip)) continue;
      seen.add(e.src_ip);
      out.push(e);
      if (out.length >= 20) break;
    }
    return out;
  }, [events]);

  const arcsData = useMemo(
    () =>
      pins.map((e) => {
        const c = colorFor(e.event_type);
        return {
          id: e.id,
          startLat: e.lat,
          startLng: e.lon,
          endLat: HONEYPOT.lat,
          endLng: HONEYPOT.lng,
          colors: [c, HONEYPOT_COLOR],
        };
      }),
    [pins]
  );

  const ringsData = useMemo(
    () => pins.slice(0, 12).map((e) => ({ lat: e.lat, lng: e.lon, color: colorFor(e.event_type) })),
    [pins]
  );

  const pointsData = useMemo(() => {
    const pts = [{ lat: HONEYPOT.lat, lng: HONEYPOT.lng, color: HONEYPOT_COLOR, id: "honeypot" }];
    if (lookup) pts.push({ lat: lookup.lat, lng: lookup.lng, color: LOOKUP_COLOR, id: "lookup" });
    return pts;
  }, [lookup]);

  const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const handleGlobeReady = () => {
    const globe = globeRef.current;
    if (!globe) return;
    globe.pointOfView(IDLE_VIEW, 0);
    const controls = globe.controls();
    controls.autoRotate = !reduceMotion();
    controls.autoRotateSpeed = AUTO_ROTATE_SPEED;
  };

  // On each new attack, briefly zoom the camera toward its origin, then
  // ease back out to the idle overview and resume auto-rotation. Skipped
  // while the user has an IP lookup open so the two don't fight.
  useEffect(() => {
    const latest = pins[0];
    if (!latest || latest.id === lastEventIdRef.current) return;
    lastEventIdRef.current = latest.id;
    if (lookup) return;

    const globe = globeRef.current;
    if (!globe) return;

    clearTimeout(returnTimerRef.current);
    const controls = globe.controls();
    const reduce = reduceMotion();
    const zoomMs = reduce ? 0 : 500;
    const returnMs = reduce ? 0 : 600;

    controls.autoRotate = false;
    globe.pointOfView({ lat: latest.lat, lng: latest.lon, altitude: 1.4 }, zoomMs);
    returnTimerRef.current = setTimeout(() => {
      globe.pointOfView(IDLE_VIEW, returnMs);
      controls.autoRotate = !reduce;
    }, RETURN_DELAY_MS);
  }, [pins, lookup]);

  useEffect(() => () => clearTimeout(returnTimerRef.current), []);

  const goToLocation = (loc) => {
    clearTimeout(returnTimerRef.current);
    const globe = globeRef.current;
    setLookup(loc);
    setShowLookupPanel(false);
    if (!globe) return;
    const controls = globe.controls();
    controls.autoRotate = false;
    globe.pointOfView({ lat: loc.lat, lng: loc.lng, altitude: 0.6 }, reduceMotion() ? 0 : 600);
  };

  const handleReturnToLive = () => {
    setLookup(null);
    const globe = globeRef.current;
    if (!globe) return;
    const controls = globe.controls();
    globe.pointOfView(IDLE_VIEW, reduceMotion() ? 0 : 600);
    controls.autoRotate = !reduceMotion();
  };

  const handleRecentSelect = (e) => {
    const srcIp = e.target.value;
    const event = recentLocations.find((ev) => ev.src_ip === srcIp);
    if (!event) return;
    goToLocation({
      lat: event.lat,
      lng: event.lon,
      city: event.city,
      country: event.country,
      ip: event.src_ip,
    });
  };

  const handleIpSubmit = async (e) => {
    e.preventDefault();
    const ip = ipInput.trim();
    if (!ip) return;
    setLookupState("loading");
    setLookupError("");
    try {
      const loc = await geoLookupIp(ip);
      goToLocation(loc);
      setLookupState("idle");
      setIpInput("");
    } catch (err) {
      setLookupState("error");
      setLookupError(err.message || "Lookup failed");
    }
  };

  return (
    <div className="panel world-map">
      <div className="world-map-header">
        <h2>Live Attack Map</h2>
        <div className="lookup-controls">
          <button className="about-button" onClick={() => setShowLookupPanel((v) => !v)}>
            Look up IP
          </button>
          {lookup && (
            <button className="about-button lookup-return" onClick={handleReturnToLive}>
              Return to live view
            </button>
          )}
        </div>
      </div>

      {showLookupPanel && (
        <div className="lookup-popover">
          <div className="lookup-section">
            <label htmlFor="recent-locations">Recent locations</label>
            <select id="recent-locations" defaultValue="" onChange={handleRecentSelect}>
              <option value="" disabled>
                {recentLocations.length ? "Select an IP…" : "No traffic seen yet"}
              </option>
              {recentLocations.map((e) => (
                <option key={e.src_ip} value={e.src_ip}>
                  {e.src_ip} - {[e.city, e.country].filter(Boolean).join(", ") || "unknown"}
                </option>
              ))}
            </select>
          </div>
          <form className="lookup-section" onSubmit={handleIpSubmit}>
            <label htmlFor="ip-input">Look up any IP</label>
            <div className="lookup-input-row">
              <input
                id="ip-input"
                type="text"
                placeholder="e.g. 8.8.8.8"
                value={ipInput}
                onChange={(e) => setIpInput(e.target.value)}
              />
              <button type="submit" className="about-button" disabled={lookupState === "loading"}>
                {lookupState === "loading" ? "…" : "Go"}
              </button>
            </div>
            {lookupState === "error" && <p className="lookup-error">{lookupError}</p>}
          </form>
        </div>
      )}

      <div className="globe-wrap" ref={containerRef}>
        {width > 0 && (
          <Globe
            ref={globeRef}
            width={width}
            height={GLOBE_HEIGHT}
            globeImageUrl={GLOBE_IMAGE_URL}
            bumpImageUrl={BUMP_IMAGE_URL}
            backgroundImageUrl={BACKGROUND_IMAGE_URL}
            backgroundColor="rgba(0,0,0,0)"
            showAtmosphere
            atmosphereColor="#60a5fa"
            atmosphereAltitude={0.2}
            onGlobeReady={handleGlobeReady}
            arcsData={arcsData}
            arcColor="colors"
            arcDashLength={0.4}
            arcDashGap={0.25}
            arcDashAnimateTime={1000}
            arcStroke={0.55}
            arcsTransitionDuration={0}
            pointsData={pointsData}
            pointColor="color"
            pointAltitude={0.01}
            pointRadius={0.45}
            pointLabel={(d) => (d.id === "lookup" ? "Lookup result" : "Honeypot")}
            ringsData={ringsData}
            ringColor="color"
            ringMaxRadius={4}
            ringPropagationSpeed={2.5}
            ringRepeatPeriod={2600}
          />
        )}
        {lookup && <div className="lookup-badge">{formatLookupLabel(lookup)}</div>}
      </div>
    </div>
  );
}
