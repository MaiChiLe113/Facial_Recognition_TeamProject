<script setup>
// "QR" button: opens a dialog with a QR code of the Camera page on this computer's Wi-Fi address
// (https://<host IP>:5173/camera, from GET /api/live host_urls), so a phone can scan it instead of typing it.
import qrcode from 'qrcode-generator'
import { computed, ref } from 'vue'

const props = defineProps({ url: String })   // undefined while the backend has not reported a Wi-Fi address
const dialog = ref(null)

const svg = computed(() => {
  if (!props.url) return ''
  const qr = qrcode(0, 'M')
  qr.addData(props.url)
  qr.make()
  return qr.createSvgTag({ cellSize: 6, margin: 2, scalable: true })
})
</script>

<template>
  <button class="btn" type="button" aria-haspopup="dialog" @click="dialog.showModal()">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 18h2v2h-2zM14 18h2M18 14h2" />
    </svg>
    QR
  </button>
  <dialog ref="dialog" class="qr-dialog" @click.self="dialog.close()">
    <header class="card-head">
      <h2>Scan to send a camera</h2>
      <button class="btn" type="button" @click="dialog.close()">Close</button>
    </header>
    <template v-if="url">
      <div class="qr" v-html="svg" />
      <p class="mono qr-url">{{ url }}</p>
      <p class="muted small">The phone must be on the same Wi-Fi, and the app started with <code>npm run dev:lan</code>.
        <RouterLink to="/guide/lan" @click="dialog.close()">Wi-Fi demo guide</RouterLink></p>
    </template>
    <p v-else class="empty">No Wi-Fi address yet. Start the backend and run <code>npm run dev:lan</code>, then try again.</p>
  </dialog>
</template>

<style scoped>
.qr-dialog { border: 1px solid var(--line); border-radius: 14px; padding: var(--space-5); width: min(380px, calc(100vw - 32px));
  background: var(--card); color: var(--text); box-shadow: 0 12px 40px rgba(0,0,0,.2); }
.qr-dialog::backdrop { background: rgba(0,0,0,.4); }
.qr { width: 100%; max-width: 280px; margin: 0 auto; }
.qr :deep(svg) { width: 100%; height: auto; display: block; }
.qr-url { text-align: center; word-break: break-all; margin: var(--space-3) 0; }
.small a { color: var(--green); }
</style>
