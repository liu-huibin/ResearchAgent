import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const backendUrl = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rolldownOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('/pdfjs-dist/') || id.includes('/react-pdf/')) return 'pdf'
          if (id.includes('/mammoth/')) return 'mammoth'
          if (
            id.includes('/react-markdown/') ||
            id.includes('/remark-') ||
            id.includes('/unified/') ||
            id.includes('/micromark') ||
            id.includes('/mdast-') ||
            id.includes('/hast-')
          ) return 'markdown'
          if (id.includes('/react/') || id.includes('/react-dom/')) return 'react'
          return 'vendor'
        },
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: backendUrl,
        changeOrigin: true,
      },
    },
  },
})
