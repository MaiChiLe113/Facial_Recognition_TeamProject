<script setup>
// Live view: each camera frame has a "+" box that asks this device for camera permission and shows it live.
import { computed, onMounted, ref } from 'vue'
import { fetchDashboard, fetchDemoConfig } from '../api.js'
import CameraCard from '../components/CameraCard.vue'
import EventLog from '../components/EventLog.vue'
import ClassRoster from '../components/ClassRoster.vue'
import RoomMap from '../components/RoomMap.vue'

const ORDER = ['cam_1', 'cam_2', 'attendance_cam']

const dash = ref(null)
const demo = ref(null)

const cameras = computed(() => (demo.value ? ORDER.map((id) => demo.value.cameras.find((c) => c.cam_id === id)).filter(Boolean) : []))
const st = computed(() => dash.value.attendance_cam_status)

onMounted(() => {
  fetchDashboard().then((d) => { dash.value = d })
  fetchDemoConfig().then((d) => { demo.value = d })
})

const capitalise = (s) => s[0].toUpperCase() + s.slice(1)
</script>

<template>
  <div v-if="!dash || !demo" class="loading">Loading Hawkeye…</div>
  <div v-else class="home">
    <header class="topbar">
      <h1>{{ dash.course.id }} · Room {{ dash.course.room }}</h1>
    </header>

    <div class="grid-top">
      <CameraCard v-for="cam in cameras" :key="cam.cam_id" :cam="cam" live
        :highlight="cam.cam_id === 'attendance_cam'">
        <!-- TODO: live values from liveness.py / recognizer.py / emotion.py (currently mock) -->
        <ul v-if="cam.cam_id === 'attendance_cam'" class="checks">
          <li v-if="st.identity_verified" class="ok">Identity verified · {{ st.name }}</li>
          <li v-else class="bad">Unknown — <RouterLink to="/add">please register</RouterLink></li>
          <li :class="st.liveness === 'live' ? 'ok' : 'bad'">{{ st.liveness === 'live' ? 'Liveness passed' : 'Spoof detected' }}</li>
          <li class="ok">Emotion: {{ capitalise(st.emotion) }}</li>
        </ul>
      </CameraCard>
      <EventLog :events="dash.events" />
    </div>

    <div class="grid-bottom">
      <ClassRoster :roster="dash.roster" />
      <RoomMap :map="dash.map" :room="dash.course.room" />
    </div>
  </div>
</template>
