<script setup>
// 2D map of the corridor + Room 204, drawn from the team's FigJam design (see ../roomLayout.js).
// The SVG is MAP_W x MAP_H user units. Positions passed in (people, trails) are fractions (0-1) of the map:
// x 0 left -> 1 right, y 0 top -> 1 bottom, as the homographies produce them.
import { computed } from 'vue'
import {
  CAMERA, MAP_H, MAP_W, cameras, corridor, corridorLabel, desks, doorLabels, doorLeaves, glassWindow, room, roomLabel, walls,
} from '../roomLayout.js'

// map: dashboard map (only its layout is used); trails (optional): [{ track_id, name, points: [[t, x, y], ...] }], the
// live tracking positions of the session (pages/Home.vue), drawn as paths.
const props = defineProps({ map: { type: Object, required: true }, room: String, trails: { type: Array, default: null },
  time: Number })   // seconds since the session started; dots of people not seen for a while are hidden

const W = MAP_W, H = MAP_H
const X = (f) => f * W
const Y = (f) => f * H

// One colour per person. Red is left out (the app's colour for problems). The colour follows the person's index in the
// full list (trails keep every track of the session, only their points grow), so it does not change as people move.
const PALETTE = ['#2f6fb5', '#e07b1a', '#7a4fb3', '#1f9a8a', '#c2478f', '#8a6a1f', '#4a9a2f', '#5b6b80', '#b5872f', '#3b8fd0']
const colorAt = (i) => PALETTE[i % PALETTE.length]

// One map object per person, not per camera. Live tracking gives one trail per camera track
// ("cam_1:3", "cam_2:5"); tracks that carry the same name (door handoff) are the same person, so their points are
// merged into one time-ordered trail. Unnamed tracks stay on their own. Grouping uses the full list, so the person
// numbers (P1, P2...) and colours stay stable during the session.
const people = computed(() => {
  const groups = new Map()
  for (const tr of props.trails ?? []) {
    const key = tr.name ? `name:${tr.name}` : `track:${tr.track_id}`
    if (!groups.has(key)) groups.set(key, { name: tr.name, tracks: [], points: [] })
    const g = groups.get(key)
    g.tracks.push(tr.track_id)
    g.points.push(...tr.points)
  }
  return [...groups.values()].map((g, i) => ({ ...g, id: `P${i + 1}`, color: colorAt(i),
    points: smooth(g.points.sort((a, b) => a[0] - b[0])) }))
})

// Two cameras can see the same person at the same moment (where their views overlap): average points closer
// than STEP_S in time, so the merged trail does not zigzag between the two cameras' estimates.
const STEP_S = 0.4
function smooth(pts) {
  const out = []
  for (const p of pts) {
    const last = out[out.length - 1]
    if (last && p[0] - last.t0 < STEP_S) { last.n++; last.x += p[1]; last.y += p[2] }
    else out.push({ t0: p[0], t: p[0], x: p[1], y: p[2], n: 1 })
    out[out.length - 1].t = p[0]
  }
  return out.map((q) => [q.t, q.x / q.n, q.y / q.n])
}

// A person whose last point is older than GONE_S (left every camera's view) keeps a faint trail but loses the dot.
const GONE_S = 2
const now = computed(() => props.time ?? Math.max(0, ...people.value.flatMap((g) => g.points.map((p) => p[0]))))

const trailPaths = computed(() => people.value
  .filter((g) => g.points.length > 0)
  .map((g) => {
    const last = g.points[g.points.length - 1]
    return { id: g.id, name: g.name, tracks: g.tracks, color: g.color,
      gone: now.value - last[0] > GONE_S, x: X(last[1]), y: Y(last[2]),
      d: g.points.map(([, x, y], i) => `${i ? 'L' : 'M'}${X(x).toFixed(1)} ${Y(y).toFixed(1)}`).join(' ') }
  }))

// Legend: who is who (colour, person number, name, the camera tracks merged into it).
const legend = computed(() => trailPaths.value.map((t) => ({ key: t.id, color: t.color, id: t.id, name: t.name,
  gone: t.gone, tracks: t.tracks.map((s) => s.replace(':', ' #')).join(', ') })))
</script>

