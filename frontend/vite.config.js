import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
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
