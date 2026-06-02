"use client";

import React, { useState, useEffect, useRef } from "react";
import { Terminal, Send, CheckCircle2, ChevronDown, ChevronUp, RefreshCw, User } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import MarkdownRenderer from "../components/markdown-renderer";

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

// === ReasoningPanel: 渲染已定型历史, 支持用户手动折叠 ===
// 实时思考由 LiveAgentContainer (原生 DOM) 接管, 永远展开 — 用户看流式
// 思考结束后定型到 messages, 此时由本组件渲染, 默认折叠 — 节省屏幕
// 用户可点击 button 展开查看
function ReasoningPanel({ content }: { content: string }) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!content) return null;

  return (
    <div className="mb-3 pl-4 border-l-2 border-indigo-200 dark:border-indigo-800 bg-slate-50/40 dark:bg-zinc-850/40 rounded-r-sm overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-3 py-2 text-[10px] font-mono font-medium text-indigo-400 dark:text-indigo-500 uppercase tracking-wider hover:bg-slate-100/60 dark:hover:bg-zinc-800/60"
      >
        <span>已完成思考</span>
        {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>
      {isExpanded && (
        <div className="px-3 pb-3 text-xs text-slate-400 dark:text-zinc-400 font-mono whitespace-pre-wrap leading-relaxed">
          {content}
        </div>
      )}
    </div>
  );
}

