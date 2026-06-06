"use client";

import { motion, AnimatePresence } from "framer-motion";
import { PanelLeft, Plus, Trash2, FileText, X } from "lucide-react";

// 跟 sessions.ts 的 SessionMeta 类型一致
export interface SessionMeta {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
}

interface SessionSidebarProps {
  show: boolean;
  sessions: SessionMeta[];
  currentSessionId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}

// 相对时间格式化 (中文)
function formatRelativeTime(ts: number): string {
  const now = Date.now();
  const diff = now - ts;
  const minutes = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days = Math.floor(diff / 86_400_000);

  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  if (hours < 24) return `${hours} 小时前`;
  if (days < 7) return `${days} 天前`;
  return new Date(ts).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

/**
 * 左侧会话管理侧栏 (对称于 PreviewPanel)
 * - show=true 时宽度从 0 平滑展开至 300px; show=false 时收缩回 0
 * - 列表渲染仅依赖 SessionMeta 元数据 (不订阅 messages 数组, 避坑 1)
 * - 悬停时显示删除按钮, 激活态有蓝色竖条
 */
export default function SessionSidebar({
  show,
  sessions,
  currentSessionId,
  onSelect,
  onCreate,
  onDelete,
  onClose,
}: SessionSidebarProps) {
  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.div
          key="session-sidebar"
          initial={{ width: 0 }}
          animate={{ width: 300 }}
          exit={{ width: 0 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className="h-full shrink-0 border-r border-slate-200/60 dark:border-zinc-800/60 bg-white/70 dark:bg-zinc-900/70 backdrop-blur-md shadow-2xl overflow-hidden"
        >
          <div className="h-full flex flex-col">
            {/* Header: PanelLeft 图标 + 会话标题 + 新建按钮 + 关闭 X */}
            <div className="h-14 px-4 flex items-center justify-between border-b border-slate-200/60 dark:border-zinc-800/60 shrink-0 bg-white/40 dark:bg-zinc-900/40">
              <div className="flex items-center gap-2">
                <PanelLeft className="w-4 h-4 text-indigo-400 dark:text-indigo-500" />
                <span className="text-xs font-mono font-semibold text-slate-700 dark:text-zinc-200 uppercase tracking-wider">
                  会话
                </span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={onCreate}
                  className="p-1.5 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 transition-colors"
                  aria-label="新建会话"
                  title="新建会话"
                >
                  <Plus className="w-4 h-4" />
                </button>
                <button
                  onClick={onClose}
                  className="p-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-zinc-800 text-slate-500 dark:text-zinc-400 transition-colors"
                  aria-label="关闭侧栏"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* 列表区 (滚动) */}
            <div className="flex-1 overflow-y-auto">
              {sessions.length === 0 ? (
                <div className="p-6 text-center text-xs text-slate-400 dark:text-zinc-500">
                  <FileText className="w-8 h-8 mx-auto mb-2 opacity-50" />
                  <p>暂无会话</p>
                  <p className="mt-1">点击 + 新建一个</p>
                </div>
              ) : (
                <div className="py-2">
                  {sessions.map((s) => {
                    const isActive = s.id === currentSessionId;
                    return (
                      <div
                        key={s.id}
                        onClick={() => onSelect(s.id)}
                        className={`group relative px-4 py-2.5 cursor-pointer transition-colors ${
                          isActive
                            ? "bg-indigo-50/60 dark:bg-indigo-900/20"
                            : "hover:bg-slate-50/60 dark:hover:bg-zinc-800/40"
                        }`}
                      >
                        {/* 当前激活: 左侧 3px 蓝色竖条 */}
                        {isActive && (
                          <div className="absolute left-0 top-1.5 bottom-1.5 w-[3px] bg-indigo-500 rounded-r" />
                        )}
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <div
                              className={`text-[13px] font-medium truncate ${
                                isActive
                                  ? "text-indigo-700 dark:text-indigo-300"
                                  : "text-slate-700 dark:text-zinc-200"
                              }`}
                            >
                              {s.title}
                            </div>
                            <div className="flex items-center gap-1.5 mt-0.5 text-[10px] text-slate-400 dark:text-zinc-500 font-mono">
                              <span>{formatRelativeTime(s.updatedAt)}</span>
                              <span>·</span>
                              <span>{s.messageCount} 条</span>
                            </div>
                          </div>
                          {/* 删除按钮: 悬停时显示 */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onDelete(s.id);
                            }}
                            className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-50 dark:hover:bg-red-900/20 text-slate-400 hover:text-red-500 dark:hover:text-red-400 transition-all shrink-0"
                            aria-label="删除会话"
                            title="删除会话"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
