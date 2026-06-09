"use client";

import { PanelLeft } from "lucide-react";

interface ChatHeaderProps {
  docxPath: string;
  isConnected: boolean;
  tokenCount: number;
  hasDraftFiles: boolean;
  showPreview: boolean;
  sidebarOpen: boolean;
  currentSessionId: string | null;
  onToggleSidebar: () => void;
  onTogglePreview: () => void;
  onResetWorkspace: () => void;
}

// === ChatHeader: 顶部 Header Bar ===
// 左侧: 会话管理按钮 + 标题 + docxPath 路径徽章
// 右侧: 连接状态点 + token 进度条 + 草稿切换按钮 + 重置按钮
export default function ChatHeader({
  docxPath,
  isConnected,
  tokenCount,
  hasDraftFiles,
  showPreview,
  sidebarOpen,
  currentSessionId,
  onToggleSidebar,
  onTogglePreview,
  onResetWorkspace,
}: ChatHeaderProps) {
  return (
    <header className="h-14 bg-white/70 dark:bg-zinc-900/70 backdrop-blur-md sticky top-0 z-50 px-6 flex items-center justify-between shrink-0">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className={`p-1.5 rounded-md border transition-colors cursor-pointer ${
            sidebarOpen
              ? "border-indigo-300 bg-indigo-50 dark:border-indigo-700 dark:bg-indigo-900/30"
              : "border-slate-200 dark:border-zinc-700 hover:bg-slate-50 dark:hover:bg-zinc-800"
          }`}
          aria-label="会话管理"
          title="会话管理"
        >
          <PanelLeft className="w-4 h-4 text-slate-600 dark:text-zinc-300" />
        </button>
        <span className="font-mono font-bold text-sm tracking-wider uppercase text-slate-800 dark:text-zinc-100">
          DOCX-Agent 交互工作台
        </span>
        {docxPath && (
          <span className="text-[10px] font-mono px-2 py-0.5 border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800 text-slate-500 rounded truncate max-w-xs md:max-w-md">
            {docxPath}
          </span>
        )}
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className={`w-2.5 h-2.5 rounded-full ${isConnected ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} />
          <span className="text-xs font-mono text-slate-500">{isConnected ? "已连接" : "已断开"}</span>
        </div>

        {tokenCount > 0 && (
          <div className="flex items-center gap-2">
            <div className="w-24 h-1.5 bg-slate-200 dark:bg-zinc-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  tokenCount > 150000 ? "bg-amber-500" : tokenCount > 100000 ? "bg-emerald-500" : "bg-indigo-500"
                }`}
                style={{ width: `${Math.min((tokenCount / 200000) * 100, 100)}%` }}
              />
            </div>
            <span className="text-[10px] font-mono text-slate-400">
              {tokenCount > 1000 ? `${(tokenCount / 1000).toFixed(0)}k` : tokenCount}
            </span>
          </div>
        )}

        {hasDraftFiles && (
          <button
            onClick={onTogglePreview}
            className="px-3 py-1 text-xs font-semibold border border-indigo-200 dark:border-indigo-800 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded transition-colors cursor-pointer text-indigo-600 dark:text-indigo-400"
          >
            {showPreview ? "隐藏草稿" : "查看草稿"}
          </button>
        )}

        <button
          onClick={onResetWorkspace}
          className="px-3 py-1 text-xs font-semibold border border-slate-200 dark:border-zinc-700 hover:bg-slate-50 dark:hover:bg-zinc-800 rounded transition-colors cursor-pointer text-slate-600 dark:text-zinc-300"
        >
          重置会话
        </button>
      </div>
    </header>
  );
}
