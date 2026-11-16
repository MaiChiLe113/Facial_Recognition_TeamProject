// 2D map of the corridor + Room 204. Positions are fractions (0-1) of the map.
// Real positions will come from the homography step (matcher.py, task T1).
const W = 460, H = 260, SPLIT = 0.3

export default function RoomMap({ map, room }) {
  const X = (f) => f * W
  const Y = (f) => f * H
  const desks = []
  for (let r = 0; r < 5; r++) for (let c = 0; c < 4; c++) desks.push([X(0.4 + c * 0.14), Y(0.3 + r * 0.13)])
  return (
    <section className="card room-map">
      <h2>Room {room} map</h2>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Room ${room} map`}>
        <rect x="1" y="1" width={W - 2} height={H - 2} rx="4" className="map-frame" />
        <rect x={X(SPLIT)} y="1" width={W - X(SPLIT) - 1} height={H - 2} className="map-room" />
        <line x1={X(SPLIT)} y1="1" x2={X(SPLIT)} y2={H - 1} className="map-wall" />
        <text x={X(SPLIT / 2)} y="24" className="map-label">Corridor</text>
        <text x={X((1 + SPLIT) / 2)} y="24" className="map-label">Room {room}</text>
        <text x={X((1 + SPLIT) / 2)} y="40" className="map-sub">(Classroom)</text>
        {desks.map(([x, y], i) => <rect key={i} x={x} y={y} width="46" height="18" rx="3" className="map-desk" />)}
        <path d={`M${X(map.door.x)} ${Y(map.door.y) - 26} a26 26 0 0 0 -26 26 L${X(map.door.x)} ${Y(map.door.y)}`} className="map-door" />
        {map.cameras.map((c) => (
          <g key={c.cam_id}>
            <rect x={X(c.x) - 7} y={Y(c.y) - 5} width="14" height="10" rx="2" className="map-cam" />
            <title>{c.cam_id}</title>
          </g>
        ))}
        {map.people.map((p) => (
          <g key={p.global_id}>
            <circle cx={X(p.x)} cy={Y(p.y)} r="6" className={p.label.startsWith('ID') ? 'map-dot unknown' : 'map-dot'} />
            <rect x={X(p.x) - 34} y={Y(p.y) + 9} width="68" height="18" rx="4" className="map-tag" />
            <text x={X(p.x)} y={Y(p.y) + 22} className="map-tag-text">{p.label}</text>
          </g>
        ))}
      </svg>
    </section>
  )
}
