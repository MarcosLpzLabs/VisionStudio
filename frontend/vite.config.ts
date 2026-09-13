import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Configuración de Vite.
// En desarrollo sirve el frontend en :5173 y reenvía /api y /ws al backend
// (uvicorn en :8000), evitando CORS. El build produce frontend/dist, que el
// backend sirve como aplicación unificada (docs/ARQUITECTURA.md §10).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  build: {
    outDir: 'dist',
  },
})