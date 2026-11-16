<script setup>
// Course table per session: name, student ID, attended, check-in, entry, exit, total time, link to logs.
import { computed, onMounted, ref, watch } from 'vue'
import { buildRoster, fetchCourses, fetchSessions, fetchStudents } from '../api.js'
import ClassRoster from '../components/ClassRoster.vue'
import { attended, formatDate } from '../format.js'

const courses = ref(null)
const sessions = ref([])
const students = ref([])
const offline = ref(false)
const courseKey = ref(null)
const sessionId = ref(null)
const showAll = ref(false)

onMounted(async () => {
  const [c, se, st] = await Promise.all([fetchCourses(), fetchSessions(), fetchStudents()])
  courses.value = c.items
  sessions.value = se.items
  students.value = st.items
  offline.value = c.offline || se.offline || st.offline
  courseKey.value = se.items[0]?.course_key ?? c.items[0]?.key_id ?? null
})

const course = computed(() => courses.value?.find((c) => c.key_id === courseKey.value) ?? null)
const courseSessions = computed(() => sessions.value.filter((s) => s.course_key === courseKey.value))
const session = computed(() => courseSessions.value.find((s) => s.id === sessionId.value) ?? null)

// New course -> its latest session.
watch(courseKey, () => { sessionId.value = courseSessions.value[0]?.id ?? null })

const fullRoster = computed(() => (session.value ? buildRoster(students.value, session.value) : []))
const roster = computed(() => (showAll.value ? fullRoster.value : fullRoster.value.filter((r) => r.enrolled)))
const notEnrolled = computed(() => fullRoster.value.length - fullRoster.value.filter((r) => r.enrolled).length)

const stats = computed(() => {
  const rows = fullRoster.value.filter((r) => r.enrolled)
  const present = rows.filter(attended)
  const mins = present.map((r) => r.minutes).filter((m) => m != null)
  return [
    { label: 'Enrolled', value: rows.length },
    { label: 'Attended', value: present.length, sub: rows.length ? `${Math.round((present.length / rows.length) * 100)}%` : '' },
    { label: 'Checked in, not in room', value: rows.filter((r) => r.check_in && !r.entry).length },
    { label: 'Average time in class', value: mins.length ? `${Math.round(mins.reduce((a, b) => a + b, 0) / mins.length)} min` : '—' },
  ]
})
</script>

<template>
  <div v-if="!courses" class="loading">Loading class…</div>
  <div v-else class="page">
    <header class="topbar">
      <h1>Class<template v-if="course"> · {{ course.course_id }}</template></h1>
      <div class="topbar-right">
        <div class="demo-controls">
          <select v-model="courseKey" class="input compact" aria-label="Course">
            <option v-for="c in courses" :key="c.key_id" :value="c.key_id">{{ c.course_id }} · {{ c.course_name }}</option>
          </select>
          <select v-model="sessionId" class="input compact" aria-label="Session" :disabled="!courseSessions.length">
            <option v-for="s in courseSessions" :key="s.id" :value="s.id">{{ formatDate(s.date) }} · {{ s.start }}–{{ s.end }}</option>
          </select>
        </div>
      </div>
    </header>

    <div v-if="offline" class="notice"><span class="badge">offline · mock data</span></div>

    <div v-if="!session" class="card panel empty-card">No sessions recorded for this course yet. Start one on <RouterLink to="/attend">Attend Course</RouterLink>.</div>
    <template v-else>
      <div class="stats">
        <div v-for="s in stats" :key="s.label" class="card stat">
          <div class="stat-label">{{ s.label }}</div>
          <div class="stat-value">{{ s.value }} <span v-if="s.sub" class="muted stat-sub">{{ s.sub }}</span></div>
        </div>
      </div>

      <ClassRoster :roster="roster" :title="`${formatDate(session.date)} · Room ${session.room}`" show-attended />

      <label v-if="notEnrolled" class="toggle below">
        <input v-model="showAll" type="checkbox" /> Also show {{ notEnrolled }} registered students without this course
      </label>
    </template>
  </div>
</template>
