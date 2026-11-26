<script setup>
// Register a student: details, courses and an AI face scan (components/FaceScan.vue: live camera or an uploaded
// video; the backend keeps the best photo per head pose, checks liveness and duplicates). The only way to register.
// The backend saves the scan's photos + scan.json to data/photos/<student_id_vn>/ and embeds them for recognition.
import { computed, onMounted, ref } from 'vue'
import FaceScan from '../components/FaceScan.vue'
import { createStudent, fetchCourses, fetchStudents } from '../api.js'
import { initials } from '../format.js'

const MIN_PHOTOS = 10      // kept scan photos needed to register (a full scan keeps 15)

const courses = ref(null)
const students = ref([])
const offline = ref(false)
const result = ref(null)          // { ok, message }
const saving = ref(false)

const empty = () => ({ name: '', student_id_vn: '', student_id_au: '', year: '', courses: [] })
const form = ref(empty())
const scan = ref(null)            // summary from FaceScan (session_id, slots, missing, done, liveness, duplicate)
const scanner = ref(null)
const scanCount = computed(() => (scan.value ? Object.values(scan.value.slots).reduce((n, v) => n + v.length, 0) : 0))

onMounted(loadLists)
async function loadLists() {
  const [c, s] = await Promise.all([fetchCourses(), fetchStudents()])
  courses.value = c.items
  students.value = s.items
  offline.value = c.offline || s.offline
}

// ---- validation ----
const errors = computed(() => {
  const f = form.value, e = {}
  if (!f.name.trim()) e.name = 'Enter the full name.'
  if (!/^SWH\d{5}$/i.test(f.student_id_vn.trim())) e.student_id_vn = 'Format: SWH followed by 5 digits, e.g. SWH02701.'
  else if (students.value.some((s) => s.student_id_vn.toUpperCase() === f.student_id_vn.trim().toUpperCase())) e.student_id_vn = 'This student is already registered.'
  if (f.student_id_au && !/^\d{9}$/.test(f.student_id_au.trim())) e.student_id_au = '9 digits, e.g. 105547489.'
  if (scanCount.value < MIN_PHOTOS) e.photos = `Scan the face until at least ${MIN_PHOTOS} photos are kept (${scanCount.value} so far).`
  else if (scan.value?.liveness?.live === false) e.photos = 'The liveness check failed: scan a real face again.'
  return e
})
const touched = ref(false)
const valid = computed(() => Object.keys(errors.value).length === 0)

// ---- submit ----
async function submit() {
  touched.value = true
  result.value = null
  if (!valid.value) return
  const f = form.value
  const data = new FormData()
  data.append('name', f.name.trim())
  data.append('student_id_vn', f.student_id_vn.trim().toUpperCase())
  data.append('student_id_au', f.student_id_au.trim())
  data.append('year', f.year.trim())
  data.append('courses', JSON.stringify(f.courses))
  data.append('enrol_session', scan.value.session_id)
  saving.value = true
  const r = await createStudent(data)
  saving.value = false
  result.value = r.ok ? { ok: true, message: `${f.name.trim()} registered with ${scanCount.value} scanned photos.` } : r
  if (r.ok) {
    scan.value = null
    scanner.value?.restart()
    form.value = empty()
    touched.value = false
    loadLists()
  }
}

const courseName = (key) => courses.value?.find((c) => c.key_id === key)?.course_id ?? key
</script>

<template>
  <div v-if="!courses" class="loading">Loading…</div>
  <div v-else class="page">
    <header class="topbar">
      <h1>Add person</h1>
      <div class="topbar-right">
        <span class="muted">{{ students.length }} registered</span>
      </div>
    </header>

    <div v-if="result" class="notice">
      <span v-if="result" :class="result.ok ? 'ok-text' : 'error'">{{ result.message }}</span>
    </div>

    <div class="page-grid add-grid">
      <form class="card panel form" novalidate @submit.prevent="submit">
        <header class="card-head"><h2>Student details</h2></header>

        <label class="field">
          <span>Full name</span>
          <input v-model="form.name" class="input" placeholder="e.g. Nguyen Duc Manh" autocomplete="off" />
          <small v-if="touched && errors.name" class="error">{{ errors.name }}</small>
        </label>
        <div class="field-row">
          <label class="field">
            <span>Student ID (VN)</span>
            <input v-model="form.student_id_vn" class="input" placeholder="SWH02701" autocomplete="off" />
            <small v-if="touched && errors.student_id_vn" class="error">{{ errors.student_id_vn }}</small>
          </label>
          <label class="field">
            <span>Student ID (AU) <em class="muted">optional</em></span>
            <input v-model="form.student_id_au" class="input" placeholder="105547489" inputmode="numeric" autocomplete="off" />
            <small v-if="touched && errors.student_id_au" class="error">{{ errors.student_id_au }}</small>
          </label>
        </div>
        <label class="field narrow">
          <span>Year</span>
          <input v-model="form.year" class="input" list="years" placeholder="K6" />
          <datalist id="years"><option v-for="y in ['K4', 'K5', 'K6', 'K7', 'K8']" :key="y" :value="y" /></datalist>
        </label>

        <fieldset class="field">
          <span>Courses</span>
          <div class="checks-row">
            <label v-for="c in courses" :key="c.key_id" class="check-chip" :class="{ on: form.courses.includes(c.key_id) }">
              <input v-model="form.courses" type="checkbox" :value="c.key_id" />
              <strong>{{ c.course_id }}</strong> {{ c.course_name }}
            </label>
          </div>
        </fieldset>

        <div class="field">
          <span>Face scan <em class="muted">{{ scanCount }} photos kept · at least {{ MIN_PHOTOS }}</em></span>
          <small class="muted">The camera guides you through 5 head poses and keeps the sharpest photos automatically.
            Photos and screens are refused. If you sometimes wear glasses, scan once with them on.</small>
          <div class="dropzone">
            <FaceScan ref="scanner" @update="scan = $event" />
          </div>
          <small v-if="touched && errors.photos" class="error">{{ errors.photos }}</small>
        </div>

        <div class="actions">
          <button class="btn primary" type="submit" :disabled="saving">{{ saving ? 'Saving…' : '+ Register student' }}</button>
          <span class="muted small">The scanned photos are embedded on the backend after saving.</span>
        </div>
      </form>

      <div class="side">
        <section class="card panel">
          <header class="card-head"><h2>Scan tips</h2></header>
          <ul class="checks tips">
            <li>Use a phone (better camera) through the Wi-Fi demo link</li>
            <li>Face a window or a lamp, not a bright background</li>
            <li>Follow the hint: straight, left, right, chin up, chin down</li>
            <li>Move slowly; a green box means the photo is good</li>
            <li>Only one person close to the camera</li>
          </ul>
        </section>

        <section class="card roster">
          <header class="card-head"><h2>Registered</h2><span class="muted">{{ students.length }} students</span></header>
          <table>
            <thead><tr><th>Student</th><th>ID (VN)</th><th>Courses</th></tr></thead>
            <tbody>
              <tr v-for="s in students" :key="s.student_id_vn">
                <td class="student"><span class="avatar">{{ initials(s.name) }}</span><strong>{{ s.name }}</strong></td>
                <td>{{ s.student_id_vn }}</td>
                <td>{{ s.courses.length ? s.courses.map(courseName).join(', ') : '—' }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </div>
  </div>
</template>
