export default function EventFeed({ events }) {
  return (
    <div className="panel event-feed">
      <h2>Live Feed</h2>
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Source IP</th>
            <th>Country</th>
            <th>Type</th>
            <th>Username</th>
            <th>Password</th>
            <th>Command</th>
          </tr>
        </thead>
        <tbody>
          {events.slice(0, 100).map((e) => (
            <tr key={e.id}>
              <td>{new Date(e.ts).toLocaleTimeString()}</td>
              <td>{e.src_ip}</td>
              <td>{e.country ?? "?"}</td>
              <td className={`event-type ${e.event_type}`}>{e.event_type}</td>
              <td>{e.username ?? ""}</td>
              <td>{e.password ?? ""}</td>
              <td>{e.command ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
