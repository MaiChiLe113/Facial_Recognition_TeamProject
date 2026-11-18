// Talks to the FastAPI backend. If the backend is not running, falls back to the
// same mock files in ../data/mock so the page still renders.
import sessionMock from '../../data/mock/session.json'
import studentsCsv from '../../data/mock/students.csv?raw'
import coursesCsv from '../../data/mock/courses.csv?raw'
import videoConfig from '../../data/video_config.json'
import trackCam1 from '../../data/mock/tracks/cam_1.json'
import trackCam2 from '../../data/mock/tracks/cam_2.json'
import trackAtt from '../../data/mock/tracks/attendance_cam.json'
import pastSessionsJson from '../../data/mock/past_sessions.json'

const pastSessions = pastSessionsJson.sessions

const MOCK_TRACKS = { cam_1: trackCam1, cam_2: trackCam2, attendance_cam: trackAtt }

async function getJson(url) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${url} -> ${res.status}`)
  return res.json()
}

export async function fetchDashboard() {
  try {
    return { ...(await getJson('/api/dashboard')), offline: false }
  } catch {
    return { ...buildMockDashboard(), offline: true }
  }
}

// take: optional take number; without it the backend uses the take selected in data/video_config.json.
export async function fetchDemoConfig(take) {
  try {
    return { ...(await getJson(take == null ? '/api/demo/config' : `/api/demo/config?take=${take}`)), offline: false }
  } catch {
    return {
      offline: true,
      take: take ?? videoConfig.take,
      cameras: videoConfig.cameras.map((c) => ({ ...c, available: false, url: null })),
    }
  }
}

export async function fetchTracks(camId, take) {
  try {
    return await getJson(take == null ? `/api/tracks/${camId}` : `/api/tracks/${camId}?take=${take}`)
  } catch {
    // The mock boxes only make sense for the selected take.
    if (take != null && take !== videoConfig.take) return { cam_id: camId, source: 'none', tracks: [] }
    return MOCK_TRACKS[camId] ?? { cam_id: camId, source: 'none', tracks: [] }
  }
}

// ---- pages beyond Home --------------------------------------------------------------
// Served from SQLite by backend/app/api/records.py. Without the backend, each call falls back to data/mock.
// Shapes:
//   GET /api/students  -> [{ student_id_vn, student_id_au, name, year, courses: [course_key], photo_folder }]
//   GET /api/courses   -> [{ key_id, course_id, course_name, session_time, room }]
//   GET /api/sessions  -> [{ id, course_key, room, date, start, end, attendance: [...], events: [...] }]  newest first
//                         attendance rows as in session.json plus attended (manual override, null = rule);
//                         events: { time, event, source, student_id }
//   PATCH /api/sessions/{id}/attendance/{student_id}  body { status?, attended? } -> the saved attendance row
//   POST /api/students -> multipart form (see createStudent); returns the saved student

export async function fetchStudents() {
  try {
    return { items: await getJson('/api/students'), offline: false }
  } catch {
    return { items: mockStudents(), offline: true }
  }
}

export async function fetchCourses() {
  try {
    return { items: await getJson('/api/courses'), offline: false }
  } catch {
    return { items: mockCourses(), offline: true }
  }
}

export async function fetchSessions() {
  try {
    return { items: await getJson('/api/sessions'), offline: false }
  } catch {
    return { items: mockSessions(), offline: true }
  }
}

// All recorded takes (data/video_config.json); the backend streams any of them with ?take=N.
export function demoTakes() {
  return { take: videoConfig.take, takes: videoConfig.takes }
}

// Manual change from the History roster. Returns { ok, row } or { ok: false, message }.
export async function updateAttendance(sessionId, studentId, changes) {
  try {
    const res = await fetch(`/api/sessions/${sessionId}/attendance/${encodeURIComponent(studentId)}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes),
    })
    const body = await res.json().catch(() => null)
    if (res.ok) return { ok: true, row: body }
    return { ok: false, message: body?.detail ? String(body.detail) : `The backend answered ${res.status}.` }
  } catch {
    return { ok: false, message: 'The backend is not running, so the change was not saved.' }
  }
}

