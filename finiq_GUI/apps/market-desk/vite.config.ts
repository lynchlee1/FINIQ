import { resolve } from 'node:path'
import { defineConfig } from 'vite'

const downloadAliasPlugin = () => ({
  name: 'download-alias',
  configureServer(server) {
    server.middlewares.use((request, _response, next) => {
      if (request.url === '/download') {
        request.url = '/download.html'
      } else if (request.url === '/table') {
        request.url = '/table.html'
      } else if (request.url === '/filter') {
        request.url = '/filter.html'
      } else if (request.url === '/html-download') {
        request.url = '/html-download.html'
      } else if (request.url === '/html-parse') {
        request.url = '/html-parse.html'
      } else if (request.url === '/html-bond-summary') {
        request.url = '/html-bond-summary.html'
      }
      next()
    })
  },
  configurePreviewServer(server) {
    server.middlewares.use((request, _response, next) => {
      if (request.url === '/download') {
        request.url = '/download.html'
      } else if (request.url === '/table') {
        request.url = '/table.html'
      } else if (request.url === '/filter') {
        request.url = '/filter.html'
      } else if (request.url === '/html-download') {
        request.url = '/html-download.html'
      } else if (request.url === '/html-parse') {
        request.url = '/html-parse.html'
      } else if (request.url === '/html-bond-summary') {
        request.url = '/html-bond-summary.html'
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
        table: resolve(__dirname, 'table.html'),
        filter: resolve(__dirname, 'filter.html'),
        htmlDownload: resolve(__dirname, 'html-download.html'),
        htmlParse: resolve(__dirname, 'html-parse.html'),
        htmlBondSummary: resolve(__dirname, 'html-bond-summary.html'),
      },
    },
  },
  server: {
    proxy: {
      '/api': process.env.VITE_API_TARGET || 'http://127.0.0.1:8765',
    },
  },
})
