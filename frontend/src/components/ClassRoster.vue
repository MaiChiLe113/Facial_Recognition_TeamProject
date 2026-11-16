<script setup>
import { computed } from 'vue'
import { STATUS, attended, dash, initials, minutes } from '../format.js'

const props = defineProps({
  roster: { type: Array, required: true },
  title: { type: String, default: 'Class roster' },
  showAttended: { type: Boolean, default: false },   // Class page: adds the Attended yes/no column
})

const enrolled = computed(() => props.roster.filter((r) => r.enrolled).length)
const inClass = computed(() => props.roster.filter((r) => r.status === 'in_class').length)
</script>

<template>
  <section class="card roster">
    <header class="card-head">
      <h2>{{ title }}</h2>
      <span class="muted">{{ enrolled }} enrolled · {{ inClass }} in class</span>
    </header>
    <table>
      <thead>
        <tr>
          <th>Student</th><th>Student ID</th><th v-if="showAttended">Attended</th><th>Status</th><th>Check-in</th>
          <th>Entry</th><th>Exit</th><th>Duration</th><th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in roster" :key="i" :class="{ 'placeholder-row': r.status === 'placeholder' }">
          <td class="student">
            <!-- TODO: show the first registration photo when photo != null -->
            <span class="avatar">{{ initials(r.name) }}</span>
            <span>
              <strong>{{ r.name }}</strong>
              <span v-if="!r.enrolled && r.status !== 'placeholder'" class="tag">course not set</span>
              <span v-if="r.note" class="tag">{{ r.note }}</span>
            </span>
          </td>
          <td>{{ dash(r.student_id) }}</td>
          <td v-if="showAttended"><span class="yesno" :class="attended(r) ? 'yes' : 'no'">{{ attended(r) ? 'Yes' : 'No' }}</span></td>
          <td><span class="status" :class="r.status">{{ STATUS[r.status] ?? r.status }}</span></td>
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
  </section>
</template>
