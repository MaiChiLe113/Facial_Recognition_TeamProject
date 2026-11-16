const STATUS = {
  in_class: 'In class',
  left: 'Left',
  checked_in: 'Checked in',
  not_seen: 'Not seen',
  placeholder: 'TBC',
}

const initials = (name) => name.split(' ').filter(Boolean).slice(-2).map((w) => w[0]).join('').toUpperCase()
const dash = (v) => v ?? '—'

export default function ClassRoster({ roster }) {
  const enrolled = roster.filter((r) => r.enrolled).length
  const inClass = roster.filter((r) => r.status === 'in_class').length
  return (
    <section className="card roster">
      <header className="card-head">
        <h2>Class roster</h2>
        <span className="muted">{enrolled} enrolled · {inClass} in class</span>
      </header>
      <table>
        <thead>
          <tr>
            <th>Student</th><th>Student ID</th><th>Status</th><th>Check-in</th>
            <th>Entry</th><th>Exit</th><th>Duration</th><th></th>
          </tr>
        </thead>
        <tbody>
          {roster.map((r, i) => (
            <tr key={i} className={r.status === 'placeholder' ? 'placeholder-row' : ''}>
              <td className="student">
                {/* TODO: show the first registration photo when photo != null */}
                <span className="avatar">{initials(r.name)}</span>
                <span>
                  <strong>{r.name}</strong>
                  {!r.enrolled && r.status !== 'placeholder' && <span className="tag">course not set</span>}
                  {r.note && <span className="tag">{r.note}</span>}
                </span>
              </td>
              <td>{dash(r.student_id)}</td>
              <td><span className={`status ${r.status}`}>{STATUS[r.status] ?? r.status}</span></td>
              <td>{dash(r.check_in)}</td>
              <td>{dash(r.entry)}</td>
              <td>{dash(r.exit)}</td>
              <td>{r.minutes != null ? `${r.minutes} min` : '—'}</td>
              <td><a href="#" onClick={(e) => e.preventDefault()} title="TODO: per-student log page">Logs</a></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
