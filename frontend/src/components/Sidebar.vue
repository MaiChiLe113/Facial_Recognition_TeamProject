<script setup>
import { useRoute, useRouter } from 'vue-router'
import { PAGES } from '../pages.js'

const route = useRoute()
const router = useRouter()
const items = PAGES.filter((p) => p.sidebar !== false)
</script>

<template>
  <aside class="sidebar">
    <div class="brand" title="Hawkeye">H</div>
    <nav>
      <!-- Icon only (more room for the cameras); the label is the tooltip and the accessible name. -->
      <button v-for="it in items" :key="it.key" class="nav-item" :class="{ active: route.name === it.key }"
        :title="it.label" :aria-label="it.label" @click="router.push(it.path)">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
          stroke-linecap="round" stroke-linejoin="round">
          <path :d="it.icon" />
        </svg>
      </button>
    </nav>
    <button class="add-person" :class="{ active: route.name === 'add' }" title="Add student" aria-label="Add student"
      @click="router.push('/add')">
      <span class="plus">+</span>
    </button>
  </aside>
</template>
