// Talks to the FastAPI backend. If the backend is not running, falls back to the
// same mock files in ../data/mock so the page still renders.
import sessionMock from '../../data/mock/session.json'
import studentsCsv from '../../data/mock/students.csv?raw'
import coursesCsv from '../../data/mock/courses.csv?raw'
import videoConfig from '../../data/video_config.json'
import trackCam1 from '../../data/mock/tracks/cam_1.json'
import trackCam2 from '../../data/mock/tracks/cam_2.json'
import trackAtt from '../../data/mock/tracks/attendance_cam.json'

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

export async function fetchDemoConfig() {
  try {
    return { ...(await getJson('/api/demo/config')), offline: false }
  } catch {
    return {
      offline: true,
      take: videoConfig.take,
      cameras: videoConfig.cameras.map((c) => ({ ...c, available: false, url: null })),
    }
  }
}

export async function fetchTracks(camId) {
  try {
    return await getJson(`/api/tracks/${camId}`)
  } catch {
    return MOCK_TRACKS[camId] ?? { cam_id: camId, source: 'none', tracks: [] }
  }
}

// ---- offline fallback: same shape as backend/app/mock_store.py ----
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
      exit: a.exit ?? null, minutes: a.minutes ?? null, photo: null,
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
