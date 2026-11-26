<script setup>
// AI face scan (Đức Mạnh's innovative feature): replaces uploading face photos on Add person.
// Live scan: the camera preview is sent ~4 times a second (downscaled) to POST /api/enrol/frame; the backend answers
// with the face box, head pose, quality and a hint. When a frame fits a missing pose slot and passes, the full-resolution
// frame is sent again with final=true and kept. Upload video: the backend samples the video and does the same.
// Emits 'update' with the scan summary (session_id, missing, done, slots) so the form can submit enrol_session.
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { discardScan, failScan, fetchScan, scanStillUrl, sendScanFrame, startScan, uploadScanVideo } from '../api.js'

const emit = defineEmits(['update'])
const SLOT_LABEL = { front: 'Straight', left: 'Turn left', right: 'Turn right', up: 'Chin up', down: 'Chin down' }
// No overall time limit: an attempt fails when no new photo is kept for ATTEMPT_S seconds (no face, too dark, not live…).
// The scan retries automatically; after MAX_ATTEMPTS failed attempts it stops and the backend logs the failure.
const PREVIEW_W = 640, PREVIEW_MS = 250, ATTEMPT_S = 10, MAX_ATTEMPTS = 3

const mode = ref('live')              // 'live' | 'video'
const summary = ref(null)
const last = ref(null)                // last frame analysis
const error = ref('')
const running = ref(false)
const busy = ref(false)
const elapsed = ref(0)
const videoEl = ref(null)
const fileInput = ref(null)
const camInfo = ref('')
const failedAttempts = ref(0)
const failed = ref(null)              // { reason, attempts } once the scan gave up
let stream = null, timer = null, inFlight = false, attemptStart = 0, keptAtStart = 0, reasonCounts = {}

const sid = computed(() => summary.value?.session_id)
const kept = computed(() => (summary.value ? Object.values(summary.value.slots).reduce((n, v) => n + v.length, 0) : 0))
const total = computed(() => (summary.value ? Object.keys(summary.value.slots).length * summary.value.per_slot : 15))

async function ensureSession(source) {
  if (summary.value && summary.value.source === source) return true
  if (sid.value) discardScan(sid.value)
  const s = await startScan(source)
  if (s.error) { error.value = s.error; return false }
  setSummary(s)
  return true
}
function setSummary(s) { summary.value = s; emit('update', s) }

// ---- live --------------------------------------------------------------------------------------
async function startLive() {
  error.value = ''
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    error.value = 'The camera needs HTTPS (or localhost). On a phone, open the app through the Wi-Fi demo link (docs/LAN_DEMO.md).'
    return
  }
  if (failed.value) await restart()
  if (!(await ensureSession('live'))) return
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 3840 }, height: { ideal: 2160 } }, audio: false })
  } catch (e) {
    error.value = `Camera not available (${e.name || e}). Allow camera access, or upload a video instead.`
    return
  }
  running.value = true
  await nextTick()
  videoEl.value.srcObject = stream
  await videoEl.value.play().catch(() => {})
  const s = stream.getVideoTracks()[0].getSettings()
  camInfo.value = s.width ? `${s.width}×${s.height}` : ''
  newAttempt()
  timer = setInterval(tick, PREVIEW_MS)
}

function stopLive() {
  clearInterval(timer); timer = null
  stream?.getTracks().forEach((t) => t.stop()); stream = null
  running.value = false
}

function grab(maxW) {
  const v = videoEl.value
  if (!v?.videoWidth) return null
  const scale = maxW ? Math.min(1, maxW / v.videoWidth) : 1
  const c = document.createElement('canvas')
  c.width = Math.round(v.videoWidth * scale); c.height = Math.round(v.videoHeight * scale)
  c.getContext('2d').drawImage(v, 0, 0, c.width, c.height)
  return new Promise((res) => c.toBlob(res, 'image/jpeg', maxW ? 0.8 : 0.95))
}

function newAttempt() { attemptStart = Date.now(); keptAtStart = kept.value; reasonCounts = {} }

async function attemptFailed() {
  const top = Object.entries(reasonCounts).filter(([k]) => k !== 'ok').sort((a, b) => b[1] - a[1])[0]
  const reason = top ? top[0] : 'no_progress'
  failedAttempts.value += 1
  if (failedAttempts.value < MAX_ATTEMPTS) {
    error.value = `Attempt ${failedAttempts.value} of ${MAX_ATTEMPTS} failed (${REASON_TEXT[reason] ?? reason}). Retrying…`
    newAttempt()
    return
  }
  stopLive()
  failed.value = { reason, attempts: failedAttempts.value }
  error.value = `Scan failed after ${MAX_ATTEMPTS} attempts: ${REASON_TEXT[reason] ?? reason}. Fix it and press Start again, or upload a video.`
  const r = await failScan(sid.value, reason, failedAttempts.value, reasonCounts)
  if (!r.error) setSummary(r)
}

