// Small helpers shared by the pages.

export const STATUS = {
  in_class: 'In class',
  left: 'Left',
  checked_in: 'Checked in',
  not_seen: 'Not seen',
  placeholder: 'TBC',
}

export const CAMERA = { cam_1: 'CAM 1', cam_2: 'CAM 2', attendance_cam: 'Doorway' }

export const initials = (name) => name.split(' ').filter(Boolean).slice(-2).map((w) => w[0]).join('').toUpperCase()
export const dash = (v) => v ?? '—'
export const minutes = (m) => (m != null ? `${m} min` : '—')

// Attended = checked in AND entered the room at least once (design doc, attendance rules).
export const attended = (row) => Boolean(row.check_in && row.entry)

export function todayIso() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function formatDate(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
}

// "Wednesday 8-12AM" -> { start: "08:00", end: "12:00" };  "Wednesday 1-5PM" -> { start: "13:00", end: "17:00" }
export function parseSessionTime(text) {
  const m = /(\d{1,2})\s*-\s*(\d{1,2})\s*(AM|PM)/i.exec(text || '')
  if (!m) return { start: '', end: '' }
  const pm = m[3].toUpperCase() === 'PM'
  const to24 = (h) => (pm && h < 12 ? h + 12 : h)
  const fmt = (h) => `${String(h).padStart(2, '0')}:00`
  return { start: fmt(to24(Number(m[1]))), end: fmt(to24(Number(m[2]))) }
}
