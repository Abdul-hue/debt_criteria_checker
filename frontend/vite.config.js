import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8005',
        changeOrigin: true,
        configure: (proxy, options) => {
          proxy.on('proxyReq', (proxyReq, req, res) => {
            console.log(`[Proxy] Sending Request: ${req.method} ${req.url} -> ${options.target}${req.url}`);
          });
          proxy.on('error', (err, req, res) => {
            console.log('[Proxy] Error:', err);
          });
        },
      },
    },
  },
})
