"use client";

import { useState, useEffect, useRef } from "react";
import { ChevronDown } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

// === ReasoningPanel: 渲染已定型历史, 支持手动折叠 + autoCollapse 接力 ===
// autoCollapse=true 时, 400ms 后自动收起 (历史 thinking 接力折叠)
// height 改 "auto" 替代 max-height, 真正解决"收起卡顿"
export default function ReasoningPanel({
  content,
  autoCollapse = false,
}: {
  content: string;
  autoCollapse?: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(autoCollapse);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // autoCollapse 模式: 50ms 后极速触发收起 (光速折叠, 不留可见的展开过程)
  useEffect(() => {
    if (autoCollapse) {
      const timer = setTimeout(() => setIsExpanded(false), 50);
      return () => clearTimeout(timer);
    }
  }, [autoCollapse]);

  if (!content) return null;

  return (
    <div className="pl-4 border-l-2 border-indigo-200 dark:border-indigo-800 bg-slate-50/40 dark:bg-zinc-850/40 rounded-r-sm overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-3 py-2 text-[10px] font-mono font-medium text-indigo-400 dark:text-indigo-500 uppercase tracking-wider hover:bg-slate-100/60 dark:hover:bg-zinc-800/60"
      >
        <span>已完成思考</span>
        <motion.span
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          className="inline-flex"
        >
          <ChevronDown className="w-3.5 h-3.5" />
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            key="reasoning-content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 text-xs text-slate-400 dark:text-zinc-400 font-mono whitespace-pre-wrap leading-relaxed">
              {content}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
