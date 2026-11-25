<script setup>
// Home: the room's three camera tiles, from one of two sources (the switch in the top bar, kept in the URL):
//   Live          phones / laptops used as cameras (/camera page). Each tile shows that camera's MJPEG stream
//                 (GET /api/live/<cam_id>/stream, boxes drawn by the backend) and the doorway tile lists the real
//                 per-face results from GET /api/live, polled every second. "+" on an idle tile opens /camera?cam=<id>.
//   Recorded      one of the recorded takes played in sync, with its precomputed track boxes (/api/tracks), the take's
//                 event log, presence verification + door audit and the map trails. (This was the MultiCam page, /demo,
//                 which now redirects here: /?source=recorded&take=N.)
// Class roster and room map are shown in both modes.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { demoTakes, fetchDashboard, fetchDemoConfig, fetchLive, fetchPresence, fetchTracks, liveStreamUrl, removeLiveCamera } from '../api.js'
import CameraCard from '../components/CameraCard.vue'
import ClassRoster from '../components/ClassRoster.vue'
import EventLog from '../components/EventLog.vue'
import QrButton from '../components/QrButton.vue'
import PresencePanel from '../components/PresencePanel.vue'
import RoomMap from '../components/RoomMap.vue'
import { useSyncedPlayback } from '../composables/useSyncedPlayback.js'
import { clockOf, eventsFromTracks } from '../takeEvents.js'
import { liveRoster, recordedRoster, updateLive } from '../rosterStatus.js'

const ORDER = ['cam_1', 'cam_2', 'attendance_cam']
const POLL_MS = 1000

const route = useRoute()
const router = useRouter()
const { take: defaultTake, takes } = demoTakes()

const takeFromUrl = () => {
  const n = Number(route.query.take)
  return takes.some((t) => t.take === n) ? n : defaultTake
}
const recorded = computed(() => route.query.source === 'recorded')
const selected = ref(takeFromUrl())

const dash = ref(null)       // course, roster, map and the live-mode event log (mock session until the DB has one)
const demo = ref(null)       // camera list (labels, places) and, in Recorded mode, the take's video URLs

// ---------------- source switch ----------------
function setSource(source, take = selected.value) {
  const query = source === 'recorded' ? { source, take: String(take) } : {}
  router.replace({ query })
}
watch(recorded, (on) => {
  if (on) { startRecorded() } else { stop(); message.value = '' }
})
watch(() => route.query.take, () => { if (recorded.value) choose(takeFromUrl()) })

// ---------------- live ----------------
const live = ref(null)
const epoch = ref(Date.now())   // changes the stream URLs after the backend comes back, so the <img>s reconnect
let timer = null, wasOffline = false, alive = true

async function poll() {
  const r = await fetchLive()
  if (!alive) return
  if (wasOffline && !r.offline) epoch.value = Date.now()
  wasOffline = r.offline
  live.value = r
  updateLive(r)
  timer = setTimeout(poll, POLL_MS)
}
const liveOf = (camId) => live.value?.cameras.find((c) => c.cam_id === camId) ?? null
// Remove a live camera (also while its device is still sending), then refresh at once so the tile goes idle.
async function removeCam(camId) {
  try { await removeLiveCamera(camId) } catch (e) { console.warn(e) }
  await poll()
}
const streamOf = (camId) => (liveOf(camId)?.connected ? `${liveStreamUrl(camId)}?e=${epoch.value}` : undefined)
const senderUrl = computed(() => live.value?.host_urls?.[0] ?? 'https://<this computer\'s IP>:5173/camera')
const connected = computed(() => live.value?.cameras.filter((c) => c.connected).length ?? 0)
// Every camera runs face recognition, liveness and emotion (always on); only the doorway checks people in.
const facesOf = (camId) => liveOf(camId)?.faces ?? []
const peopleOf = (camId) => liveOf(camId)?.people ?? []

// ---------------- recorded (was MultiCam) ----------------
const tracks = ref({})
const presence = ref(null)   // presence verification + door audit of the take (null while loading)
const message = ref('')
const cards = {}
const videoOf = (camId) => cards[camId]?.video
const cameras = computed(() => (demo.value ? ORDER.map((id) => demo.value.cameras.find((c) => c.cam_id === id)).filter(Boolean) : []))
const { srcs, playing, position, duration, seek, play, togglePause, restart, stop } = useSyncedPlayback(cameras, videoOf)

// Camera list + video URLs and the boxes for one take. Ignores answers for a take that is no longer selected.
function loadTake(n) {
  fetchDemoConfig(n).then((d) => { if (selected.value === n) demo.value = d })
  tracks.value = {}
  presence.value = null
  fetchPresence(n).then((p) => { if (selected.value === n) presence.value = p })
  Promise.all(ORDER.map((c) => fetchTracks(c, n))).then((list) => {
    if (selected.value === n) tracks.value = Object.fromEntries(ORDER.map((c, i) => [c, list[i]]))
  })
}
function startRecorded() {
  selected.value = takeFromUrl()
  loadTake(selected.value)
}

