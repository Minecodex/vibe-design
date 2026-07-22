import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const usePolling = process.env.CHOKIDAR_USEPOLLING === 'true'

  return {
    envPrefix: ['VITE_', 'APP_'],
    plugins: [react(), tailwindcss()],
    optimizeDeps: {
      include: ['react-markdown', 'remark-gfm'],
    },
    resolve: {
      dedupe: [
        '@wendellhu/redi',
        '@univerjs/core',
        '@univerjs/design',
        '@univerjs/docs',
        '@univerjs/docs-ui',
        '@univerjs/engine-formula',
        '@univerjs/engine-render',
        '@univerjs/network',
        '@univerjs/preset-docs-core',
        '@univerjs/preset-sheets-core',
        '@univerjs/presets',
        '@univerjs/sheets',
        '@univerjs/sheets-formula',
        '@univerjs/sheets-formula-ui',
        '@univerjs/sheets-numfmt',
        '@univerjs/sheets-numfmt-ui',
        '@univerjs/sheets-ui',
        '@univerjs/ui',
      ],
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: parseInt(process.env.PORT || '5173'),
      host: '0.0.0.0',
      watch: {
        usePolling,
        interval: usePolling ? 300 : undefined,
        ignored: ['**/node_modules/**', '**/dist/**', '**/.git/**'],
      },
      proxy: {
        '/api': {
          target: env.VITE_PROXY_TARGET || env.APP_API_BASE_URL?.replace('/api/v1', '') || 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: mode !== 'production',
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom', 'react-router-dom'],
            state: ['zustand', 'axios'],
          },
        },
      },
    },
  }
})
