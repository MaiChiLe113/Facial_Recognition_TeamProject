<script setup>
// Past sessions and their logs, filtered by student and date. ?student=<id> preselects a student (Logs links).
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { buildRoster, fetchCourses, fetchSessions, fetchStudents } from '../api.js'
import EventLog from '../components/EventLog.vue'
import { attended, formatDate, initials } from '../format.js'

const route = useRoute()
const router = useRouter()
const courses = ref(null)
const sessions = ref([])
const students = ref([])
const offline = ref(false)

const filters = ref({ student: route.query.student || '', course: '', from: '', to: '' })
const sessionId = ref(null)          // one session picked from the list, or null for all

onMounted(async () => {
  const [c, se, st] = await Promise.all([fetchCourses(), fetchSessions(), fetchStudents()])
  courses.value = c.items
  sessions.value = se.items
  students.value = st.items
  offline.value = c.offline || se.offline || st.offline
})

// Keep the student filter in the URL so a Logs link can be shared or reloaded.
watch(() => filters.value.student, (student) => {
  router.replace({ query: student ? { student } : {} })
})
watch(() => route.query.student, (s) => { filters.value.student = s || '' })

const courseOf = (key) => courses.value?.find((c) => c.key_id === key)
const student = computed(() => students.value.find((s) => s.student_id_vn === filters.value.student) ?? null)

const shownSessions = computed(() => sessions.value.filter((s) => {
  const f = filters.value
  if (f.course && s.course_key !== Number(f.course)) return false
  if (f.from && s.date < f.from) return false
  if (f.to && s.date > f.to) return false
  if (f.student) return students.value.find((st) => st.student_id_vn === f.student)?.courses.includes(s.course_key)
    || s.attendance.some((a) => a.student_id_vn === f.student)
  return true
}))

// If the picked session is filtered out, fall back to all.
watch(shownSessions, (list) => { if (sessionId.value && !list.some((s) => s.id === sessionId.value)) sessionId.value = null })

const rowFor = (s) => {
  const roster = buildRoster(students.value, s).filter((r) => r.enrolled)
  if (student.value) {
    const me = roster.find((r) => r.student_id === student.value.student_id_vn)
    return { present: me && attended(me) ? 'Yes' : 'No', minutes: me?.minutes }
  }
  return { present: `${roster.filter(attended).length} / ${roster.length}`, minutes: null }
}

const events = computed(() => shownSessions.value
  .filter((s) => !sessionId.value || s.id === sessionId.value)
  .flatMap((s) => s.events.map((e) => ({ ...e, date: s.date })))
  .filter((e) => !filters.value.student || e.student_id === filters.value.student))

const summary = computed(() => {
  if (!student.value) return null
  const rows = shownSessions.value.map(rowFor)
  return {
    sessions: rows.length,
    attended: rows.filter((r) => r.present === 'Yes').length,
    minutes: rows.reduce((sum, r) => sum + (r.minutes || 0), 0),
  }
})

function reset() {
  filters.value = { student: '', course: '', from: '', to: '' }
  sessionId.value = null
}
const toggleSession = (id) => { sessionId.value = sessionId.value === id ? null : id }
</script>

<template>
  <div v-if="!courses" class="loading">Loading history…</div>
  <div v-else class="page">
    <header class="topbar">
      <h1>History</h1>
      <div class="topbar-right">
        <div class="demo-controls">
          <select v-model="filters.student" class="input compact" aria-label="Student">
            <option value="">All students</option>
            <option v-for="s in students" :key="s.student_id_vn" :value="s.student_id_vn">{{ s.name }}</option>
          </select>
          <select v-model="filters.course" class="input compact" aria-label="Course">
            <option value="">All courses</option>
            <option v-for="c in courses" :key="c.key_id" :value="c.key_id">{{ c.course_id }}</option>
          </select>
          <label class="toggle">From <input v-model="filters.from" type="date" class="input compact" /></label>
          <label class="toggle">To <input v-model="filters.to" type="date" class="input compact" /></label>
          <button class="btn" @click="reset">Reset</button>
        </div>
      </div>
    </header>

    <div v-if="offline" class="notice"><span class="badge">offline · mock data</span></div>

    <section v-if="student" class="card panel active-session">
      <span class="avatar">{{ initials(student.name) }}</span>
      <div class="grow">
        <div class="cam-title">{{ student.name }}</div>
        <div class="muted">{{ student.student_id_vn }} · AU {{ student.student_id_au || '—' }} · {{ student.year || '—' }}</div>
      </div>
      <div class="mini-stats">
        <div><strong>{{ summary.attended }} / {{ summary.sessions }}</strong><span class="muted">sessions attended</span></div>
        <div><strong>{{ summary.minutes }} min</strong><span class="muted">time in class</span></div>
      </div>
    </section>

    <div class="page-grid history-grid">
      <section class="card roster">
        <header class="card-head">
          <h2>Sessions</h2>
          <span class="muted">{{ shownSessions.length }} found<template v-if="sessionId"> · 1 selected</template></span>
        </header>
        <table>
          <thead>
            <tr><th>Date</th><th>Course</th><th>Time</th><th>Room</th><th>{{ student ? 'Attended' : 'Present' }}</th><th v-if="student">Duration</th></tr>
          </thead>
          <tbody>
            <tr v-for="s in shownSessions" :key="s.id" class="clickable" :class="{ selected: s.id === sessionId }"
              @click="toggleSession(s.id)">
              <td>{{ formatDate(s.date) }}</td>
              <td><strong>{{ courseOf(s.course_key)?.course_id }}</strong></td>
              <td>{{ s.start }}–{{ s.end }}</td>
              <td>{{ s.room }}</td>
              <td>
                <span v-if="student" class="yesno" :class="rowFor(s).present === 'Yes' ? 'yes' : 'no'">{{ rowFor(s).present }}</span>
                <template v-else>{{ rowFor(s).present }}</template>
              </td>
              <td v-if="student">{{ rowFor(s).minutes != null ? `${rowFor(s).minutes} min` : '—' }}</td>
            </tr>
            <tr v-if="!shownSessions.length"><td colspan="6" class="empty">No sessions match these filters.</td></tr>
          </tbody>
        </table>
      </section>

      <EventLog :events="events" show-date :highlight-latest="false"
        :title="sessionId ? 'Event log · selected session' : 'Event log'" />
    </div>
  </div>
</template>
