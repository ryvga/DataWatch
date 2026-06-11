import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// When running inside Docker Compose, set API_TARGET=http://api:8000
const apiTarget = process.env.API_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(process.cwd(), './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('recharts') || id.includes('date-fns') || id.includes('d3-')) {
            return 'charts'
          }
          return 'vendor'
        },
      },
    },
  },
  server: {
    // '0.0.0.0' lets *.localhost subdomains resolve to this dev server
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api':    { target: apiTarget, changeOrigin: true },
      '/auth':   { target: apiTarget, changeOrigin: true },
      '/orgs':   { target: apiTarget, changeOrigin: true },
      '/health': { target: apiTarget, changeOrigin: true },
    },
  },
})
