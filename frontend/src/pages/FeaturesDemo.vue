<script setup>
// Live demo of the camera features on this device's webcam.
// Tick the features to use; every ~0.4 s a frame goes to POST /api/features-demo/infer and the result is drawn
// over the video. The models are the ones in ml/<feature>/ (weights <feature>.pt), run by the backend.
// Recognition compares against the registered students: their enrolment photos on the shared Drive, the same
// ones the recorded takes on Home are named from (loaded by the backend on first use).
// Session log: from camera on to camera off, every result is listed in the Session log panel. The
// "Save log" box only decides whether that session is written to logs/*.csv when the camera turns off.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  fetchDemoGallery, fetchFeatureStatus, inferFrame, saveSessionLog,
} from '../api.js'

const FEATURES = [
  { key: 'face_recognition', label: 'Face recognition', hint: 'Who is it? Compared with the registered students (Drive photos).' },
  { key: 'anti_spoofing', label: 'Anti-spoofing', hint: 'Real face or a printed photo / phone screen?' },
  { key: 'emotion', label: 'Emotion', hint: 'Facial expression of each face.' },
  { key: 'glasses_detection', label: 'Glasses detection', hint: 'Check for glasses on each detected face.' },
  { key: 'mask_detection', label: 'Face mask', hint: 'Is each face wearing a face mask? (colour rule, no trained model yet)' },
  { key: 'gesture', label: 'Gesture', hint: 'Hand gesture of each hand (👍 ✌️ ✋ ✊ ☝️ 👌 …).' },
]
const ICONS = { angry: '😠', disgust: '🤢', fear: '😨', happy: '😄', sad: '😢', surprise: '😮', neutral: '😐' }
// Hand skeleton: pairs of MediaPipe hand points joined by a line (0 = wrist; thumb 1-4, index 5-8, middle 9-12, ring 13-16, little 17-20).
const HAND_BONES = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17]]
const HAND_ICONS = { like: '👍', dislike: '👎', peace: '✌️', peace_inverted: '✌️', palm: '✋', stop: '✋', stop_inverted: '✋', fist: '✊',
  one: '☝️', ok: '👌', call: '🤙', rock: '🤘', mute: '🤫', four: '🖐️', three: '🤟', three2: '🤟', two_up: '✌️', two_up_inverted: '✌️', no_gesture: '🖐️' }

const selected = ref({ face_recognition: true, anti_spoofing: true, emotion: true, glasses_detection: false, mask_detection: false, gesture: false })
const status = ref({})             // feature -> { found, code, error, expected_file }
const backendUp = ref(true)
const video = ref(null)
const camOn = ref(false)
const camError = ref('')
const faces = ref([])
const hands = ref([])              // gesture: one { label, score, box } per hand
const errors = ref({})
const latency = ref(null)
const saveLog = ref(false)         // save the session to logs/*.csv when the camera turns off
const sessionRows = ref([])        // log rows of the current / last camera session (kept after the camera is off)
const sessionStart = ref(null)     // Date the camera was turned on
const sessionEnd = ref(null)
const saved = ref(null)            // { ok, text } result of the last save
const toast = ref(null)            // { ok, text }, shown for a few seconds
let toastTimer = null
function showToast(ok, text) {
  toast.value = { ok, text }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = null }, ok ? 4000 : 7000)
}
// Adjustable thresholds. custom = null means "use the model's own (calibrated) value", saved in the weights.
// Face recognition: cosine similarity in [-1, 1]. Anti-spoofing: live score in [0, 1].
function makeThreshold(feature, storageKey, lo, hi, fallback) {
  const custom = ref(null)
  try {
    const saved = parseFloat(localStorage.getItem(storageKey))
    if (Number.isFinite(saved) && saved >= lo && saved <= hi) custom.value = saved
  } catch { /* storage blocked: keep the default */ }
  const def = computed(() => status.value[feature]?.threshold ?? null)
  const shown = computed(() => custom.value ?? def.value ?? fallback)
  function set(v) {
    const n = v == null || v === '' ? NaN : Number(v)
    custom.value = Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : null
    try {
      if (custom.value == null) localStorage.removeItem(storageKey)
      else localStorage.setItem(storageKey, String(custom.value))
    } catch { /* ignore */ }
  }
  return { custom, def, shown, set, lo, hi }
}
const recTh = makeThreshold('face_recognition', 'hawkeye.faceThreshold', -1, 1, 0.5)
const liveTh = makeThreshold('anti_spoofing', 'hawkeye.livenessThreshold', 0, 1, 0.5)
const registered = ref(null)       // null while loading, then { people, skipped, error, drive_root_exists }

