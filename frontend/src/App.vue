<script setup>
import Sidebar from './components/Sidebar.vue'
</script>

<template>
  <div class="app">
    <Sidebar />
    <main class="main">
      <RouterView />
    </main>
  </div>
</template>
