// Plays several <video> elements together and keeps them in step (Home, Recorded mode).
//   cameras: ref of camera objects ({ cam_id, offset_s })
//   videoOf: cam_id -> <video> element
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

export function useSyncedPlayback(cameras, videoOf) {
  const srcs = ref({})          // cam_id -> video URL
  const playing = ref(false)
  const position = ref(0)       // take time in seconds (lead video time minus its offset)
  const duration = ref(0)       // longest take time over the loaded videos
  let timer, posTimer

  // A .webm written by MediaRecorder has no duration in its header: the browser reports Infinity until it has read
  // to the end. lengthOf() treats that as unknown (0), and play() makes the browser find the real length first.
  const lengthOf = (v) => (Number.isFinite(v?.duration) ? v.duration : 0)
  const loaded = () => cameras.value.filter((c) => srcs.value[c.cam_id] && videoOf(c.cam_id))

  // Playback line: read the lead video's time ~10x a second.
  function readPosition() {
    const cams = loaded()
    if (!cams.length) { position.value = 0; duration.value = 0; return }
    const lv = videoOf(cams[0].cam_id)
    position.value = Math.max(0, lv.currentTime - (cams[0].offset_s || 0))
    duration.value = Math.max(0, ...cams.map((c) => lengthOf(videoOf(c.cam_id)) - (c.offset_s || 0)))
  }
  watch(srcs, (s) => {
    clearInterval(posTimer)
    if (Object.keys(s).length) posTimer = setInterval(readPosition, 100)
    else readPosition()
  })

  // Jump every video to take time t (each with its own offset).
  function seek(t) {
    for (const c of loaded()) {
      const v = videoOf(c.cam_id)
      v.currentTime = Math.min(t + (c.offset_s || 0), lengthOf(v) || Infinity)
    }
    position.value = t
  }

  // Follow the first loaded camera; correct drift above 0.3 s.
  function sync() {
    const cams = cameras.value.filter((c) => srcs.value[c.cam_id] && videoOf(c.cam_id))
    if (!cams.length) return
    const lead = cams[0], lv = videoOf(lead.cam_id)
    const base = lv.currentTime - (lead.offset_s || 0)
    for (const c of cams.slice(1)) {
      const v = videoOf(c.cam_id)
      const want = base + (c.offset_s || 0)
      if (Math.abs(v.currentTime - want) > 0.3 && want < (lengthOf(v) || Infinity)) v.currentTime = want
    }
    if (cams.every((c) => videoOf(c.cam_id).ended)) playing.value = false
  }
  watch(playing, (on) => {
    clearInterval(timer)
    if (on) timer = setInterval(sync, 500)
  })
  onBeforeUnmount(() => { clearInterval(timer); clearInterval(posTimer) })

  async function play(sources) {
    srcs.value = sources
    await nextTick()
    const cams = cameras.value.filter((c) => sources[c.cam_id] && videoOf(c.cam_id))
    // wait until every loaded video knows its length, then start together
    await Promise.all(cams.map((c) => new Promise((resolve) => {
      const v = videoOf(c.cam_id)
      if (v.readyState >= 1) return resolve()
      v.addEventListener('loadedmetadata', resolve, { once: true })
      v.addEventListener('error', resolve, { once: true })
    })))
    await Promise.all(cams.map((c) => findLength(videoOf(c.cam_id))))
    for (const c of cams) {
      const v = videoOf(c.cam_id)
      v.currentTime = c.offset_s || 0
      v.play().catch(() => {})
    }
    playing.value = cams.length > 0
  }

  // Seeking far past the end makes the browser read the whole file and fire durationchange with the real length.
  function findLength(v) {
    if (!v || Number.isFinite(v.duration) || v.error) return Promise.resolve()
    return new Promise((resolve) => {
      const done = () => { clearTimeout(guard); v.removeEventListener('durationchange', check); resolve() }
      const check = () => { if (Number.isFinite(v.duration)) done() }
      const guard = setTimeout(done, 5000)     // never block Play on a file that will not tell
      v.addEventListener('durationchange', check)
      v.currentTime = 1e101
    })
  }

  function togglePause() {
    const vs = cameras.value.map((c) => videoOf(c.cam_id)).filter((v) => v && v.src)
    if (playing.value) vs.forEach((v) => v.pause())
    else vs.forEach((v) => v.play().catch(() => {}))
    playing.value = !playing.value
  }

  function stop() {
    cameras.value.forEach((c) => videoOf(c.cam_id)?.pause())
    playing.value = false
    srcs.value = {}
  }

  return { srcs, playing, position, duration, seek, play, togglePause, restart: () => play(srcs.value), stop }
}
