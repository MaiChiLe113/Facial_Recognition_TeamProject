<script setup>
import { useRoute } from 'vue-router'
import Sidebar from './components/Sidebar.vue'

const route = useRoute()
</script>

<template>
  <div class="app">
    <Sidebar v-if="!route.meta.bare" />
    <main class="main" :class="{ bare: route.meta.bare }">
      <RouterView />
    </main>
  </div>
</template>
