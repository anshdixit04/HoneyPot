export default function AboutPanel({ onClose }) {
  return (
    <div className="about-overlay" onClick={onClose}>
      <div className="about-panel" onClick={(e) => e.stopPropagation()}>
        <button className="about-close" onClick={onClose} aria-label="Close">
          &times;
        </button>
        <h2>About This Project</h2>
        <p>
          This dashboard shows real, live attack traffic against a{" "}
          <a href="https://github.com/cowrie/cowrie" target="_blank" rel="noreferrer">
            Cowrie
          </a>{" "}
          SSH/Telnet honeypot &mdash; not synthetic or replayed data. Every pin,
          credential, and command on this page came from an actual internet
          host connecting to the honeypot within the last 24 hours.
        </p>
        <h3>How it works</h3>
        <p>
          Cowrie emulates a vulnerable Linux shell and logs every connection,
          login attempt, and command as JSON. A FastAPI backend tails that
          log, enriches each event with GeoIP data, persists it to SQLite, and
          broadcasts it to this page over a WebSocket.
        </p>
        <h3>Isolation</h3>
        <p>
          Cowrie runs with a read-only root filesystem, all Linux capabilities
          dropped, no-new-privileges, resource limits, and its own Docker
          network. A host-level iptables rule additionally blocks the
          container from making any new outbound connection, so a fully
          compromised honeypot still can&rsquo;t reach anything else.
        </p>
        <h3>Why</h3>
        <p>
          Built as a portfolio project to demonstrate Linux/container
          hardening, real-time systems design, and SIEM-style log pipelines
          end to end &mdash; from raw attacker traffic to a live map.
        </p>
      </div>
    </div>
  );
}
