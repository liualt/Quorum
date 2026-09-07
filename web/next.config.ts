import type { NextConfig } from "next";

// The browser only ever talks to the Next.js origin; these rewrites proxy the
// API and the voice agent's LLM endpoint to the FastAPI backend. Keeping the
// SSE stream same-origin means EventSource sends the session cookie and the
// backend's Origin check sees a value it allows.
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // The proxied event stream must not be gzipped: the compressor holds each
  // small SSE frame back until its buffer fills, so the browser sees nothing
  // until the connection closes. Interim: the backend will send
  // `Cache-Control: no-transform` on its SSE routes, which the compressor
  // honours, and then this returns to the default.
  compress: false,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backendUrl}/api/:path*` },
      { source: "/llm/:path*", destination: `${backendUrl}/llm/:path*` },
    ];
  },
};

export default nextConfig;
