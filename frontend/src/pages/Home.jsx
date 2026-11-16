import { useEffect, useRef, useState } from 'react'
import { fetchDashboard, fetchDemoConfig, fetchTracks } from '../api.js'
import CameraCard from '../components/CameraCard.jsx'
import EventLog from '../components/EventLog.jsx'
import ClassRoster from '../components/ClassRoster.jsx'
import RoomMap from '../components/RoomMap.jsx'

const ORDER = ['cam_1', 'cam_2', 'attendance_cam']

function useClock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  const hh = String(now.getHours()).padStart(2, '0'), mm = String(now.getMinutes()).padStart(2, '0')
  return `${hh}:${mm} · ${now.toLocaleDateString('en-GB')}`
}

export default function Home() {
  const [dash, setDash] = useState(null)
  const [demo, setDemo] = useState(null)
  const [tracks, setTracks] = useState({})
  const [srcs, setSrcs] = useState({})
  const [playing, setPlaying] = useState(false)
  const [showBoxes, setShowBoxes] = useState(true)
  const [message, setMessage] = useState('')
  const videos = { cam_1: useRef(null), cam_2: useRef(null), attendance_cam: useRef(null) }
  const fileInput = useRef(null)
  const clock = useClock()
  const cameras = demo ? ORDER.map((id) => demo.cameras.find((c) => c.cam_id === id)).filter(Boolean) : []

  useEffect(() => {
    fetchDashboard().then(setDash)
    fetchDemoConfig().then(setDemo)
    Promise.all(ORDER.map(fetchTracks)).then((list) => setTracks(Object.fromEntries(ORDER.map((c, i) => [c, list[i]]))))
  }, [])

  // Keep the three videos in step: follow CAM 1 (or the first loaded one), correct drift > 0.3 s.
  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => {
      const cams = cameras.filter((c) => srcs[c.cam_id] && videos[c.cam_id].current)
      if (cams.length < 2) return
      const lead = cams[0], lv = videos[lead.cam_id].current
      const base = lv.currentTime - (lead.offset_s || 0)
      for (const c of cams.slice(1)) {
        const v = videos[c.cam_id].current
        const want = base + (c.offset_s || 0)
        if (Math.abs(v.currentTime - want) > 0.3 && want < (v.duration || Infinity)) v.currentTime = want
      }
      if (cams.every((c) => videos[c.cam_id].current.ended)) setPlaying(false)
    }, 500)
    return () => clearInterval(id)
  })

  if (!dash || !demo) return <div className="loading">Loading Hawkeye…</div>

  const startAll = async (sources) => {
    // wait until every loaded video knows its length, then start together
    await Promise.all(cameras.filter((c) => sources[c.cam_id]).map((c) => new Promise((resolve) => {
      const v = videos[c.cam_id].current
      if (v.readyState >= 1) return resolve()
      v.addEventListener('loadedmetadata', resolve, { once: true })
      v.addEventListener('error', resolve, { once: true })
    })))
    for (const c of cameras) {
      const v = videos[c.cam_id].current
      if (!sources[c.cam_id] || !v) continue
      v.currentTime = c.offset_s || 0
      v.play().catch(() => {})
    }
    setPlaying(true)
  }

  const runDemo = () => {
    const ready = cameras.filter((c) => c.available)
    if (!ready.length) {
      setMessage(demo.offline
        ? 'Backend is not running, so videos cannot stream. Start uvicorn, or use "Load from computer".'
        : 'Backend cannot find the videos. Set HAWKEYE_VIDEO_ROOT in backend/.env, or use "Load from computer".')
      return
    }
    setMessage(ready.length < cameras.length ? `Only ${ready.length} of ${cameras.length} videos found.` : `Playing take ${demo.take}.`)
    const next = Object.fromEntries(ready.map((c) => [c.cam_id, c.url]))
    setSrcs(next)
    setTimeout(() => startAll(next), 0)
  }

  // Match picked files to cameras by the stream ID at the start of the filename (e.g. sCi8Jvd_....webm)
  const loadLocal = (e) => {
    const files = [...e.target.files]
    const next = {}
    for (const c of cameras) {
      const f = files.find((file) => file.name.startsWith(c.stream_id)) || files.find((file) => file.name.includes(c.cam_id))
      if (f) next[c.cam_id] = URL.createObjectURL(f)
    }
    const n = Object.keys(next).length
    setMessage(n ? `Loaded ${n} of ${cameras.length} cameras from your computer.` : 'No file matched a camera stream ID (sCi8Jvd, pDHjQPf, 2SiEwN8).')
    setSrcs(next)
    setTimeout(() => startAll(next), 0)
    e.target.value = ''
  }

  const togglePause = () => {
    const vs = cameras.map((c) => videos[c.cam_id].current).filter((v) => v && v.src)
    if (playing) { vs.forEach((v) => v.pause()); setPlaying(false) }
    else { vs.forEach((v) => v.play().catch(() => {})); setPlaying(true) }
  }

  const restart = () => startAll(srcs)
  const hasVideo = Object.keys(srcs).length > 0
  const st = dash.attendance_cam_status

  return (
    <div className="home">
      <header className="topbar">
        <h1>{dash.course.id} · Room {dash.course.room}</h1>
        <div className="topbar-right">
          <div className="demo-controls">
            <button className="btn primary" onClick={runDemo}>▶ Run demo videos</button>
            <button className="btn" onClick={() => fileInput.current.click()}>Load from computer</button>
            <input ref={fileInput} type="file" accept="video/*" multiple hidden onChange={loadLocal} />
            {hasVideo && <button className="btn" onClick={togglePause}>{playing ? 'Pause' : 'Play'}</button>}
            {hasVideo && <button className="btn" onClick={restart}>Restart</button>}
            <label className="toggle"><input type="checkbox" checked={showBoxes} onChange={(e) => setShowBoxes(e.target.checked)} /> Boxes</label>
          </div>
          <div className="clock">Time: {clock}</div>
        </div>
      </header>

      {(dash.offline || message) && (
        <div className="notice">
          {dash.offline && <span className="badge">offline · mock data</span>}
          {message && <span>{message}</span>}
        </div>
      )}

      <div className="grid-top">
        {cameras.map((cam) => (
          <CameraCard key={cam.cam_id} ref={videos[cam.cam_id]} cam={cam} src={srcs[cam.cam_id]}
            tracks={tracks[cam.cam_id]} showBoxes={showBoxes} highlight={cam.cam_id === 'attendance_cam'}>
            {cam.cam_id === 'attendance_cam' && (
              // TODO: live values from liveness.py / recognizer.py / emotion.py (currently mock)
              <ul className="checks">
                <li className={st.identity_verified ? 'ok' : 'bad'}>{st.identity_verified ? `Identity verified · ${st.name}` : 'Unknown — please register'}</li>
                <li className={st.liveness === 'live' ? 'ok' : 'bad'}>{st.liveness === 'live' ? 'Liveness passed' : 'Spoof detected'}</li>
                <li className="ok">Emotion: {st.emotion[0].toUpperCase() + st.emotion.slice(1)}</li>
              </ul>
            )}
          </CameraCard>
        ))}
        <EventLog events={dash.events} />
      </div>

      <div className="grid-bottom">
        <ClassRoster roster={dash.roster} />
        <RoomMap map={dash.map} room={dash.course.room} />
      </div>
    </div>
  )
}
