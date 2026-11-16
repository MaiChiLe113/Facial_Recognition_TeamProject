export default function Placeholder({ label, todo, owner }) {
  return (
    <div className="placeholder-page">
      <h1>{label}</h1>
      <div className="card placeholder-card">
        <span className="badge">Placeholder</span>
        <p>{todo}</p>
        <p className="muted">Owner: {owner}</p>
      </div>
    </div>
  )
}