// === LiveAgentContainer: React.memo + () => true 物理隔离 ===
// 关键: () => true 让 React 永远认为 props 没变, 永不触发 re-render
// 内部 DOM 完全由原生 JS 掌控, 不会被 React 协调机制抹除
const LiveAgentContainer = React.memo(
  () => {
    return (
      <div id="live-agent-container" style={{ display: "none" }} className="mb-8">
        {/* 实时思考框 */}
        <div
          id="live-reasoning-box"
          style={{ display: "none" }}
          className="mb-3 pl-4 border-l-2 border-indigo-200 dark:border-indigo-800 bg-slate-50/40 dark:bg-zinc-850/40 rounded-r-sm p-3"
        >
          <div className="text-[10px] text-indigo-400 dark:text-indigo-500 uppercase tracking-wider mb-1 font-semibold select-none">
            正在思考 <span id="live-time-text">0</span> 秒
          </div>
          <span
            id="live-reasoning-text"
            className="text-xs text-slate-400 dark:text-zinc-400 font-mono whitespace-pre-wrap leading-relaxed"
          ></span>
        </div>
        {/* 实时正文框 */}
        <div
          id="live-content-box"
          style={{ display: "none" }}
          className="text-[15px] text-slate-700 dark:text-zinc-200 leading-relaxed select-text"
        >
          <span id="live-content-text"></span>
        </div>
      </div>
    );
  },
  () => true  // 👈 永远返回 true, 阻断 React 重绘
);

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

  const wsRef = useRef<WebSocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // === 原生 DOM 工具函数 ===
  const flushLiveStreamToMessages = () => {
    const rText = document.getElementById("live-reasoning-text");
    const cText = document.getElementById("live-content-text");
    const txtR = rText?.textContent || "";
    const txtC = cText?.textContent || "";
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
  };

  const clearLiveStreamContainer = () => {
    // 清理计时器
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    // 重置 DOM
    const rText = document.getElementById("live-reasoning-text");
    const cText = document.getElementById("live-content-text");
    const rBox = document.getElementById("live-reasoning-box");
    const cBox = document.getElementById("live-content-box");
    const container = document.getElementById("live-agent-container");
    const timeEl = document.getElementById("live-time-text");
    if (rText) rText.textContent = "";
    if (cText) cText.textContent = "";
    if (timeEl) timeEl.textContent = "0";
    if (rBox) rBox.style.display = "none";
    if (cBox) cBox.style.display = "none";
    if (container) container.style.display = "none";
  };

  // Auto-scroll chat window
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isWaitingApproval]);

  const resetWorkspace = () => {
    setMessages([]);
    clearLiveStreamContainer();
    setDocxPath("");
    setIsWaitingApproval(false);
    setApprovalPhase(null);
    setIsGenerating(false);
    setExpandedTools(new Set());
    setSelectedToolId(null);
    setInputValue("");
    setFeedbackValue("");
    if (wsRef.current) {
      wsRef.current.close();
    }
  };

  const startAgentSession = (initialPrompt: string, path: string) => {
    if (wsRef.current) {
      wsRef.current.close();
    }

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
          // === 启动原生秒数计时器 ===
          if (timerRef.current) clearInterval(timerRef.current);
          const startTime = Date.now();
          const timeEl = document.getElementById("live-time-text");
          if (timeEl) timeEl.textContent = "0";
          timerRef.current = setInterval(() => {
            const el = document.getElementById("live-time-text");
            if (el) el.textContent = String(Math.round((Date.now() - startTime) / 1000));
          }, 1000);

          // === 显示容器, 重置内部文本 ===
          const container = document.getElementById("live-agent-container");
          if (container) container.style.display = "block";
          const rBox = document.getElementById("live-reasoning-box");
          const cBox = document.getElementById("live-content-box");
          if (rBox) rBox.style.display = "none";
          if (cBox) cBox.style.display = "none";
          const rText = document.getElementById("live-reasoning-text");
          const cText = document.getElementById("live-content-text");
          if (rText) rText.textContent = "";
          if (cText) cText.textContent = "";

          setIsGenerating(true);
          if (data.token_count !== undefined) {
            setTokenCount(data.token_count);
          }
          break;
        }

        case "heartbeat":
          break;

        case "reasoning": {
          // === 纯原生 DOM 累加: 绕过 React 批处理, 浏览器立即 paint ===
          const el = document.getElementById("live-reasoning-text");
          const box = document.getElementById("live-reasoning-box");
          if (el && box) {
            el.textContent += data.delta;
            box.style.display = "block";
          }
          break;
        }

        case "content": {
          const el = document.getElementById("live-content-text");
          const box = document.getElementById("live-content-box");
          if (el && box) {
            el.textContent += data.delta;
            box.style.display = "block";
          }
          break;
        }

        case "tool_start": {
          // === 结算: DOM 文本 -> messages, 然后清空 DOM ===
          flushLiveStreamToMessages();
          clearLiveStreamContainer();
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
          flushLiveStreamToMessages();
          clearLiveStreamContainer();
          if (data.content !== undefined) {
            setMessages((prev) => {
              const lastIdx = prev.length - 1;
              if (lastIdx >= 0 && prev[lastIdx].role === "assistant") {
                return [...prev.slice(0, lastIdx), { ...prev[lastIdx], content: data.content }];
              }
              return prev;
            });
          }
          setApprovalPhase(data.phase);
          setIsWaitingApproval(true);
          setIsGenerating(false);
          break;
        }

        case "done": {
          flushLiveStreamToMessages();
          clearLiveStreamContainer();
          if (data.content !== undefined) {
            setMessages((prev) => {
              const lastIdx = prev.length - 1;
              if (lastIdx >= 0 && prev[lastIdx].role === "assistant") {
                return [...prev.slice(0, lastIdx), { ...prev[lastIdx], content: data.content }];
              }
              return prev;
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
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
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
      setIsGenerating(true);
      startAgentSession(prompt, "");
      return;
    }

    if (isWaitingApproval) return;

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

          <button
            onClick={resetWorkspace}
            className="px-3 py-1 text-xs font-semibold border border-slate-200 dark:border-zinc-700 hover:bg-slate-50 dark:hover:bg-zinc-800 rounded transition-colors cursor-pointer text-slate-600 dark:text-zinc-300"
          >
            重置会话
          </button>
        </div>
      </header>

      {/* Main Chat Flow Container */}
      <div className="flex-1 w-full overflow-y-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
        <div className="max-w-4xl w-full mx-auto py-6 space-y-6 px-4 md:px-8">
        {messages.length === 0 && (
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

        {messages.map((msg, index) => {
          if (msg.role === "user") {
            return (
              <div key={index} className="mb-6 pl-9 relative">
                <User size={14} className="absolute left-0 top-[2px] text-indigo-400 dark:text-indigo-500" />
                <p className="whitespace-pre-wrap select-text text-[15px] font-medium text-slate-800 dark:text-zinc-100 leading-relaxed">{msg.content}</p>
              </div>
            );
          } else if (msg.role === "tool") {
            if (index > 0 && messages[index - 1].role === "tool") {
              return null;
            }
            const toolGroup: any[] = [];
            let j = index;
            while (j < messages.length && messages[j].role === "tool") {
              toolGroup.push(messages[j]);
              j++;
            }

            return (
              <motion.div
                key={`tool-group-${index}`}
                className="flex flex-wrap gap-x-4 gap-y-1 max-w-[90%] my-3 pl-3 border-l-2 border-slate-200/60 dark:border-zinc-800/60"
                layout
              >
                <AnimatePresence mode="popLayout">
                  {toolGroup.map((tool, tIdx) => {
                    const isExpanded = selectedToolId === tool.id;
                    return (
                      <motion.div
                        key={tool.id || `tool-${tIdx}`}
                        className="relative"
                        layout
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, transition: { duration: 0.1 } }}
                        transition={{ type: "spring", stiffness: 400, damping: 25 }}
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
          } else {
            return (
              <div key={index} className="mb-8 select-text">
                {msg.reasoning_content && (
                  <ReasoningPanel content={msg.reasoning_content} />
                )}
                {msg.content && (
                  <div className="text-[15px] text-slate-700 dark:text-zinc-200 leading-relaxed">
                    <MarkdownRenderer content={msg.content} />
                  </div>
                )}
              </div>
            );
          }
        })}

        {/* === React.memo 物理隔离的原生流容器 === */}
        <LiveAgentContainer />

        {/* Ghost-style Thinking Indicator */}
        {isGenerating && (
          <div className="flex items-center gap-3 mt-3 px-1">
            <div className="relative flex items-center justify-center w-5 h-5">
              <div className="absolute inset-0 rounded-full border-2 border-indigo-500/20"></div>
              <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-indigo-500 animate-spin"></div>
            </div>
            <span className="text-xs font-mono font-medium text-transparent bg-clip-text bg-gradient-to-r from-indigo-500 to-slate-400 animate-pulse">
              Agent 深度思考与调度中...
            </span>
          </div>
        )}

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
      <footer className="bg-white/70 dark:bg-zinc-900/70 backdrop-blur-md sticky bottom-0 z-50 p-4 shrink-0">
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
  );
}
