import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

const p = (path: string) => fileURLToPath(new URL(path, import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // components/ui e lib vêm da loja (sem duplicar). Os mais específicos vêm antes de '@'.
    alias: [
      { find: '@/components/ui', replacement: p('../frontend/src/components/ui') },
      { find: '@/lib', replacement: p('../frontend/src/lib') },
      { find: '@', replacement: p('./src') },
    ],
  },
  server: {
    fs: { allow: ['..'] },
    port: 5174,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
