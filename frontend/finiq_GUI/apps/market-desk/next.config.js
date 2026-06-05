const path = require('path')

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
        destination: 'http://127.0.0.1:8765/api/:path*' // Backend port updated to match default configuration
      }
    ]
  }
}

module.exports = nextConfig
