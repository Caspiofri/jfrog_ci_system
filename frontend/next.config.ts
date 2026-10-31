import type { NextConfig } from "next";

// The browser calls /api/v1/* on the Next server, which forwards to the CI API.
// Same origin, so the backend needs no CORS. Dev API: python -m ci.api --port 8011 (run in the worktree).
const API = process.env.CI_API_URL ?? "http://127.0.0.1:8011";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${API}/api/v1/:path*` }];
  },
};

export default nextConfig;
