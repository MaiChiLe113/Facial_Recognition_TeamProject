// Drawing layout of the Room 204 2D map, copied from the team's FigJam board
// (https://www.figma.com/board/b8wiU877MrltPtUYAI4BiW, section "Room 204 map", node 19:6).
// Coordinates are in map pixels: the map is MAP_W x MAP_H, origin top-left, y down. The Figma drawing is
// 920 x 520 with its top-left at (48, 120) in the section; that offset is subtracted here (FIGMA_ORIGIN).
// To change the map: edit it in Figma, then update the numbers below (same node names: Corridor, Room 204,
// Desk, Wall, Door leaf, cam_1 / cam_2 / attendance_cam, Door labels).
//
// This is how the map is DRAWN. Positions of people and trails are fractions of the map (0..1) from the
// homographies (data/calibration/), drawn at fraction * MAP_W / MAP_H. The door gap here (y 0.727 to 0.906)
// is the Figma design and data/calibration/room204_map.json uses the same numbers.
export const MAP_W = 920
export const MAP_H = 520
const FIGMA_ORIGIN = [48, 120]
const o = ([x, y]) => [x - FIGMA_ORIGIN[0], y - FIGMA_ORIGIN[1]]

const area = (x, y, w, h) => { const [lx, ly] = o([x, y]); return { x: lx, y: ly, w, h } }

export const corridor = area(48, 120, 276, 520)
export const room = area(324, 120, 644, 520)
export const roomLabel = { x: 646 - FIGMA_ORIGIN[0], y: 156 - FIGMA_ORIGIN[1] }      // centre of the "Room 204" text
export const corridorLabel = { x: 64 - FIGMA_ORIGIN[0], y: 156 - FIGMA_ORIGIN[1] }   // left edge of the "Corridor" text

// Wall between corridor and room, with the door gap (y 378 to 471).
export const walls = [area(320, 120, 16, 378), area(320, 591, 16, 49)]

// Door leaves (orange): one swung open into the room at the doorway, one open in the corridor.
// matrix = SVG matrix(a b c d e f) from Figma's relativeTransform (rotation 125 degrees).
export const doorLeaves = [
  { x: 0, y: 0, w: 89.44, h: 16, matrix: [1, 0, 0, 1, ...o([336, 591])] },
  { x: 0, y: 0, w: 89.44, h: 16, matrix: [-0.574, -0.819, 0.819, -0.574, ...o([253.301, 202.442])] },
]
export const doorLabels = [
  { text: 'Door', x: o([275, 539.68])[0], y: o([275, 539.68])[1] + 15 },
  { text: 'Door', x: o([257, 132.68])[0], y: o([257, 132.68])[1] + 15 },
]

// Desks: long tables (198 x 36), 4 rows x 2 columns, plus one small desk by CAM 2. [x, y, w, h] in Figma px.
export const DESK = { w: 198, h: 36 }
export const desks = [
  [389, 237], [694, 237],
  [389, 315], [694, 315],
  [389, 389], [694, 389],
  [389, 463.4], [694, 462],
].map(([x, y]) => [...o([x, y]), DESK.w, DESK.h]).concat([[...o([822, 555]), 92, 36]])

export const CAMERA = { w: 72, h: 32 }
export const cameras = [
  { id: 'cam_1', label: 'CAM 1', p: o([76, 193]) },
  { id: 'cam_2', label: 'CAM 2', p: o([714, 557]) },
  { id: 'attendance_cam', label: 'ATT', p: o([389, 467]) },
].map(({ id, label, p }) => ({ id, label, x: p[0], y: p[1] }))
