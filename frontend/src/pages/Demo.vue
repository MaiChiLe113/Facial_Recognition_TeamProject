<script setup>
// Choose one of the recorded takes and play its three clips in sync.
// TODO (Đức Mạnh + Mai Chi): run the take through the pipeline on the backend; for now the backend
// streams only the take selected in data/video_config.json, other takes play from local files.
import { computed, onMounted, ref } from 'vue'
import { demoTakes, fetchDemoConfig, fetchTracks } from '../api.js'
import CameraCard from '../components/CameraCard.vue'
import { useSyncedPlayback } from '../composables/useSyncedPlayback.js'

const ORDER = ['cam_1', 'cam_2', 'attendance_cam']

const demo = ref(null)
const tracks = ref({})
const { take: servedTake, takes } = demoTakes()
const selected = ref(servedTake)
const showBoxes = ref(true)
const message = ref('')
const fileInput = ref(null)

const cards = {}
const videoOf = (camId) => cards[camId]?.video
const cameras = computed(() => (demo.value ? ORDER.map((id) => demo.value.cameras.find((c) => c.cam_id === id)).filter(Boolean) : []))
const { srcs, playing, play, togglePause, restart, stop } = useSyncedPlayback(cameras, videoOf)

onMounted(() => {
  fetchDemoConfig().then((d) => { demo.value = d })
  Promise.all(ORDER.map(fetchTracks)).then((list) => { tracks.value = Object.fromEntries(ORDER.map((c, i) => [c, list[i]])) })
})

const take = computed(() => takes.find((t) => t.take === selected.value))
const streamable = computed(() => demo.value && !demo.value.offline && selected.value === servedTake
  && cameras.value.some((c) => c.available))
// The precomputed boxes belong to the served take only.
const takeTracks = (camId) => (selected.value === servedTake ? tracks.value[camId] : null)
const hasVideo = computed(() => Object.keys(srcs.value).length > 0)

function choose(n) {
  if (n === selected.value) return
  stop()
  selected.value = n
  message.value = ''
}

function playTake() {
  if (!streamable.value) {
    message.value = demo.value?.offline
      ? 'The backend is not running. Use "Load from computer" and pick this take\'s three files.'
      : `The backend streams take ${servedTake} only. Load take ${selected.value}'s files from your computer.`
    return
  }
  const ready = cameras.value.filter((c) => c.available)
  message.value = ready.length < cameras.value.length ? `Only ${ready.length} of ${cameras.value.length} videos found.` : `Playing take ${selected.value}.`
  play(Object.fromEntries(ready.map((c) => [c.cam_id, c.url])))
}

// Match the picked files to this take: exact filename first, then the camera's stream ID.
function loadLocal(e) {
  const files = [...e.target.files]
  const next = {}
  for (const c of cameras.value) {
    const want = take.value?.files[c.cam_id]
    const f = files.find((file) => file.name === want) || files.find((file) => file.name.startsWith(c.stream_id))
    if (f) next[c.cam_id] = URL.createObjectURL(f)
  }
  const n = Object.keys(next).length
  message.value = n ? `Loaded ${n} of ${cameras.value.length} cameras for take ${selected.value}.` : 'No file matched this take.'
  if (n) play(next)
  e.target.value = ''
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
          <button class="btn" @click="fileInput.click()">Load from computer</button>
          <input ref="fileInput" type="file" accept="video/*" multiple hidden @change="loadLocal" />
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
        <span class="muted">{{ takes.length }} takes · backend streams take {{ servedTake }}</span>
      </header>
      <table>
        <thead>
          <tr><th>Take</th><th>Length</th><th>Scenario</th><th>Files</th><th>Source</th></tr>
        </thead>
        <tbody>
          <tr v-for="t in takes" :key="t.take" class="clickable" :class="{ selected: t.take === selected }" @click="choose(t.take)">
            <td><strong>Take {{ t.take }}</strong></td>
            <td>~{{ t.approx_seconds }} s</td>
            <td>{{ t.scenario }}</td>
            <td class="files">
              <span v-for="c in ORDER" :key="c" class="mono">{{ t.files[c] }}</span>
            </td>
            <td>
              <span v-if="t.take === servedTake" class="yesno yes">backend + boxes</span>
              <span v-else class="muted">local files</span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>
