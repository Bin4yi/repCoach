import type { NextConfig } from "next";

// The browser talks to /api/* on the same origin; Next proxies it to the FastAPI backend.
// This keeps the coach cookie first-party (no CORS / third-party cookie trouble).
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const config: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/:path*` }];
  },
  // Videos can be up to 100 MB; let the proxy stream them through.
  experimental: { proxyClientMaxBodySize: "110mb" },
};

export default config;
