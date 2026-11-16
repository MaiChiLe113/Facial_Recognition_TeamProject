<script setup>
import { computed } from 'vue'

const props = defineProps({ roster: { type: Array, required: true } })

const STATUS = {
  in_class: 'In class',
  left: 'Left',
  checked_in: 'Checked in',
  not_seen: 'Not seen',
  placeholder: 'TBC',
}

const initials = (name) => name.split(' ').filter(Boolean).slice(-2).map((w) => w[0]).join('').toUpperCase()
const dash = (v) => v ?? '—'

const enrolled = computed(() => props.roster.filter((r) => r.enrolled).length)
const inClass = computed(() => props.roster.filter((r) => r.status === 'in_class').length)
</script>

<template>
  <section class="card roster">
    <header class="card-head">
      <h2>Class roster</h2>
      <span class="muted">{{ enrolled }} enrolled · {{ inClass }} in class</span>
    </header>
    <table>
      <thead>
        <tr>
          <th>Student</th><th>Student ID</th><th>Status</th><th>Check-in</th>
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
          <td><span class="status" :class="r.status">{{ STATUS[r.status] ?? r.status }}</span></td>
          <td>{{ dash(r.check_in) }}</td>
          <td>{{ dash(r.entry) }}</td>
          <td>{{ dash(r.exit) }}</td>
          <td>{{ r.minutes != null ? `${r.minutes} min` : '—' }}</td>
          <td><a href="#" title="TODO: per-student log page" @click.prevent>Logs</a></td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