const clientId = Math.random().toString(36).slice(2)
let stream = null
let timer = null
let busy = false
let cameraRun = 0        // +1 each time the camera turns on or off: a reply from an earlier run is dropped
let alive = true
const grab = document.createElement('canvas')

const chosen = computed(() => FEATURES.map((f) => f.key).filter((k) => selected.value[k]))

onMounted(async () => {
  await refresh()
})
onMounted(() => window.addEventListener('pagehide', saveOnLeave))
onBeforeUnmount(() => { alive = false; clearTimeout(toastTimer); window.removeEventListener('pagehide', saveOnLeave); stopCamera() })

async function refresh() {
  const s = await fetchFeatureStatus()
  backendUp.value = !s.offline
  status.value = Object.fromEntries((s.features || []).map((f) => [f.feature, f]))
  await loadRegistered(false)
}

// The first load embeds every enrolment photo (some seconds); reload = read the Drive folders again.
async function loadRegistered(reload) {
  registered.value = null
  let r = await fetchDemoGallery(reload)
  registered.value = r
  while (r.loading && alive) {                 // the backend is still embedding photos: ask again
    await new Promise((res) => setTimeout(res, 1500))
    r = await fetchDemoGallery(false)
    registered.value = r
  }
}

function readiness(key) {
  const s = status.value[key]
  if (!s) return { ok: false, text: backendUp.value ? 'unknown' : 'backend offline' }
  if (!s.code) return { ok: false, text: 'code not found' }
  if (!s.found) return { ok: false, text: `weights missing: ${s.expected_file}` }
  return { ok: true, text: '' }
}

// ---- camera ----
async function startCamera() {
  camError.value = ''
  cameraRun++
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false })
    camOn.value = true
    sessionRows.value = []                        // a new session starts
    sessionStart.value = new Date()
    sessionEnd.value = null
    saved.value = null
    await new Promise((r) => setTimeout(r, 0))   // the <video> exists once camOn is true
    video.value.srcObject = stream
    timer = setInterval(tick, 400)
  } catch (e) {
    camError.value = e?.name === 'NotAllowedError' ? 'Camera permission was denied.' : 'Could not open the camera.'
  }
}
async function stopCamera() {
  const wasOn = camOn.value
  cameraRun++                                    // a frame still being analysed must not draw after this
  clearInterval(timer)
  timer = null
  stream?.getTracks().forEach((t) => t.stop())
  stream = null
  camOn.value = false
  faces.value = []
  hands.value = []
  errors.value = {}
  latency.value = null
  if (!wasOn) return
  sessionEnd.value = new Date()
  if (!saveLog.value) { saved.value = { ok: true, text: 'Not saved (the "Save log" box was off).' }; return }
  if (!sessionRows.value.length) { saved.value = { ok: true, text: 'Nothing to save: no frame was analysed.' }; return }
  const r = await saveSessionLog(sessionRows.value, sessionStart.value.toISOString())
  saved.value = r.ok ? { ok: true, text: `Saved ${r.rows} rows to ${r.log_file}` } : { ok: false, text: r.error }
  showToast(r.ok, r.ok ? `Log saved: ${r.log_file} (${r.rows} rows)` : `Log was not saved: ${r.error}`)
}

// The tab is closed or reloaded while the camera is on: send the session once more, it cannot wait for a response.
function saveOnLeave() {
  if (camOn.value && saveLog.value && sessionRows.value.length) {
    const body = JSON.stringify({ started: sessionStart.value.toISOString(), rows: sessionRows.value })
    navigator.sendBeacon('/api/features-demo/log', new Blob([body], { type: 'application/json' }))
  }
}

function frameBlob() {
  const v = video.value
  if (!v || !v.videoWidth) return Promise.resolve(null)
  const w = Math.min(v.videoWidth, 480)
  grab.width = w
  grab.height = Math.round((v.videoHeight * w) / v.videoWidth)
  grab.getContext('2d').drawImage(v, 0, 0, grab.width, grab.height)
  return new Promise((resolve) => grab.toBlob(resolve, 'image/jpeg', 0.85))
}