async function tick() {
  if (summary.value?.done) { stopLive(); return }
  if (kept.value > keptAtStart) { newAttempt(); if (error.value.startsWith('Attempt')) error.value = '' }
  elapsed.value = Math.round((Date.now() - attemptStart) / 1000)
  if (elapsed.value >= ATTEMPT_S) { await attemptFailed(); return }
  if (inFlight) return
  inFlight = true
  try {
    const blob = await grab(PREVIEW_W)
    if (!blob) return
    const r = await sendScanFrame(sid.value, blob)
    if (r.error) { error.value = r.error; if (r.status === 404) stopLive(); return }
    last.value = r
    if (r.reason) reasonCounts[r.reason] = (reasonCounts[r.reason] || 0) + 1
    if (r.accepted && summary.value.missing.includes(r.slot)) {
      const full = await grab(0)                       // the full-resolution still for the gallery
      const k = full && (await sendScanFrame(sid.value, full, true))
      if (k && !k.error) last.value = { ...k, stillRejected: !k.kept }
    }
    const s = await fetchScan(sid.value)
    if (!s.error) setSummary(s)
  } finally {
    inFlight = false
  }
}

// ---- video -------------------------------------------------------------------------------------
async function onVideo(e) {
  const file = e.target.files[0]
  e.target.value = ''
  if (!file) return
  error.value = ''
  if (!(await ensureSession('video'))) return
  busy.value = true
  const r = await uploadScanVideo(sid.value, file)
  busy.value = false
  if (r.error) { error.value = r.error; return }
  setSummary(r)
  last.value = { hint: r.done ? 'done' : `missing: ${r.missing.map((m) => SLOT_LABEL[m]).join(', ')}`, reasons: r.frame_reasons }
}

async function restart() {
  stopLive()
  if (sid.value) discardScan(sid.value)
  summary.value = null; last.value = null; error.value = ''; failed.value = null; failedAttempts.value = 0
  emit('update', null)
}
function switchMode(m) { if (m !== mode.value) { restart(); mode.value = m } }

defineExpose({ restart })
onBeforeUnmount(() => { stopLive() })

const boxStyle = computed(() => {
  const b = last.value?.box
  if (!b || !running.value) return null
  return { left: `${(1 - b[0] - b[2]) * 100}%`, top: `${b[1] * 100}%`, width: `${b[2] * 100}%`, height: `${b[3] * 100}%` }  // preview is mirrored
})
// Meter state: green = this frame is being kept, amber = quality passes but another check fails, red = quality too low
const meterState = computed(() => {
  const r = last.value
  if (!r || r.quality == null) return 'low'
  if (r.accepted && !r.stillRejected && (r.kept || summary.value?.missing.includes(r.slot))) return 'good'
  return r.quality >= (summary.value?.threshold ?? 1) ? 'warn' : 'low'
})
const meterReason = computed(() => {
  const r = last.value
  if (!r || r.quality == null) return ''
  if (meterState.value === 'good') return 'kept'
  if (r.accepted && r.stillRejected) return 'still rejected (moved?)'
  if (r.accepted) return r.kept === false && r.slot && summary.value?.missing.includes(r.slot) ? 'same view' : `${SLOT_LABEL[r.slot] ?? r.slot} slot full`
  return REASON_TEXT[r.reason] ?? r.reason
})
const REASON_TEXT = { ok: 'kept', no_face: 'no face', several_faces: 'several faces', too_small: 'too far',
  too_dark: 'too dark', too_bright: 'too bright', not_live: 'not live', between_poses: 'between poses', low_quality: 'low quality', no_progress: 'no new photo' }
</script>

