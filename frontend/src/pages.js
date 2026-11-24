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
import LanGuide from './pages/LanGuide.vue'

export const PAGES = [
  // Home shows the three cameras Live (phones) or Recorded (a take); it replaced the MultiCam and Live cameras pages.
  { key: 'home', path: '/', label: 'Home', component: Home,
    icon: 'M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z' },
  { key: 'history', path: '/history', label: 'History', component: History,
    icon: 'M3 12a9 9 0 1 0 3-6.7M3 4v4h4M12 7v5l3 2' },
  { key: 'features-demo', path: '/features-demo', label: 'Features demo', component: FeaturesDemo,
    icon: 'M12 3l2.5 5.5L20 9l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-.5z' },
  // Opened on a phone / laptop over Wi-Fi: it only sends its camera to the host (see docs/LAN_DEMO.md).
  { key: 'camera', path: '/camera', label: 'Camera', sidebar: false, bare: true, component: Camera },
  // The Wi-Fi demo guide, rendered from docs/LAN_DEMO.md (linked from Home).
  { key: 'lan-guide', path: '/guide/lan', label: 'Wi-Fi demo guide', sidebar: false, component: LanGuide },
  // Shown as the "+ Add person" button at the bottom of the sidebar, not in the nav list.
  { key: 'add', path: '/add', label: 'Add person', sidebar: false, component: AddPerson },
]
