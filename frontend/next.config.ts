import type { NextConfig } from "next";

// v2: 前端 fetch('/api/*') 通过 rewrites 代理到后端 FastAPI :8000
// (避免 CORS + 浏览器同源问题; 前端代码不感知后端地址)
// WebSocket 走绝对地址 ws://127.0.0.1:8000/api/ws/agent (Next.js dev server 不支持 WS 代理)
const BACKEND_ORIGIN = "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/sessions",
        destination: `${BACKEND_ORIGIN}/api/sessions`,
      },
      {
        source: "/api/sessions/:id",
        destination: `${BACKEND_ORIGIN}/api/sessions/:id`,
      },
      {
        source: "/api/style/analyze",
        destination: `${BACKEND_ORIGIN}/api/style/analyze`,
      },
      {
        source: "/api/word/compile",
        destination: `${BACKEND_ORIGIN}/api/word/compile`,
      },
      {
        source: "/api/word/diff",
        destination: `${BACKEND_ORIGIN}/api/word/diff`,
      },
      {
        source: "/api/download",
        destination: `${BACKEND_ORIGIN}/api/download`,
      },
    ];
  },
};

export default nextConfig;
