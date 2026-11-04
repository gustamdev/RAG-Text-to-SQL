import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Encaminha /api/* para o backend FastAPI (porta 8000), evitando CORS no dev.
    // Sem rewrite: as rotas do backend já vivem em /api/{versão}/... (ver app/main.py).
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
