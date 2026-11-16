<script setup>
import { CAMERA } from '../format.js'

defineProps({
  events: { type: Array, required: true },
  title: { type: String, default: 'Event log' },
  showDate: { type: Boolean, default: false },      // History page: events from several sessions
  highlightLatest: { type: Boolean, default: true },
})
</script>

<template>
  <section class="card event-log">
    <h2>{{ title }}</h2>
    <table>
      <thead>
        <tr><th v-if="showDate">Date</th><th>Time</th><th>Event</th><th class="right">Source</th></tr>
      </thead>
      <tbody>
        <tr v-for="(e, i) in events" :key="i" :class="{ latest: highlightLatest && i === 0 }">
          <td v-if="showDate">{{ e.date }}</td>
          <td>{{ e.time }}</td>
          <td>{{ e.event }}</td>
          <td class="right">{{ CAMERA[e.source] ?? e.source }}</td>
        </tr>
        <tr v-if="!events.length">
          <td :colspan="showDate ? 4 : 3" class="empty">No events match.</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
