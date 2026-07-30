/// <reference types="vitest/config" />
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
        '../profiles/example/profile.json',
        '../profiles/example/desired-state.json',
        '../studio/catalog/features.json',
        '../studio/catalog/capabilities.json',
        '../studio/templates/university/profile.json',
        '../studio/templates/university/university.desired-state.json',
      ],
    },
    proxy: {
      '/api/v1': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/api/v2': { target: 'http://127.0.0.1:8765', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
    exclude: ['**/node_modules/**', '**/e2e/**'],
  },
})
