<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PAGES } from '../pages.js'

const route = useRoute()
const router = useRouter()
const items = PAGES.filter((p) => p.sidebar !== false)

// Collapsed (icons only) by default; the choice is remembered in this browser.
const KEY = 'hawkeye.sidebar.expanded'
let saved = false
try { saved = localStorage.getItem(KEY) === '1' } catch { /* storage blocked */ }
const expanded = ref(saved)
watch(expanded, (v) => { try { localStorage.setItem(KEY, v ? '1' : '0') } catch { /* storage blocked */ } })
</script>

<template>
  <aside class="sidebar" :class="{ expanded }">
    <div class="brand" title="Hawkeye">{{ expanded ? 'Hawkeye' : 'H' }}</div>
    <button class="nav-item sidebar-toggle" :aria-expanded="expanded"
      :title="expanded ? 'Collapse menu' : 'Expand menu'" :aria-label="expanded ? 'Collapse menu' : 'Expand menu'"
      @click="expanded = !expanded">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
        stroke-linecap="round" stroke-linejoin="round">
        <path :d="expanded ? 'M15 6l-6 6 6 6' : 'M9 6l6 6-6 6'" />
      </svg>
      <span v-if="expanded" class="nav-label">Collapse</span>
    </button>
    <nav>
      <!-- Collapsed: icon only (more room for the cameras), the label is the tooltip. Expanded: icon + label. -->
      <button v-for="it in items" :key="it.key" class="nav-item" :class="{ active: route.name === it.key }"
        :title="it.label" :aria-label="it.label" @click="router.push(it.path)">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
          stroke-linecap="round" stroke-linejoin="round">
          <path :d="it.icon" />
        </svg>
        <span v-if="expanded" class="nav-label">{{ it.label }}</span>
      </button>
    </nav>
    <button class="add-person" :class="{ active: route.name === 'add' }" title="Add student" aria-label="Add student"
      @click="router.push('/add')">
      <span class="plus">+</span>
      <span v-if="expanded" class="nav-label">Add student</span>
    </button>
  </aside>
</template>