// form: FormData with name, student_id_vn, student_id_au, year, courses (JSON list of course keys), photos (files)
export async function createStudent(form) {
  let res
  try {
    res = await fetch('/api/students', { method: 'POST', body: form })
  } catch {
    return { ok: false, offline: true, message: 'The backend is not running, so nothing was saved.' }
  }
  const body = await res.json().catch(() => null)
  if (res.ok) return { ok: true, student: body }
  if (res.status === 404 || res.status === 405 || (res.status >= 500 && !body)) {
    return { ok: false, offline: true, message: 'POST /api/students is not built on the backend yet, so nothing was saved.' }
  }
  return { ok: false, message: body?.detail ? String(body.detail) : `The backend answered ${res.status}.` }
}

// One roster row per student for a session. Same row shape as the dashboard roster.
export function buildRoster(students, session) {
  const byId = Object.fromEntries((session.attendance ?? []).map((a) => [a.student_id_vn, a]))
  return students.map((st) => {
    const a = byId[st.student_id_vn] ?? {}
    return {
      name: st.name, student_id: st.student_id_vn, global_id: a.global_id ?? null,
      enrolled: st.courses.includes(session.course_key),
      status: a.status ?? 'not_seen', check_in: a.check_in ?? null, entry: a.entry ?? null,
      exit: a.exit ?? null, minutes: a.minutes ?? null, attended: a.attended ?? null, photo: st.photo ?? null,
    }
  })
}

const parseCourseKeys = (value) => (value || '').replace(/[[\]]/g, '').split(',').filter((v) => v.trim()).map(Number)

function mockStudents() {
  return parseCsv(studentsCsv).map((s) => ({
    student_id_vn: s.student_id_vn, student_id_au: s.student_id_au, name: s.student_name,
    year: s.year, courses: parseCourseKeys(s.courses), photo_folder: s.photo_folder,
    photo: s.student_card ? `/photos/${s.student_id_vn}` : null,
  }))
}

function mockCourses() {
  return parseCsv(coursesCsv).map((c) => ({ ...c, key_id: Number(c.key_id) }))
}

function mockSessions() {
  const s = sessionMock.session
  const students = mockStudents()
  // session.json events carry no student ID, so match the student's name in the text (mock only).
  const idOf = (text) => students.find((st) => text.includes(st.name))?.student_id_vn ?? null
  const current = {
    id: `${s.date}-${s.course_key}`, course_key: s.course_key, room: s.room, date: s.date, start: s.start, end: s.end,
    attendance: sessionMock.attendance,
    events: sessionMock.events.map((e) => ({ ...e, student_id: idOf(e.event) })),
  }
  return [current, ...pastSessions].sort((a, b) => `${b.date} ${b.start}`.localeCompare(`${a.date} ${a.start}`))
}

// ---- offline fallback: same shape as backend/app/db/queries.py ----
function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/)
  const header = lines[0].split(',')
  return lines.slice(1).map((line) => {
    const cells = line.match(/("[^"]*"|[^,]*)(,|$)/g).map((c) => c.replace(/,$/, '').replace(/^"|"$/g, ''))
    return Object.fromEntries(header.map((h, i) => [h, cells[i] ?? '']))
  })
}

function buildMockDashboard() {
  const students = parseCsv(studentsCsv)
  const courses = parseCsv(coursesCsv)
  const s = sessionMock.session
  const course = courses.find((c) => Number(c.key_id) === s.course_key)
  const byId = Object.fromEntries(sessionMock.attendance.map((a) => [a.student_id_vn, a]))
  const roster = students.map((st) => {
    const a = byId[st.student_id_vn] ?? {}
    const enrolled = (st.courses || '').replace(/[[\]]/g, '').split(',').map(Number).includes(s.course_key)
    return {
      name: st.student_name, student_id: st.student_id_vn, global_id: a.global_id ?? null, enrolled,
      status: a.status ?? 'not_seen', check_in: a.check_in ?? null, entry: a.entry ?? null,
      exit: a.exit ?? null, minutes: a.minutes ?? null,
      photo: st.student_card ? `/photos/${st.student_id_vn}` : null,
    }
  })
  for (const p of sessionMock.placeholder_students ?? []) {
    roster.push({ name: p.student_name, student_id: null, global_id: null, enrolled: false, status: 'placeholder', note: p.note })
  }
  return {
    source: 'mock',
    course: { id: course.course_id, name: course.course_name, session_time: course.session_time, room: s.room },
    session: s,
    roster,
    events: sessionMock.events,
    attendance_cam_status: sessionMock.attendance_cam_status,
    map: sessionMock.map,
  }
}
