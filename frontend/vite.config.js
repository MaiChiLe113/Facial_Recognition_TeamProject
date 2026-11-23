import { existsSync, readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import basicSsl from '@vitejs/plugin-basic-ssl'

// A trusted certificate made with mkcert (docs/LAN_DEMO.md, "No warning"), git-ignored. Without it, LAN mode
// falls back to a self-signed certificate that browsers label "Not secure".
const CERT = new URL('./certs/lan.pem', import.meta.url)
const KEY = new URL('./certs/lan-key.pem', import.meta.url)
const trusted = existsSync(CERT) && existsSync(KEY)
// The backend this dev server forwards to (same machine). HAWKEYE_BACKEND=http://localhost:8001 to use another port.
const BACKEND = process.env.HAWKEYE_BACKEND ?? 'http://localhost:8000'

// `npm run dev`      -> http://localhost:5173, this machine only (as before).
// `npm run dev:lan`  -> https://<this machine's Wi-Fi IP>:5173 for every device on the same Wi-Fi.
//    Browsers only allow the camera on https pages or on localhost, so LAN mode serves https: with the
//    mkcert certificate in certs/ when present, else a self-signed one (each device accepts a warning).
//    See docs/LAN_DEMO.md.
export default defineConfig(({ mode }) => {
  const lan = mode === 'lan'
  return {
    plugins: [vue(), lan && !trusted && basicSsl()],
    server: {
      port: 5173,
      https: lan && trusted ? { cert: readFileSync(CERT), key: readFileSync(KEY) } : undefined,
      host: lan,                    // false = localhost only
      // The backend runs on :8000 (uvicorn) on this same machine. These paths are forwarded to it, so
      // other devices only need to reach this dev server, never the backend directly.
      proxy: {
        '/api': BACKEND,
        '/videos': BACKEND,
        '/photos': BACKEND,
        '/ws': { target: BACKEND.replace(/^http/, 'ws'), ws: true },   // live cameras (Camera page)
      },
      // Allows importing the shared mock files from ../data as an offline fallback.
      fs: { allow: ['..'] },
    },
  }
})
