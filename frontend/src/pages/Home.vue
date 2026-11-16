<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { fetchDashboard, fetchDemoConfig, fetchTracks } from '../api.js'
import CameraCard from '../components/CameraCard.vue'
import EventLog from '../components/EventLog.vue'
import ClassRoster from '../components/ClassRoster.vue'
import RoomMap from '../components/RoomMap.vue'

const ORDER = ['cam_1', 'cam_2', 'attendance_cam']

const dash = ref(null)
const demo = ref(null)
const tracks = ref({})
const srcs = ref({})
const playing = ref(false)
const showBoxes = ref(true)
const message = ref('')
const fileInput = ref(null)

const cards = {}                                   // cam_id -> CameraCard instance
const videoOf = (camId) => cards[camId]?.video     // the <video> element of that camera

const cameras = computed(() => (demo.value ? ORDER.map((id) => demo.value.cameras.find((c) => c.cam_id === id)).filter(Boolean) : []))
const hasVideo = computed(() => Object.keys(srcs.value).length > 0)
const st = computed(() => dash.value.attendance_cam_status)

// ---- clock ----
const now = ref(new Date())
const clock = computed(() => {
  const hh = String(now.value.getHours()).padStart(2, '0'), mm = String(now.value.getMinutes()).padStart(2, '0')
  return `${hh}:${mm} · ${now.value.toLocaleDateString('en-GB')}`
})
let clockTimer, syncTimer

onMounted(() => {
  clockTimer = setInterval(() => { now.value = new Date() }, 1000)
  fetchDashboard().then((d) => { dash.value = d })
  fetchDemoConfig().then((d) => { demo.value = d })
  Promise.all(ORDER.map(fetchTracks)).then((list) => { tracks.value = Object.fromEntries(ORDER.map((c, i) => [c, list[i]])) })
})
onBeforeUnmount(() => { clearInterval(clockTimer); clearInterval(syncTimer) })

// Keep the three videos in step: follow CAM 1 (or the first loaded one), correct drift > 0.3 s.
function syncVideos() {
  const cams = cameras.value.filter((c) => srcs.value[c.cam_id] && videoOf(c.cam_id))
  if (cams.length < 2) return
  const lead = cams[0], lv = videoOf(lead.cam_id)
  const base = lv.currentTime - (lead.offset_s || 0)
  for (const c of cams.slice(1)) {
    const v = videoOf(c.cam_id)
    const want = base + (c.offset_s || 0)
    if (Math.abs(v.currentTime - want) > 0.3 && want < (v.duration || Infinity)) v.currentTime = want
  }
  if (cams.every((c) => videoOf(c.cam_id).ended)) playing.value = false
}
watch(playing, (on) => {
  clearInterval(syncTimer)
  if (on) syncTimer = setInterval(syncVideos, 500)
})

async function startAll(sources) {
  await nextTick()   // let the new video sources reach the page
  // wait until every loaded video knows its length, then start together
  await Promise.all(cameras.value.filter((c) => sources[c.cam_id]).map((c) => new Promise((resolve) => {
    const v = videoOf(c.cam_id)
    if (v.readyState >= 1) return resolve()
    v.addEventListener('loadedmetadata', resolve, { once: true })
    v.addEventListener('error', resolve, { once: true })
  })))
  for (const c of cameras.value) {
    const v = videoOf(c.cam_id)
    if (!sources[c.cam_id] || !v) continue
    v.currentTime = c.offset_s || 0
    v.play().catch(() => {})
  }
  playing.value = true
}

function runDemo() {
  const ready = cameras.value.filter((c) => c.available)
  if (!ready.length) {
    message.value = demo.value.offline
      ? 'Backend is not running, so videos cannot stream. Start uvicorn, or use "Load from computer".'
      : 'Backend cannot find the videos. Set HAWKEYE_VIDEO_ROOT in backend/.env, or use "Load from computer".'
    return
  }
  message.value = ready.length < cameras.value.length ? `Only ${ready.length} of ${cameras.value.length} videos found.` : `Playing take ${demo.value.take}.`
  srcs.value = Object.fromEntries(ready.map((c) => [c.cam_id, c.url]))
  startAll(srcs.value)
}

// Match picked files to cameras by the stream ID at the start of the filename (e.g. sCi8Jvd_....webm)
function loadLocal(e) {
  const files = [...e.target.files]
  const next = {}
  for (const c of cameras.value) {
    const f = files.find((file) => file.name.startsWith(c.stream_id)) || files.find((file) => file.name.includes(c.cam_id))
    if (f) next[c.cam_id] = URL.createObjectURL(f)
  }
  const n = Object.keys(next).length
  message.value = n ? `Loaded ${n} of ${cameras.value.length} cameras from your computer.` : 'No file matched a camera stream ID (sCi8Jvd, pDHjQPf, 2SiEwN8).'
  srcs.value = next
  startAll(next)
  e.target.value = ''
}

function togglePause() {
  const vs = cameras.value.map((c) => videoOf(c.cam_id)).filter((v) => v && v.src)
  if (playing.value) { vs.forEach((v) => v.pause()); playing.value = false }
  else { vs.forEach((v) => v.play().catch(() => {})); playing.value = true }
}

const restart = () => startAll(srcs.value)
const capitalise = (s) => s[0].toUpperCase() + s.slice(1)
</script>

<template>
  <div v-if="!dash || !demo" class="loading">Loading Hawkeye…</div>
  <div v-else class="home">
    <header class="topbar">
      <h1>{{ dash.course.id }} · Room {{ dash.course.room }}</h1>
      <div class="topbar-right">
        <div class="demo-controls">
          <button class="btn primary" @click="runDemo">▶ Run demo videos</button>
          <button class="btn" @click="fileInput.click()">Load from computer</button>
          <input ref="fileInput" type="file" accept="video/*" multiple hidden @change="loadLocal" />
          <button v-if="hasVideo" class="btn" @click="togglePause">{{ playing ? 'Pause' : 'Play' }}</button>
          <button v-if="hasVideo" class="btn" @click="restart">Restart</button>
          <label class="toggle"><input v-model="showBoxes" type="checkbox" /> Boxes</label>
        </div>
        <div class="clock">Time: {{ clock }}</div>
      </div>
    </header>

    <div v-if="dash.offline || message" class="notice">
      <span v-if="dash.offline" class="badge">offline · mock data</span>
      <span v-if="message">{{ message }}</span>
    </div>

    <div class="grid-top">
      <CameraCard v-for="cam in cameras" :key="cam.cam_id" :ref="(el) => { cards[cam.cam_id] = el }"
        :cam="cam" :src="srcs[cam.cam_id]" :tracks="tracks[cam.cam_id]" :show-boxes="showBoxes"
        :highlight="cam.cam_id === 'attendance_cam'">
        <!-- TODO: live values from liveness.py / recognizer.py / emotion.py (currently mock) -->
        <ul v-if="cam.cam_id === 'attendance_cam'" class="checks">
          <li :class="st.identity_verified ? 'ok' : 'bad'">{{ st.identity_verified ? `Identity verified · ${st.name}` : 'Unknown — please register' }}</li>
          <li :class="st.liveness === 'live' ? 'ok' : 'bad'">{{ st.liveness === 'live' ? 'Liveness passed' : 'Spoof detected' }}</li>
          <li class="ok">Emotion: {{ capitalise(st.emotion) }}</li>
        </ul>
      </CameraCard>
      <EventLog :events="dash.events" />
    </div>

    <div class="grid-bottom">
      <ClassRoster :roster="dash.roster" />
      <RoomMap :map="dash.map" :room="dash.course.room" />
    </div>
  </div>
</template>
