const path = require('path')

const apiBaseUrl = (process.env.FINIQ_API_BASE_URL || 'http://127.0.0.1:8765').replace(/\/$/, '')

/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ['@finiq/theme', '@finiq/ui', '@finiq/graph-viewer'],
  turbopack: {
    root: path.resolve(__dirname, '../../..'),
  },
  experimental: {
    staleTimes: {
      dynamic: 30,
    },
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${apiBaseUrl}/api/:path*`
      }
    ]
  }
}

module.exports = nextConfig
