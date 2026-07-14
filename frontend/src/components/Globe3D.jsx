import { useEffect, useMemo, useRef, useState } from "react";
import Globe from "react-globe.gl";

// Approximate location of the honeypot VPS (NYC1 datacenter) — arcs
// converge here regardless of exact host, so this is intentionally coarse.
const HONEYPOT = { lat: 40.7128, lng: -74.006 };

const GLOBE_HEIGHT = 380;
const IDLE_VIEW = { lat: 15, lng: 10, altitude: 2.2 };
const MAX_ARCS = 50;
const RETURN_DELAY_MS = 2200;

const GLOBE_IMAGE_URL = "https://unpkg.com/three-globe/example/img/earth-night.jpg";
const BUMP_IMAGE_URL = "https://unpkg.com/three-globe/example/img/earth-topology.png";

const EVENT_COLOR = {
  connection: "#60a5fa",
  login_attempt: "#fbbf24",
  command_input: "#f87171",
};

function colorFor(eventType) {
  return EVENT_COLOR[eventType] || EVENT_COLOR.connection;
}

export default function Globe3D({ events }) {
  const containerRef = useRef(null);
  const globeRef = useRef(null);
  const lastEventIdRef = useRef(null);
  const returnTimerRef = useRef(null);
  const [width, setWidth] = useState(0);

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

  const arcsData = useMemo(
    () =>
      pins.map((e) => ({
        id: e.id,
        startLat: e.lat,
        startLng: e.lon,
        endLat: HONEYPOT.lat,
        endLng: HONEYPOT.lng,
        color: colorFor(e.event_type),
      })),
    [pins]
  );

  const ringsData = useMemo(
    () => pins.slice(0, 12).map((e) => ({ lat: e.lat, lng: e.lon, color: colorFor(e.event_type) })),
    [pins]
  );

  const pointsData = useMemo(() => [{ lat: HONEYPOT.lat, lng: HONEYPOT.lng, color: "#4ade80" }], []);

  const handleGlobeReady = () => {
    const globe = globeRef.current;
    if (!globe) return;
    globe.pointOfView(IDLE_VIEW, 0);
    const controls = globe.controls();
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.35;
  };

  // On each new attack, briefly zoom the camera toward its origin, then
  // ease back out to the idle overview and resume auto-rotation.
  useEffect(() => {
    const latest = pins[0];
    if (!latest || latest.id === lastEventIdRef.current) return;
    lastEventIdRef.current = latest.id;

    const globe = globeRef.current;
    if (!globe) return;

    clearTimeout(returnTimerRef.current);
    const controls = globe.controls();
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const zoomMs = reduceMotion ? 0 : 500;
    const returnMs = reduceMotion ? 0 : 600;

    controls.autoRotate = false;
    globe.pointOfView({ lat: latest.lat, lng: latest.lon, altitude: 1.4 }, zoomMs);
    returnTimerRef.current = setTimeout(() => {
      globe.pointOfView(IDLE_VIEW, returnMs);
      controls.autoRotate = true;
    }, RETURN_DELAY_MS);
  }, [pins]);

  useEffect(() => () => clearTimeout(returnTimerRef.current), []);

  return (
    <div className="panel world-map">
      <h2>Live Attack Map</h2>
      <div className="globe-wrap" ref={containerRef}>
        {width > 0 && (
          <Globe
            ref={globeRef}
            width={width}
            height={GLOBE_HEIGHT}
            globeImageUrl={GLOBE_IMAGE_URL}
            bumpImageUrl={BUMP_IMAGE_URL}
            backgroundColor="rgba(0,0,0,0)"
            showAtmosphere
            atmosphereColor="#60a5fa"
            atmosphereAltitude={0.2}
            onGlobeReady={handleGlobeReady}
            arcsData={arcsData}
            arcColor="color"
            arcDashLength={0.4}
            arcDashGap={0.25}
            arcDashAnimateTime={1400}
            arcStroke={0.4}
            arcsTransitionDuration={0}
            pointsData={pointsData}
            pointColor="color"
            pointAltitude={0.01}
            pointRadius={0.45}
            pointLabel={() => "Honeypot"}
            ringsData={ringsData}
            ringColor="color"
            ringMaxRadius={4}
            ringPropagationSpeed={2.5}
            ringRepeatPeriod={2600}
          />
        )}
      </div>
    </div>
  );
}
