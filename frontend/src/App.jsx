import { useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import Home from './pages/Home.jsx'
import Placeholder from './pages/Placeholder.jsx'

// Pages from the design doc (section 7). Only Home is built; the rest are placeholders.
const PAGES = {
  home: { label: 'Home' },
  attend: { label: 'Attend Course', todo: 'Pick the course + session (e.g. COS30082, Room 204) to start taking attendance.', owner: 'Đức Mạnh' },
  class: { label: 'Class', todo: 'Course table: name, student ID, attended, time in/out, total time, link to logs.', owner: 'Đức Mạnh' },
  history: { label: 'History', todo: 'Past sessions and logs, filter by student and date.', owner: 'Đức Mạnh' },
  demo: { label: 'Demo', todo: 'Choose any of the 9 recorded takes and run it through the pipeline. For now, use "Run demo videos" on Home.', owner: 'Đức Mạnh' },
  add: { label: 'Add person', todo: 'Register a student: name, student ID, 10–20 photos → embeddings saved. The only way to register.', owner: 'Đức Mạnh + Thuận Minh' },
}

export default function App() {
  const [page, setPage] = useState('home')
  return (
    <div className="app">
      <Sidebar page={page} onNavigate={setPage} />
      <main className="main">
        {page === 'home' ? <Home /> : <Placeholder {...PAGES[page]} />}
      </main>
    </div>
  )
}