const streamable = computed(() => demo.value && !demo.value.offline && demo.value.take === selected.value
  && cameras.value.some((c) => c.available))
const takeTracks = (camId) => tracks.value[camId] ?? null
const hasVideo = computed(() => Object.keys(srcs.value).length > 0)

function choose(n) {
  if (n === selected.value && demo.value?.take === n) return
  stop()
  selected.value = n
  message.value = ''
  if (Number(route.query.take) !== n) setSource('recorded', n)
  loadTake(n)
  window.scrollTo({ top: 0, behavior: 'smooth' })   // back to the cameras to play the chosen take
}

function playTake() {
  if (!streamable.value) {
    message.value = demo.value?.offline
      ? 'The backend is not running, so videos cannot stream. Start uvicorn.'
      : demo.value?.take !== selected.value
        ? `Loading take ${selected.value}…`
        : `No video found for take ${selected.value}. Check HAWKEYE_VIDEO_ROOT in backend/.env.`
    return
  }
  const ready = cameras.value.filter((c) => c.available)
  // No box while things work; only a warning when some videos are missing.
  message.value = ready.length < cameras.value.length ? `Only ${ready.length} of ${cameras.value.length} videos found.` : ''
  play(Object.fromEntries(ready.map((c) => [c.cam_id, c.url])))
}

// Event log that follows the video: the take's events up to the playback position.
const allTakeEvents = computed(() => eventsFromTracks(tracks.value,
  Object.fromEntries(cameras.value.map((c) => [c.cam_id, c.offset_s || 0]))))
const takeEvents = computed(() => (hasVideo.value ? allTakeEvents.value.filter((e) => e.t <= position.value + 0.05) : [])
  .map((e) => ({ ...e, time: clockOf(e.t) })))

// Roster status from the cameras, for the demo only (kept in the page, never saved to the database).
const roster = computed(() => {
  if (!recorded.value) { void live.value; return liveRoster(dash.value.roster) }   // re-evaluated on every poll
  return recordedRoster(dash.value.roster, tracks.value,
    Object.fromEntries(cameras.value.map((c) => [c.cam_id, c.offset_s || 0])), position.value, hasVideo.value)
})

// Map trails from presence verification, drawn up to the playback position while a video plays.
const trails = computed(() => {
  if (!recorded.value) return null
  const all = presence.value?.trails ?? []
  // Nothing is drawn until the take plays; Restart and a new take start from an empty map (position 0).
  if (!hasVideo.value) return all.map((tr) => ({ ...tr, points: [] }))
  return all.map((tr) => ({ ...tr, points: tr.points.filter((p) => p[0] <= position.value + 0.05) }))
})

