<script setup>
// One camera panel: the <video>, a canvas overlay with the track boxes, and a slot
// below for extra content (the attendance cam's liveness / identity / emotion lines).
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  cam: { type: Object, required: true },
  src: String,
  tracks: Object,
  showBoxes: Boolean,
  highlight: Boolean,
  live: Boolean,       // Home: empty frame shows a "+" box that asks for this device's camera
})

const video = ref(null)
// Green dot = picture is moving: a live camera, or a video that is playing (grey when paused / ended).
const videoPlaying = ref(false)
const canvas = ref(null)
// The frame takes the video's own shape (no black bars); 16:9 until a video has loaded (all recordings are 1280x720).
const ratio = ref('16 / 9')
const onMeta = () => { frameT = null; const v = video.value; if (v?.videoWidth) ratio.value = `${v.videoWidth} / ${v.videoHeight}` }
defineExpose({ video })   // the Demo page plays, pauses and syncs the videos

// ---- live device camera (Home) ----
// TODO (Đức Mạnh, task 5): send frames to /ws/camera/{cam_id} for the pipeline.
const stream = ref(null)
const devices = ref([])          // video inputs, known once permission is given
const deviceId = ref('')
const camError = ref('')

async function startCamera(id) {
  camError.value = ''
  if (!navigator.mediaDevices?.getUserMedia) {
    camError.value = 'This browser cannot open a camera here (needs https or localhost).'
    return
  }
  try {
    const s = await navigator.mediaDevices.getUserMedia({ video: id ? { deviceId: { exact: id } } : true, audio: false })
    stopCamera()
    stream.value = s
    video.value.srcObject = s
    video.value.play().catch(() => {})
    deviceId.value = s.getVideoTracks()[0]?.getSettings().deviceId ?? ''
    devices.value = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'videoinput')
  } catch (e) {
    camError.value = e.name === 'NotAllowedError' ? 'Camera permission was denied.' : `Camera error: ${e.message}`
  }
}
function stopCamera() {
  stream.value?.getTracks().forEach((t) => t.stop())
  stream.value = null
  if (video.value) video.value.srcObject = null
  ratio.value = '16 / 9'   // khung trở về kích thước cũ khi tắt camera
}

// Box for one track at time t: linear interpolation between keyframes,
// hidden outside the first..last keyframe range.
function boxAt(track, t) {
  const k = track.keyframes
  if (!k?.length || t < k[0].t || t > k[k.length - 1].t) return null
  for (let i = 0; i < k.length - 1; i++) {
    if (t <= k[i + 1].t) {
      const a = k[i], b = k[i + 1]
      const f = b.t === a.t ? 0 : (t - a.t) / (b.t - a.t)
      return a.box.map((v, j) => v + (b.box[j] - v) * f)
    }
  }
  return k[k.length - 1].box
}

// Name shown once the track is recognised (name_from = check-in time, if given); "Le Mai Chi" -> "Mai Chi".
const nameAt = (tr, t) => (tr.name && (tr.name_from == null || t >= tr.name_from) ? tr.name : null)
const shortName = (name) => (name.split(' ').length > 2 ? name.split(' ').slice(1).join(' ') : name)
const labelOf = (tr, t) => { const n = nameAt(tr, t); return `ID ${tr.global_id} · ${n ? shortName(n) : 'Unknown'}` }

// Draws the track boxes on the canvas laid over the <video>, once per animation frame.
// The video uses object-fit: contain, so we compute where the picture actually sits.
let raf

// Time of the frame actually on screen. video.currentTime jumps to the target at once when seeking,
// but the picture changes only after the new frame is decoded, so boxes drawn at currentTime run ahead
// of the video while scrubbing. requestVideoFrameCallback reports the presented frame's time.
const hasRvfc = typeof HTMLVideoElement !== 'undefined' && 'requestVideoFrameCallback' in HTMLVideoElement.prototype
let frameT = null, frameVideo = null
function watchFrames(v) {
  if (!hasRvfc || !v || frameVideo === v) return
  frameVideo = v
  const onFrame = (_now, meta) => { frameT = meta.mediaTime; v.requestVideoFrameCallback(onFrame) }
  v.requestVideoFrameCallback(onFrame)
}
const shownTime = (v) => (hasRvfc && frameT != null ? frameT : v.currentTime)
function draw() {
  raf = requestAnimationFrame(draw)
  const v = video.value, c = canvas.value
  if (!v || !c) return
  const W = c.clientWidth, H = c.clientHeight
  if (c.width !== W) c.width = W
  if (c.height !== H) c.height = H
  watchFrames(v)
  const ctx = c.getContext('2d')
  ctx.clearRect(0, 0, W, H)
  if (!props.showBoxes || !props.tracks || !v.videoWidth) return
  const s = Math.min(W / v.videoWidth, H / v.videoHeight)
  const pw = v.videoWidth * s, ph = v.videoHeight * s
  const ox = (W - pw) / 2, oy = (H - ph) / 2
  // Without requestVideoFrameCallback, hide the boxes while a seek is still loading its frame.
  if (!hasRvfc && v.seeking) return
  const now = shownTime(v)
  for (const tr of props.tracks.tracks) {
    const b = boxAt(tr, now)
    if (!b) continue
    const [x, y, w, h] = [ox + b[0] * pw, oy + b[1] * ph, b[2] * pw, b[3] * ph]
    const color = nameAt(tr, now) ? '#3fbf4f' : '#f2b233'
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.strokeRect(x, y, w, h)
    const text = labelOf(tr, now)
    ctx.font = '600 13px system-ui, sans-serif'
    const tw = ctx.measureText(text).width + 12
    ctx.fillStyle = 'rgba(30,30,30,0.85)'
    ctx.fillRect(x, Math.max(0, y - 22), tw, 20)
    ctx.fillStyle = '#fff'
    ctx.fillText(text, x + 6, Math.max(14, y - 8))
  }
}

onMounted(draw)
onBeforeUnmount(() => { cancelAnimationFrame(raf); stopCamera() })
</script>

<template>
  <section class="card cam-card" :class="{ 'cam-highlight': highlight }">
    <header class="cam-head">
      <span class="dot" :class="{ on: stream || videoPlaying }" />
      <div>
        <div class="cam-title">{{ cam.label }}</div>
        <div class="cam-place">{{ cam.place }}</div>
      </div>
      <select v-if="stream && devices.length > 1" v-model="deviceId" class="input compact" aria-label="Camera device"
        @change="startCamera(deviceId)">
        <option v-for="(d, i) in devices" :key="d.deviceId" :value="d.deviceId">{{ d.label || `Camera ${i + 1}` }}</option>
      </select>
    </header>
    <div class="cam-view" :style="{ aspectRatio: ratio }">
      <video ref="video" :src="src || undefined" muted playsinline preload="auto" @loadedmetadata="onMeta"
        @playing="videoPlaying = true" @pause="videoPlaying = false" @ended="videoPlaying = false" @emptied="videoPlaying = false" />
      <canvas ref="canvas" class="cam-overlay" />
      <button v-if="stream" class="btn cam-stop" @click="stopCamera">Stop</button>
      <button v-else-if="live" class="cam-add" :aria-label="`Turn on a camera for ${cam.label}`" @click="startCamera()">
        <span class="plus">+</span>
        <span>Add camera</span>
        <span v-if="camError" class="muted">{{ camError }}</span>
      </button>
      <div v-else-if="!src" class="cam-empty">
        <div>No video loaded</div>
        <div class="muted">{{ cam.folder }}/ · stream {{ cam.stream_id }}</div>
      </div>
    </div>
    <slot />
  </section>
</template>
