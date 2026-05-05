import { resolve } from 'node:path'
import { defineConfig } from 'vite'

const downloadAliasPlugin = () => ({
  name: 'download-alias',
  configureServer(server) {
    server.middlewares.use((request, _response, next) => {
      if (request.url === '/download') {
        request.url = '/download.html'
      } else if (request.url === '/filter') {
        request.url = '/filter.html'
      } else if (request.url === '/html-download') {
        request.url = '/html-download.html'
      }
      next()
    })
  },
  configurePreviewServer(server) {
    server.middlewares.use((request, _response, next) => {
      if (request.url === '/download') {
        request.url = '/download.html'
      } else if (request.url === '/filter') {
        request.url = '/filter.html'
      } else if (request.url === '/html-download') {
        request.url = '/html-download.html'
      }
      next()
    })
  },
})

export default defineConfig({
  plugins: [downloadAliasPlugin()],
  build: {
    rollupOptions: {
      input: {
        index: resolve(__dirname, 'index.html'),
        company: resolve(__dirname, 'company.html'),
        download: resolve(__dirname, 'download.html'),
        filter: resolve(__dirname, 'filter.html'),
        htmlDownload: resolve(__dirname, 'html-download.html'),
      },
    },
  },
  server: {
    proxy: {
      '/api': process.env.VITE_API_TARGET || 'http://127.0.0.1:8765',
    },
  },
})
