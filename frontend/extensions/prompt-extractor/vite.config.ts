import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    css: true,
    include: ['extensions/prompt-extractor/tests/**/*.test.{ts,tsx}'],
  },
  resolve: {
    alias: {
      '@prompt-extractor': path.resolve(__dirname, './src'),
    },
  },
})
