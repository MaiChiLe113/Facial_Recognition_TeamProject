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
})

const video = ref(null)
const canvas = ref(null)
defineExpose({ video })   // the Home page plays, pauses and syncs the videos

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

const labelOf = (tr) => (tr.name ? `ID ${tr.global_id} · ${tr.name.split(' ').slice(-1)[0]}` : `ID ${tr.global_id} · Unknown`)

// Draws the track boxes on the canvas laid over the <video>, once per animation frame.
// The video uses object-fit: contain, so we compute where the picture actually sits.
let raf
function draw() {
  raf = requestAnimationFrame(draw)
  const v = video.value, c = canvas.value
  if (!v || !c) return
  const W = c.clientWidth, H = c.clientHeight
  if (c.width !== W) c.width = W
  if (c.height !== H) c.height = H
  const ctx = c.getContext('2d')
  ctx.clearRect(0, 0, W, H)
  if (!props.showBoxes || !props.tracks || !v.videoWidth) return
  const s = Math.min(W / v.videoWidth, H / v.videoHeight)
  const pw = v.videoWidth * s, ph = v.videoHeight * s
  const ox = (W - pw) / 2, oy = (H - ph) / 2
  for (const tr of props.tracks.tracks) {
    const b = boxAt(tr, v.currentTime)
    if (!b) continue
    const [x, y, w, h] = [ox + b[0] * pw, oy + b[1] * ph, b[2] * pw, b[3] * ph]
    const color = tr.name ? '#3fbf4f' : '#f2b233'
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.strokeRect(x, y, w, h)
    const text = labelOf(tr)
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
      <span class="dot" :class="{ on: src }" />
      <div>
        <div class="cam-title">{{ cam.label }}</div>
        <div class="cam-place">{{ cam.place }}</div>
      </div>
      <span v-if="tracks?.source === 'mock' && showBoxes && src" class="badge small">mock boxes</span>
    </header>
    <div class="cam-view">
      <video ref="video" :src="src || undefined" muted playsinline preload="auto" />
      <canvas ref="canvas" class="cam-overlay" />
      <div v-if="!src" class="cam-empty">
        <div>No video loaded</div>
        <div class="muted">{{ cam.folder }}/ · stream {{ cam.stream_id }}</div>
      </div>
    </div>
    <slot />
  </section>
</template>
