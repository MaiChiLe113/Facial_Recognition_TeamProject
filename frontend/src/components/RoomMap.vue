<script setup>
// 2D map of the corridor + Room 204, drawn from the team's FigJam design (see ../roomLayout.js).
// The SVG is MAP_W x MAP_H user units. Positions passed in (people, trails) are fractions (0-1) of the map:
// x 0 left -> 1 right, y 0 top -> 1 bottom, as the homographies produce them.
import { computed } from 'vue'
import {
  CAMERA, DESK, MAP_H, MAP_W, cameras, corridor, corridorLabel, desks, doorLabels, doorLeaves, room, roomLabel, walls,
} from '../roomLayout.js'

// map: dashboard map (only its layout is used; live mode draws no people yet); trails (optional): [{ track_id, name, flagged, points: [[t, x, y], ...] }]
// from presence verification, drawn as paths, red when the track is part of an alert.
const props = defineProps({ map: { type: Object, required: true }, room: String, trails: { type: Array, default: null } })

const W = MAP_W, H = MAP_H
const X = (f) => f * W
const Y = (f) => f * H

// One colour per person. Red is left out: it is reserved for alerts. The colour follows the person's index in the
// full list (trails keep every track while the video plays, only their points grow), so it never changes mid-take.
const PALETTE = ['#2f6fb5', '#e07b1a', '#7a4fb3', '#1f9a8a', '#c2478f', '#8a6a1f', '#4a9a2f', '#5b6b80', '#b5872f', '#3b8fd0']
const colorAt = (i) => PALETTE[i % PALETTE.length]

const trailPaths = computed(() => (props.trails ?? [])
  .map((tr, i) => ({ tr, color: colorAt(i) }))
  .filter(({ tr }) => tr.points.length > 0)
  .map(({ tr, color }) => {
    const last = tr.points[tr.points.length - 1]
    return { id: tr.track_id, name: tr.name, flagged: tr.flagged, color, x: X(last[1]), y: Y(last[2]),
      d: tr.points.map(([, x, y], i) => `${i ? 'L' : 'M'}${X(x).toFixed(1)} ${Y(y).toFixed(1)}`).join(' ') }
  }))

// Legend: who is who (colour, ID, name).
const legend = computed(() => trailPaths.value.map((t) => ({ key: t.id, color: t.color, id: t.id, name: t.name, flagged: t.flagged })))
</script>

<template>
  <section class="card room-map">
    <h2>Room {{ props.room }} map</h2>
    <svg :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="`Room ${props.room} map`">
      <rect :x="corridor.x" :y="corridor.y" :width="corridor.w" :height="corridor.h" class="rm-area rm-corridor" />
      <rect :x="room.x" :y="room.y" :width="room.w" :height="room.h" class="rm-area rm-room" />
      <text :x="corridorLabel.x" :y="corridorLabel.y" class="rm-title">Corridor</text>
      <text :x="roomLabel.x" :y="roomLabel.y" class="rm-title rm-title-mid">Room {{ props.room }}</text>
      <rect v-for="([x, y], i) in desks" :key="i" :x="x" :y="y" :width="DESK.w" :height="DESK.h" rx="4" class="rm-desk" />

      <rect v-for="(w, i) in walls" :key="`wall${i}`" :x="w.x" :y="w.y" :width="w.w" :height="w.h" class="rm-wall" />
      <rect v-for="(d, i) in doorLeaves" :key="`leaf${i}`" :x="d.x" :y="d.y" :width="d.w" :height="d.h" rx="3"
        :transform="`matrix(${d.matrix.join(' ')})`" class="rm-leaf" />
      <text v-for="(l, i) in doorLabels" :key="`dl${i}`" :x="l.x" :y="l.y" class="rm-small">{{ l.text }}</text>

      <g v-for="c in cameras" :key="c.id">
        <rect :x="c.x" :y="c.y" :width="CAMERA.w" :height="CAMERA.h" rx="16" class="rm-cam" />
        <text :x="c.x + CAMERA.w / 2" :y="c.y + CAMERA.h / 2 + 5" class="rm-cam-text">{{ c.label }}</text>
        <title>{{ c.id }}</title>
      </g>

      <g v-for="tr in trailPaths" :key="tr.id" class="map-trail" :class="{ flagged: tr.flagged }" :style="{ '--c': tr.color }">
        <path v-if="tr.d.includes('L')" :d="tr.d" />
        <circle :cx="tr.x" :cy="tr.y" r="10" />
        <text :x="tr.x" :y="tr.y - 16" class="rm-id">{{ tr.id }}</text>
        <title>{{ tr.id }}{{ tr.name ? ` · ${tr.name}` : '' }}{{ tr.flagged ? ' · alert' : '' }}</title>
      </g>
    </svg>
    <ul v-if="legend.length" class="rm-legend" aria-label="People on the map">
      <li v-for="l in legend" :key="l.key" :class="{ flagged: l.flagged }">
        <span class="rm-swatch" :style="{ background: l.color }" />
        <strong>{{ l.id }}</strong>
        <span v-if="l.name" class="muted">{{ l.name }}</span>
        <span v-if="l.flagged" class="rm-alert">Alert</span>
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
/* Alert: the person keeps their colour, a dashed red halo marks the alert. */
.map-trail.flagged path { stroke-width: 5; opacity: 1; }
.map-trail.flagged circle { stroke: var(--danger); stroke-width: 4; animation: map-blink 1s ease-in-out infinite; }
@keyframes map-blink { 50% { opacity: 0.35; } }
@media (prefers-reduced-motion: reduce) { .map-trail.flagged circle { animation: none; } }
.rm-legend { list-style: none; margin: 12px 0 0; padding: 12px 0 0; border-top: 1px solid var(--line);
  display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 8px 16px; font-size: 13px; }
.rm-legend li { display: flex; align-items: center; gap: 8px; min-width: 0; }
.rm-legend .muted { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rm-swatch { width: 12px; height: 12px; border-radius: 50%; flex: none; }
.rm-alert { margin-left: auto; font-size: 11px; font-weight: 600; color: var(--danger); background: var(--danger-soft); border-radius: 999px; padding: 1px 8px; }
.rm-none { margin: 12px 0 0; }
</style>
