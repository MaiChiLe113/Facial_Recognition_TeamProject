import { createRouter, createWebHistory } from 'vue-router'
import { PAGES } from './pages.js'
import Placeholder from './pages/Placeholder.vue'

const routes = PAGES.map((p) => ({
  path: p.path,
  name: p.key,
  meta: { bare: !!p.bare },
  component: p.component ?? Placeholder,
  props: p.component ? false : { label: p.label, todo: p.todo, owner: p.owner },
}))
routes.push({ path: '/class', redirect: '/history' })   // Class was merged into History
// MultiCam (/demo) and Live cameras (/live) were merged into Home; old links still work.
routes.push({ path: '/demo', redirect: (to) => ({ path: '/', query: { source: 'recorded', ...(to.query.take ? { take: to.query.take } : {}) } }) })
routes.push({ path: '/live', redirect: '/' })
routes.push({ path: '/:pathMatch(.*)*', redirect: '/' })

export default createRouter({ history: createWebHistory(), routes })
