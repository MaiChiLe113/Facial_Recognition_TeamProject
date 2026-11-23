import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import basicSsl from '@vitejs/plugin-basic-ssl'

// `npm run dev`      -> http://localhost:5173, this machine only (as before).
// `npm run dev:lan`  -> https://<this machine's Wi-Fi IP>:5173 for every device on the same Wi-Fi.
//    Browsers only allow the camera on https pages or on localhost, so LAN mode serves https with a
//    self-signed certificate (each device accepts the warning once). See docs/LAN_DEMO.md.
export default defineConfig(({ mode }) => {
  const lan = mode === 'lan'
  return {
    plugins: [vue(), lan && basicSsl()],
    server: {
      port: 5173,
      host: lan,                    // false = localhost only
      // The backend runs on :8000 (uvicorn) on this same machine. These paths are forwarded to it, so
      // other devices only need to reach this dev server, never the backend directly.
      proxy: {
        '/api': 'http://localhost:8000',
        '/videos': 'http://localhost:8000',
        '/photos': 'http://localhost:8000',
      },
      // Allows importing the shared mock files from ../data as an offline fallback.
      fs: { allow: ['..'] },
    },
  }
})
