<script setup>
// 2D map of the corridor + Room 204, drawn from the team's FigJam design (see ../roomLayout.js).
// The SVG is MAP_W x MAP_H user units. Positions passed in (people, trails) are fractions (0-1) of the map:
// x 0 left -> 1 right, y 0 top -> 1 bottom, as the homographies produce them.
import { computed } from 'vue'
import {
  CAMERA, DESK, MAP_H, MAP_W, cameras, corridor, corridorLabel, desks, doorLabels, doorLeaves, room, roomLabel, walls,
} from '../roomLayout.js'

// map: dashboard map (mock people dots); trails (optional): [{ track_id, name, flagged, points: [[t, x, y], ...] }]
// from presence verification, drawn as paths, red when the track is part of an alert.
const props = defineProps({ map: { type: Object, required: true }, room: String, trails: { type: Array, default: () => [] } })

const W = MAP_W, H = MAP_H
const X = (f) => f * W
const Y = (f) => f * H

const trailPaths = computed(() => props.trails
  .filter((tr) => tr.points.length > 1)
  .map((tr) => {
    const last = tr.points[tr.points.length - 1]
    return { id: tr.track_id, name: tr.name, flagged: tr.flagged, x: X(last[1]), y: Y(last[2]),
      d: tr.points.map(([, x, y], i) => `${i ? 'L' : 'M'}${X(x).toFixed(1)} ${Y(y).toFixed(1)}`).join(' ') }
  }))
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

      <g v-for="tr in trailPaths" :key="tr.id" class="map-trail" :class="{ flagged: tr.flagged }">
        <path :d="tr.d" />
        <circle :cx="tr.x" :cy="tr.y" r="8" />
        <title>{{ tr.id }}{{ tr.name ? ` · ${tr.name}` : '' }}{{ tr.flagged ? ' · alert' : '' }}</title>
      </g>
      <g v-for="p in trails.length ? [] : map.people" :key="p.global_id">
        <circle :cx="X(p.x)" :cy="Y(p.y)" r="12" class="map-dot" :class="{ unknown: p.label.startsWith('ID') }" />
        <rect :x="X(p.x) - 68" :y="Y(p.y) + 18" width="136" height="36" rx="8" class="map-tag" />
        <text :x="X(p.x)" :y="Y(p.y) + 44" class="rm-tag-text">{{ p.label }}</text>
      </g>
    </svg>
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
.rm-tag-text { font-size: 22px; font-weight: 600; text-anchor: middle; fill: #222; }
.map-trail path { fill: none; stroke: #4a7fc1; stroke-width: 3.2; stroke-linejoin: round; opacity: 0.75; }
.map-trail circle { fill: #4a7fc1; }
.map-trail.flagged path { stroke: #d9453a; stroke-width: 4.8; opacity: 1; }
.map-trail.flagged circle { fill: #d9453a; animation: map-blink 1s ease-in-out infinite; }
@keyframes map-blink { 50% { opacity: 0.25; } }
@media (prefers-reduced-motion: reduce) { .map-trail.flagged circle { animation: none; } }
</style>
