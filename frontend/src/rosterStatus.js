// Class roster status driven by the cameras (Home page), in both sources. Everyone starts as "Not seen".
//   Checked in  the attendance camera recognised the face (recorded: the track's name_from; live: a live, named face)
//   In class    seen by the classroom camera (cam_2) after that
//   Left        no longer seen by the classroom camera (recorded: its track ended before the clip did;
//               live: not recognised on cam_2 for LEFT_AFTER_S)
// Roster rows are matched by student_id (live) or by full name (recorded tracks carry names only).
import { reactive } from 'vue'
import { clockOf } from './takeEvents.js'

const END_SLACK_S = 0.5      // a cam_2 track that lasts until the end of the clip did not "leave"
const LEFT_AFTER_S = 30      // live: not recognised in class for this long = left

const blank = (r) => (r.status === 'placeholder' ? r
  : { ...r, status: 'not_seen', check_in: null, entry: null, exit: null, minutes: null, attended: null })
const mins = (s) => Math.round((s / 60) * 10) / 10

// ---- Recorded: from the take's tracks, up to the playback position ----
export function recordedRoster(roster, tracksByCam, offsets, position, playing) {
  const rows = roster.map(blank)
  if (!playing) return rows
  const byName = new Map(rows.map((r) => [r.name, r]))
  const door = tracksByCam.attendance_cam?.tracks ?? []
  for (const tr of door) {
    const r = byName.get(tr.name)
    if (!r || tr.name_from == null) continue
    const t = tr.name_from - (offsets.attendance_cam || 0)
    if (t <= position && (r.check_in == null || t < r._in)) Object.assign(r, { _in: t, check_in: clockOf(t), status: 'checked_in' })
  }
  const room = tracksByCam.cam_2?.tracks ?? []
  const off = offsets.cam_2 || 0
  const clipEnd = Math.max(0, ...room.map((tr) => tr.keyframes?.at(-1)?.t ?? 0))
  for (const r of rows) {
    const seen = room.filter((tr) => tr.name === r.name && tr.keyframes?.length)
      .map((tr) => ({ start: tr.keyframes[0].t - off, end: tr.keyframes.at(-1).t - off, open: tr.keyframes.at(-1).t >= clipEnd - END_SLACK_S }))
      .filter((s) => s.start <= position)
    if (!seen.length) continue
    const entry = Math.min(...seen.map((s) => s.start))
    const last = seen.reduce((a, b) => (b.end > a.end ? b : a))
    const gone = !last.open && last.end <= position
    Object.assign(r, { entry: clockOf(entry), status: gone ? 'left' : 'in_class', exit: gone ? clockOf(last.end) : null,
      minutes: mins((gone ? last.end : position) - entry), attended: r.check_in != null })
  }
  return rows
}

// ---- Live: accumulated from GET /api/live polls (wall-clock times) ----
const live = reactive({})    // student_id -> { checkIn, entry, lastInside }  (ms timestamps)
const hhmm = (ms) => new Date(ms).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })

// Call on every poll with the /api/live answer.
export function updateLive(liveStatus, now = Date.now()) {
  const cams = Object.fromEntries((liveStatus?.cameras ?? []).map((c) => [c.cam_id, c]))
  const known = (c) => (c?.connected ? c.faces ?? [] : []).filter((f) => f.student_id && f.live !== false)
  for (const f of known(cams.attendance_cam)) {
    live[f.student_id] ??= {}
    live[f.student_id].checkIn ??= now
  }
  // In class: a face recognised by the classroom camera, or a classroom track named by the door handoff.
  const insidePeople = (cams.cam_2?.connected ? cams.cam_2.people ?? [] : []).filter((p) => p.student_id)
  for (const x of [...known(cams.cam_2), ...insidePeople]) {
    const s = (live[x.student_id] ??= {})
    s.entry ??= now
    s.lastInside = now
  }
}
export function resetLive() { for (const k of Object.keys(live)) delete live[k] }

export function liveRoster(roster, now = Date.now()) {
  return roster.map((r0) => {
    const r = blank(r0)
    const s = live[r.student_id]
    if (!s) return r
    if (s.checkIn) Object.assign(r, { status: 'checked_in', check_in: hhmm(s.checkIn) })
    if (s.entry) {
      const gone = now - s.lastInside > LEFT_AFTER_S * 1000
      Object.assign(r, { entry: hhmm(s.entry), status: gone ? 'left' : 'in_class', exit: gone ? hhmm(s.lastInside) : null,
        minutes: mins(((gone ? s.lastInside : now) - s.entry) / 1000), attended: !!s.checkIn })
    }
    return r
  })
}
