<script setup>
defineProps({ events: { type: Array, required: true } })

const SOURCE = { cam_1: 'CAM 1', cam_2: 'CAM 2', attendance_cam: 'Doorway' }
</script>

<template>
  <section class="card event-log">
    <h2>Event log</h2>
    <table>
      <thead>
        <tr><th>Time</th><th>Event</th><th class="right">Source</th></tr>
      </thead>
      <tbody>
        <tr v-for="(e, i) in events" :key="i" :class="{ latest: i === 0 }">
          <td>{{ e.time }}</td>
          <td>{{ e.event }}</td>
          <td class="right">{{ SOURCE[e.source] ?? e.source }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
