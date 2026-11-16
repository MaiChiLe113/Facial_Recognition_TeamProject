// Plays several <video> elements together and keeps them in step (same logic as the Home page).
//   cameras: ref of camera objects ({ cam_id, offset_s })
//   videoOf: cam_id -> <video> element
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

export function useSyncedPlayback(cameras, videoOf) {
  const srcs = ref({})          // cam_id -> video URL
  const playing = ref(false)
  let timer

  // Follow the first loaded camera; correct drift above 0.3 s.
  function sync() {
    const cams = cameras.value.filter((c) => srcs.value[c.cam_id] && videoOf(c.cam_id))
    if (!cams.length) return
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
    clearInterval(timer)
    if (on) timer = setInterval(sync, 500)
  })
  onBeforeUnmount(() => clearInterval(timer))

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
    for (const c of cams) {
      const v = videoOf(c.cam_id)
      v.currentTime = c.offset_s || 0
      v.play().catch(() => {})
    }
    playing.value = cams.length > 0
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

  return { srcs, playing, play, togglePause, restart: () => play(srcs.value), stop }
}
