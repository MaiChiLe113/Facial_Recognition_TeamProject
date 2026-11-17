<script setup>
// Choose one of the recorded takes and play its three clips in sync.
// The backend streams every take (?take=N) with its precomputed boxes (data/tracks/take<N>/).
// TODO (Đức Mạnh + Mai Chi): run the take through the live pipeline on the backend.
import { computed, onMounted, ref } from 'vue'
import { demoTakes, fetchDemoConfig, fetchTracks } from '../api.js'
import CameraCard from '../components/CameraCard.vue'
import { useSyncedPlayback } from '../composables/useSyncedPlayback.js'

const ORDER = ['cam_1', 'cam_2', 'attendance_cam']

const demo = ref(null)
const tracks = ref({})
const { take: defaultTake, takes } = demoTakes()
const selected = ref(defaultTake)
const showBoxes = ref(true)
const message = ref('')

const cards = {}
const videoOf = (camId) => cards[camId]?.video
const cameras = computed(() => (demo.value ? ORDER.map((id) => demo.value.cameras.find((c) => c.cam_id === id)).filter(Boolean) : []))
const { srcs, playing, play, togglePause, restart, stop } = useSyncedPlayback(cameras, videoOf)

// Camera list + video URLs and the boxes for one take. Ignores answers for a take that is no longer selected.
function loadTake(n) {
  fetchDemoConfig(n).then((d) => { if (selected.value === n) demo.value = d })
  tracks.value = {}
  Promise.all(ORDER.map((c) => fetchTracks(c, n))).then((list) => {
    if (selected.value === n) tracks.value = Object.fromEntries(ORDER.map((c, i) => [c, list[i]]))
  })
}

onMounted(() => loadTake(selected.value))

const streamable = computed(() => demo.value && !demo.value.offline && demo.value.take === selected.value
  && cameras.value.some((c) => c.available))
const takeTracks = (camId) => tracks.value[camId] ?? null
const hasVideo = computed(() => Object.keys(srcs.value).length > 0)

function choose(n) {
  if (n === selected.value) return
  stop()
  selected.value = n
  message.value = ''
  loadTake(n)
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
  message.value = ready.length < cameras.value.length ? `Only ${ready.length} of ${cameras.value.length} videos found.` : `Playing take ${selected.value}.`
  play(Object.fromEntries(ready.map((c) => [c.cam_id, c.url])))
}
</script>

<template>
  <div v-if="!demo" class="loading">Loading demo…</div>
  <div v-else class="page">
    <header class="topbar">
      <h1>Demo · Take {{ selected }}</h1>
      <div class="topbar-right">
        <div class="demo-controls">
          <button class="btn primary" @click="playTake">▶ Play take {{ selected }}</button>
          <button v-if="hasVideo" class="btn" @click="togglePause">{{ playing ? 'Pause' : 'Play' }}</button>
          <button v-if="hasVideo" class="btn" @click="restart">Restart</button>
          <label class="toggle"><input v-model="showBoxes" type="checkbox" /> Boxes</label>
        </div>
      </div>
    </header>

    <div v-if="demo.offline || message" class="notice">
      <span v-if="demo.offline" class="badge">offline · mock data</span>
      <span v-if="message">{{ message }}</span>
    </div>

    <div class="demo-grid">
      <CameraCard v-for="cam in cameras" :key="cam.cam_id" :ref="(el) => { cards[cam.cam_id] = el }"
        :cam="cam" :src="srcs[cam.cam_id]" :tracks="takeTracks(cam.cam_id)" :show-boxes="showBoxes"
        :highlight="cam.cam_id === 'attendance_cam'" />
    </div>

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
  </div>
</template>