<template>
  <div class="scan">
    <div class="source-switch scan-tabs" role="tablist">
      <button type="button" class="btn" :class="{ active: mode === 'live' }" @click="switchMode('live')">Live scan</button>
      <button type="button" class="btn" :class="{ active: mode === 'video' }" @click="switchMode('video')">Upload video</button>
    </div>

    <div v-if="mode === 'live'" class="scan-live">
      <div v-if="running" class="scan-view">
        <video ref="videoEl" autoplay muted playsinline />
        <div v-if="boxStyle" class="scan-box" :class="last?.accepted ? 'good' : 'bad'" :style="boxStyle" />
        <div class="scan-hint">{{ last?.hint ?? 'Look at the camera' }}</div>
        <div class="scan-meter" :title="`quality ${last?.quality ?? '—'} / threshold ${summary?.threshold}`">
          <span :style="{ width: `${Math.round((last?.quality ?? 0) * 100)}%` }" :class="meterState" />
          <i :style="{ left: `${(summary?.threshold ?? 0) * 100}%` }" />
          <em v-if="meterReason" class="scan-reason" :class="meterState">{{ meterReason }}</em>
        </div>
      </div>
      <div class="drop-actions">
        <button v-if="!running" class="btn primary" type="button" @click="startLive">{{ failed ? 'Start again' : summary ? 'Continue scan' : 'Start face scan' }}</button>
        <button v-else class="btn" type="button" @click="stopLive">Pause</button>
        <span v-if="running" class="muted small">attempt {{ failedAttempts + 1 }}/{{ MAX_ATTEMPTS }} · {{ elapsed }} / {{ ATTEMPT_S }} s without a new photo<template v-if="camInfo"> · camera {{ camInfo }}</template></span>
      </div>
    </div>

    <div v-else class="scan-video">
      <p class="muted small">Film the face slowly for about 15 s: straight, left, right, chin up, chin down. Good light,
        1080p or 4K, one person only. MP4, WebM or MOV, up to 60 s.</p>
      <div class="drop-actions">
        <button class="btn primary" type="button" :disabled="busy" @click="fileInput.click()">{{ busy ? 'Analysing video…' : 'Choose video' }}</button>
      </div>
      <input ref="fileInput" type="file" accept="video/*,.mov,.mp4,.webm" hidden @change="onVideo" />
      <p v-if="last?.reasons" class="muted small">Frames: <span v-for="(n, k) in last.reasons" :key="k">{{ REASON_TEXT[k] ?? k }} {{ n }} · </span></p>
      <p v-if="last?.hint" class="small">{{ last.hint }}</p>
    </div>

    <small v-if="error" class="error">{{ error }}</small>

    <div v-if="summary" class="scan-slots">
      <div v-for="(items, slot) in summary.slots" :key="slot" class="scan-slot" :class="{ full: items.length >= summary.per_slot }">
        <strong>{{ SLOT_LABEL[slot] }}</strong> <span class="muted small">{{ items.length }}/{{ summary.per_slot }}</span>
        <div class="thumbs">
          <figure v-for="(e, i) in items" :key="i" class="thumb">
            <img :src="scanStillUrl(summary.session_id, slot, i) + `?q=${e.quality}`" :alt="`${slot} ${i + 1}`" />
            <figcaption>{{ e.quality.toFixed(2) }}</figcaption>
          </figure>
        </div>
      </div>
    </div>

    <div v-if="summary" class="scan-foot">
      <div class="progress"><span :style="{ width: `${Math.min(100, (kept / total) * 100)}%` }" /></div>
      <span class="muted small">{{ kept }} / {{ total }} photos · quality model: {{ summary.model }} (threshold {{ summary.threshold }})
        <template v-if="summary.liveness?.score != null"> · liveness {{ summary.liveness.score.toFixed(2) }}</template></span>
      <small v-if="summary.liveness?.live === false" class="error">Liveness check failed: use a real face, not a photo or a screen.</small>
      <small v-if="summary.duplicate" class="error">This face already matches {{ summary.duplicate.name }} ({{ summary.duplicate.student_id }}, score {{ summary.duplicate.score }}). Check before registering.</small>
      <button class="btn" type="button" @click="restart">Start again</button>
    </div>
  </div>
</template>

<style scoped>
.scan { display: grid; gap: var(--space-3); }
.scan-tabs { justify-content: flex-start; }
.scan-view { position: relative; width: 100%; max-width: 640px; aspect-ratio: 16 / 9; background: #111; border-radius: 10px; overflow: hidden; }
.scan-view video { width: 100%; height: 100%; object-fit: contain; transform: scaleX(-1); }
.scan-box { position: absolute; border: 3px solid; border-radius: 8px; pointer-events: none; }
.scan-box.good { border-color: #6ad16a; }
.scan-box.bad { border-color: #f2b233; }
.scan-hint { position: absolute; left: 50%; bottom: 28px; transform: translateX(-50%); background: rgba(0, 0, 0, .65); color: #fff;
  padding: 6px 14px; border-radius: 999px; font-weight: 600; white-space: nowrap; max-width: 92%; overflow: hidden; text-overflow: ellipsis; }
.scan-meter { position: absolute; left: 12px; right: 12px; bottom: 10px; height: 8px; background: rgba(255, 255, 255, .25); border-radius: 4px; }
.scan-meter span { display: block; height: 100%; background: var(--danger); border-radius: 4px; transition: width .2s; }
.scan-meter span.warn { background: var(--amber); }
.scan-meter span.good { background: #6ad16a; }
.scan-reason { position: absolute; right: 0; bottom: 12px; font-size: 12px; font-style: normal; font-weight: 600; color: #fff;
  background: rgba(0, 0, 0, .55); padding: 1px 8px; border-radius: 999px; white-space: nowrap; }
.scan-meter i { position: absolute; top: -3px; width: 2px; height: 14px; background: #fff; }
.scan-slots { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: var(--space-2); }
.scan-slot { border: 1px solid var(--line); border-radius: 8px; padding: var(--space-2); }
.scan-slot.full { border-color: var(--green); background: var(--green-soft); }
.scan-slot .thumbs { margin-top: 6px; }
.scan-slot figcaption { font-size: 11px; text-align: center; color: var(--muted); }
.scan-foot { display: grid; gap: 6px; justify-items: start; }
.scan-foot .progress { width: 100%; }
</style>
