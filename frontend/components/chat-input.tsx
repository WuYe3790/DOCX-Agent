"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Send } from "lucide-react";

interface ChatInputProps {
  inputValue: string;
  isConnected: boolean;
  isWaitingApproval: boolean;
  isGenerating: boolean;
  liveReasoning: string;
  liveContent: string;
  onChangeInput: (value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
}

// === ChatInput: footer 输入框 + 悬浮系统路由胶囊 ===
// 胶囊在 isGenerating && !liveReasoning && !liveContent 时出现
// (即后端在路由, 但 LLM 还没开始推 reasoning / content 的间隙)
export default function ChatInput({
  inputValue,
  isConnected,
  isWaitingApproval,
  isGenerating,
  liveReasoning,
  liveContent,
  onChangeInput,
  onSubmit,
}: ChatInputProps) {
  // 胶囊显示条件: 仅在 isGenerating && 流式尚未开始时
  const showSystemRoutingPill = isGenerating && !liveReasoning && !liveContent;

  return (
    <footer className="bg-white/70 dark:bg-zinc-900/70 backdrop-blur-md sticky bottom-0 z-50 p-4 shrink-0 relative">
      {/* === 悬浮毛玻璃状态胶囊 (脱离文档流,0抖动) === */}
      <AnimatePresence>
        {showSystemRoutingPill && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 5, transition: { duration: 0.2 } }}
            className="absolute -top-6 left-1/2 -translate-x-1/2 px-3 py-1.5 bg-white/90 dark:bg-zinc-800/90 backdrop-blur-sm shadow-sm border border-slate-200/50 dark:border-zinc-700/50 rounded-full flex items-center gap-2 z-50 pointer-events-none"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
            <span className="text-[10px] font-mono font-bold text-slate-500 dark:text-zinc-400 tracking-wider uppercase">
              System Routing
            </span>
          </motion.div>
        )}
      </AnimatePresence>
      <form onSubmit={onSubmit} className="max-w-4xl w-full mx-auto flex items-center gap-3">
        <input
          type="text"
          placeholder={
            isWaitingApproval
              ? "审批挂起中，请完成上方确认或提交反馈意见..."
              : isConnected
              ? "输入追加排版或段落修改需求..."
              : "输入您的问题或排版需求以开始会话..."
          }
          value={inputValue}
          onChange={(e) => onChangeInput(e.target.value)}
          disabled={isWaitingApproval}
          className="flex-1 min-h-[44px] bg-white/80 dark:bg-zinc-800/80 border border-slate-200/60 dark:border-zinc-700/60 focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 rounded-xl px-4 py-2 text-sm placeholder:text-slate-400 dark:placeholder:text-zinc-500 outline-0 disabled:bg-slate-100 disabled:text-slate-400 select-text shadow-sm backdrop-blur-sm"
        />
        <button
          type="submit"
          disabled={!inputValue.trim() || isWaitingApproval}
          className="w-11 h-11 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-100 dark:disabled:bg-zinc-850 dark:disabled:text-zinc-600 text-white rounded-xl flex items-center justify-center shadow-sm hover:shadow-md transition-all duration-150 cursor-pointer"
        >
          <Send className="w-5 h-5" />
        </button>
      </form>
    </footer>
  );
}
