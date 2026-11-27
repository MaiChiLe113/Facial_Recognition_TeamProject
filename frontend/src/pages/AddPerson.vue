<script setup>
// Register a student: details, courses and a live_face_scan (components/FaceScan.vue: live camera or an uploaded
// video; the backend keeps the best photo per head pose, checks liveness and duplicates). The only way to register.
// The backend saves the scan's photos + scan.json to data/photos/<student_id_vn>/ and embeds them for recognition.
import { computed, onMounted, ref } from 'vue'
import FaceScan from '../components/FaceScan.vue'
import { createStudent, deleteStudent, fetchCourses, fetchStudents } from '../api.js'
import { initials } from '../format.js'

const MIN_PHOTOS = 6       // kept scan photos needed to register (a full scan keeps 9: 3 poses x 3)
const MIN_UPLOAD = 5        // uploaded photos needed instead of a scan (the backend takes 1-20)
const MAX_UPLOAD = 20

const courses = ref(null)
const students = ref([])
const offline = ref(false)
const result = ref(null)          // { ok, message }
const saving = ref(false)

const empty = () => ({ name: '', student_id_vn: '', student_id_au: '', year: '', courses: [] })
const form = ref(empty())
const scan = ref(null)            // summary from FaceScan (session_id, slots, missing, done, liveness, duplicate)
const scanner = ref(null)
const faceMode = ref('scan')      // 'scan' (FaceScan: live / video) or 'upload' (photo files)
const uploads = ref([])           // [{ file, url }] when faceMode is 'upload'
const fileInput = ref(null)
function addFiles(e) {
  const files = [...(e.target.files || [])].filter((f) => f.type.startsWith('image/'))
  uploads.value = [...uploads.value, ...files.map((file) => ({ file, url: URL.createObjectURL(file) }))].slice(0, MAX_UPLOAD)
  e.target.value = ''
}
function removeUpload(i) {
  URL.revokeObjectURL(uploads.value[i].url)
  uploads.value = uploads.value.filter((_, j) => j !== i)
}
function clearUploads() { uploads.value.forEach((u) => URL.revokeObjectURL(u.url)); uploads.value = [] }
function resetForm() { form.value = empty(); touched.value = false }
const scanCount = computed(() => (scan.value ? Object.values(scan.value.slots).reduce((n, v) => n + v.length, 0) : 0))

onMounted(loadLists)
async function loadLists() {
  const [c, s] = await Promise.all([fetchCourses(), fetchStudents()])
  courses.value = c.items
  students.value = s.items
  offline.value = c.offline || s.offline
}

// ---- remove (only students added here by live scan / upload; Drive students have removable = false) ----
const removing = ref(null)
const broken = ref({})            // photo urls that failed to load: show initials instead
const removeError = ref('')
async function removeStudent(s) {
  if (!window.confirm(`Remove ${s.name} (${s.student_id_vn}) and their face photos?`)) return
  removeError.value = ''
  removing.value = s.student_id_vn
  try {
    await deleteStudent(s.student_id_vn)
    students.value = students.value.filter((x) => x.student_id_vn !== s.student_id_vn)
  } catch (e) {
    removeError.value = e.message
  } finally {
    removing.value = null
  }
}

