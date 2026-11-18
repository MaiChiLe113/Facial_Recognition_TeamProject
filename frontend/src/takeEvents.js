// Event log for a recorded take, built from its precomputed tracks (data/tracks/take<N>/).
// Each event has t = take time in seconds, so the Demo page shows only the events up to the playback position.
// TODO (Đức Mạnh + Mai Chi): use the events the live pipeline emits once the take runs through it.

const MIN_TRACK_S = 1.0     // shorter tracks are tracker noise (a box that flickers on for a few frames)
const END_SLACK_S = 0.5     // a track that lasts until the end of the clip did not "leave"

const shortName = (name) => (name.split(' ').length > 2 ? name.split(' ').slice(1).join(' ') : name)

// What appearing / disappearing means on each camera.
const WORDS = {
  cam_1: ['seen in the corridor', 'left the corridor view'],
  cam_2: ['entered class', 'left class'],
  attendance_cam: ['at the attendance camera', 'left the attendance camera'],
}

// tracksByCam: { cam_id: { tracks: [{ global_id, name, name_from, keyframes: [{ t }] }] } }
// offsets: { cam_id: offset_s } so every event is on the same take clock as the playback line.
export function eventsFromTracks(tracksByCam, offsets = {}) {
  const events = []
  for (const [camId, data] of Object.entries(tracksByCam)) {
    const tracks = data?.tracks ?? []
    const off = offsets[camId] || 0
    const clipEnd = Math.max(0, ...tracks.map((tr) => tr.keyframes?.at(-1)?.t ?? 0))
    const [inWord, outWord] = WORDS[camId] ?? ['seen', 'gone']
    for (const tr of tracks) {
      const k = tr.keyframes
      if (!k?.length) continue
      const start = k[0].t, end = k[k.length - 1].t
      if (end - start < MIN_TRACK_S) continue
      // Before check-in a person is "ID n"; from name_from on, their name.
      const who = (t) => (tr.name && (tr.name_from == null || t >= tr.name_from) ? shortName(tr.name) : `ID ${tr.global_id}`)
      events.push({ t: start - off, source: camId, event: `${who(start)} ${inWord}` })
      if (tr.name && tr.name_from != null && tr.name_from > start && camId === 'attendance_cam') {
        events.push({ t: tr.name_from - off, source: camId, event: `${shortName(tr.name)} checked in (ID ${tr.global_id})` })
      }
      if (end < clipEnd - END_SLACK_S) events.push({ t: end - off, source: camId, event: `${who(end)} ${outWord}` })
    }
  }
  return events.sort((a, b) => b.t - a.t)     // newest first, like the live log
}

export const clockOf = (s) => `${Math.floor(Math.max(0, s) / 60)}:${String(Math.floor(Math.max(0, s) % 60)).padStart(2, '0')}`
