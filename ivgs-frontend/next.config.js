/** @type {import('next').NextConfig} */

/*
 * IVGS v5 — Next.js Configuration
 *
 * API proxy: /api/v1/* → http://node-01:8000/api/v1/*
 * Scheduler proxy: /scheduler/* → http://node-01:8001/*
 *
 * Per §8: Dashboard served on node-01 via Nginx.
 * In development, rewrites proxy API requests to avoid CORS.
 * In production, Nginx handles reverse proxy.
 */

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

  /* API proxy rewrites for development */
  async rewrites() {
    const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const schedulerBaseUrl =
      process.env.NEXT_PUBLIC_SCHEDULER_URL || "http://localhost:8001";

    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiBaseUrl}/api/v1/:path*`,
      },
      {
        source: "/scheduler/:path*",
        destination: `${schedulerBaseUrl}/:path*`,
      },
    ];
  },

  /* Image optimization domains — SeaweedFS filer */
  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "node-01",
        port: "8888",
        pathname: "/ivgs/**",
      },
    ],
    unoptimized: process.env.NODE_ENV === "development",
  },

  /* Disable telemetry */
  env: {
    NEXT_TELEMETRY_DISABLED: "1",
  },

  /* Output standalone for Docker deployment */
  output: "standalone",
};

module.exports = nextConfig;
