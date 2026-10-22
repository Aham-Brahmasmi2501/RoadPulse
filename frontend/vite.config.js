import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies the FastAPI backend so the browser only talks to one origin.
const API = process.env.ROADPULSE_API || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: API, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, '') },
      '/media': { target: API, changeOrigin: true },
    },
  },
})
