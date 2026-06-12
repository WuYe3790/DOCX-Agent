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
        // v3 修复: 之前列表里没有这条规则, 前端 fetch('/api/sessions/<id>/drafts')
        // 不会被代理到后端, Next.js 自己 404
        // 后果: fetchDrafts 永远失败 → draftFiles 保持空 → "查看草稿"按钮不渲染
        source: "/api/sessions/:id/drafts",
        destination: `${BACKEND_ORIGIN}/api/sessions/:id/drafts`,
      },
      {
        // v4 修复: 代理 session 相关的通配子路由（包括 workspace/upload、workspace/clear 等）
        source: "/api/sessions/:id/:path*",
        destination: `${BACKEND_ORIGIN}/api/sessions/:id/:path*`,
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
        // v3: 实时 DOCX 预览 — 替换原 /api/download 死端点
        source: "/api/word/preview",
        destination: `${BACKEND_ORIGIN}/api/word/preview`,
      },
    ];
  },
};

export default nextConfig;