<template>
  <section class="card room-map">
    <h2>Room {{ props.room }} map</h2>
    <svg :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="`Room ${props.room} map`">
      <rect :x="corridor.x" :y="corridor.y" :width="corridor.w" :height="corridor.h" class="rm-area rm-corridor" />
      <rect :x="room.x" :y="room.y" :width="room.w" :height="room.h" class="rm-area rm-room" />
      <text :x="corridorLabel.x" :y="corridorLabel.y" class="rm-title">Corridor</text>
      <text :x="roomLabel.x" :y="roomLabel.y" class="rm-title rm-title-mid">Room {{ props.room }}</text>
      <rect v-for="([x, y, w, h], i) in desks" :key="i" :x="x" :y="y" :width="w" :height="h" rx="4" class="rm-desk" />

      <rect v-for="(w, i) in walls" :key="`wall${i}`" :x="w.x" :y="w.y" :width="w.w" :height="w.h" class="rm-wall" />
      <rect :x="glassWindow.x" :y="glassWindow.y" :width="glassWindow.w" :height="glassWindow.h" class="rm-glass" />
      <rect v-for="(d, i) in doorLeaves" :key="`leaf${i}`" :x="d.x" :y="d.y" :width="d.w" :height="d.h" rx="3"
        :transform="`matrix(${d.matrix.join(' ')})`" class="rm-leaf" />
      <text v-for="(l, i) in doorLabels" :key="`dl${i}`" :x="l.x" :y="l.y" class="rm-small">{{ l.text }}</text>

      <g v-for="c in cameras" :key="c.id">
        <rect :x="c.x" :y="c.y" :width="CAMERA.w" :height="CAMERA.h" rx="16" class="rm-cam" />
        <text :x="c.x + CAMERA.w / 2" :y="c.y + CAMERA.h / 2 + 5" class="rm-cam-text">{{ c.label }}</text>
        <title>{{ c.id }}</title>
      </g>

      <g v-for="tr in trailPaths" :key="tr.id" class="map-trail" :class="{ gone: tr.gone }" :style="{ '--c': tr.color }">
        <path v-if="tr.d.includes('L')" :d="tr.d" />
        <template v-if="!tr.gone">
          <circle :cx="tr.x" :cy="tr.y" r="10" />
          <text :x="tr.x" :y="tr.y - 16" class="rm-id">{{ tr.name || tr.id }}</text>
        </template>
        <title>{{ tr.id }}{{ tr.name ? ` · ${tr.name}` : '' }} ({{ tr.tracks.join(', ') }})</title>
      </g>
    </svg>
    <ul v-if="legend.length" class="rm-legend" aria-label="People on the map">
      <li v-for="l in legend" :key="l.key" :class="{ gone: l.gone }" :title="`Camera tracks: ${l.tracks}`">
        <span class="rm-swatch" :style="{ background: l.color }" />
        <strong>{{ l.id }}</strong>
        <span class="muted">{{ l.name || 'Unknown' }}</span>
      </li>
    </ul>
    <p v-else class="muted small rm-none">Nobody on the map yet.</p>
  </section>
</template>

<style scoped>
.rm-area { stroke: #b3b3b3; stroke-width: 3; }
.rm-corridor { fill: #fff; }
.rm-room { fill: #cdf4d3; }
.rm-title { font-size: 24px; fill: #1e1e1e; }
.rm-title-mid { text-anchor: middle; }
.rm-small { font-size: 16px; fill: #1e1e1e; }
.rm-desk { fill: #fff; stroke: #b3b3b3; stroke-width: 3; }
.rm-wall { fill: #1e1e1e; }
.rm-leaf { fill: #ff9e42; stroke: #eb7500; stroke-width: 3; }
.rm-cam { fill: #757575; stroke: #5e5e5e; stroke-width: 3; }
.rm-cam-text { font-size: 14px; fill: #fff; text-anchor: middle; }
.rm-id { font-size: 18px; font-weight: 600; text-anchor: middle; fill: var(--c); paint-order: stroke; stroke: #fff; stroke-width: 5px; }
.map-trail path { fill: none; stroke: var(--c); stroke-width: 3.5; stroke-linejoin: round; stroke-linecap: round; opacity: 0.8; }
.map-trail circle { fill: var(--c); stroke: #fff; stroke-width: 3; }
.map-trail.gone path { opacity: 0.3; }
.rm-glass { fill: #7cc4fa; }
.rm-legend li.gone { opacity: 0.5; }
.rm-legend { list-style: none; margin: 12px 0 0; padding: 12px 0 0; border-top: 1px solid var(--line);
  display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 8px 16px; font-size: 13px; }
.rm-legend li { display: flex; align-items: center; gap: 8px; min-width: 0; }
.rm-legend .muted { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rm-swatch { width: 12px; height: 12px; border-radius: 50%; flex: none; }
.rm-none { margin: 12px 0 0; }
</style>
