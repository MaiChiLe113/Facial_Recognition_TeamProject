<script setup>
import { computed, ref, watch } from 'vue'
import { CAMERA } from '../format.js'

const props = defineProps({
  events: { type: Array, required: true },
  title: { type: String, default: 'Event log' },
  showDate: { type: Boolean, default: false },      // History page: events from several sessions
  highlightLatest: { type: Boolean, default: true },
  pageSize: { type: Number, default: 8 },
})

const page = ref(1)
const pages = computed(() => Math.max(1, Math.ceil(props.events.length / props.pageSize)))
const shown = computed(() => props.events.slice((page.value - 1) * props.pageSize, page.value * props.pageSize))
// Fewer events (new filter / session, Demo scrubbed back) -> first page. More events (Demo playing)
// keep the page; it only moves if it no longer exists.
watch(() => props.events.length, (n, old) => {
  if (n < old) page.value = 1
  else if (page.value > pages.value) page.value = pages.value
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
        <tr v-for="(e, i) in shown" :key="i" :class="{ latest: highlightLatest && page === 1 && i === 0 }">
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
    <nav v-if="pages > 1" class="pager">
      <button class="btn" :disabled="page === 1" @click="page--">‹ Prev</button>
      <span class="muted">Page {{ page }} / {{ pages }} · {{ events.length }} events</span>
      <button class="btn" :disabled="page === pages" @click="page++">Next ›</button>
    </nav>
  </section>
</template>
