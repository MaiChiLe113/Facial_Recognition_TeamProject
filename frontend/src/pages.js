// Page registry (design doc section 7). The router and the sidebar are both built
// from this list, so adding a page = adding one entry here.
//   component  the page to show. Leave it out to show the Placeholder card (todo + owner).
//   icon       SVG path for the sidebar. Pages with sidebar: false are reached another way.
//   bare       full screen, no sidebar (the phone camera page).
import AddPerson from './pages/AddPerson.vue'
import Camera from './pages/Camera.vue'
import FeaturesDemo from './pages/FeaturesDemo.vue'
import History from './pages/History.vue'
import Home from './pages/Home.vue'
import SystemLog from './pages/SystemLog.vue'

export const PAGES = [
  // Home shows the three cameras Live (phones) or Recorded (a take); it replaced the MultiCam and Live cameras pages.
  { key: 'home', path: '/', label: 'Home', component: Home,
    icon: 'M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z' },
  { key: 'history', path: '/history', label: 'History', component: History,
    icon: 'M3 12a9 9 0 1 0 3-6.7M3 4v4h4M12 7v5l3 2' },
  { key: 'features-demo', path: '/features-demo', label: 'Features demo', component: FeaturesDemo,
    icon: 'M12 3l2.5 5.5L20 9l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-.5z' },
  // When each model file the app infers with last changed, its version label (ml/model_versions.json), change history.
  { key: 'system', path: '/system', label: 'System log', component: SystemLog,
    icon: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z' },
  // Opened on a phone / laptop over Wi-Fi: it only sends its camera to the host (see docs/LAN_DEMO.md).
  { key: 'camera', path: '/camera', label: 'Camera', sidebar: false, bare: true, component: Camera },
  // Shown as the "+ Add person" button at the bottom of the sidebar, not in the nav list.
  { key: 'add', path: '/add', label: 'Add person', sidebar: false, component: AddPerson },
]
