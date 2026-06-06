"use client";

import React, { useState, useEffect, useRef } from "react";
import { Terminal, Send, CheckCircle2, ChevronDown, RefreshCw, User } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import MarkdownRenderer from "../components/markdown-renderer";
import PreviewPanel from "../components/preview-panel";

interface Message {
  role: "user" | "assistant" | "tool";
  content?: string;
  reasoning_content?: string;
  toolName?: string;
  toolArgs?: string;
  toolResult?: string;
  toolStatus?: "running" | "success" | "error";
  id?: string;
}

interface TokenInfo {
  token_count: number;
}

// === ReasoningPanel: 渲染已定型历史, 支持手动折叠 + autoCollapse 接力 ===
// autoCollapse=true 时, 400ms 后自动收起 (历史 thinking 接力折叠)
// height 改 "auto" 替代 max-height, 真正解决"收起卡顿"
function ReasoningPanel({
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

// === AnimatedLivePanel: React 状态驱动 + framer-motion layout ===
// height: "auto" + spring 200/25 → 文字换行时果冻般平滑撑开
// exit 改为极短 fade-out (100ms tween) → 退场干脆, 不弹跳
// reasoningAutoCollapse 概念与 ReasoningPanel.autoCollapse 一致:
//   - reasoning 出现: 展开
//   - content 出现 (reasoningAutoCollapse=true): 折叠
function AnimatedLivePanel({
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

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isWaitingApproval, setIsWaitingApproval] = useState<boolean>(false);
  const [approvalPhase, setApprovalPhase] = useState<"style_review" | "md_draft" | "word_editing" | null>(null);
  const [docxPath, setDocxPath] = useState<string>("");
  const [inputValue, setInputValue] = useState<string>("");
  const [feedbackValue, setFeedbackValue] = useState<string>("");
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const [selectedToolId, setSelectedToolId] = useState<string | null>(null);
  const [tokenCount, setTokenCount] = useState<number>(0);

  // === 草稿预览侧栏 (md_draft 阶段自动展开) ===
  const [showPreview, setShowPreview] = useState<boolean>(false);
  const [previewContent, setPreviewContent] = useState<string>("");

  // === 实时流状态 (RAF 节流) ===
  const [liveReasoning, setLiveReasoning] = useState<string>("");
  const [liveContent, setLiveContent] = useState<string>("");
  const [thinkTime, setThinkTime] = useState<number>(0);

  // === 实时流 Refs ===
  const liveReasoningRef = useRef<string>("");
  const liveContentRef = useRef<string>("");
  const isRenderingRef = useRef<boolean>(false);  // RAF 节流锁
  const thinkTimerRef = useRef<NodeJS.Timeout | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // === 滚动意图侦测 (修复 2) ===
  const isScrolledToBottom = useRef<boolean>(true);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    // 阈值 150px: 离底部 150px 内算"在底部"
    isScrolledToBottom.current = scrollHeight - scrollTop - clientHeight < 150;
  };

  // === 实时流清理 ===
  const clearLiveStream = () => {
    liveReasoningRef.current = "";
    liveContentRef.current = "";
    setLiveReasoning("");
    setLiveContent("");
    setThinkTime(0);
    if (thinkTimerRef.current) {
      clearInterval(thinkTimerRef.current);
      thinkTimerRef.current = null;
    }
  };

  // Auto-scroll chat window (修复 2: 滚动意图侦测)
  useEffect(() => {
    if (!isScrolledToBottom.current) return;
    chatEndRef.current?.scrollIntoView({
      behavior: isGenerating ? "auto" : "smooth",  // 流式用 auto 避免动画排队
    });
  }, [messages, isWaitingApproval, liveReasoning, liveContent, isGenerating]);

  const resetWorkspace = () => {
    setMessages([]);
    clearLiveStream();
    setDocxPath("");
    setIsWaitingApproval(false);
    setApprovalPhase(null);
    setIsGenerating(false);
    setExpandedTools(new Set());
    setSelectedToolId(null);
    setShowPreview(false);
    setPreviewContent("");
    setInputValue("");
    setFeedbackValue("");
    isScrolledToBottom.current = true;  // 重置, 准备跟读
    if (wsRef.current) {
      wsRef.current.close();
    }
  };

  const startAgentSession = (initialPrompt: string, path: string) => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    // 发起新会话: 重置预览侧栏状态
    setShowPreview(false);
    setPreviewContent("");

    const socket = new WebSocket("ws://127.0.0.1:8000/api/ws/agent");
    wsRef.current = socket;

    socket.onopen = () => {
      setIsConnected(true);
      setIsGenerating(true);
      socket.send(
        JSON.stringify({
          type: "start",
          prompt: initialPrompt,
          docx_path: path,
        })
      );
      setMessages((prev) => [...prev, { role: "user", content: initialPrompt }]);
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case "round_start": {
          // 修复 B: 先把当前 ref 里的内容固化为 messages (防止"被后端打回"时数据丢失)
          // 后端在 LLM 漏调/错调工具时会丢弃上一轮 reasoning+content, 直接发 round_start
          // 此时如果没有兜底固化, 用户会看到内容"突然消失"
          const prevR = liveReasoningRef.current;
          const prevC = liveContentRef.current;
          if (prevR || prevC) {
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant" as const,
                content: prevC || undefined,
                reasoning_content: prevR || undefined,
              },
            ]);
          }
          // 然后才清空
          liveReasoningRef.current = "";
          liveContentRef.current = "";
          setLiveReasoning("");
          setLiveContent("");
          setThinkTime(0);

          if (thinkTimerRef.current) clearInterval(thinkTimerRef.current);
          thinkTimerRef.current = setInterval(() => {
            setThinkTime((prev) => prev + 1);
          }, 1000);

          setIsGenerating(true);
          if (data.token_count !== undefined) {
            setTokenCount(data.token_count);
          }
          break;
        }

        case "heartbeat":
          break;

        case "reasoning": {
          // RAF 节流
          liveReasoningRef.current += data.delta;
          if (!isRenderingRef.current) {
            isRenderingRef.current = true;
            requestAnimationFrame(() => {
              setLiveReasoning(liveReasoningRef.current);
              isRenderingRef.current = false;
            });
          }
          break;
        }

        case "content": {
          liveContentRef.current += data.delta;
          if (!isRenderingRef.current) {
            isRenderingRef.current = true;
            requestAnimationFrame(() => {
              setLiveContent(liveContentRef.current);
              isRenderingRef.current = false;
            });
          }
          break;
        }

        case "reasoning_end": {
          // 推理结束: 立即固化思考到历史, 让 ReasoningPanel 触发折叠动画
          // 消除"思考-工具调用"之间的视觉黑洞期
          const txtR = liveReasoningRef.current;
          const txtC = liveContentRef.current;
          if (txtR || txtC) {
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant" as const,
                content: txtC || undefined,
                reasoning_content: txtR || undefined,
              },
            ]);
          }
          clearLiveStream();
          break;
        }

        case "tool_start": {
          // 读 ref 固化为 messages
          const txtR = liveReasoningRef.current;
          const txtC = liveContentRef.current;
          if (txtR || txtC) {
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant" as const,
                content: txtC || undefined,
                reasoning_content: txtR || undefined,
              },
            ]);
          }
          // 延迟一帧清空: 让 messages 推入先 commit, AnimatePresence 看到 exit
          clearLiveStream();
          setMessages((prev) => [
            ...prev,
            {
              role: "tool",
              toolName: data.name,
              toolArgs: data.arguments,
              toolStatus: "running",
              id: data.name + "_" + crypto.randomUUID(),
            },
          ]);
          break;
        }

        case "tool_end": {
          setMessages((prev) =>
            prev.map((msg) => {
              if (msg.role === "tool" && msg.toolName === data.name && msg.toolStatus === "running") {
                return {
                  ...msg,
                  toolStatus: data.result.includes('"status": "error"') ? "error" : "success",
                  toolResult: data.result,
                };
              }
              return msg;
            })
          );
          break;
        }

        case "wait_approval": {
          const txtR = liveReasoningRef.current;
          const txtC = liveContentRef.current;
          if (txtR || txtC) {
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant" as const,
                content: txtC || undefined,
                reasoning_content: txtR || undefined,
              },
            ]);
          }
          clearLiveStream();

          // 修复 1: 智能 push vs merge
          // 如果最后一条是 assistant, 合并 content; 否则 push 新 assistant
          if (data.content !== undefined) {
            setMessages((prev) => {
              const lastIdx = prev.length - 1;
              if (lastIdx >= 0 && prev[lastIdx].role === "assistant") {
                // 最后一条是 assistant: 合并 content
                return [...prev.slice(0, lastIdx), { ...prev[lastIdx], content: data.content }];
              }
              // 最后一条不是 assistant (如 tool): 安全地 push 新 assistant
              return [...prev, { role: "assistant", content: data.content }];
            });
          }
          setApprovalPhase(data.phase);
          setIsWaitingApproval(true);
          setIsGenerating(false);

          // md_draft 阶段: 自动展开右侧预览侧栏(只显示真实草稿, 不再兜底对话 content)
          if (data.phase === "md_draft" && data.draft_content) {
            setPreviewContent(data.draft_content);
            setShowPreview(true);
          }
          break;
        }

        case "done": {
          const txtR = liveReasoningRef.current;
          const txtC = liveContentRef.current;
          if (txtR || txtC) {
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant" as const,
                content: txtC || undefined,
                reasoning_content: txtR || undefined,
              },
            ]);
          }
          clearLiveStream();

          // 修复 1: 同 wait_approval 模式
          if (data.content !== undefined) {
            setMessages((prev) => {
              const lastIdx = prev.length - 1;
              if (lastIdx >= 0 && prev[lastIdx].role === "assistant") {
                return [...prev.slice(0, lastIdx), { ...prev[lastIdx], content: data.content }];
              }
              return [...prev, { role: "assistant", content: data.content }];
            });
          }
          setIsWaitingApproval(false);
          setApprovalPhase(null);
          setIsGenerating(false);
          break;
        }

        case "error":
          setIsGenerating(false);
          alert(`Agent 运行报错: ${data.message}`);
          break;
      }
    };

    socket.onclose = () => {
      setIsConnected(false);
      setIsWaitingApproval(false);
      setApprovalPhase(null);
      setIsGenerating(false);
      if (thinkTimerRef.current) {
        clearInterval(thinkTimerRef.current);
        thinkTimerRef.current = null;
      }
    };

    socket.onerror = (err) => {
      console.error("WebSocket error", err);
      setIsConnected(false);
      setIsWaitingApproval(false);
      setApprovalPhase(null);
      setIsGenerating(false);
    };
  };

  const handleSendPrompt = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim()) return;
    const prompt = inputValue.trim();
    setInputValue("");

    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      isScrolledToBottom.current = true;  // 新会话, 用户应跟读
      setIsGenerating(true);
      startAgentSession(prompt, "");
      return;
    }

    if (isWaitingApproval) return;

    isScrolledToBottom.current = true;  // 修复 2: 用户发了 prompt, 应该跟读
    setMessages((prev) => [...prev, { role: "user", content: prompt }]);
    setIsGenerating(true);
    wsRef.current.send(JSON.stringify({ type: "continue", prompt }));
  };

  const handleApprove = (approved: boolean, feedback?: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      alert("与 Agent 的连接已断开，请重新输入需求开始新会话。");
      return;
    }

    wsRef.current.send(
      JSON.stringify({
        type: "approve",
        approved,
        feedback: feedback || "",
      })
    );

    const userActionText = approved
      ? "【确认同意】同意并进入下一阶段"
      : `【拒绝反馈】反馈修改建议：${feedback}`;
    setMessages((prev) => [...prev, { role: "user", content: userActionText }]);

    isScrolledToBottom.current = true;  // 修复 2: 审批完成, 用户应跟读下一阶段
    setIsWaitingApproval(false);
    setApprovalPhase(null);
    setIsGenerating(true);
  };

  const handleApproveAction = () => {
    handleApprove(true);
  };

  const handleRejectAction = () => {
    if (!feedbackValue.trim()) return;
    handleApprove(false, feedbackValue.trim());
    setFeedbackValue("");
  };

  // === 派生 renderBlocks: 折叠 messages 数组为 4 种类型化渲染块 ===
  // 目的: 让间距判断从"消息本身属性"升级为"前后块类型关系",更精准
  // 类型: user | reasoning | content | toolGroup
  const renderBlocks: Array<{
    type: "user" | "reasoning" | "content" | "toolGroup";
    content?: string;
    tools?: Message[];
    id: string;
    autoCollapse?: boolean;
  }> = [];
  {
    let i = 0;
    while (i < messages.length) {
      const msg = messages[i];
      if (msg.role === "user") {
        renderBlocks.push({ type: "user", content: msg.content, id: `user-${i}` });
        i++;
      } else if (msg.role === "assistant") {
        if (msg.reasoning_content) {
          const hasContentNext = !!msg.content;
          const isLastFew = i >= messages.length - 2;
          renderBlocks.push({
            type: "reasoning",
            content: msg.reasoning_content,
            autoCollapse: isLastFew && !hasContentNext,
            id: `reasoning-${i}`,
          });
        }
        if (msg.content) {
          renderBlocks.push({ type: "content", content: msg.content, id: `content-${i}` });
        }
        i++;
      } else if (msg.role === "tool") {
        const tools: Message[] = [];
        const startIndex = i;   // 核心修复: 锁死这个 toolGroup 的起始索引, id 永远不变 (避免 React 卸载重挂载触发集体重入场)
        while (i < messages.length && messages[i].role === "tool") {
          tools.push(messages[i]);
          i++;
        }
        renderBlocks.push({ type: "toolGroup", tools, id: `toolGroup-${startIndex}` });
      }
    }
  }

  return (
    <div className="w-full h-screen flex flex-col bg-gradient-to-br from-slate-50 via-white to-slate-100 dark:from-zinc-950 dark:via-zinc-900 dark:to-zinc-950 text-slate-900 dark:text-zinc-50 font-sans">
      {/* Header Bar */}
      <header className="h-14 bg-white/70 dark:bg-zinc-900/70 backdrop-blur-md sticky top-0 z-50 px-6 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
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

          {previewContent && (
            <button
              onClick={() => setShowPreview(v => !v)}
              className="px-3 py-1 text-xs font-semibold border border-indigo-200 dark:border-indigo-800 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded transition-colors cursor-pointer text-indigo-600 dark:text-indigo-400"
            >
              {showPreview ? "隐藏草稿" : "查看草稿"}
            </button>
          )}

          <button
            onClick={resetWorkspace}
            className="px-3 py-1 text-xs font-semibold border border-slate-200 dark:border-zinc-700 hover:bg-slate-50 dark:hover:bg-zinc-800 rounded transition-colors cursor-pointer text-slate-600 dark:text-zinc-300"
          >
            重置会话
          </button>
        </div>
      </header>

      {/* 主区域: 横向 flex 父容器, 左侧 chat+input, 右侧 preview */}
      <div className="flex-1 w-full flex overflow-hidden">
        {/* 左侧: 聊天列表 + 输入框 */}
        <div className="flex-1 flex flex-col min-w-[400px]">
          {/* Main Chat Flow Container (修复 2: onScroll 绑定) */}
          <div
            className="flex-1 w-full overflow-y-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]"
            onScroll={handleScroll}
          >
          <div className="max-w-4xl w-full mx-auto py-6 space-y-6 px-4 md:px-8">
          {messages.length === 0 && !liveReasoning && !liveContent && (
            <div className="h-full flex flex-col items-center justify-center p-8 text-center text-slate-400 dark:text-zinc-500 select-none space-y-4">
              <div className="w-14 h-14 rounded-2xl bg-slate-100/80 dark:bg-zinc-800/80 shadow-sm flex items-center justify-center text-slate-400 dark:text-zinc-500">
                <Terminal className="w-6 h-6" />
              </div>
              <div className="max-w-md">
                <h3 className="text-sm font-semibold text-slate-700 dark:text-zinc-300">新建排版任务会话</h3>
                <p className="text-xs text-slate-400 dark:text-zinc-500 mt-2 leading-relaxed font-mono text-left">
                  请输入您的提问或排版需求，让 Agent 开始自主分析运行。<br /><br />
                  <strong>示例需求：</strong><br />
                  <span className="text-indigo-400 dark:text-indigo-400 text-[11px] block mt-1 bg-slate-100/60 dark:bg-zinc-800/60 p-3 rounded-xl leading-relaxed select-text">
                    把 <code>文档格式测试/cases/insert_text_001/docx/实验报告模板_v3_insert_text_001.docx</code> 中的"依据实验指导书"后插入"测试文本"，另存为 out/demo.docx，并对比原文档。
                  </span>
                </p>
              </div>
            </div>
          )}
  
          {renderBlocks.map((block, index) => {
            const nextBlock = renderBlocks[index + 1];
  
            // === 动态 Margin 终极规则：自适应上下文 ===
            let marginClass = "mb-8";
            const isLast = index === renderBlocks.length - 1;
  
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
                              onClick={() => setSelectedToolId(isExpanded ? null : tool.id)}
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
                              <div className="mt-2 w-full max-w-[600px] border border-slate-200/60 dark:border-zinc-800/60 bg-slate-50/80 dark:bg-zinc-900/50 backdrop-blur-sm rounded-md p-3 space-y-3 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
                                {tool.toolArgs && (
                                  <div>
                                    <p className="text-[9px] font-mono text-slate-400 dark:text-zinc-600 uppercase tracking-widest font-semibold mb-1.5">args</p>
                                    <pre className="text-[10px] font-mono bg-white/60 dark:bg-zinc-950/60 p-2 rounded text-slate-500 dark:text-zinc-400 whitespace-pre-wrap break-all leading-relaxed max-h-40 overflow-y-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
                                      {tool.toolArgs}
                                    </pre>
                                  </div>
                                )}
                                {tool.toolResult && (
                                  <div>
                                    <p className="text-[9px] font-mono text-slate-400 dark:text-zinc-600 uppercase tracking-widest font-semibold mb-1.5">result</p>
                                    <pre className="text-[10px] font-mono bg-white/60 dark:bg-zinc-950/60 p-2 rounded text-slate-500 dark:text-zinc-400 whitespace-pre-wrap break-all leading-relaxed max-h-48 overflow-y-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
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
  
          {/* === 实时流式 AnimatedLivePanel === */}
          <AnimatedLivePanel reasoning={liveReasoning} content={liveContent} time={thinkTime} />
  
          {/* 旧的文档流内指示器已移除: 替换为 footer 上方悬浮胶囊(见下) */}
  
          {/* Inline Phase Checkpoint (Waiting Approval) */}
          {isWaitingApproval && (
            <div className="mb-8 space-y-3">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-indigo-400 dark:text-indigo-500 shrink-0" />
                <p className="text-xs text-slate-500 dark:text-zinc-400 leading-relaxed">
                  {approvalPhase === "style_review"
                    ? "样式已提取完毕，请确认后进入草稿拟定阶段；如需修改请输入反馈"
                    : "草稿已生成，请确认后启动编译写入；若需调整请提交反馈"}
                </p>
              </div>
  
              <div className="flex flex-row items-center gap-3">
                <button
                  onClick={handleApproveAction}
                  disabled={!isConnected}
                  className="w-fit px-5 py-2 bg-indigo-500/10 hover:bg-indigo-500/20 disabled:bg-slate-100/60 dark:disabled:bg-zinc-800/60 disabled:text-slate-400 text-indigo-600 dark:text-indigo-400 text-[12px] font-medium rounded-full border border-indigo-500/20 hover:border-indigo-500/30 shadow-sm hover:shadow-md transition-all duration-150 flex items-center justify-center cursor-pointer shrink-0"
                >
                  {isConnected ? "同意并进入下一阶段" : "已断开连接"}
                </button>
  
                <div className="flex-1 flex items-center gap-2 bg-slate-50/60 dark:bg-zinc-900/40 border border-slate-200/50 dark:border-zinc-700/50 rounded-full px-4 py-1.5">
                  <input
                    type="text"
                    placeholder={isConnected ? "输入修改建议..." : ""}
                    value={feedbackValue}
                    onChange={(e) => setFeedbackValue(e.target.value)}
                    disabled={!isConnected}
                    className="flex-1 bg-transparent text-xs text-slate-600 dark:text-zinc-300 border-0 outline-0 focus:ring-0 select-text disabled:text-slate-400 placeholder:text-slate-400/60 dark:placeholder:text-zinc-600"
                  />
                  <button
                    onClick={handleRejectAction}
                    disabled={!feedbackValue.trim() || !isConnected}
                    className={`shrink-0 text-[11px] font-medium px-3 py-1 rounded-full transition-all duration-150 cursor-pointer ${
                      feedbackValue.trim() && isConnected
                        ? "text-rose-500 hover:text-rose-600"
                        : "text-slate-400 dark:text-zinc-600"
                    } disabled:text-slate-300 dark:disabled:text-zinc-700 disabled:cursor-not-allowed`}
                  >
                    反馈
                  </button>
                </div>
              </div>
            </div>
          )}
  
          <div ref={chatEndRef} />
          </div>
        </div>
  
        {/* Input Prompt Box area */}
        <footer className="bg-white/70 dark:bg-zinc-900/70 backdrop-blur-md sticky bottom-0 z-50 p-4 shrink-0 relative">
          {/* === 悬浮毛玻璃状态胶囊 (脱离文档流，0抖动) === */}
          <AnimatePresence>
            {isGenerating && !liveReasoning && !liveContent && (
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
          <form onSubmit={handleSendPrompt} className="max-w-4xl w-full mx-auto flex items-center gap-3">
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
              onChange={(e) => setInputValue(e.target.value)}
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
        </div>
        {/* 右侧: 预览侧栏 (内部 AnimatePresence 处理 0↔50% 动画) */}
        <PreviewPanel
          show={showPreview}
          content={previewContent}
          onClose={() => setShowPreview(false)}
        />
      </div>
    </div>
  );
}
