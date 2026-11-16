<script setup>
defineProps({ label: String, todo: String, owner: String })
</script>

<template>
  <div class="placeholder-page">
    <h1>{{ label }}</h1>
    <div class="card placeholder-card">
      <span class="badge">Placeholder</span>
      <p>{{ todo }}</p>
      <p class="muted">Owner: {{ owner }}</p>
    </div>
  </div>
</template>
