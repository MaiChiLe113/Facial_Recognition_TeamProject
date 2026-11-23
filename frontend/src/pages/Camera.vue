<script setup>
// Opened on a phone or laptop over Wi-Fi (https://<host IP>:5173/camera). The device is only a camera: it sends its
// frames to the host (WebSocket /ws/camera/<cam_id>), which runs detection, tracking and recognition and shows the
// result on its Home page (Live source). ?cam=<cam_id> picks the camera straight away.
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { cameraSocketUrl, fetchLive } from '../api.js'

const MAX_FPS = 10, WIDTH = 640, QUALITY = 0.7, RETRY_MS = 2000

const route = useRoute()
const cameras = ref([])
const offline = ref(false)
const camId = ref(null)
const facing = ref('environment')        // back camera on phones; laptops have only one
const state = ref('idle')                // idle | starting | sending | reconnecting | error
const message = ref('')
const fps = ref(0)
const video = ref(null)

let stream = null, socket = null, wakeLock = null, canvas = null, lastSent = 0, stopped = true, retry = null

onMounted(async () => {
  const r = await fetchLive()
  cameras.value = r.cameras
  offline.value = r.offline
  const wanted = route.query.cam
  if (wanted && r.cameras.some((c) => c.cam_id === wanted)) start(wanted)
})
onBeforeUnmount(stop)

async function start(id) {
  camId.value = id
  stopped = false
  state.value = 'starting'
  message.value = ''
  try {
    await openCamera()
  } catch (e) {
    state.value = 'error'
    message.value = `Camera not available (${e.name || e}). Allow the camera for this page and try again.`
    return
  }
  try { wakeLock = await navigator.wakeLock?.request('screen') } catch { /* keeps working, screen may dim */ }
  connect()
}

async function openCamera() {
  stream?.getTracks().forEach((t) => t.stop())
  stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: facing.value, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false,
  })
  video.value.srcObject = stream
  await video.value.play().catch(() => {})
}

async function switchCamera() {
  facing.value = facing.value === 'environment' ? 'user' : 'environment'
  try { await openCamera() } catch { facing.value = facing.value === 'environment' ? 'user' : 'environment' }
}

function connect() {
  if (stopped) return
  socket = new WebSocket(cameraSocketUrl(camId.value))
  socket.binaryType = 'arraybuffer'
  socket.onopen = () => { state.value = 'sending'; sendFrame() }
  socket.onmessage = (e) => {
    const r = JSON.parse(e.data)
    if (r.error) message.value = r.error
    const now = performance.now()
    if (lastSent) fps.value = Math.round((0.8 * fps.value + 0.2 * (1000 / (now - lastSent))) * 10) / 10
    // The host answered: send the next frame, at most MAX_FPS per second.
    setTimeout(sendFrame, Math.max(0, 1000 / MAX_FPS - (now - lastSent)))
  }
  socket.onclose = (e) => {
    if (stopped) return
    state.value = 'reconnecting'
    message.value = e.code === 4404 ? `The host has no camera "${camId.value}".` : 'Lost the host. Reconnecting…'
    retry = setTimeout(connect, RETRY_MS)
  }
}

function sendFrame() {
  const v = video.value
  if (stopped || socket?.readyState !== WebSocket.OPEN) return
  if (!v?.videoWidth) { setTimeout(sendFrame, 100); return }
  canvas ??= document.createElement('canvas')
  canvas.width = Math.min(WIDTH, v.videoWidth)
  canvas.height = Math.round(v.videoHeight * canvas.width / v.videoWidth)
  canvas.getContext('2d').drawImage(v, 0, 0, canvas.width, canvas.height)
  canvas.toBlob((blob) => {
    if (!blob || socket?.readyState !== WebSocket.OPEN) return
    lastSent = performance.now()
    socket.send(blob)
  }, 'image/jpeg', QUALITY)
}

function stop() {
  stopped = true
  clearTimeout(retry)
  socket?.close()
  stream?.getTracks().forEach((t) => t.stop())
  wakeLock?.release?.()
  socket = stream = wakeLock = null
  state.value = 'idle'
  fps.value = 0
}

const label = (id) => cameras.value.find((c) => c.cam_id === id)
</script>

<template>
  <div class="cam-page">
    <video ref="video" class="cam-video" :class="{ hidden: state === 'idle' }" autoplay playsinline muted></video>

    <div v-if="state === 'idle'" class="cam-pick">
      <h1>Use this device as a camera</h1>
      <p class="muted">Pick where this device stands. The host shows its video with detection and tracking.</p>
      <p v-if="offline" class="error">The host's backend is not reachable. Start it on the host, then reload.</p>
      <button v-for="c in cameras" :key="c.cam_id" class="cam-choice" @click="start(c.cam_id)">
        <strong>{{ c.label }}</strong>
        <span>{{ c.place }}<template v-if="c.connected"> · another device is sending</template></span>
      </button>
    </div>

    <div v-else class="cam-bar">
      <div class="cam-status">
        <span class="dot" :class="state"></span>
        <span>
          <strong>{{ label(camId)?.label ?? camId }}</strong>
          <template v-if="state === 'sending'"> · sending to the host · {{ fps }} fps</template>
          <template v-else-if="state === 'starting'"> · starting…</template>
        </span>
      </div>
      <div v-if="message" class="cam-msg">{{ message }}</div>
      <div class="cam-actions">
        <button class="btn" @click="switchCamera">Switch camera</button>
        <button class="btn" @click="stop">Stop</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cam-page { position: fixed; inset: 0; background: #111; color: #f2f2f2; display: flex; flex-direction: column; }
.cam-video { flex: 1; width: 100%; min-height: 0; object-fit: contain; background: #000; }
.cam-video.hidden { display: none; }
.cam-pick { margin: auto; padding: 24px 16px; width: min(440px, 100%); display: flex; flex-direction: column; gap: 12px; }
.cam-pick h1 { font-size: 22px; }
.cam-pick .muted { color: #aaa; margin: 0 0 8px; }
.cam-choice { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 16px 18px; border-radius: 12px;
  border: 1px solid #444; background: #1d1d1d; color: inherit; font: inherit; font-size: 17px; cursor: pointer; text-align: left; }
.cam-choice:hover { border-color: var(--accent); }
.cam-choice span { font-size: 14px; color: #aaa; }
.cam-bar { padding: 12px 16px calc(12px + env(safe-area-inset-bottom)); background: #1b1b1b; display: flex; flex-direction: column; gap: 8px; }
.cam-status { display: flex; align-items: center; gap: 10px; font-size: 15px; }
.cam-msg { font-size: 13px; color: #f2b233; }
.cam-actions { display: flex; gap: 10px; }
.cam-actions .btn { flex: 1; background: #2a2a2a; color: #f2f2f2; border-color: #444; padding: 12px; }
.dot { width: 10px; height: 10px; border-radius: 50%; background: #777; flex: none; }
.dot.sending { background: #34c759; }
.dot.starting, .dot.reconnecting { background: #f2b233; }
.dot.error { background: #ff3b30; }
</style>
