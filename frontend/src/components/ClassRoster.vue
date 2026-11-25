<script setup>
import { computed, reactive, ref } from 'vue'
import { updateAttendance } from '../api.js'
import { STATUS, attended, dash, initials, minutes } from '../format.js'

const props = defineProps({
  roster: { type: Array, required: true },
  title: { type: String, default: 'Class roster' },
  showAttended: { type: Boolean, default: false },   // History page: adds the Attended yes/no column
  editable: { type: Boolean, default: false },       // History page: Attended and Status can be changed by hand
  sessionId: { type: [Number, String], default: null },   // where edits are saved (PATCH .../attendance/...)
})
const emit = defineEmits(['saved'])

// Manual changes, keyed by student ID: shown at once, saved to SQLite, kept on screen if saving fails.
const edits = reactive({})
const saveError = ref('')
const keyOf = (r, i) => r.student_id ?? `row-${i}`
const attendedOf = (r, i) => edits[keyOf(r, i)]?.attended ?? attended(r)
const statusOf = (r, i) => edits[keyOf(r, i)]?.status ?? r.status
async function setEdit(r, i, field, value) {
  edits[keyOf(r, i)] = { ...edits[keyOf(r, i)], [field]: value }
  if (props.sessionId == null || !r.student_id) return
  const res = await updateAttendance(props.sessionId, r.student_id, { [field]: value })
  saveError.value = res.ok ? '' : res.message
  if (res.ok) emit('saved', { studentId: r.student_id, row: res.row })
}

// A photo that fails to load (backend off, file missing) falls back to the initials.
const broken = reactive({})

const enrolled = computed(() => props.roster.filter((r) => r.enrolled).length)
const inClass = computed(() => props.roster.filter((r, i) => statusOf(r, i) === 'in_class').length)
const STATUS_CHOICES = Object.keys(STATUS).filter((k) => k !== 'placeholder')
</script>

<template>
  <section class="card roster">
    <header class="card-head">
      <h2>{{ title }}</h2>
      <span class="muted">
        <span v-if="saveError" class="save-error">{{ saveError }} · </span>{{ enrolled }} enrolled · {{ inClass }} in class
      </span>
    </header>
    <!-- Wide table: it scrolls sideways inside the card on narrow screens instead of spilling out of the page. -->
    <div class="table-scroll">
    <table>
      <thead>
        <tr>
          <th>Student</th><th>Student ID</th><th v-if="showAttended">Attended</th><th>Status</th><th>Check-in</th>
          <th>Entry</th><th>Exit</th><th>Duration</th><th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in roster" :key="keyOf(r, i)" :class="{ 'placeholder-row': r.status === 'placeholder' }">
          <td class="student">
            <img v-if="r.photo && !broken[r.photo]" :src="r.photo" :alt="r.name" class="avatar photo"
              loading="lazy" @error="broken[r.photo] = true" />
            <span v-else class="avatar">{{ initials(r.name) }}</span>
            <span>
              <strong>{{ r.name }}</strong>
              <span v-if="!r.enrolled && r.status !== 'placeholder'" class="tag">course not set</span>
              <span v-if="r.note" class="tag">{{ r.note }}</span>
            </span>
          </td>
          <td>{{ dash(r.student_id) }}</td>
          <td v-if="showAttended">
            <select v-if="editable && r.student_id" class="yesno pick" :class="attendedOf(r, i) ? 'yes' : 'no'"
              :value="attendedOf(r, i) ? 'yes' : 'no'" aria-label="Attended"
              @change="setEdit(r, i, 'attended', $event.target.value === 'yes')">
              <option value="yes">Yes</option><option value="no">No</option>
            </select>
            <span v-else class="yesno" :class="attendedOf(r, i) ? 'yes' : 'no'">{{ attendedOf(r, i) ? 'Yes' : 'No' }}</span>
          </td>
          <td>
            <select v-if="editable && r.student_id" class="status pick" :class="statusOf(r, i)" :value="statusOf(r, i)"
              aria-label="Status" @change="setEdit(r, i, 'status', $event.target.value)">
              <option v-for="k in STATUS_CHOICES" :key="k" :value="k">{{ STATUS[k] }}</option>
            </select>
            <span v-else class="status" :class="statusOf(r, i)">{{ STATUS[statusOf(r, i)] ?? statusOf(r, i) }}</span>
          </td>
          <td>{{ dash(r.check_in) }}</td>
          <td>{{ dash(r.entry) }}</td>
          <td>{{ dash(r.exit) }}</td>
          <td>{{ minutes(r.minutes) }}</td>
          <td>
            <RouterLink v-if="r.student_id" :to="{ path: '/history', query: { student: r.student_id } }">Logs</RouterLink>
          </td>
        </tr>
      </tbody>
    </table>
    </div>
  </section>
</template>
