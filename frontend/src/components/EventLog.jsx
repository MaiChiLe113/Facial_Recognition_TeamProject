const SOURCE = { cam_1: 'CAM 1', cam_2: 'CAM 2', attendance_cam: 'Doorway' }

export default function EventLog({ events }) {
  return (
    <section className="card event-log">
      <h2>Event log</h2>
      <table>
        <thead>
          <tr><th>Time</th><th>Event</th><th className="right">Source</th></tr>
        </thead>
        <tbody>
          {events.map((e, i) => (
            <tr key={i} className={i === 0 ? 'latest' : ''}>
              <td>{e.time}</td>
              <td>{e.event}</td>
              <td className="right">{SOURCE[e.source] ?? e.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
