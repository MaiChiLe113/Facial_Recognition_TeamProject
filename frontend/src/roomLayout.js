// Layout of the Room 204 2D map, read from data/calibration/room204_map.json (the single source).
// To change the map: edit that JSON, then run `python ml/tracking/render_map.py` to preview the SVG.
// JSON coordinates are fractions 0..1 (x left -> right, y top -> bottom), the same as the homographies;
// here they are multiplied by MAP_W / MAP_H to get map pixels.
import MAP from '../../data/calibration/room204_map.json'

export const MAP_W = 920
export const MAP_H = 520
const X = (f) => f * MAP_W
const Y = (f) => f * MAP_H
const box = ([x0, x1], [y0, y1]) => ({ x: X(x0), y: Y(y0), w: X(x1 - x0), h: Y(y1 - y0) })

export const corridor = box(MAP.corridor.x, MAP.corridor.y)
export const room = box(MAP.room.x, MAP.room.y)
export const roomLabel = { x: X((MAP.room.x[0] + MAP.room.x[1]) / 2), y: 36 }   // centre of the room
export const corridorLabel = { x: 16, y: 36 }

// Wall between corridor and room, leaving the door gap (MAP.door.y).
const WALL = 16
const wx = X(MAP.corridor_wall_x) - WALL / 2
const [d0, d1] = MAP.door.y
export const walls = [
  { x: wx, y: 0, w: WALL, h: Y(d0) },
  { x: wx, y: Y(d1), w: WALL, h: MAP_H - Y(d1) },
]
export const glassWindow = { x: wx, y: Y(MAP.glass_window.y[0]), w: WALL, h: Y(MAP.glass_window.y[1] - MAP.glass_window.y[0]) }

// Door leaves (orange): decoration only, kept from the old FigJam drawing (map pixels).
// matrix = SVG matrix(a b c d e f), rotated 125 degrees.
export const doorLeaves = [
  { x: 0, y: 0, w: 89.44, h: 16, matrix: [1, 0, 0, 1, 288, 471] },
  { x: 0, y: 0, w: 89.44, h: 16, matrix: [-0.574, -0.819, 0.819, -0.574, 205.301, 82.442] },
]
export const doorLabels = [
  { text: 'Door', x: X(MAP.corridor_wall_x) - 49, y: Y((d0 + d1) / 2) - 6 },
  { text: 'Door', x: 209, y: 27.68 },
]

// Desks: [x, y, w, h] fractions in the JSON -> pixels.
export const desks = MAP.desks.map(([x, y, w, h]) => [X(x), Y(y), X(w), Y(h)])

// Cameras: MAP.cameras holds centre positions; c.x / c.y here are the top-left of the label.
export const CAMERA = { w: 72, h: 32 }
const LABEL = { cam_1: 'CAM 1', cam_2: 'CAM 2', attendance_cam: 'ATT' }
export const cameras = Object.entries(MAP.cameras).map(([id, c]) => ({
  id, label: LABEL[id] ?? id, x: X(c.x) - CAMERA.w / 2, y: Y(c.y) - CAMERA.h / 2,
}))
