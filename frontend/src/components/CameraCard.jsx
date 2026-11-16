import { forwardRef, useEffect, useRef } from 'react'

// Box for one track at time t: linear interpolation between keyframes,
// hidden outside the first..last keyframe range.
function boxAt(track, t) {
  const k = track.keyframes
  if (!k?.length || t < k[0].t || t > k[k.length - 1].t) return null
  for (let i = 0; i < k.length - 1; i++) {
    if (t <= k[i + 1].t) {
      const a = k[i], b = k[i + 1]
      const f = b.t === a.t ? 0 : (t - a.t) / (b.t - a.t)
      return a.box.map((v, j) => v + (b.box[j] - v) * f)
    }
  }
  return k[k.length - 1].box
}

const labelOf = (tr) => (tr.name ? `ID ${tr.global_id} · ${tr.name.split(' ').slice(-1)[0]}` : `ID ${tr.global_id} · Unknown`)

// Draws the track boxes on a canvas laid over the <video>.
// The video uses object-fit: contain, so we compute where the picture actually sits.
function useOverlay(videoRef, canvasRef, tracks, showBoxes) {
  useEffect(() => {
    let raf
    const draw = () => {
      raf = requestAnimationFrame(draw)
      const v = videoRef.current, c = canvasRef.current
      if (!v || !c) return
      const W = c.clientWidth, H = c.clientHeight
      if (c.width !== W) c.width = W
      if (c.height !== H) c.height = H
      const ctx = c.getContext('2d')
      ctx.clearRect(0, 0, W, H)
      if (!showBoxes || !tracks || !v.videoWidth) return
      const s = Math.min(W / v.videoWidth, H / v.videoHeight)
      const pw = v.videoWidth * s, ph = v.videoHeight * s
      const ox = (W - pw) / 2, oy = (H - ph) / 2
      for (const tr of tracks.tracks) {
        const b = boxAt(tr, v.currentTime)
        if (!b) continue
        const [x, y, w, h] = [ox + b[0] * pw, oy + b[1] * ph, b[2] * pw, b[3] * ph]
        const color = tr.name ? '#3fbf4f' : '#f2b233'
        ctx.strokeStyle = color
        ctx.lineWidth = 2
        ctx.strokeRect(x, y, w, h)
        const text = labelOf(tr)
        ctx.font = '600 13px system-ui, sans-serif'
        const tw = ctx.measureText(text).width + 12
        ctx.fillStyle = 'rgba(30,30,30,0.85)'
        ctx.fillRect(x, Math.max(0, y - 22), tw, 20)
        ctx.fillStyle = '#fff'
        ctx.fillText(text, x + 6, Math.max(14, y - 8))
      }
    }
    draw()
    return () => cancelAnimationFrame(raf)
  }, [videoRef, canvasRef, tracks, showBoxes])
}

const CameraCard = forwardRef(function CameraCard({ cam, src, tracks, showBoxes, highlight, children }, videoRef) {
  const canvasRef = useRef(null)
  useOverlay(videoRef, canvasRef, tracks, showBoxes)
  return (
    <section className={`card cam-card ${highlight ? 'cam-highlight' : ''}`}>
      <header className="cam-head">
        <span className={`dot ${src ? 'on' : ''}`} />
        <div>
          <div className="cam-title">{cam.label}</div>
          <div className="cam-place">{cam.place}</div>
        </div>
        {tracks?.source === 'mock' && showBoxes && src && <span className="badge small">mock boxes</span>}
      </header>
      <div className="cam-view">
        <video ref={videoRef} src={src || undefined} muted playsInline preload="auto" />
        <canvas ref={canvasRef} className="cam-overlay" />
        {!src && (
          <div className="cam-empty">
            <div>No video loaded</div>
            <div className="muted">{cam.folder}/ · stream {cam.stream_id}</div>
          </div>
        )}
      </div>
      {children}
    </section>
  )
})

export default CameraCard