// Playback line: drag to scrub. While dragging, the videos pause and resume on release.
let wasPlaying = false
function scrubStart() { wasPlaying = playing.value; if (wasPlaying) togglePause() }
function scrubEnd() { if (wasPlaying) togglePause() }
const fmtTime = (s) => (Number.isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}` : '–:––')

// ---------------- page ----------------
onMounted(() => {
  fetchDashboard().then((d) => { dash.value = d })
  if (recorded.value) startRecorded()
  else fetchDemoConfig().then((d) => { if (!recorded.value) demo.value = d })
  poll()
})
onBeforeUnmount(() => { alive = false; clearTimeout(timer) })

function faceText(f) {
  if (f.live === false) return 'Spoof detected'
  return f.name ? `Identity verified · ${f.name}${f.held ? ' (held)' : ''}` : 'Unknown face'
}
const capitalise = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s)
</script>

<template>
  <div v-if="!dash || !demo" class="loading">Loading Hawkeye…</div>
  <div v-else class="home">
    <header class="topbar">
      <h1>{{ dash.course.id }} · Room {{ dash.course.room }}
        <span v-if="recorded" class="accent"> · Take {{ selected }}</span></h1>
      <div class="topbar-right">
        <QrButton :url="live?.host_urls?.[0]" />
        <div class="source-switch" role="group" aria-label="Camera source">
          <button class="btn" :class="{ active: !recorded }" :aria-pressed="!recorded" @click="setSource('live')">Live</button>
          <button class="btn" :class="{ active: recorded }" :aria-pressed="recorded" @click="setSource('recorded')">Recorded</button>
          <select v-if="recorded" class="input compact" aria-label="Recorded take" :value="selected"
            @change="choose(Number($event.target.value))">
            <option v-for="t in takes" :key="t.take" :value="t.take">Take {{ t.take }}</option>
          </select>
        </div>
        <div v-if="recorded" class="demo-controls">
          <!-- One button: loads and plays the take the first time, then pauses / resumes it. -->
          <button class="btn primary" @click="hasVideo ? togglePause() : playTake()">
            {{ playing ? '❚❚ Pause' : `▶ Play take ${selected}` }}
          </button>
          <button v-if="hasVideo" class="btn" @click="restart">Restart</button>
        </div>
        <template v-else>
          <span v-if="live?.offline" class="badge">Backend offline</span>
          <span v-else-if="live" class="muted">{{ connected }} of {{ live.cameras.length }} cameras sending</span>
        </template>
      </div>
    </header>

    <div v-if="recorded && message" class="notice"><span>{{ message }}</span></div>
    <div v-if="!recorded" class="notice">
      <span>On a phone or laptop on the <b>same Wi-Fi</b>, open <strong>{{ senderUrl }}</strong> and pick a camera, or press
        <strong>+</strong> on a tile to use this device. Or press <strong>QR</strong> and scan it. First time on a device: see the
        <RouterLink to="/guide/lan">Wi-Fi demo guide</RouterLink>.</span>
    </div>

    <div class="grid-top">
      <CameraCard v-for="cam in cameras" :key="cam.cam_id" :ref="(el) => { cards[cam.cam_id] = el }" :cam="cam"
        :live="!recorded" :stream="recorded ? undefined : streamOf(cam.cam_id)"
        :src="recorded ? srcs[cam.cam_id] : undefined" :tracks="recorded ? takeTracks(cam.cam_id) : null" :show-boxes="recorded"
        :highlight="cam.cam_id === 'attendance_cam'" @remove="removeCam">
        <template v-if="!recorded && liveOf(cam.cam_id)?.connected">
          <ul class="checks">
            <li v-if="cam.cam_id !== 'attendance_cam'" class="ok">{{ peopleOf(cam.cam_id).length === 1 ? '1 person' : `${peopleOf(cam.cam_id).length} people` }} tracked
              <span class="muted">· {{ liveOf(cam.cam_id).fps }} fps</span></li>
            <li v-if="!facesOf(cam.cam_id).length" class="bad">No face in view</li>
            <template v-for="(f, i) in facesOf(cam.cam_id)" :key="i">
              <li :class="f.live !== false && f.name ? 'ok' : 'bad'">
                {{ faceText(f) }}<template v-if="f.live !== false && !f.name"> — <RouterLink to="/add">please register</RouterLink></template>
              </li>
              <li v-if="f.live != null" :class="f.live ? 'ok' : 'bad'">{{ f.live ? 'Liveness passed' : 'Spoof detected' }}</li>
              <li v-if="f.emotion" class="ok">Emotion: {{ capitalise(f.emotion) }}</li>
              <li v-if="'glasses' in f" class="muted">{{ f.glasses ? 'Glasses detected' : 'No glasses detected' }}</li>
            </template>
          </ul>
        </template>
      </CameraCard>
    </div>

    <!-- Recorded: always shown (disabled before Play) so choosing a take does not change the page height. -->
    <div v-if="recorded" class="card timeline" :class="{ off: !hasVideo }">
      <button class="btn" :disabled="!hasVideo" :aria-label="playing ? 'Pause' : 'Play'" @click="togglePause">{{ playing ? '❚❚' : '▶' }}</button>
      <span class="mono">{{ fmtTime(position) }}</span>
      <input type="range" :disabled="!hasVideo" min="0" :max="duration || 0" step="0.05" :value="position" aria-label="Playback position"
        @pointerdown="scrubStart" @pointerup="scrubEnd" @input="seek(Number($event.target.value))" />
      <span class="mono muted">{{ fmtTime(duration) }}</span>
    </div>

    <!-- Event log and room map side by side under the playback line. -->
    <div class="grid-log-map">
      <EventLog v-if="recorded" class="demo-log" :events="takeEvents" :title="`Event log · take ${selected}`" />
      <!-- Live: no live event feed yet, so the log starts blank (dash.events is mock data). -->
      <EventLog v-else :events="[]" />
      <RoomMap :map="dash.map" :room="dash.course.room" :trails="trails" :time="hasVideo ? position : undefined" />
    </div>

    <ClassRoster :roster="roster" />

    <template v-if="recorded">
      <PresencePanel :result="presence" :position="position" :live="hasVideo" />

      <section class="card roster">
        <header class="card-head">
          <h2>Recorded takes</h2>
          <span class="muted">{{ takes.length }} takes · click one, then Play</span>
        </header>
        <table>
          <thead>
            <tr><th>Take</th><th>Length</th><th>Scenario</th><th>Files</th></tr>
          </thead>
          <tbody>
            <tr v-for="t in takes" :key="t.take" class="clickable" :class="{ selected: t.take === selected }" @click="choose(t.take)">
              <td><strong>Take {{ t.take }}</strong></td>
              <td>~{{ t.approx_seconds }} s</td>
              <td>{{ t.scenario }}</td>
              <td class="files">
                <span v-for="c in ORDER" :key="c" class="mono">{{ t.files[c] }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </div>
</template>
