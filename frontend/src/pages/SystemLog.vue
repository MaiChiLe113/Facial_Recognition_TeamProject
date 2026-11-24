<script setup>
// System log: the model files the app infers with, when each was last modified, its version label
// (ml/model_versions.json, edited by hand) and a fingerprint, plus every change the backend has detected
// (logs/model_changes.jsonl). How to change a model version: .agents/architecture.md, "Model versions".
import { onMounted, ref } from 'vue'
import { fetchSystemModels } from '../api.js'

const data = ref(null)
const loading = ref(false)
async function load() {
  loading.value = true
  data.value = await fetchSystemModels()
  loading.value = false
}
onMounted(load)

const when = (iso) => (iso ? new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'medium' }) : '—')
const size = (b) => (b == null ? '—' : b >= 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.round(b / 1e3)} KB`)
const short = (h) => (h ? h.slice(0, 12) : '—')
const CHANGE = { 'first seen': 'first', 'file replaced': 'replaced', 'version label changed': 'label', 'file missing': 'missing' }
</script>

<template>
  <div class="page">
    <header class="topbar">
      <h1>System log</h1>
      <button class="btn" type="button" :disabled="loading" @click="load">{{ loading ? 'Checking…' : 'Check again' }}</button>
    </header>

    <p v-if="data?.offline" class="notice">The backend is not running, so the model files cannot be read. Start uvicorn.</p>

    <section class="card roster">
      <header class="card-head">
        <h2>Inference models</h2>
        <span class="muted small">Versions from <code>{{ data?.versions_file ?? 'ml/model_versions.json' }}</code></span>
      </header>
      <table>
        <thead>
          <tr><th>Model</th><th>Version</th><th>Last modified</th><th>Size</th><th>Fingerprint</th><th>File</th></tr>
        </thead>
        <tbody>
          <tr v-for="m in data?.models ?? []" :key="m.key">
            <td><strong>{{ m.label }}</strong><div v-if="m.note" class="muted small">{{ m.note }}</div></td>
            <td><span class="sl-version">{{ m.version || 'unset' }}</span></td>
            <td>{{ m.found ? when(m.modified) : '' }}<span v-if="!m.found" class="yesno no">Missing</span></td>
            <td>{{ size(m.size) }}</td>
            <td class="mono" :title="m.sha256">{{ short(m.sha256) }}</td>
            <td class="mono">{{ m.file }}</td>
          </tr>
          <tr v-if="data && !data.models.length"><td colspan="6" class="empty">No model information.</td></tr>
        </tbody>
      </table>
      <p class="muted small sl-foot">"Last modified" is the file's date on this computer: a fresh clone or copy sets it to when the
        file arrived, not when the model was trained. The fingerprint (SHA-256) changes only when the file's content does.</p>
    </section>

    <section class="card roster">
      <header class="card-head">
        <h2>Change history</h2>
        <span class="muted small">Newest first · <code>{{ data?.log_file ?? 'logs/model_changes.jsonl' }}</code> (this computer only)</span>
      </header>
      <table>
        <thead>
          <tr><th>Detected</th><th>Model</th><th>Change</th><th>Version</th><th>File modified</th><th>Fingerprint</th></tr>
        </thead>
        <tbody>
          <tr v-for="(h, i) in data?.history ?? []" :key="i">
            <td>{{ when(h.detected) }}</td>
            <td>{{ h.label }}</td>
            <td><span class="sl-change" :class="CHANGE[h.change]">{{ h.change }}</span></td>
            <td>{{ h.previous_version && h.previous_version !== h.version ? `${h.previous_version} → ` : '' }}{{ h.version || 'unset' }}</td>
            <td>{{ when(h.modified) }}</td>
            <td class="mono" :title="h.sha256">{{ short(h.sha256) }}</td>
          </tr>
          <tr v-if="data && !data.history.length"><td colspan="6" class="empty">No changes logged yet.</td></tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.sl-version { font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace; font-size: 12px; font-weight: 600;
  background: var(--bg); border: 1px solid var(--line); border-radius: 999px; padding: 2px 10px; white-space: nowrap; }
.sl-change { display: inline-block; font-size: 12px; font-weight: 600; border-radius: 999px; padding: 2px 10px; white-space: nowrap;
  background: var(--bg); color: var(--muted); }
.sl-change.replaced { background: var(--yellow-soft); color: var(--warning-text); }
.sl-change.label { background: var(--green-soft); color: var(--green); }
.sl-change.missing { background: var(--danger-soft); color: var(--danger); }
.sl-foot { padding: var(--space-3) var(--space-4) var(--space-1); }
td.mono { word-break: break-all; }
</style>
