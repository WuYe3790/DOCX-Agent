"use client";

import { motion, AnimatePresence } from "framer-motion";
import { FileText, X } from "lucide-react";
import MarkdownRenderer from "./markdown-renderer";

interface PreviewPanelProps {
  show: boolean;
  content: string;
  onClose: () => void;
}

/**
 * 侧边栏分屏预览面板（仿 Claude Artifacts 风格）
 * - show=true 时宽度从 0 平滑展开至 50%；show=false 时收缩回 0
 * - 使用 AnimatePresence 包裹条件渲染，exit 动画保证退场丝滑
 * - 内容区采用 A4 白纸居中卡片样式，内部复用 MarkdownRenderer
 */
export default function PreviewPanel({ show, content, onClose }: PreviewPanelProps) {
  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.div
          key="preview-panel"
          initial={{ width: 0 }}
          animate={{ width: "50%" }}
          exit={{ width: 0 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className="h-full shrink-0 border-l border-slate-200/60 dark:border-zinc-800/60 bg-white/70 dark:bg-zinc-900/70 backdrop-blur-md shadow-2xl overflow-hidden"
        >
          <div className="h-full flex flex-col">
            {/* Header：FileText 图标标题 + X 关闭按钮 */}
            <div className="h-14 px-4 flex items-center justify-between border-b border-slate-200/60 dark:border-zinc-800/60 shrink-0 bg-white/40 dark:bg-zinc-900/40">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-indigo-400 dark:text-indigo-500" />
                <span className="text-xs font-mono font-semibold text-slate-700 dark:text-zinc-200 uppercase tracking-wider">
                  草稿预览
                </span>
              </div>
              <button
                onClick={onClose}
                className="p-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors text-slate-500 dark:text-zinc-400 hover:text-slate-700 dark:hover:text-zinc-200"
                aria-label="关闭预览"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* A4 卡片主体 */}
            <div className="flex-1 overflow-y-auto p-4 md:p-6 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
              <div className="max-w-3xl mx-auto bg-white dark:bg-zinc-950 shadow-sm rounded-md p-8 md:p-12 min-h-[800px] border border-slate-200/40 dark:border-zinc-800/40">
                <MarkdownRenderer content={content} />
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
