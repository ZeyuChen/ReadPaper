import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  output: "standalone",
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "lh3.googleusercontent.com",
      },
      {
        protocol: "https",
        hostname: "lh3.googleusercontent.com",
      },
    ],
  },
  async rewrites() {
    return [
      {
        source: '/backend/:path*',
        // Route to our internal API route handler which reads API_URL at runtime.
        // next.config.ts rewrites() are evaluated at BUILD time, so env vars like
        // API_URL are not available here. The /api/backend/* route reads them at
        // REQUEST time instead.
        destination: '/api/backend/:path*',
      },
    ];
  },
};

export default nextConfig;
