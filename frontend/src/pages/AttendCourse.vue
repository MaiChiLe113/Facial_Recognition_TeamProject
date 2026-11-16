<script setup>
// Pick the course + session (e.g. COS30082, Room 204) to start taking attendance.
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchCourses, fetchStudents } from '../api.js'
import { activeSession, setActiveSession } from '../activeSession.js'
import { formatDate, parseSessionTime, todayIso } from '../format.js'

const router = useRouter()
const courses = ref(null)
const students = ref([])
const offline = ref(false)
const message = ref('')

const form = ref({ course_key: null, room: '', date: todayIso(), start: '', end: '' })

onMounted(async () => {
  const [c, s] = await Promise.all([fetchCourses(), fetchStudents()])
  courses.value = c.items
  students.value = s.items
  offline.value = c.offline || s.offline
  if (c.items.length) pick(c.items[0].key_id)
})

const course = computed(() => courses.value?.find((c) => c.key_id === form.value.course_key) ?? null)
const enrolledIn = (key) => students.value.filter((s) => s.courses.includes(key)).length

// Choosing a course fills in its usual room and time.
function pick(key) {
  form.value.course_key = key
}
watch(course, (c) => {
  if (!c) return
  const t = parseSessionTime(c.session_time)
  Object.assign(form.value, { room: c.room, start: t.start, end: t.end })
})

const valid = computed(() => course.value && form.value.room && form.value.date && form.value.start && form.value.end
  && form.value.start < form.value.end)

function start() {
  if (!valid.value) return
  // TODO (Đức Mạnh): POST /api/sessions so the backend opens the session and the cameras start logging.
  setActiveSession({
    course_key: course.value.key_id, course_id: course.value.course_id, course_name: course.value.course_name,
    room: form.value.room, date: form.value.date, start: form.value.start, end: form.value.end,
    started_at: new Date().toISOString(),
  })
  message.value = `Attendance started for ${course.value.course_id} · Room ${form.value.room}.`
}

function stop() {
  setActiveSession(null)
  message.value = 'Attendance stopped.'
}
</script>

<template>
  <div v-if="!courses" class="loading">Loading courses…</div>
  <div v-else class="page">
    <header class="topbar">
      <h1>Attend Course</h1>
      <div class="topbar-right">
        <RouterLink v-if="activeSession" class="btn" to="/">Open live view</RouterLink>
      </div>
    </header>

    <div v-if="offline || message" class="notice">
      <span v-if="offline" class="badge">offline · mock data</span>
      <span v-if="message">{{ message }}</span>
    </div>

    <section v-if="activeSession" class="card panel active-session">
      <span class="dot on" />
      <div class="grow">
        <div class="cam-title">{{ activeSession.course_id }} · Room {{ activeSession.room }}</div>
        <div class="muted">
          {{ activeSession.course_name }} · {{ formatDate(activeSession.date) }} · {{ activeSession.start }}–{{ activeSession.end }}
        </div>
      </div>
      <span class="badge">taking attendance</span>
      <button class="btn" @click="stop">Stop</button>
    </section>

    <div class="page-grid">
      <section class="card panel">
        <header class="card-head"><h2>New session</h2></header>
        <form class="form" @submit.prevent="start">
          <label class="field">
            <span>Course</span>
            <select v-model="form.course_key" class="input">
              <option v-for="c in courses" :key="c.key_id" :value="c.key_id">{{ c.course_id }} · {{ c.course_name }}</option>
            </select>
          </label>
          <div class="field-row">
            <label class="field"><span>Room</span><input v-model.trim="form.room" class="input" required /></label>
            <label class="field"><span>Date</span><input v-model="form.date" type="date" class="input" required /></label>
          </div>
          <div class="field-row">
            <label class="field"><span>Start</span><input v-model="form.start" type="time" class="input" required /></label>
            <label class="field"><span>End</span><input v-model="form.end" type="time" class="input" required /></label>
          </div>
          <p v-if="form.start && form.end && form.start >= form.end" class="error">End must be after start.</p>
          <p v-if="course" class="muted small">
            {{ enrolledIn(course.key_id) }} students enrolled · usual time {{ course.session_time }}
          </p>
          <div class="actions">
            <button class="btn primary" type="submit" :disabled="!valid">▶ Start attendance</button>
            <button v-if="activeSession" class="btn" type="button" @click="router.push('/')">Go to Home</button>
          </div>
        </form>
      </section>

      <section class="card roster">
        <header class="card-head">
          <h2>Courses</h2>
          <span class="muted">{{ courses.length }} courses</span>
        </header>
        <table>
          <thead>
            <tr><th>Code</th><th>Name</th><th>Schedule</th><th>Room</th><th>Enrolled</th></tr>
          </thead>
          <tbody>
            <tr v-for="c in courses" :key="c.key_id" class="clickable" :class="{ selected: c.key_id === form.course_key }"
              @click="pick(c.key_id)">
              <td><strong>{{ c.course_id }}</strong></td>
              <td>{{ c.course_name }}</td>
              <td>{{ c.session_time }}</td>
              <td>{{ c.room }}</td>
              <td>{{ enrolledIn(c.key_id) }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </div>
</template>
