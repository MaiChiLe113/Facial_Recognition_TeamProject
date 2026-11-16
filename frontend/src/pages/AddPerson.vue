<script setup>
// Register a student: details, courses and 10–20 face photos (upload or webcam). The only way to register.
// The backend saves the photos to data/photos/<student_id_vn>/ and computes the face embeddings
// (TODO, Thuận Minh: recognizer.embed). This page only collects and sends them.
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { createStudent, fetchCourses, fetchStudents } from '../api.js'
import { initials } from '../format.js'

const MIN_PHOTOS = 10, MAX_PHOTOS = 20

const courses = ref(null)
const students = ref([])
const offline = ref(false)
const result = ref(null)          // { ok, message }
const saving = ref(false)

const empty = () => ({ name: '', student_id_vn: '', student_id_au: '', year: '', courses: [] })
const form = ref(empty())
const photos = ref([])            // [{ file, url }]
const fileInput = ref(null)

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
  if (photos.value.length < MIN_PHOTOS) e.photos = `Add at least ${MIN_PHOTOS} photos (${photos.value.length} so far).`
  return e
})
const touched = ref(false)
const valid = computed(() => Object.keys(errors.value).length === 0)

// ---- photos ----
function addFiles(files) {
  for (const file of files) {
    if (!file.type.startsWith('image/') || photos.value.length >= MAX_PHOTOS) continue
    photos.value.push({ file, url: URL.createObjectURL(file) })
  }
}
function onPick(e) { addFiles([...e.target.files]); e.target.value = '' }
function onDrop(e) { addFiles([...e.dataTransfer.files]) }
function removePhoto(i) {
  URL.revokeObjectURL(photos.value[i].url)
  photos.value.splice(i, 1)
}

// ---- webcam capture ----
const camVideo = ref(null)
const camOn = ref(false)
const camError = ref('')
let stream = null

async function startCamera() {
  camError.value = ''
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false })
    camOn.value = true
    await nextTick()                 // the <video> appears once camOn is true
    camVideo.value.srcObject = stream
  } catch (e) {
    camError.value = `Camera not available (${e.name || e}). Upload photos instead.`
  }
}
function stopCamera() {
  stream?.getTracks().forEach((t) => t.stop())
  stream = null
  camOn.value = false
}
function capture() {
  const v = camVideo.value
  if (!v?.videoWidth || photos.value.length >= MAX_PHOTOS) return
  const c = document.createElement('canvas')
  c.width = v.videoWidth
  c.height = v.videoHeight
  c.getContext('2d').drawImage(v, 0, 0)
  c.toBlob((blob) => {
    if (blob) addFiles([new File([blob], `webcam_${Date.now()}.jpg`, { type: 'image/jpeg' })])
  }, 'image/jpeg', 0.92)
}
onBeforeUnmount(() => {
  stopCamera()
  photos.value.forEach((p) => URL.revokeObjectURL(p.url))
})

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
  photos.value.forEach((p) => data.append('photos', p.file, p.file.name))
  saving.value = true
  const r = await createStudent(data)
  saving.value = false
  result.value = r.ok ? { ok: true, message: `${f.name.trim()} registered with ${photos.value.length} photos.` } : r
  if (r.ok) {
    photos.value.forEach((p) => URL.revokeObjectURL(p.url))
    photos.value = []
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

    <div v-if="offline || result" class="notice">
      <span v-if="offline" class="badge">offline · mock data</span>
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
          <span>Face photos <em class="muted">{{ photos.length }} / {{ MAX_PHOTOS }} · at least {{ MIN_PHOTOS }}</em></span>
          <div class="dropzone" @dragover.prevent @drop.prevent="onDrop">
            <div class="drop-actions">
              <button class="btn" type="button" :disabled="photos.length >= MAX_PHOTOS" @click="fileInput.click()">Upload photos</button>
              <button v-if="!camOn" class="btn" type="button" @click="startCamera">Use webcam</button>
              <button v-else class="btn" type="button" @click="stopCamera">Close webcam</button>
              <span class="muted small">or drop image files here</span>
            </div>
            <input ref="fileInput" type="file" accept="image/*" multiple hidden @change="onPick" />
            <small v-if="camError" class="error">{{ camError }}</small>

            <div v-if="camOn" class="capture">
              <div class="cam-view"><video ref="camVideo" autoplay muted playsinline /></div>
              <button class="btn primary" type="button" :disabled="photos.length >= MAX_PHOTOS" @click="capture">Capture photo</button>
            </div>

            <div v-if="photos.length" class="thumbs">
              <figure v-for="(p, i) in photos" :key="p.url" class="thumb">
                <img :src="p.url" :alt="`Photo ${i + 1}`" />
                <button type="button" class="thumb-remove" :aria-label="`Remove photo ${i + 1}`" @click="removePhoto(i)">×</button>
              </figure>
            </div>
            <div class="progress"><span :style="{ width: `${Math.min(100, (photos.length / MIN_PHOTOS) * 100)}%` }" /></div>
          </div>
          <small v-if="touched && errors.photos" class="error">{{ errors.photos }}</small>
        </div>

        <div class="actions">
          <button class="btn primary" type="submit" :disabled="saving">{{ saving ? 'Saving…' : '+ Register student' }}</button>
          <span class="muted small">Embeddings are computed on the backend after saving.</span>
        </div>
      </form>

      <div class="side">
        <section class="card panel">
          <header class="card-head"><h2>Photo checklist</h2></header>
          <ul class="checks tips">
            <li>Face the camera straight on</li>
            <li>Turn about 30° left and right</li>
            <li>With and without glasses</li>
            <li>Two different lighting setups</li>
            <li>Only one face in each photo</li>
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
