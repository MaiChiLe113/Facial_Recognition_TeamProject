<script setup>
import { useRoute, useRouter } from 'vue-router'
import { PAGES } from '../pages.js'

const route = useRoute()
const router = useRouter()
const items = PAGES.filter((p) => p.sidebar !== false)
</script>

<template>
  <aside class="sidebar">
    <div class="brand">Hawkeye</div>
    <nav>
      <button v-for="it in items" :key="it.key" class="nav-item" :class="{ active: route.name === it.key }"
        @click="router.push(it.path)">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
          stroke-linecap="round" stroke-linejoin="round">
          <path :d="it.icon" />
        </svg>
        <span>{{ it.label }}</span>
      </button>
    </nav>
    <button class="add-person" :class="{ active: route.name === 'add' }" @click="router.push('/add')">
      <span class="plus">+</span> Add person
    </button>
  </aside>
</template>
