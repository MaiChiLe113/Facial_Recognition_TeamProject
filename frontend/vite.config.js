import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // The backend runs on :8000 (uvicorn). These paths are forwarded to it.
    proxy: {
      '/api': 'http://localhost:8000',
      '/videos': 'http://localhost:8000',
    },
    // Allows importing the shared mock files from ../data as an offline fallback.
    fs: { allow: ['..'] },
  },
})
