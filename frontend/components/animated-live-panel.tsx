"use client";

import { useState, useEffect } from "react";
import { ChevronDown } from "lucide-react";
import { motion } from "framer-motion";

// === AnimatedLivePanel: React 状态驱动 + framer-motion layout ===
// height: "auto" + spring 200/25 → 文字换行时果冻般平滑撑开
// exit 改为极短 fade-out (100ms tween) → 退场干脆, 不弹跳
// reasoningAutoCollapse 概念与 ReasoningPanel.autoCollapse 一致:
//   - reasoning 出现: 展开
//   - content 出现 (reasoningAutoCollapse=true): 折叠
export default function AnimatedLivePanel({
  reasoning,
  content,
  time,
}: {
  reasoning: string;
  content: string;
  time: number;
}) {
  // 当 content 出现时, 思考框应该自动折叠 (与 ReasoningPanel.autoCollapse 同概念)
  const reasoningAutoCollapse = !!content;

  // 初始值: 有 content → 直接折叠, 无 content → 展开
  const [isReasoningExpanded, setIsReasoningExpanded] = useState(!reasoningAutoCollapse);

  // reasoning 从空变有时 (新一轮开始), 重新展开 — 同 ReasoningPanel 模式
  useEffect(() => {
    if (reasoning) {
      setIsReasoningExpanded(true);
    }
  }, [reasoning]);

  // content 出现时折叠思考 (与 ReasoningPanel.autoCollapse 行为一致)
  useEffect(() => {
    if (content) {
      setIsReasoningExpanded(false);
    }
  }, [content]);

  return (
    <motion.div
      layout
      transition={{ duration: 0.2, ease: "easeOut" }}
      className={content ? "mb-8" : "mb-2"}
    >
      {reasoning && (
        <motion.div
          key="reasoning-box"
          layout
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            layout: { duration: 0.2, ease: "easeOut" },
            opacity: { duration: 0.1, ease: "linear" },
            default: { duration: 0.1 }
          }}
          className="mb-2 pl-4 border-l-2 border-indigo-200 dark:border-indigo-800 bg-slate-50/40 dark:bg-zinc-850/40 rounded-r-sm p-3"
        >
          <button
            onClick={() => setIsReasoningExpanded(!isReasoningExpanded)}
            className="w-full flex items-center justify-between text-[10px] text-indigo-400 dark:text-indigo-500 uppercase tracking-wider font-semibold select-none"
          >
            <span>
              {isReasoningExpanded
                ? `正在思考 ${time} 秒`
                : "已完成思考"}
            </span>
            <motion.span
              animate={{ rotate: isReasoningExpanded ? 180 : 0 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="inline-flex"
            >
              <ChevronDown className="w-3.5 h-3.5" />
            </motion.span>
          </button>
          {isReasoningExpanded && (
            <div className="mt-1 text-xs text-slate-400 dark:text-zinc-400 font-mono whitespace-pre-wrap leading-relaxed">
              {reasoning}
            </div>
          )}
        </motion.div>
      )}

      {content && (
        <motion.div
          key="content-box"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          // 不带 layout: 正文换行时高度直接跳,无果冻
          // 保留 motion 包装供 AnimatePresence 处理退场
          transition={{ duration: 0.2 }}
          className="text-[15px] text-slate-700 dark:text-zinc-200 leading-relaxed select-text"
        >
          {content}
        </motion.div>
      )}
    </motion.div>
  );
}
