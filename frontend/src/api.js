// Talks to the FastAPI backend. If the backend is not running, falls back to the
// same mock files in ../data/mock so the page still renders.
import sessionMock from '../../data/mock/session.json'
import roster from '../../data/mock/roster.json'
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

// ---- Presence verification + door audit (backend/app/features/presence_verification/) --------------------
// The model runs on the backend only. Without it this answers { offline: true } (backend down) or
// { unavailable: true, message } (feature switched off or model not trained), and the page hides the panel.
export async function fetchPresence(take) {
  try {
    const res = await fetch(`/api/features/presence_verification/take/${take}`)
    if (res.ok) return { ...(await res.json()), offline: false }
    const body = await res.json().catch(() => null)
    return { unavailable: true, offline: false,
      message: res.status === 404 && !body?.detail?.startsWith?.('No data')
        ? 'Presence verification is not running. Train the model (ml/presence_verification/train.py), then restart the backend.'
        : (body?.detail ?? `The backend answered ${res.status}.`) }
  } catch {
    return { offline: true }
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

export async function deleteStudent(studentId) {
  const res = await fetch(`/api/students/${encodeURIComponent(studentId)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || `Could not remove ${studentId} (${res.status})`)
  return res.json()
}

// form: FormData with name, student_id_vn, student_id_au, year, courses (JSON list of course keys), and either
// photos (files) or enrol_session (id of a finished face scan, see the scan helpers below)
export async function createStudent(form) {
  let res
  try {
    res = await fetch('/api/students', { method: 'POST', body: form })
  } catch {
    return { ok: false, offline: true, message: 'The backend is not running, so nothing was saved.' }
  }
  const body = await res.json().catch(() => null)
  if (res.ok) return { ok: true, student: body }
  if (((res.status === 404 || res.status === 405) && !body?.detail) || (res.status >= 500 && !body)) {
    return { ok: false, offline: true, message: 'POST /api/students is not built on the backend yet, so nothing was saved.' }
  }
  return { ok: false, message: body?.detail ? String(body.detail) : `The backend answered ${res.status}.` }
}

// ---- live_face_scan for Add person (backend/app/api/enrol.py) ------------------------------------
//   POST /api/enrol/session            -> summary { session_id, model, threshold, per_slot, missing, done, slots, ... }
//   POST /api/enrol/frame (multipart)  -> analysis { faces, box, yaw, pitch, slot, quality, reason, hint, kept, ... }
//   POST /api/enrol/video (multipart)  -> summary + frame_reasons
//   GET  /api/enrol/session/{id}/still/{slot}/{i}  kept still (JPEG)
// The scan needs the backend (the models run there); with the backend down these return { error }.
async function scanCall(url, form) {
  try {
    const res = await fetch(url, { method: 'POST', body: form })
    const body = await res.json().catch(() => null)
    return res.ok ? body : { error: body?.detail ? String(body.detail) : `The backend answered ${res.status}.`, status: res.status }
  } catch {
    return { error: 'The face scan needs the backend, and it is not running.', offline: true }
  }
}

export function startScan(source = 'live') {
  const form = new FormData()
  form.append('source', source)
  return scanCall('/api/enrol/session', form)
}

export function sendScanFrame(sessionId, blob, final = false) {
  const form = new FormData()
  form.append('session_id', sessionId)
  form.append('final', final ? 'true' : 'false')
  form.append('image', blob, 'frame.jpg')
  return scanCall('/api/enrol/frame', form)
}

export function uploadScanVideo(sessionId, file) {
  const form = new FormData()
  form.append('session_id', sessionId)
  form.append('video', file, file.name)
  return scanCall('/api/enrol/video', form)
}

export async function fetchScan(sessionId) {
  try { return await getJson(`/api/enrol/session/${sessionId}`) } catch (e) { return { error: String(e) } }
}

export function failScan(sessionId, reason, attempts, reasons) {
  const form = new FormData()
  form.append('reason', reason)
  form.append('attempts', String(attempts))
  form.append('reasons', JSON.stringify(reasons || {}))
  return scanCall(`/api/enrol/session/${sessionId}/fail`, form)
}

export function discardScan(sessionId) {
  return fetch(`/api/enrol/session/${sessionId}`, { method: 'DELETE' }).catch(() => null)
}

export async function removeScanStill(sessionId, slot, i) {
  const res = await fetch(`/api/enrol/session/${sessionId}/still/${slot}/${i}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Could not remove the photo (${res.status})`)
  return res.json()
}

export const scanStillUrl = (sessionId, slot, i) => `/api/enrol/session/${sessionId}/still/${slot}/${i}`

// ---- Live cameras over Wi-Fi (backend/app/api/live.py) -------------------------------------------
//   GET /api/live -> { cameras: [{ cam_id, label, place, role, connected, senders, fps, people, faces, frame_ms }],
//                      host_urls: ['https://<host IP>:5173/camera'] }
//   GET /api/live/{cam_id}/stream   MJPEG of the annotated frames (use as <img src>)
//   WS  /ws/camera/{cam_id}         the Camera page sends JPEG frames; each answer = that frame's summary
export async function fetchLive() {
  try {
    return { ...(await getJson('/api/live')), offline: false }
  } catch {
    return { cameras: [], host_urls: [], offline: true }
  }
}

export const liveStreamUrl = (camId) => `/api/live/${camId}/stream`
// Host removes a camera, even while a device is sending: the backend closes that device's connection.
export async function removeLiveCamera(camId) {
  const r = await fetch(`/api/live/${encodeURIComponent(camId)}/remove`, { method: 'POST' })
  if (!r.ok) throw new Error(`Remove failed (${r.status})`)
}
export const cameraSocketUrl = (camId) =>
  `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/camera/${encodeURIComponent(camId)}`

// ---- Features demo page (backend/app/api/features_demo.py) ----------------------------------------
// The three basic models run on the backend; there is no offline fallback, so these report offline: true.
export async function fetchFeatureStatus() {
  try {
    return { ...(await getJson('/api/features-demo/status')), offline: false }
  } catch {
    return { features: [], offline: true }
  }
}

// blob: one JPEG frame; features: ['face_recognition', 'anti_spoofing', 'emotion']; client: id of this page
// threshold: optional face-recognition cosine threshold; livenessThreshold: optional anti-spoofing score
// threshold (0..1). null = the one saved in the weights.
// The answer carries log_rows: the frame's lines for the session log shown on the page.
export async function inferFrame(blob, features, client, threshold = null, livenessThreshold = null) {
  try {
    const extra = (threshold == null ? '' : `&threshold=${threshold}`)
      + (livenessThreshold == null ? '' : `&liveness_threshold=${livenessThreshold}`)
    const res = await fetch(`/api/features-demo/infer?features=${features.join(',')}&client=${client}${extra}`,
      { method: 'POST', headers: { 'Content-Type': 'image/jpeg' }, body: blob })
    if (!res.ok) return { faces: [], errors: { backend: `answered ${res.status}` }, offline: false }
    return { ...(await res.json()), offline: false }
  } catch {
    return { faces: [], errors: {}, offline: true }
  }
}

// Save a finished camera session (rows = the log rows collected from inferFrame) as logs/features_demo_<start>.csv.
export async function saveSessionLog(rows, started) {
  try {
    const res = await fetch('/api/features-demo/log', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ started, rows }),
    })
    const body = await res.json().catch(() => null)
    return res.ok ? { ok: true, ...body } : { ok: false, error: body?.detail ? String(body.detail) : `The backend answered ${res.status}.` }
  } catch {
    return { ok: false, error: 'The backend is not running, so the log was not saved.' }
  }
}

// The registered students (Drive enrolment photos, embedded by the backend on first use; a few seconds).
export async function fetchDemoGallery(reload = false) {
  try {
    return await getJson(`/api/features-demo/gallery${reload ? '?reload=true' : ''}`)
  } catch {
    return { people: [], skipped: [], error: 'The backend is not running.', drive_root_exists: true }
  }
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

// Offline fallback = the seed the backend starts from (data/mock/roster.json), same shape as GET /api/students.
function mockStudents() {
  return roster.students.map((s) => ({ ...s, photo: s.student_card ? `/photos/${s.student_id_vn}` : null }))
}

function mockCourses() {
  return roster.courses
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
function buildMockDashboard() {
  const s = sessionMock.session
  const course = roster.courses.find((c) => c.key_id === s.course_key)
  const byId = Object.fromEntries(sessionMock.attendance.map((a) => [a.student_id_vn, a]))
  const rows = mockStudents().map((st) => {
    const a = byId[st.student_id_vn] ?? {}
    return {
      name: st.name, student_id: st.student_id_vn, global_id: a.global_id ?? null, enrolled: st.courses.includes(s.course_key),
      status: a.status ?? 'not_seen', check_in: a.check_in ?? null, entry: a.entry ?? null,
      exit: a.exit ?? null, minutes: a.minutes ?? null,
      photo: st.photo,
    }
  })
  for (const p of sessionMock.placeholder_students ?? []) {
    rows.push({ name: p.student_name, student_id: null, global_id: null, enrolled: false, status: 'placeholder', note: p.note })
  }
  return {
    source: 'mock',
    course: { id: course.course_id, name: course.course_name, session_time: course.session_time, room: s.room },
    session: s,
    roster: rows,
    events: sessionMock.events,
    attendance_cam_status: sessionMock.attendance_cam_status,
    map: sessionMock.map,
  }
}

// ---- System log page (backend/app/api/system.py, services/model_log.py) ----
// { models: [{key, label, file, found, version, note, modified, size, sha256}], history: [...newest first] }
export async function fetchSystemModels() {
  try {
    return { ...(await getJson('/api/system/models')), offline: false }
  } catch {
    return { models: [], history: [], offline: true }
  }
}
