import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";
const backend = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  // `next dev` serves on :3000, so proxy /api to the FastAPI backend. Rewrites are
  // unsupported by `output: export`, hence dev-only.
  ...(isDev
    ? {
        // Gzip buffers the proxied SSE body, so ticks never flush to the browser.
        compress: false,
        async rewrites() {
          return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
        },
      }
    : {}),
};

export default nextConfig;