async function tick() {
  if (busy || !chosen.value.length) return
  busy = true
  const run = cameraRun
  try {
    const blob = await frameBlob()
    if (!blob || run !== cameraRun) return
    const r = await inferFrame(blob, chosen.value, clientId, recTh.custom.value, liveTh.custom.value)
    if (run !== cameraRun) return                // the camera was turned off (or on again) while waiting: drop it
    backendUp.value = !r.offline
    faces.value = r.faces || []
    hands.value = r.hands || []
    errors.value = r.errors || {}
    latency.value = r.ms ?? null
    if (camOn.value && r.log_rows) sessionRows.value.push(...r.log_rows)
  } finally {
    busy = false
  }
}

function toggle(key) {
  selected.value[key] = !selected.value[key]
  if (!chosen.value.length) faces.value = []
  if (!selected.value.gesture) hands.value = []
}

// ---- drawing ----
function boxStyle(f) {
  const [x, y, w, h] = f.box
  return { left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%` }
}
function tone(f) {
  if (f.live === false) return 'bad'
  if (f.live === true) return 'good'
  return 'plain'
}
// Tag on the box: the recognised name ("Unknown" when recognition ran and found nobody) and the emotion,
// e.g. "Manh · 😀 happy". Only emotion ticked: the emotion alone.
function nameTag(f) {
  const emo = f.emotion ? `${ICONS[f.emotion] ?? ''} ${f.emotion}`.trim() : ''
  let tag = null
  if (f.loading) tag = { text: 'Loading…', cls: 'wait' }
  else if ('similarity' in f) tag = f.name ? { text: f.name, cls: 'known' } : { text: 'Unknown', cls: 'unknown' }
  else if ('glasses' in f && !emo) tag = { text: f.glasses ? 'Glasses' : 'No glasses', cls: 'wait' }
  else if ('mask' in f && !emo) tag = { text: f.mask ? 'Mask' : 'No mask', cls: f.mask ? 'unknown' : 'wait' }
  if (!emo) return tag
  return tag ? { ...tag, text: `${tag.text} · ${emo}` } : { text: emo, cls: 'wait' }
}
// ---- session log ----
const LOG_SHOWN = 100
const faceRows = computed(() => sessionRows.value.filter((r) => r.face > 0))
const shownRows = computed(() => faceRows.value.slice(-LOG_SHOWN).reverse())      // newest first
const noFaceFrames = computed(() => sessionRows.value.length - faceRows.value.length)
const clock = (iso) => String(iso).slice(11, 19)
const pct = (v) => (v == null ? '' : ` ${Math.round(v * 100)}%`)

function lines(f) {
  const out = []
  if ('live' in f) {
    const sure = f.liveness_confidence ?? f.liveness_score          // how sure the label is (falls back to the raw score)
    out.push({ cls: f.live ? 'ok' : 'bad', text: `${f.live ? 'Live' : 'Spoof'}${pct(sure)}` })
  }
  if (f.loading) out.push({ cls: 'bad', text: 'Loading registered faces…' })
  else if (f.recognition_skipped) out.push({ cls: 'bad', text: 'Not identified (spoof)' })
  else if ('similarity' in f) {
    if (f.name) out.push({ cls: 'ok', text: `${f.name} (${f.similarity.toFixed(2)})` })
    else out.push({ cls: 'bad', text: f.registered ? `Unknown (${f.similarity.toFixed(2)})` : 'Unknown (nobody registered)' })
  }
  if (f.emotion) out.push({ cls: 'ok', text: `${ICONS[f.emotion] ?? ''} ${f.emotion}${pct(f.emotion_score)}` })
  if ('mask' in f) out.push({ cls: f.mask ? 'bad' : 'ok', text: `${f.mask ? 'Face mask detected' : 'No face mask'} (${f.mask_score.toFixed(2)})` })
  if ('glasses' in f) {
    out.push({ cls: 'muted', text: f.glasses ? 'Glasses detected' : 'No glasses detected' })
    if (f.glasses && f.live !== false && f.registered && !f.name && !f.loading) {
      out.push({ cls: 'muted', text: 'If the lenses reflect light, turn away from the glare and try again.' })
    }
  }
  return out
}
</script>

<template>
  <div class="page">
    <header class="topbar">
      <h1>Features demo</h1>
      <div class="topbar-right">
        <span v-if="latency != null" class="muted">{{ latency }} ms / frame</span>
      </div>
    </header>

    <div class="page-grid fd-grid">
      <div class="side">
        <section class="card panel">
          <header class="card-head"><h2>Camera</h2>
            <button v-if="!camOn" class="btn" @click="startCamera">Turn camera on</button>
            <button v-else class="btn" @click="stopCamera">Turn camera off</button>
          </header>
          <div class="fd-view">
            <video ref="video" autoplay playsinline muted></video>
            <div v-if="!camOn" class="cam-empty clickable" role="button" tabindex="0" title="Turn the camera on"
              @click="startCamera" @keydown.enter.prevent="startCamera" @keydown.space.prevent="startCamera">
              <div>{{ camError || 'Camera is off' }}</div>
              <div class="small">Click here to turn the camera on</div>
            </div>
            <div v-for="(f, i) in faces" :key="i" class="fd-box" :class="tone(f)" :style="boxStyle(f)">
              <span v-if="nameTag(f)" class="fd-name" :class="nameTag(f).cls">{{ nameTag(f).text }}</span>
            </div>
            <svg v-if="hands.length" class="fd-skeleton" viewBox="0 0 4 3" preserveAspectRatio="none">
              <g v-for="(h, i) in hands.filter((h) => h.points)" :key="'s' + i">
                <line v-for="([a, b], j) in HAND_BONES" :key="j" class="bone"
                  :x1="h.points[a][0] * 4" :y1="h.points[a][1] * 3" :x2="h.points[b][0] * 4" :y2="h.points[b][1] * 3" />
                <circle v-for="(p, j) in h.points" :key="'p' + j" class="joint" :cx="p[0] * 4" :cy="p[1] * 3" r="0.022" />
              </g>
            </svg>
            <div v-for="(h, i) in hands" :key="'h' + i" class="fd-box hand" :style="boxStyle(h)">
              <span class="fd-name hand">{{ HAND_ICONS[h.label] ?? '' }} {{ h.label }}</span>
            </div>
          </div>
          <ul v-for="(f, i) in faces" :key="'t' + i" class="checks fd-lines">
            <li v-for="(l, j) in lines(f)" :key="j" :class="l.cls">{{ faces.length > 1 ? `Face ${i + 1}: ` : '' }}{{ l.text }}</li>
          </ul>
          <ul v-if="hands.length" class="checks fd-lines">
            <li v-for="(h, i) in hands" :key="i" class="ok">Hand {{ i + 1 }}: {{ HAND_ICONS[h.label] ?? '' }} {{ h.label }}{{ pct(h.score) }}</li>
          </ul>
          <p v-if="camOn && !faces.length && chosen.some((k) => k !== 'gesture')" class="empty">No face found. Face the camera in good light.</p>
          <p v-if="camOn && !chosen.length" class="empty">Select at least one feature.</p>
          <p v-for="(msg, key) in errors" :key="key" class="error">{{ key }}: {{ msg }}</p>
        </section>

        <section class="card panel">
          <header class="card-head"><h2>Features</h2><span class="muted small">{{ chosen.length }} selected</span></header>
          <label v-for="f in FEATURES" :key="f.key" class="fd-option">
            <input type="checkbox" :checked="selected[f.key]" @change="toggle(f.key)" />
            <span class="grow">
              <strong>{{ f.label }}</strong>
              <small class="muted">{{ f.hint }}</small>
            </span>
            <span v-if="!readiness(f.key).ok" class="tag fd-bad">{{ readiness(f.key).text }}</span>
          </label>
          <div v-if="selected.face_recognition" class="fd-option fd-threshold">
            <span class="grow">
              <strong>Recognition threshold: {{ recTh.shown.value.toFixed(2) }}
                <span class="muted small">{{ recTh.custom.value == null ? '(model default)' : '(custom)' }}</span></strong>
              <small class="muted">A face is named only when its similarity is at least this. Higher = stricter (fewer wrong names, more
                "Unknown"); lower = more lenient (more wrong names). Mixed enrolment uses a minimum of 0.74 for faces with glasses.
                <template v-if="recTh.def.value != null">Model default: {{ recTh.def.value.toFixed(2) }}.</template></small>
              <span class="fd-slider">
                <input type="range" :min="recTh.lo" :max="recTh.hi" step="0.01" :value="recTh.shown.value" @input="recTh.set($event.target.value)" />
                <input type="number" :min="recTh.lo" :max="recTh.hi" step="0.01" :value="recTh.shown.value.toFixed(2)" @change="recTh.set($event.target.value)" />
                <button class="btn" type="button" :disabled="recTh.custom.value == null" @click="recTh.set(null)">Reset</button>
              </span>
            </span>
          </div>
          <div v-if="selected.anti_spoofing" class="fd-option fd-threshold">
            <span class="grow">
              <strong>Liveness threshold: {{ liveTh.shown.value.toFixed(3) }}
                <span class="muted small">{{ liveTh.custom.value == null ? '(model default)' : '(custom)' }}</span></strong>
              <small class="muted">A face counts as live only when its live score is at least this. Higher = stricter (fewer spoofs accepted,
                more real faces rejected); lower = more lenient (printed photos and screens may pass).
                <template v-if="liveTh.def.value != null">Model default: {{ liveTh.def.value.toFixed(3) }}.</template></small>
              <span class="fd-slider">
                <input type="range" :min="liveTh.lo" :max="liveTh.hi" step="0.001" :value="liveTh.shown.value" @input="liveTh.set($event.target.value)" />
                <input type="number" :min="liveTh.lo" :max="liveTh.hi" step="0.001" :value="liveTh.shown.value.toFixed(3)" @change="liveTh.set($event.target.value)" />
                <button class="btn" type="button" :disabled="liveTh.custom.value == null" @click="liveTh.set(null)">Reset</button>
              </span>
            </span>
          </div>
          <label class="fd-option">
            <input type="checkbox" v-model="saveLog" />
            <span class="grow">
              <strong>Save log (CSV)</strong>
              <small class="muted">The session log on the right is always shown. When this is ticked, it is also saved when the camera turns off, to
                <span class="mono">logs/</span> in the repo folder.</small>
            </span>
          </label>
        </section>
      </div>

      <div class="side">
        <section class="card panel">
          <header class="card-head"><h2>Session log</h2>
            <span class="muted small">
              <template v-if="camOn">camera on since {{ clock(sessionStart.toISOString()) }} · </template>
              {{ sessionRows.length }} frame{{ sessionRows.length === 1 ? '' : 's' }}
              <template v-if="noFaceFrames"> ({{ noFaceFrames }} without a face)</template>
            </span>
          </header>
          <p v-if="saved" :class="saved.ok ? 'muted' : 'error'" class="small">{{ saved.text }}</p>
          <p v-else-if="camOn" class="muted small">{{ saveLog ? 'This session will be saved to logs/ when the camera turns off.' : 'This session will not be saved. Tick "Save log" to keep it.' }}</p>
          <div class="fd-log">
            <table v-if="shownRows.length">
              <thead><tr><th>Time</th><th>Face</th><th>Name</th><th>Similarity</th><th>Threshold</th><th>Liveness</th><th>Live thr.</th><th>Emotion</th></tr></thead>
              <tbody>
                <tr v-for="(r, i) in shownRows" :key="i">
                  <td class="mono">{{ clock(r.time) }}</td>
                  <td>{{ r.face }}</td>
                  <td>{{ r.name || (r.similarity === '' ? '' : 'Unknown') }}</td>
                  <td>{{ r.similarity }}</td>
                  <td>{{ r.threshold }}</td>
                  <td :class="r.live === false ? 'error' : ''">{{ r.live === '' ? '' : (r.live ? 'Live' : 'Spoof') }} {{ r.liveness_score }}</td>
                  <td>{{ r.liveness_threshold }}</td>
                  <td>{{ r.emotion }} {{ r.emotion_score }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="empty">{{ camOn ? 'Waiting for a face…' : 'Turn the camera on to start a session.' }}</p>
        </div>
      <p v-if="faceRows.length > LOG_SHOWN" class="muted small">Showing the latest {{ LOG_SHOWN }} of {{ faceRows.length }} lines.</p>
        </section>

        <section v-if="selected.face_recognition" class="card panel">
          <header class="card-head"><h2>Registered students</h2>
            <button class="btn" type="button" :disabled="!registered" @click="loadRegistered(true)">Reload</button>
          </header>
          <p v-if="!registered" class="empty">Loading the registered faces…</p>
          <p v-else-if="registered.loading" class="empty">Preparing the registered faces… (first time only, then it is cached)</p>
          <template v-else>
            <p v-if="registered.error" class="error small">{{ registered.error }}</p>
            <p v-else-if="!registered.drive_root_exists" class="error small">The photo folder was not found. Put AppliedML/ in the repo folder, or set HAWKEYE_VIDEO_ROOT in backend/.env.</p>
            <ul class="fd-people">
              <li v-for="p in registered.people" :key="p.student_id">
                <span class="grow">{{ p.name }}
                  <span v-if="p.glasses_photos != null" class="muted small">· {{ p.glasses_photos }} with glasses, {{ p.no_glasses_photos }} without</span>
                  <span v-else class="muted small">· {{ p.folder_photos }} photo{{ p.folder_photos === 1 ? '' : 's' }}</span>
                </span>
              </li>
              <li v-if="!registered.people.length" class="empty">No registered face could be loaded.</li>
            </ul>
            <p class="muted small">Photos counted in each member's folder on the Drive; the same ones the recorded takes on Home are named from (plus the student card).
              <span v-if="registered.skipped.length">{{ registered.skipped.length }} photo(s) had no detectable face and are not used for matching.</span></p>
          </template>
        </section>
      </div>
    </div>

    <Transition name="fd-toast">
      <div v-if="toast" class="fd-toast" :class="toast.ok ? 'ok' : 'bad'" role="status" aria-live="polite" @click="toast = null">
        <strong>{{ toast.ok ? '✓' : '!' }}</strong> {{ toast.text }}
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.fd-grid { grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr); }
.fd-view { position: relative; aspect-ratio: 4 / 3; background: #1d1d1d; border-radius: 8px; overflow: hidden; }
.fd-view video { width: 100%; height: 100%; object-fit: cover; display: block; }
.fd-box { position: absolute; border: 3px solid #fff; border-radius: 6px; pointer-events: none; }
.fd-box.good { border-color: var(--green); }
.fd-box.bad { border-color: var(--danger); }
.fd-name { position: absolute; left: -3px; bottom: -3px; max-width: calc(100% + 6px); padding: 3px 9px; border-radius: 0 6px 0 4px;
  font-size: 14px; font-weight: 600; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fd-name.known { background: var(--green); }
.fd-name.unknown { background: var(--danger); }
.fd-name.wait { background: var(--muted); }
.fd-box.hand { border-color: transparent; }
.fd-name.hand { background: #f0a020; top: -32px; bottom: auto; border-radius: 4px; }
.fd-skeleton { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.fd-skeleton .bone { stroke: #f0a020; stroke-width: 3; stroke-linecap: round; vector-effect: non-scaling-stroke; }
.fd-skeleton .joint { fill: #fff; stroke: #f0a020; stroke-width: 1.5; vector-effect: non-scaling-stroke; }
.fd-lines { padding: 0; margin: 10px 0 0; }
.fd-log { max-height: 340px; overflow: auto; }
.fd-log table { width: 100%; border-collapse: collapse; font-size: 13px; }
.fd-log th { text-align: left; color: var(--muted); font-weight: 500; position: sticky; top: 0; background: var(--card); }
.fd-log th, .fd-log td { padding: 6px 12px 6px 0; border-bottom: 1px solid var(--line); white-space: nowrap; }
.fd-option { display: flex; gap: 12px; align-items: flex-start; padding: 10px 0; border-bottom: 1px solid var(--line); cursor: pointer; }
.fd-option:last-child { border-bottom: 0; }
.fd-option .grow { display: flex; flex-direction: column; gap: 2px; }
.fd-option input { margin-top: 4px; width: 16px; height: 16px; }
.fd-threshold { cursor: default; }
.fd-slider { display: flex; gap: 8px; align-items: center; margin-top: 6px; }
.fd-slider input[type=range] { flex: 1; }
.fd-slider input[type=number] { width: 72px; }
.fd-bad { background: var(--danger-soft); color: var(--danger); }
.fd-people { list-style: none; margin: 0; padding: 0; }
.fd-people li { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-top: 1px solid var(--line); }
.fd-toast { position: fixed; right: 24px; bottom: 24px; z-index: 50; max-width: min(420px, calc(100vw - 48px)); padding: 12px 16px;
  border-radius: 10px; color: #fff; font-size: 14px; box-shadow: 0 6px 20px rgba(0,0,0,.22); cursor: pointer; word-break: break-word; }
.fd-toast.ok { background: var(--green); }
.fd-toast.bad { background: var(--danger); }
.fd-toast strong { margin-right: 6px; }
.fd-toast-enter-active, .fd-toast-leave-active { transition: opacity .25s ease, transform .25s ease; }
.fd-toast-enter-from, .fd-toast-leave-to { opacity: 0; transform: translateY(12px); }
</style>
