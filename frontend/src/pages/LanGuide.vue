<script setup>
// The Wi-Fi demo guide, shown in the app so nobody has to open the repo. The text is docs/LAN_DEMO.md itself,
// imported raw: in `npm run dev` Vite hot-reloads this page when the file changes; a build bundles the file as it was.
import { marked } from 'marked'
import md from '../../../docs/LAN_DEMO.md?raw'

const html = marked.parse(md)
</script>

<template>
  <div class="page">
    <header class="topbar">
      <h1>Wi-Fi demo guide</h1>
      <RouterLink class="btn" to="/">Back to Home</RouterLink>
    </header>
    <!-- Our own repo file, so its HTML is trusted. -->
    <article class="card panel md" v-html="html" />
  </div>
</template>

<style scoped>
/* Centred reading column: wide enough for the tables and commands, narrow enough to read comfortably. */
.page { max-width: 1080px; width: 100%; margin: 0 auto; }
.md { line-height: 1.6; padding: 32px 40px; }
@media (max-width: 700px) { .md { padding: var(--space-4); } }
.md :deep(h1) { font-size: 22px; margin: 0 0 var(--space-4); }
.md :deep(h2) { font-size: 17px; margin: var(--space-5) 0 var(--space-2); padding-top: var(--space-4); border-top: 1px solid var(--line); }
.md :deep(h3) { font-size: 15px; margin: var(--space-4) 0 var(--space-2); }
.md :deep(p), .md :deep(ul), .md :deep(ol) { margin: 0 0 var(--space-3); }
.md :deep(li) { margin-bottom: var(--space-1); }
.md :deep(code) { font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace; font-size: 12px; background: var(--bg); border: 1px solid var(--line); border-radius: 4px; padding: 1px 5px; }
.md :deep(pre) { background: var(--bg); border: 1px solid var(--line); border-radius: 8px; padding: var(--space-3) var(--space-4); overflow-x: auto; margin: 0 0 var(--space-3); }
.md :deep(pre code) { border: 0; padding: 0; background: none; }
.md :deep(table) { margin: 0 0 var(--space-3); border: 1px solid var(--line); }
.md :deep(th) { background: var(--bg); }
.md :deep(a) { color: var(--green); }
.md :deep(blockquote) { margin: 0 0 var(--space-3); padding: var(--space-2) var(--space-4); border-left: 3px solid var(--accent-strong); background: var(--bg); }
</style>
