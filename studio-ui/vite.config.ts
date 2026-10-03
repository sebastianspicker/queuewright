import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: process.env.VITE_STATIC_DEMO === 'true' ? '/queuewright/' : '/',
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    fs: {
      strict: true,
      allow: [
        '.',
        '../queuewright/examples/minimal/profile.json',
        '../queuewright/examples/minimal/desired-state.json',
        '../queuewright/examples/minimal/project-v2.json',
        '../queuewright/examples/university/profile.json',
        '../queuewright/examples/university/university.desired-state.json',
        '../queuewright/examples/university/project-v2.json',
        '../queuewright/contracts/catalogs/features.json',
      ],
    },
    proxy: {
      '/api/v1': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/api/v2': { target: 'http://127.0.0.1:8765', changeOrigin: true },
    },
  },
})
