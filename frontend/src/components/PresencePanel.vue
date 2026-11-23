<script setup>
// Presence verification + door audit for one recorded take (GET /api/features/presence_verification/take/N).
// Door alerts appear when the playback reaches them (all of them when no video is playing);
// the students table shows each checked-in student's score and the reasons.
import { computed } from 'vue'

const props = defineProps({
  result: { type: Object, default: null },     // fetchPresence() answer, null while loading
  position: { type: Number, default: 0 },      // playback position (s)
  live: { type: Boolean, default: false },     // true while a video is loaded: reveal alerts as it plays
})

const CODES = {
  D1: 'Entered without check-in',
  D2: 'Tailgating',
  D3: 'Checked in, never entered',
}
const shortName = (n) => (n && n.split(' ').length > 2 ? n.split(' ').slice(1).join(' ') : n)
const clock = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

const alerts = computed(() => (props.result?.alerts ?? []).map((a) => ({ ...a, shown: !props.live || a.t <= props.position + 0.05 })))
const shownCount = computed(() => alerts.value.filter((a) => a.shown).length)
const students = computed(() => [...(props.result?.students ?? [])].sort((a, b) => b.score - a.score))
const matchOf = (sid) => props.result?.matches?.find((m) => m.student_id === sid)
</script>

<template>
  <section class="card panel pv">
    <header class="card-head">
      <h2>Presence verification</h2>
      <span v-if="result?.model" class="muted small">door: {{ result.model.door_mode }} · presence: {{ result.model.presence_model }}
        · threshold {{ result.model.threshold }}</span>
    </header>

    <p v-if="!result" class="empty">Analysing the take…</p>
    <p v-else-if="result.offline" class="empty">The backend is not running.</p>
    <p v-else-if="result.unavailable" class="error small">{{ result.message }}</p>
    <template v-else>
      <h3 class="pv-sub">Door audit <span class="muted small">{{ result.check_ins.length }} check-in(s) ·
        {{ result.crossings.filter((c) => c.direction === 'in').length }} entr{{ result.crossings.filter((c) => c.direction === 'in').length === 1 ? 'y' : 'ies' }}
        · {{ result.matches.length }} matched</span></h3>
      <ul class="pv-alerts">
        <li v-for="(a, i) in alerts" :key="i" :class="{ pending: !a.shown }">
          <span class="mono">{{ clock(a.t) }}</span>
          <span class="pv-code" :class="a.code">{{ a.code }}</span>
          <span class="grow"><strong>{{ CODES[a.code] }}</strong> · {{ a.shown ? a.reason : 'later in the take' }}</span>
          <span class="muted small">score {{ a.score.toFixed(2) }}</span>
        </li>
        <li v-if="!alerts.length" class="ok">No door alert: every entry has a check-in and every check-in an entry.</li>
        <li v-else-if="live && !shownCount" class="muted small">{{ alerts.length }} alert(s) later in this take.</li>
      </ul>

      <h3 class="pv-sub">Students</h3>
      <table v-if="students.length" class="pv-table">
        <thead><tr><th>Student</th><th>Entered</th><th>Score</th><th>Status</th><th>Reasons</th></tr></thead>
        <tbody>
          <tr v-for="s in students" :key="s.student_id" :class="{ flagged: s.flagged }">
            <td>{{ shortName(s.student_id) }}</td>
            <td class="mono">{{ matchOf(s.student_id) ? `${clock(matchOf(s.student_id).crossing_t)} (+${matchOf(s.student_id).dt.toFixed(1)} s)` : '—' }}</td>
            <td>{{ Math.round(s.score * 100) }}%</td>
            <td><span class="pv-status" :class="{ bad: s.flagged }">{{ s.flagged ? 'Check' : 'OK' }}</span></td>
            <td class="small">{{ s.reasons.join(' · ') || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty">Nobody was recognised at the attendance camera in this take.</p>
      <p class="muted small">Scores are suggestions for the lecturer, not decisions. A recorded take is only a few seconds of a
        class, so time-based reasons (late, short stay) are weaker here than in a full session.</p>
    </template>
  </section>
</template>

<style scoped>
.pv { padding: 16px; }
.pv-sub { font-size: 14px; margin: 12px 0 6px; }
.pv-alerts { list-style: none; margin: 0; padding: 0; }
.pv-alerts li { display: flex; gap: 10px; align-items: baseline; padding: 6px 0; border-bottom: 1px solid var(--line); font-size: 13px; }
.pv-alerts li.pending { opacity: 0.45; }
.pv-alerts li.ok { color: #3f7d2f; }
.pv-alerts .grow { flex: 1; }
.pv-code { font-weight: 700; font-size: 11px; padding: 1px 6px; border-radius: 4px; color: #fff; background: #b3392e; }
.pv-code.D3 { background: #b36b00; }
.pv-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.pv-table th { text-align: left; color: var(--muted); font-weight: 500; }
.pv-table th, .pv-table td { padding: 5px 10px 5px 0; border-bottom: 1px solid var(--line); vertical-align: top; }
.pv-table tr.flagged td:first-child { font-weight: 600; }
.pv-status { font-size: 11px; font-weight: 600; padding: 1px 7px; border-radius: 999px; background: #e3f2dd; color: #3f7d2f; }
.pv-status.bad { background: #fbe3e0; color: #8a2b22; }
</style>
