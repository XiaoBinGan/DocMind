/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  transpilePackages: [],
  async rewrites() {
    return [
      {
        source: '/api-catalog/:path*',
        destination: 'http://localhost:8000/api-catalog/:path*',
      },
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
    ]
  },
}

module.exports = nextConfig
