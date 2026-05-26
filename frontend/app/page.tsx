"use client";

import React, { useState, useEffect, useRef } from "react";
import { Terminal, Send, CheckCircle2, ChevronDown, ChevronUp, Wrench, RefreshCw } from "lucide-react";
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
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());

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
    setInputValue("");
    setFeedbackValue("");
    setExpandedTools(new Set());
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
          setIsGenerating(false);
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
    <div className="w-full h-screen flex flex-col bg-slate-50 dark:bg-zinc-950 text-slate-900 dark:text-zinc-50 font-sans">
      {/* Header Bar */}
      <header className="h-14 border-b border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-6 flex items-center justify-between shrink-0">
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

          <button
            onClick={resetWorkspace}
            className="px-3 py-1 text-xs font-semibold border border-slate-200 dark:border-zinc-700 hover:bg-slate-50 dark:hover:bg-zinc-800 rounded transition-colors cursor-pointer text-slate-600 dark:text-zinc-300"
          >
            重置会话
          </button>
        </div>
      </header>

      {/* Main Chat Flow Container */}
      <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8 max-w-4xl w-full mx-auto space-y-6">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center p-8 text-center text-slate-400 dark:text-zinc-500 select-none space-y-4">
            <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-zinc-800 flex items-center justify-center text-slate-400 dark:text-zinc-500">
              <Terminal className="w-6 h-6" />
            </div>
            <div className="max-w-md">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-zinc-300">新建排版任务会话</h3>
              <p className="text-xs text-slate-400 dark:text-zinc-500 mt-2 leading-relaxed font-mono text-left">
                请输入您的提问或排版需求，让 Agent 开始自主分析运行。<br /><br />
                <strong>示例需求：</strong><br />
                <span className="text-indigo-600 dark:text-indigo-400 text-[11px] block mt-1 bg-slate-100 dark:bg-zinc-800 p-2 rounded border border-slate-200 dark:border-zinc-700 select-text">
                  把 <code>文档格式测试/cases/insert_text_001/docx/实验报告模板_v3_insert_text_001.docx</code> 中的“依据实验指导书”后插入“测试文本”，另存为 out/demo.docx，并对比原文档。
                </span>
              </p>
            </div>
          </div>
        )}

        {messages.map((msg, index) => {
          if (msg.role === "user") {
            return (
              <div key={index} className="flex flex-col items-end">
                <div className="max-w-[85%] rounded-lg px-4 py-3 bg-indigo-600 text-white border border-indigo-700 select-text text-sm">
                  <p className="whitespace-pre-wrap select-text">{msg.content}</p>
                </div>
              </div>
            );
          } else if (msg.role === "tool") {
            const isExpanded = expandedTools.has(msg.id || "");
            return (
              <div key={index} className="flex flex-col items-start w-full">
                <div className="w-full max-w-[90%] border border-slate-200 dark:border-zinc-800 bg-slate-100/50 dark:bg-zinc-900/30 rounded-lg p-3 font-mono text-xs text-slate-600 dark:text-zinc-400">
                  <div
                    className="flex items-center justify-between cursor-pointer hover:bg-slate-200/50 dark:hover:bg-zinc-800/30 rounded -mx-2 px-2 py-1 -my-1"
                    onClick={() => msg.id && toggleToolExpanded(msg.id)}
                  >
                    <div className="flex items-center gap-2 font-bold text-slate-700 dark:text-zinc-300">
                      <Wrench className="w-3.5 h-3.5" />
                      <span>调用工具: {msg.toolName}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-sans font-semibold tracking-wide ${
                          msg.toolStatus === "running"
                            ? "bg-amber-100 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 animate-pulse"
                            : msg.toolStatus === "success"
                            ? "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400"
                            : "bg-red-100 dark:bg-red-950/40 text-red-600 dark:text-red-400"
                        }`}
                      >
                        {msg.toolStatus === "running" ? "运行中" : msg.toolStatus === "success" ? "成功" : "失败"}
                      </span>
                      <span className="text-slate-400">
                        {isExpanded ? "▲" : "▼"}
                      </span>
                    </div>
                  </div>

                  {isExpanded && (
                    <>
                      {msg.toolArgs && (
                        <div className="mb-2 mt-2 text-[10px] text-slate-500">
                          <span className="font-semibold">参数:</span>
                          <pre className="mt-1 bg-slate-50 dark:bg-zinc-850 p-2 rounded border border-slate-100 dark:border-zinc-750 overflow-x-auto whitespace-pre-wrap break-all">
                            {msg.toolArgs}
                          </pre>
                        </div>
                      )}

                      {msg.toolResult && (
                        <div className="mt-2 text-[10px] text-slate-500">
                          <span className="font-semibold">执行结果:</span>
                          <pre className="mt-1 bg-slate-50 dark:bg-zinc-850 p-2 rounded border border-slate-100 dark:border-zinc-750 overflow-x-auto max-h-40 overflow-y-auto whitespace-pre-wrap break-all">
                            {msg.toolResult}
                          </pre>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            );
          } else {
            // Assistant Message
            return (
              <div key={index} className="flex flex-col items-start w-full select-text">
                <div className="w-full max-w-[90%] border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 rounded-lg p-4 space-y-3 shadow-sm">
                  {msg.reasoning_content && (
                    <div className="p-3 bg-slate-50 dark:bg-zinc-850 border-l-2 border-slate-300 dark:border-zinc-700 text-xs text-slate-500 dark:text-zinc-400 font-mono rounded">
                      <p className="font-semibold mb-1 text-[10px] tracking-wider text-slate-400 dark:text-zinc-500 uppercase">思考路径 (DeepSeek Reasoning)</p>
                      <p className="whitespace-pre-wrap select-text">{msg.reasoning_content}</p>
                    </div>
                  )}
                  {msg.content && (
                    <div className="text-sm select-text">
                      <MarkdownRenderer content={msg.content} />
                    </div>
                  )}
                </div>
              </div>
            );
          }
        })}

        {/* Active Thinking/Generating Indicator */}
        {isGenerating && !reasoningStream && !contentStream && (
          <div className="flex flex-col items-start w-full">
            <div className="w-full max-w-[90%] border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 rounded-lg p-4 flex items-center gap-3 shadow-sm">
              <RefreshCw className="w-4 h-4 text-indigo-600 animate-spin" />
              <span className="text-xs font-mono text-slate-500">Agent 正在请求模型中，请稍候...</span>
            </div>
          </div>
        )}

        {/* Real-time Streaming Response */}
        {(reasoningStream || contentStream) && (
          <div className="flex flex-col items-start w-full">
            <div className="w-full max-w-[90%] border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 rounded-lg p-4 space-y-3 shadow-sm">
              {reasoningStream && (
                <div className="border-l-2 border-slate-300 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-850 rounded overflow-hidden">
                  <button
                    onClick={() => setIsThinkingExpanded(!isThinkingExpanded)}
                    className="w-full flex items-center justify-between px-3 py-2 text-[10px] font-semibold text-slate-400 dark:text-zinc-500 font-mono uppercase bg-slate-100/50 dark:bg-zinc-850/50 hover:bg-slate-100 dark:hover:bg-zinc-800"
                  >
                    <span>思考中...</span>
                    {isThinkingExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>
                  {isThinkingExpanded && (
                    <div className="p-3 text-xs text-slate-500 dark:text-zinc-400 font-mono whitespace-pre-wrap max-h-[160px] overflow-y-auto border-t border-slate-200 dark:border-zinc-750">
                      {reasoningStream}
                    </div>
                  )}
                </div>
              )}
              {contentStream && (
                <div className="text-sm select-text">
                  <MarkdownRenderer content={contentStream} />
                </div>
              )}
            </div>
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

      {/* Input Prompt Box area */}
      <footer className="border-t border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4 shrink-0">
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
            className="flex-1 min-h-[40px] bg-slate-50 dark:bg-zinc-850 border border-slate-200 dark:border-zinc-700 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded-lg px-4 py-2 text-sm placeholder:text-slate-400 dark:placeholder:text-zinc-500 outline-0 disabled:bg-slate-100 disabled:text-slate-400 select-text"
          />
          <button
            type="submit"
            disabled={!inputValue.trim() || isWaitingApproval}
            className="w-10 h-10 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-100 disabled:text-slate-400 dark:disabled:bg-zinc-850 dark:disabled:text-zinc-600 text-white rounded-lg flex items-center justify-center transition-colors duration-150 cursor-pointer shadow-sm"
          >
            <Send className="w-5 h-5" />
          </button>
        </form>
      </footer>
    </div>
  );
}
