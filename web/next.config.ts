import type { NextConfig } from "next";

// The browser only ever talks to the Next.js origin; these rewrites proxy the
// API and the voice agent's LLM endpoint to the FastAPI backend. Keeping the
// SSE stream same-origin means EventSource sends the session cookie and the
// backend's Origin check sees a value it allows.
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backendUrl}/api/:path*` },
      { source: "/llm/:path*", destination: `${backendUrl}/llm/:path*` },
    ];
  },
};

export default nextConfig;
