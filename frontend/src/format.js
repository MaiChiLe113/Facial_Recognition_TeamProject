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

// Attended = checked in AND entered the room at least once (design doc, attendance rules),
// unless it was changed by hand on the History page (row.attended true/false).
export const attended = (row) => (row.attended != null ? row.attended : Boolean(row.check_in && row.entry))

export function formatDate(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
}
