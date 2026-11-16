// The session picked on the Attend Course page. Kept in this browser only until the backend has
// POST /api/sessions (TODO, Đức Mạnh). Storage can be blocked, so every access is guarded.
import { ref } from 'vue'

const KEY = 'hawkeye.activeSession'

function load() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || null
  } catch {
    return null
  }
}

export const activeSession = ref(load())

export function setActiveSession(session) {
  activeSession.value = session
  try {
    if (session) localStorage.setItem(KEY, JSON.stringify(session))
    else localStorage.removeItem(KEY)
  } catch { /* storage blocked: keep it in memory only */ }
}
