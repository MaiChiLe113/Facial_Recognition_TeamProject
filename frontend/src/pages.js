// Page registry (design doc section 7). The router and the sidebar are both built
// from this list, so adding a page = adding one entry here.
//   component  the page to show. Leave it out to show the Placeholder card (todo + owner).
//   icon       SVG path for the sidebar. Pages with sidebar: false are reached another way.
import AddPerson from './pages/AddPerson.vue'
import AttendCourse from './pages/AttendCourse.vue'
import ClassPage from './pages/ClassPage.vue'
import Demo from './pages/Demo.vue'
import History from './pages/History.vue'
import Home from './pages/Home.vue'

export const PAGES = [
  { key: 'home', path: '/', label: 'Home', component: Home,
    icon: 'M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z' },
  { key: 'attend', path: '/attend', label: 'Attend Course', component: AttendCourse,
    icon: 'M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M12 9a2 2 0 1 0 0 .01M9 16c.5-1.5 1.6-2.2 3-2.2s2.5.7 3 2.2' },
  { key: 'class', path: '/class', label: 'Class', component: ClassPage,
    icon: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17l9 5 9-5' },
  { key: 'history', path: '/history', label: 'History', component: History,
    icon: 'M3 12a9 9 0 1 0 3-6.7M3 4v4h4M12 7v5l3 2' },
  { key: 'demo', path: '/demo', label: 'Demo', component: Demo,
    icon: 'M4 5h16v14H4zM10 9l5 3-5 3z' },
  // Shown as the "+ Add person" button at the bottom of the sidebar, not in the nav list.
  { key: 'add', path: '/add', label: 'Add person', sidebar: false, component: AddPerson },
]
