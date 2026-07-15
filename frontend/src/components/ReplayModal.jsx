import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../api.js";

export default function ReplayModal({ sessionId, onClose }) {
  const [state, setState] = useState("loading"); // loading | ready | error
  const [errorMsg, setErrorMsg] = useState("");
  const [banner, setBanner] = useState("");
  const [steps, setSteps] = useState([]);
  const [revealed, setRevealed] = useState(0);
  const terminalRef = useRef(null);
  const injectButtonRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    setRevealed(0);

    fetch(`${API_BASE}/api/sessions/${sessionId}/replay/steps`)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail || "Replay unavailable");
        }
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        setBanner(data.banner || "");
        setSteps(data.steps || []);
        setState("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setErrorMsg(err.message || "Failed to load recording");
        setState("error");
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const done = state === "ready" && revealed >= steps.length;

  const injectNext = () => {
    if (state !== "ready" || done) return;
    setRevealed((r) => r + 1);
  };

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [revealed, state]);

  // Auto-focus the inject button so the browser's native "Enter/Space
  // activates the focused button" behavior covers the "press Enter"
  // hint, instead of a custom global keydown listener (which would fire
  // on any Enter press anywhere on the page while this modal is open -
  // too broad, and easy to trigger unintentionally).
  useEffect(() => {
    if (state === "ready" && revealed < steps.length) {
      injectButtonRef.current?.focus();
    }
  }, [state, revealed, steps.length]);

  const nextCommand = state === "ready" && !done ? steps[revealed]?.command : null;

  return (
    <div className="about-overlay" onClick={onClose}>
      <div className="replay-panel" onClick={(e) => e.stopPropagation()}>
        <button className="about-close" onClick={onClose} aria-label="Close">
          &times;
        </button>
        <h2>Session Replay</h2>
        <p className="replay-note">
          Real attacker input against Cowrie&rsquo;s simulated shell - not a real compromised system.
          Inject each command yourself to see what happened next.
        </p>

        {state === "loading" && <p className="empty">Loading recording…</p>}
        {state === "error" && <p className="lookup-error">{errorMsg}</p>}

        {state === "ready" && (
          <>
            <pre className="injector-terminal" ref={terminalRef}>
              {banner}
              {steps.slice(0, revealed).map((s, i) => (
                <span key={i}>
                  {s.prompt}
                  {s.command}
                  {"\n"}
                  {s.output}
                </span>
              ))}
              {!done && (
                <>
                  {steps[revealed]?.prompt}
                  <span className="injector-cursor">▊</span>
                </>
              )}
            </pre>

            <div className="injector-controls">
              {!done ? (
                <button
                  ref={injectButtonRef}
                  className="about-button injector-inject"
                  onClick={injectNext}
                >
                  {nextCommand ? (
                    <>
                      Inject: <code>{nextCommand}</code>
                    </>
                  ) : (
                    "Inject next"
                  )}
                  {" "}
                  <span className="injector-hint">(or press Enter)</span>
                </button>
              ) : steps.length === 0 ? (
                <p className="empty">No commands were typed in this session.</p>
              ) : (
                <p className="empty">- session ended -</p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
