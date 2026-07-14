import { useEffect, useRef, useState } from "react";
import { create } from "asciinema-player";
import "asciinema-player/dist/bundle/asciinema-player.css";
import { API_BASE } from "../api.js";

export default function ReplayModal({ sessionId, onClose }) {
  const containerRef = useRef(null);
  const playerRef = useRef(null);
  const [state, setState] = useState("loading"); // loading | ready | error
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    const url = `${API_BASE}/api/sessions/${sessionId}/replay`;

    // Check first so a missing recording shows our own message instead
    // of the player's generic load-failure state; the player then
    // fetches the same URL itself (its best-supported loading path —
    // passing raw cast text via `data` isn't handled by every version).
    fetch(url)
      .then((res) => {
        if (cancelled) return;
        if (!res.ok) {
          setErrorMsg("No recording available for this session");
          setState("error");
          return;
        }
        if (!containerRef.current) return;
        playerRef.current = create(url, containerRef.current, {
          theme: "monokai",
          fit: "width",
          terminalFontSize: "small",
        });
        setState("ready");
      })
      .catch(() => {
        if (!cancelled) {
          setErrorMsg("Failed to load recording");
          setState("error");
        }
      });

    return () => {
      cancelled = true;
      playerRef.current?.dispose();
      playerRef.current = null;
    };
  }, [sessionId]);

  return (
    <div className="about-overlay" onClick={onClose}>
      <div className="replay-panel" onClick={(e) => e.stopPropagation()}>
        <button className="about-close" onClick={onClose} aria-label="Close">
          &times;
        </button>
        <h2>Session Replay</h2>
        <p className="replay-note">
          Real attacker input against Cowrie&rsquo;s simulated shell — not a real compromised system.
        </p>
        {state === "loading" && <p className="empty">Loading recording…</p>}
        {state === "error" && <p className="lookup-error">{errorMsg}</p>}
        <div
          ref={containerRef}
          className="replay-player"
          style={{ display: state === "ready" ? "block" : "none" }}
        />
      </div>
    </div>
  );
}