// ---- validation ----
const errors = computed(() => {
  const f = form.value, e = {}
  if (!f.name.trim()) e.name = 'Enter the full name.'
  if (!/^SWH\d{5}$/i.test(f.student_id_vn.trim())) e.student_id_vn = 'Format: SWH followed by 5 digits, e.g. SWH02701.'
  else if (students.value.some((s) => s.student_id_vn.toUpperCase() === f.student_id_vn.trim().toUpperCase())) e.student_id_vn = 'This student is already registered.'
  if (f.student_id_au && !/^\d{9}$/.test(f.student_id_au.trim())) e.student_id_au = '9 digits, e.g. 105547489.'
  if (faceMode.value === 'upload') {
    if (uploads.value.length < MIN_UPLOAD) e.photos = `Add at least ${MIN_UPLOAD} face photos (${uploads.value.length} so far).`
  } else if (scanCount.value < MIN_PHOTOS) e.photos = `Scan the face until at least ${MIN_PHOTOS} photos are kept (${scanCount.value} so far).`
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
  const upload = faceMode.value === 'upload'
  const n = upload ? uploads.value.length : scanCount.value
  if (upload) uploads.value.forEach((u) => data.append('photos', u.file))
  else data.append('enrol_session', scan.value.session_id)
  saving.value = true
  const r = await createStudent(data)
  saving.value = false
  result.value = r.ok ? { ok: true, message: `${f.name.trim()} registered with ${n} ${upload ? 'uploaded' : 'scanned'} photos.` } : r
  if (r.ok) {
    scan.value = null
    scanner.value?.restart()
    clearUploads()
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
    </header>

    <div v-if="result" class="notice">
      <span v-if="result" :class="result.ok ? 'ok-text' : 'error'">{{ result.message }}</span>
    </div>

    <div class="page-grid add-grid">
      <form class="card panel form student-form" novalidate @submit.prevent="submit">
        <header class="card-head"><h2>Student details</h2></header>

        <section class="form-section">
          <h3><span class="step">1</span> Identity</h3>
          <label class="field">
            <span>Full name</span>
            <input v-model="form.name" class="input" placeholder="e.g. Nguyen Duc Manh" autocomplete="off" />
            <small v-if="touched && errors.name" class="error">{{ errors.name }}</small>
          </label>
          <div class="field-row ids">
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
            <label class="field">
              <span>Year</span>
              <input v-model="form.year" class="input" list="years" placeholder="K6" />
              <datalist id="years"><option v-for="y in ['K4', 'K5', 'K6', 'K7', 'K8']" :key="y" :value="y" /></datalist>
            </label>
          </div>
        </section>

        <section class="form-section">
          <h3><span class="step">2</span> Courses <em class="muted">{{ form.courses.length }} selected</em></h3>
          <div class="checks-row">
            <label v-for="c in courses" :key="c.key_id" class="check-chip" :class="{ on: form.courses.includes(c.key_id) }">
              <input v-model="form.courses" type="checkbox" :value="c.key_id" />
              <strong>{{ c.course_id }}</strong> {{ c.course_name }}
            </label>
          </div>
        </section>

        <section class="form-section">
          <h3><span class="step">3</span> Face
            <em v-if="faceMode === 'scan'" class="muted">{{ scanCount }} photos kept · at least {{ MIN_PHOTOS }}</em>
            <em v-else class="muted">{{ uploads.length }} photos · at least {{ MIN_UPLOAD }}</em>
          </h3>
          <div class="source-switch face-mode" role="tablist">
            <button type="button" class="btn" :class="{ active: faceMode === 'scan' }" @click="faceMode = 'scan'">Live face scan</button>
            <button type="button" class="btn" :class="{ active: faceMode === 'upload' }" @click="faceMode = 'upload'">Upload photos</button>
          </div>
          <div v-show="faceMode === 'scan'" class="dropzone">
            <small class="muted">The camera guides you through 3 head poses (straight, left, right) and keeps the sharpest
              photos automatically. Photos and screens are refused. Take off glasses and face masks before scanning.</small>
            <FaceScan ref="scanner" @update="scan = $event" />
          </div>
          <div v-if="faceMode === 'upload'" class="dropzone upload-zone">
            <small class="muted">Clear photos of one face: straight and slightly turned, good light, no glasses or face mask.
              {{ MIN_UPLOAD }} to {{ MAX_UPLOAD }} photos (JPG, PNG, WebP).</small>
            <input ref="fileInput" type="file" accept="image/*" multiple hidden @change="addFiles" />
            <div class="drop-actions">
              <button class="btn primary" type="button" :disabled="uploads.length >= MAX_UPLOAD" @click="fileInput.click()">+ Add images</button>
              <button v-if="uploads.length" class="btn" type="button" @click="clearUploads">Clear all</button>
            </div>
            <div v-if="uploads.length" class="thumbs upload-thumbs">
              <figure v-for="(u, i) in uploads" :key="u.url" class="thumb">
                <img :src="u.url" :alt="`photo ${i + 1}`" />
                <button type="button" class="thumb-remove" aria-label="Remove photo" @click="removeUpload(i)">×</button>
              </figure>
            </div>
          </div>
          <small v-if="touched && errors.photos" class="error">{{ errors.photos }}</small>
        </section>

        <div class="actions form-actions">
          <button class="btn" type="button" :disabled="saving" @click="resetForm">Reset</button>
          <button class="btn primary" type="submit" :disabled="saving">{{ saving ? 'Saving…' : '+ Register student' }}</button>
        </div>
      </form>

      <div class="side">
        <section class="card panel">
          <header class="card-head"><h2>Scan tips</h2></header>
          <ul class="checks tips">
            <li>Use a phone (better camera) through the Wi-Fi demo link</li>
            <li>Face a window or a lamp, not a bright background</li>
            <li>Follow the hint: straight, left, right</li>
            <li>Move slowly; a green box means the photo is good</li>
            <li>Only one person close to the camera</li>
          </ul>
        </section>

        <section class="card roster">
          <header class="card-head"><h2>Registered</h2><span class="muted">{{ students.length }} students</span></header>
          <table>
            <thead><tr><th>Student</th><th>ID (VN)</th><th>Courses</th><th></th></tr></thead>
            <tbody>
              <tr v-for="s in students" :key="s.student_id_vn">
                <td class="student">
                  <img v-if="s.photo && !broken[s.photo]" :src="s.photo" :alt="s.name" class="avatar photo" loading="lazy"
                    @error="broken[s.photo] = true" />
                  <span v-else class="avatar photo">{{ initials(s.name) }}</span>
                  <strong>{{ s.name }}</strong>
                </td>
                <td>{{ s.student_id_vn }}</td>
                <td>{{ s.courses.length ? s.courses.map(courseName).join(', ') : '—' }}</td>
                <td class="remove-cell">
                  <button v-if="s.removable" type="button" class="row-remove" :disabled="removing === s.student_id_vn"
                    :title="`Remove ${s.name}`" :aria-label="`Remove ${s.name}`" @click="removeStudent(s)">×</button>
                </td>
              </tr>
            </tbody>
          </table>
          <small v-if="removeError" class="error">{{ removeError }}</small>
        </section>
      </div>
    </div>
  </div>
</template>
