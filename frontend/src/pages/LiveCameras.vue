<script setup>
// The host's view of the phones / laptops used as cameras (Camera page, /camera). Each camera's frames run through
// its pipeline on this machine (backend/pipeline.json) and come back drawn: people boxes with track IDs on the
// corridor / classroom cameras, faces with name, liveness and emotion on the doorway camera.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchLive, liveStreamUrl } from '../api.js'

const POLL_MS = 1000
const live = ref(null)
const epoch = ref(Date.now())      // changes the stream URLs after the backend comes back, so the <img>s reconnect
let timer = null, wasOffline = false

onMounted(poll)
onBeforeUnmount(() => clearTimeout(timer))

async function poll() {
  const r = await fetchLive()
  if (wasOffline && !r.offline) epoch.value = Date.now()
  wasOffline = r.offline
  live.value = r
  timer = setTimeout(poll, POLL_MS)
}

const senderUrl = computed(() => live.value?.host_urls?.[0] ?? `https://<this computer's IP>:5173/camera`)
const connected = computed(() => live.value?.cameras.filter((c) => c.connected).length ?? 0)

function faceText(f) {
  if (f.live === false) return 'Spoof'
  const who = f.name ?? 'Unknown'
  return [who, f.similarity != null && f.name ? f.similarity.toFixed(2) : null, f.emotion].filter(Boolean).join(' · ')
}
</script>

<template>
  <div v-if="!live" class="loading">Loading…</div>
  <div v-else class="page">
    <header class="topbar">
      <h1>Live cameras</h1>
      <div class="topbar-right">
        <span v-if="live.offline" class="badge">Backend offline</span>
        <span v-else class="muted">{{ connected }} of {{ live.cameras.length }} cameras sending</span>
      </div>
    </header>

    <div class="notice">
      <span>On a phone or laptop on the same Wi-Fi, open <strong>{{ senderUrl }}</strong> and pick a camera.
        First time on a device: see <code>docs/LAN_DEMO.md</code> (certificate, Local Network access).</span>
    </div>

    <div class="live-grid">
      <section v-for="c in live.cameras" :key="c.cam_id" class="card live-card">
        <header class="live-head">
          <div><strong>{{ c.label }}</strong> <span class="muted">{{ c.place }}</span></div>
          <span v-if="c.connected" class="ok-text small">● {{ c.fps }} fps · {{ c.frame_ms }} ms</span>
          <span v-else class="muted small">Waiting for a device</span>
        </header>
        <div class="live-view">
          <img v-if="c.connected" :src="`${liveStreamUrl(c.cam_id)}?e=${epoch}`" :alt="`${c.label} live`" />
          <div v-else class="cam-empty">
            <div>No device is sending</div>
            <div class="muted">{{ senderUrl }}?cam={{ c.cam_id }}</div>
          </div>
        </div>
        <footer v-if="c.connected" class="live-foot small">
          <template v-if="c.role === 'attendance'">
            <span v-if="!c.faces?.length" class="muted">No face in view</span>
            <span v-for="(f, i) in c.faces" :key="i" :class="f.live === false ? 'error' : f.name ? 'ok-text' : 'muted'">
              {{ faceText(f) }}</span>
          </template>
          <template v-else>
            <span class="muted">{{ c.people?.length === 1 ? '1 person' : `${c.people?.length ?? 0} people` }} tracked</span>
            <span v-for="p in c.people" :key="p.id">ID {{ p.id }}</span>
          </template>
        </footer>
      </section>
    </div>
  </div>
</template>

<style scoped>
.live-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 18px; }
.live-card { display: flex; flex-direction: column; overflow: hidden; }
.live-head { display: flex; justify-content: space-between; align-items: baseline; padding: 12px 16px; gap: 10px; }
.live-view { position: relative; background: #111; aspect-ratio: 16 / 9; }
.live-view img { width: 100%; height: 100%; object-fit: contain; display: block; }
.live-foot { display: flex; flex-wrap: wrap; gap: 6px 14px; padding: 10px 16px; border-top: 1px solid var(--line); }
code { font-size: 12px; }
</style>
