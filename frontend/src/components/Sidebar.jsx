const Icon = ({ d }) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
)

const ITEMS = [
  { key: 'home', label: 'Home', d: 'M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z' },
  { key: 'attend', label: 'Attend Course', d: 'M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M12 9a2 2 0 1 0 0 .01M9 16c.5-1.5 1.6-2.2 3-2.2s2.5.7 3 2.2' },
  { key: 'class', label: 'Class', d: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17l9 5 9-5' },
  { key: 'history', label: 'History', d: 'M3 12a9 9 0 1 0 3-6.7M3 4v4h4M12 7v5l3 2' },
  { key: 'demo', label: 'Demo', d: 'M4 5h16v14H4zM10 9l5 3-5 3z' },
]

export default function Sidebar({ page, onNavigate }) {
  return (
    <aside className="sidebar">
      <div className="brand">Hawkeye</div>
      <nav>
        {ITEMS.map((it) => (
          <button key={it.key} className={`nav-item ${page === it.key ? 'active' : ''}`} onClick={() => onNavigate(it.key)}>
            <Icon d={it.d} />
            <span>{it.label}</span>
          </button>
        ))}
      </nav>
      <button className={`add-person ${page === 'add' ? 'active' : ''}`} onClick={() => onNavigate('add')}>
        <span className="plus">+</span> Add person
      </button>
    </aside>
  )
}
