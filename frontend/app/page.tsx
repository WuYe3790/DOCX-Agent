"use client";

import React, { useState, useEffect, useRef } from "react";
import { Terminal, Send, CheckCircle2, ChevronDown, ChevronUp, Wrench, RefreshCw, User } from "lucide-react";
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

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [reasoningStream, setReasoningStream] = useState<string>("");
  const [contentStream, setContentStream] = useState<string>("");
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isWaitingApproval, setIsWaitingApproval] = useState<boolean>(false);
  const [approvalPhase, setApprovalPhase] = useState<"style_review" | "md_draft" | "word_editing" | null>(null);
  const [docxPath, setDocxPath] = useState<string>("");
  const [inputValue, setInputValue] = useState<string>("");
  const [feedbackValue, setFeedbackValue] = useState<string>("");
  const [isThinkingExpanded, setIsThinkingExpanded] = useState(true);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [thinkingStartTime, setThinkingStartTime] = useState<number | null>(null);
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const [selectedToolId, setSelectedToolId] = useState<string | null>(null);
  const [tokenCount, setTokenCount] = useState<number>(0);

  const wsRef = useRef<WebSocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll chat window
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, contentStream, reasoningStream, isWaitingApproval]);

  const resetWorkspace = () => {
    setMessages([]);
    setReasoningStream("");
    setContentStream("");
    setDocxPath("");
    setIsWaitingApproval(false);
    setApprovalPhase(null);
    setIsGenerating(false);
    setThinkingStartTime(null);
    setExpandedTools(new Set());
    setSelectedToolId(null);
    setInputValue("");
    setFeedbackValue("");
    if (wsRef.current) {
      wsRef.current.close();
    }
  };

  const toggleToolExpanded = (id: string) => {
    setExpandedTools((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
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
        case "round_start":
          setReasoningStream("");
          setContentStream("");
          setIsGenerating(true);
          setThinkingStartTime(Date.now());
          if (data.token_count !== undefined) {
            setTokenCount(data.token_count);
          }
          break;

        case "heartbeat":
          break;

        case "reasoning":
          setReasoningStream((prev) => prev + data.delta);
          break;

        case "content":
          setContentStream((prev) => prev + data.delta);
          break;

        case "tool_start":
          setMessages((prev) => [
            ...prev,
            {
              role: "tool",
              toolName: data.name,
              toolArgs: data.arguments,
              toolStatus: "running",
              id: data.name + "_" + Date.now(),
            },
          ]);
          break;

        case "tool_end":
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

        case "wait_approval":
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: data.content,
              reasoning_content: reasoningStream || undefined,
            },
          ]);
          setReasoningStream("");
          setContentStream("");
          setApprovalPhase(data.phase);
          setIsWaitingApproval(true);
          setIsGenerating(false);
          break;

        case "done":
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: data.content,
              reasoning_content: reasoningStream || undefined,
            },
          ]);
          setReasoningStream("");
          setContentStream("");
          setIsWaitingApproval(false);
          setApprovalPhase(null);
          setIsGenerating(false);
          break;

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

    // Append user's action to messages list!
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
          {/* Connection Badge */}
          <div className="flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${isConnected ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} />
            <span className="text-xs font-mono text-slate-500">{isConnected ? "已连接" : "已断开"}</span>
          </div>

          {/* Token Usage Bar */}
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
            // Skip if already part of a group (consecutive tools merged earlier)
            if (index > 0 && messages[index - 1].role === "tool") {
              return null;
            }

            // Collect all consecutive tool messages into a group
            const toolGroup: any[] = [];
            let j = index;
            while (j < messages.length && messages[j].role === "tool") {
              toolGroup.push(messages[j]);
              j++;
            }

            return (
              <motion.div
                key={`tool-group-${index}`}
                className="flex flex-wrap gap-2 max-w-[90%] my-4"
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
                        initial={{ opacity: 0, scale: 0.8, y: 10 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.8, transition: { duration: 0.15 } }}
                        transition={{ type: "spring", stiffness: 400, damping: 25 }}
                      >
                        {/* Pill Badge */}
                        <motion.div
                          onClick={() => setSelectedToolId(isExpanded ? null : tool.id)}
                          className={`inline-flex items-center gap-1.5 h-7 pl-1.5 pr-3 rounded-full cursor-pointer select-none ${
                            tool.toolStatus === "running"
                              ? "bg-blue-500/10 dark:bg-blue-500/20 border border-blue-400/30"
                              : tool.toolStatus === "success"
                              ? "bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700"
                              : "bg-red-500/10 dark:bg-red-500/20 border border-red-400/30"
                          } ${tool.toolStatus === "running" ? "animate-pulse" : ""}`}
                        >
                          <Wrench size={13} className={tool.toolStatus === "running" ? "text-blue-500" : tool.toolStatus === "success" ? "text-zinc-500 dark:text-zinc-400" : "text-red-500"} />
                          <span className="text-[11px] font-mono text-slate-700 dark:text-zinc-300">{tool.toolName}</span>
                          <div className={`w-1.5 h-1.5 rounded-full ${tool.toolStatus === "running" ? "bg-blue-500" : tool.toolStatus === "success" ? "bg-zinc-400" : "bg-red-500"}`} />
                        </motion.div>

                        {/* Expanded Detail Panel */}
                        <div
                          className={`absolute top-full left-0 z-20 mt-1 w-80 rounded-xl border border-slate-200 dark:border-zinc-700 bg-white/90 dark:bg-zinc-800/90 backdrop-blur-md shadow-lg overflow-hidden transition-all duration-300 ease-out ${
                            isExpanded ? "opacity-100 visible" : "opacity-0 invisible"
                          }`}
                        >
                          <div className="p-3 space-y-2">
                            {tool.toolArgs && (
                              <div>
                                <p className="text-[9px] font-mono uppercase tracking-wider text-slate-400 mb-1">参数</p>
                                <pre className="text-[10px] font-mono bg-slate-100 dark:bg-zinc-900 p-2 rounded-lg text-slate-600 dark:text-zinc-400 whitespace-pre-wrap break-all max-h-20 overflow-y-auto">
                                  {tool.toolArgs}
                                </pre>
                              </div>
                            )}
                            {tool.toolResult && (
                              <div>
                                <p className="text-[9px] font-mono uppercase tracking-wider text-slate-400 mb-1">执行结果</p>
                                <pre className="text-[10px] font-mono bg-slate-100 dark:bg-zinc-900 p-2 rounded-lg text-slate-600 dark:text-zinc-400 whitespace-pre-wrap break-all max-h-28 overflow-y-auto">
                                  {tool.toolResult}
                                </pre>
                              </div>
                            )}
                          </div>
                        </div>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              </motion.div>
            );
          } else {
            // Assistant Message — frameless typography
            return (
              <div key={index} className="mb-8 select-text">
                {msg.reasoning_content && (
                  <div className="mb-3 pl-4 border-l-2 border-indigo-200 dark:border-indigo-800 bg-slate-50/40 dark:bg-zinc-850/40 rounded-r-sm">
                    <p className="text-[10px] font-mono font-medium text-indigo-400 dark:text-indigo-500 uppercase tracking-wider mb-1">深度思考</p>
                    <p className="text-xs text-slate-400 dark:text-zinc-400 font-mono whitespace-pre-wrap leading-relaxed">{msg.reasoning_content}</p>
                  </div>
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

        {/* Real-time Streaming Response */}
        {(reasoningStream || contentStream) && (
          <div className="mb-8 select-text">
            {reasoningStream && (
              <div className="mb-3 pl-4 border-l-2 border-indigo-200 dark:border-indigo-800 bg-slate-50/40 dark:bg-zinc-850/40 rounded-r-sm overflow-hidden">
                <button
                  onClick={() => setIsThinkingExpanded(!isThinkingExpanded)}
                  className="w-full flex items-center justify-between px-3 py-2 text-[10px] font-mono font-medium text-indigo-400 dark:text-indigo-500 uppercase tracking-wider hover:bg-slate-100/60 dark:hover:bg-zinc-800/60"
                >
                  <span>{isThinkingExpanded ? "收起思考过程" : "已思考 " + (thinkingStartTime ? Math.round((Date.now() - thinkingStartTime) / 1000) : 0) + " 秒"}</span>
                  {isThinkingExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </button>
                {isThinkingExpanded && (
                  <div className="px-3 pb-3 text-xs text-slate-400 dark:text-zinc-400 font-mono whitespace-pre-wrap leading-relaxed">
                    {reasoningStream}
                  </div>
                )}
              </div>
            )}
            {contentStream && (
              <div className="text-[15px] text-slate-700 dark:text-zinc-200 leading-relaxed">
                <MarkdownRenderer content={contentStream} />
              </div>
            )}
          </div>
        )}

        {/* Ghost-style Thinking Indicator */}
        {isGenerating && !reasoningStream && !contentStream && (
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
          <div className="max-w-[90%] border border-indigo-200 dark:border-indigo-900/60 bg-indigo-50/40 dark:bg-indigo-950/20 rounded-lg p-5 space-y-4 shadow-sm">
            <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
              <CheckCircle2 className="w-5 h-5" />
              <span className="text-sm font-semibold">
                {approvalPhase === "style_review" ? "请确认样式提取结果" : "请确认 Markdown 草稿"}
              </span>
            </div>
            <p className="text-xs text-slate-600 dark:text-zinc-400 leading-relaxed">
              {approvalPhase === "style_review"
                ? "确认后将锁定制定的模板样式，并进入草稿拟定阶段；若不通过，请提交反馈修改意见。"
                : "确认后将启动 AST 编译逻辑并写入 Word 模板中；若不通过，请在下方输入您的微调说明。"}
            </p>

            <div className="flex flex-col gap-3 pt-2">
              <button
                onClick={handleApproveAction}
                disabled={!isConnected}
                className="w-full h-9 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400 dark:disabled:bg-zinc-800 dark:disabled:text-zinc-500 text-white text-xs font-semibold rounded transition-colors duration-150 flex items-center justify-center cursor-pointer shadow-sm"
              >
                {isConnected ? "同意并进入下一阶段" : "已断开连接，请刷新并重试"}
              </button>

              <div className="flex items-center gap-2 border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 rounded p-1.5 shadow-sm">
                <input
                  type="text"
                  placeholder={isConnected ? "在此输入您的修改建议..." : "连接已断开，无法提交反馈..."}
                  value={feedbackValue}
                  onChange={(e) => setFeedbackValue(e.target.value)}
                  disabled={!isConnected}
                  className="flex-1 bg-transparent px-3 py-1.5 text-xs border-0 outline-0 focus:ring-0 select-text disabled:text-slate-400"
                />
                <button
                  onClick={handleRejectAction}
                  disabled={!feedbackValue.trim() || !isConnected}
                  className="h-8 px-4 bg-red-500 hover:bg-red-600 disabled:bg-slate-200 disabled:text-slate-400 dark:disabled:bg-zinc-800 dark:disabled:text-zinc-500 text-white text-xs font-semibold rounded transition-colors duration-150 cursor-pointer"
                >
                  反馈修改
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
