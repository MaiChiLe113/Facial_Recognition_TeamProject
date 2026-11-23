<script setup>
// One camera tile on Home, in either source mode:
//   Recorded  a <video> of the take plus a canvas overlay with its precomputed track boxes (tracks, showBoxes).
//   Live      the camera's MJPEG stream from the backend (stream = /api/live/<cam_id>/stream). Its boxes and labels are
//             drawn on the frame by the backend (app/services/live.py), in the same frame they were found in; boxes
//             from the 1 s GET /api/live poll would trail a 10 fps picture by up to a second. With no device sending,
//             the "+" opens the Camera page (/camera?cam=<cam_id>) on this device, which sends its camera to the host.
// The slot below holds extra lines (the doorway camera's identity / liveness / emotion).
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  cam: { type: Object, required: true },
  src: String,           // recorded: video URL
  tracks: Object,        // recorded: data/tracks/take<N>/<cam>.json
  showBoxes: Boolean,
  highlight: Boolean,
  live: Boolean,         // live mode
  stream: String,        // live: MJPEG URL, set while a device is sending
})

const video = ref(null)
// Green dot = picture is moving: a live camera that is sending, or a video that is playing (grey when paused / ended).
const videoPlaying = ref(false)
const canvas = ref(null)
// The frame takes the picture's own shape (no black bars); 16:9 until a video or stream has loaded.
const ratio = ref('16 / 9')
const onMeta = () => { frameT = null; const v = video.value; if (v?.videoWidth) ratio.value = `${v.videoWidth} / ${v.videoHeight}` }
const onStreamLoad = (e) => { const i = e.target; if (i.naturalWidth) ratio.value = `${i.naturalWidth} / ${i.naturalHeight}` }
defineExpose({ video })   // Home plays, pauses and syncs the videos in Recorded mode

const openCamera = () => window.open(`/camera?cam=${encodeURIComponent(props.cam.cam_id)}`, '_blank')

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
  if (props.live || !props.showBoxes || !props.tracks || !v.videoWidth) return
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
onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <section class="card cam-card" :class="{ 'cam-highlight': highlight }">
    <header class="cam-head">
      <span class="dot" :class="{ on: live ? !!stream : videoPlaying }" />
      <div>
        <div class="cam-title">{{ cam.label }}</div>
        <div class="cam-place">{{ cam.place }}</div>
      </div>
    </header>
    <div class="cam-view" :style="{ aspectRatio: ratio }">
      <template v-if="live">
        <img v-if="stream" class="cam-stream" :src="stream" :alt="`${cam.label} live`" @load="onStreamLoad" />
        <button v-else class="cam-add" :aria-label="`Use this device as ${cam.label}`" @click="openCamera">
          <span class="plus">+</span>
          <span>Add camera</span>
          <span class="muted">Opens /camera?cam={{ cam.cam_id }} on this device</span>
        </button>
      </template>
      <template v-else>
        <video ref="video" :src="src || undefined" muted playsinline preload="auto" @loadedmetadata="onMeta"
          @playing="videoPlaying = true" @pause="videoPlaying = false" @ended="videoPlaying = false" @emptied="videoPlaying = false" />
        <canvas ref="canvas" class="cam-overlay" />
        <div v-if="!src" class="cam-empty">
          <div>No video loaded</div>
          <div class="muted">{{ cam.folder }}/ · stream {{ cam.stream_id }}</div>
        </div>
      </template>
    </div>
    <slot />
  </section>
</template>
