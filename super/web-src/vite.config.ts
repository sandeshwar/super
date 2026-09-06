import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Build output is served by the Python harness server (super/server.py).
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: '../web/dist',
    emptyOutDir: true,
  },
  server: {
    port: 5311,
    proxy: {
      '/api': 'http://127.0.0.1:4311',
      '/health': 'http://127.0.0.1:4311',
      '/tree': 'http://127.0.0.1:4311',
      '/ledger': 'http://127.0.0.1:4311',
    },
  },
})
