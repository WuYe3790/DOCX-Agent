"use client";

import { motion, AnimatePresence } from "framer-motion";
import { User } from "lucide-react";
import MarkdownRenderer from "./markdown-renderer";
import ReasoningPanel from "./reasoning-panel";
import type { RenderBlock } from "../lib/message-types";

interface ChatMessageBlocksProps {
  blocks: RenderBlock[];
  isGenerating: boolean;
  selectedToolId: string | null;
  onSelectTool: (id: string | null) => void;
}

// === ChatMessageBlocks: 渲染 4 种类型化消息块 (user / reasoning / content / toolGroup) ===
// marginClass 派生逻辑在内部, 不上抛不外泄
// page 只负责算好 blocks 数组, 组件内只做纯渲染
export default function ChatMessageBlocks({
  blocks,
  isGenerating,
  selectedToolId,
  onSelectTool,
}: ChatMessageBlocksProps) {
  return (
    <>
      {blocks.map((block, index) => {
        const nextBlock = blocks[index + 1];

        // === 动态 Margin 终极规则：自适应上下文 ===
        let marginClass = "mb-8";
        const isLast = index === blocks.length - 1;

        if (!isLast) {
          // 情况 1：后面还有历史区块
          if (nextBlock?.type === "user") {
            // 下一个是用户的提问，说明 AI 这一轮回合彻底结束了，必须留出标准的呼吸间距
            marginClass = "mb-8";
          } else {
            // 下一个还是 AI 的输出（工具、思考或正文），说明它们属于同一个思维链，紧凑排版
            marginClass = "mb-2";
          }
        } else {
          // 情况 2：这是当前历史记录里的最后一个区块
          if (isGenerating) {
            // 系统仍在生成中！说明它的正下方紧紧挨着 AnimatedLivePanel 实时流组件，必须无缝拼接！
            marginClass = "mb-2";
          } else {
            // 系统已闲置，生成彻底结束。下方是空白区或输入框，留出大间距
            marginClass = "mb-8";
          }
        }

        switch (block.type) {
          case "user":
            return (
              <div key={block.id} className="mb-6 pl-9 relative">
                <User size={14} className="absolute left-0 top-[2px] text-indigo-400 dark:text-indigo-500" />
                <p className="whitespace-pre-wrap select-text text-[15px] font-medium text-slate-800 dark:text-zinc-100 leading-relaxed">
                  {block.content}
                </p>
              </div>
            );

          case "reasoning":
            return (
              <div key={block.id} className={marginClass}>
                <ReasoningPanel
                  content={block.content!}
                  autoCollapse={block.autoCollapse ?? false}
                />
              </div>
            );

          case "content":
            return (
              <div
                key={block.id}
                className={`text-[15px] text-slate-700 dark:text-zinc-200 leading-relaxed select-text ${marginClass}`}
              >
                <MarkdownRenderer content={block.content!} />
              </div>
            );

          case "toolGroup":
            return (
              <motion.div
                key={block.id}
                className={`flex flex-wrap gap-x-4 gap-y-1 max-w-[90%] mt-1 pl-3 border-l-2 border-slate-200/60 dark:border-zinc-800/60 ${marginClass}`}
                layout
              >
                <AnimatePresence mode="popLayout">
                  {block.tools!.map((tool, tIdx) => {
                    const isExpanded = selectedToolId === tool.id;
                    return (
                      <motion.div
                        key={tool.id || `tool-${tIdx}`}
                        className="relative"
                        layout
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, transition: { duration: 0.1 } }}
                        // 拆分 transition: layout 点击展开 0 延迟, opacity/y 入场等 0.4s 避让思考框
                        transition={{
                          layout: { duration: 0.2, ease: "easeOut" },
                          // 核心修复：基础等待 0.4s（避让思考框），后续每个工具依次再额外延后 0.1s，形成丝滑的连续弹出效果
                          opacity: { delay: 0.4 + tIdx * 0.1, duration: 0.2 },
                          y: { delay: 0.4 + tIdx * 0.1, duration: 0.2, ease: "easeOut" },
                        }}
                      >
                        <span
                          onClick={() => onSelectTool(isExpanded ? null : (tool.id ?? null))}
                          className={`inline-flex items-center gap-1 font-mono text-[11px] cursor-pointer select-none ${
                            tool.toolStatus === "running"
                              ? "text-blue-400 dark:text-blue-400"
                              : tool.toolStatus === "error"
                              ? "text-red-400 dark:text-red-400"
                              : "text-slate-400 dark:text-zinc-500 hover:text-slate-600 dark:hover:text-zinc-400"
                          } ${tool.toolStatus === "running" ? "animate-pulse" : ""}`}
                        >
                          <span className="text-slate-300 dark:text-zinc-700 text-[10px]">{">"}_{
                            tool.toolName
                          }</span>
                        </span>

                        {isExpanded && (
                          <div className="mt-2 w-full max-w-[600px] border border-slate-200/60 dark:border-zinc-800/60 bg-slate-50/80 dark:bg-zinc-900/50 backdrop-blur-sm rounded-md p-3 space-y-3">
                            {tool.toolArgs && (
                              <div>
                                <p className="text-[9px] font-mono text-slate-400 dark:text-zinc-600 uppercase tracking-widest font-semibold mb-1.5">args</p>
                                <pre className="text-[10px] font-mono bg-white/60 dark:bg-zinc-950/60 p-2 rounded text-slate-500 dark:text-zinc-400 whitespace-pre-wrap break-all leading-relaxed max-h-40 overflow-y-auto">
                                  {tool.toolArgs}
                                </pre>
                              </div>
                            )}
                            {tool.toolResult && (
                              <div>
                                <p className="text-[9px] font-mono text-slate-400 dark:text-zinc-600 uppercase tracking-widest font-semibold mb-1.5">result</p>
                                <pre className="text-[10px] font-mono bg-white/60 dark:bg-zinc-950/60 p-2 rounded text-slate-500 dark:text-zinc-400 whitespace-pre-wrap break-all leading-relaxed max-h-48 overflow-y-auto">
                                  {tool.toolResult}
                                </pre>
                              </div>
                            )}
                          </div>
                        )}
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              </motion.div>
            );

          default:
            return null;
        }
      })}
    </>
  );
}
