"use client";

import React, { useState, useRef, useEffect } from "react";
import { Terminal, Send, CheckCircle2, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";
import MarkdownRenderer from "./markdown-renderer";

interface Message {
  role: "system" | "user" | "assistant" | "tool";
  content?: string;
  reasoning_content?: string;
  name?: string; // tool name
}

interface ToolLog {
  name: string;
  arguments: string;
  result?: string;
  status: "running" | "success" | "error";
  id: string;
}

interface ChatPanelProps {
  messages: Message[];
  reasoningStream: string;
  contentStream: string;
  toolLogs: ToolLog[];
  isWaitingApproval: boolean;
  approvalPhase: "style_review" | "md_draft" | "word_editing" | null;
  onSendPrompt: (prompt: string) => void;
  onApprove: (approved: boolean, feedback?: string) => void;
  isConnected: boolean;
}

export default function ChatPanel({
  messages,
  reasoningStream,
  contentStream,
  toolLogs,
  isWaitingApproval,
  approvalPhase,
  onSendPrompt,
  onApprove,
  isConnected,
}: ChatPanelProps) {
  const [inputValue, setInputValue] = useState("");
  const [feedbackValue, setFeedbackValue] = useState("");
  const [isThinkingExpanded, setIsThinkingExpanded] = useState(true);
  const [isLogDrawerExpanded, setIsLogDrawerExpanded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const logScrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, contentStream, reasoningStream, isWaitingApproval]);

  // Auto-scroll tool logs
  useEffect(() => {
    if (logScrollRef.current) {
      logScrollRef.current.scrollTop = logScrollRef.current.scrollHeight;
    }
  }, [toolLogs]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim()) return;
    onSendPrompt(inputValue.trim());
    setInputValue("");
  };

  const handleApproveAction = () => {
    onApprove(true);
    setFeedbackValue("");
  };

  const handleRejectAction = () => {
    if (!feedbackValue.trim()) return;
    onApprove(false, feedbackValue.trim());
    setFeedbackValue("");
  };

  return (
    <div className="w-full h-full flex flex-col bg-card border-r border-border select-none">
      {/* Panel Header */}
      <div className="h-10 border-b border-border flex items-center justify-between px-4 bg-muted-bg/50">
        <span className="text-xs font-semibold text-foreground tracking-wide uppercase">
          指令控制台
        </span>
        <div className="flex items-center gap-1.5">
          <div
            className={`w-2 h-2 rounded-full ${
              isConnected ? "bg-emerald-500 animate-pulse" : "bg-red-500"
            }`}
          />
          <span className="text-[10px] text-muted font-mono">
            {isConnected ? "已连接" : "已断开"}
          </span>
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-4 text-sm"
      >
        {messages
          .filter((msg) => msg.role !== "system" && msg.role !== "tool")
          .map((msg, index) => {
            const isUser = msg.role === "user";
            return (
              <div
                key={index}
                className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}
              >
                {/* Message Box */}
                <div
                  className={`max-w-[90%] rounded-md px-3.5 py-2.5 ${
                    isUser
                      ? "bg-accent text-white border border-accent/20"
                      : "bg-muted-bg text-foreground border border-border"
                  }`}
                >
                  {isUser ? (
                    <p className="whitespace-pre-wrap select-text selection:bg-indigo-300">{msg.content}</p>
                  ) : (
                    <div className="select-text">
                      {msg.reasoning_content && (
                        <div className="mb-3 p-2 bg-background/50 border-l-2 border-muted text-xs text-muted font-mono rounded">
                          <p className="font-semibold mb-1 text-[10px] tracking-wider text-muted uppercase">思维日志</p>
                          <p className="whitespace-pre-wrap select-text">{msg.reasoning_content}</p>
                        </div>
                      )}
                      {msg.content && <MarkdownRenderer content={msg.content} />}
                    </div>
                  )}
                </div>
              </div>
            );
          })}

        {/* Real-time Streaming Response */}
        {(reasoningStream || contentStream) && (
          <div className="flex flex-col items-start">
            <div className="max-w-[90%] bg-muted-bg text-foreground border border-border rounded-md px-3.5 py-2.5">
              {reasoningStream && (
                <div className="mb-3 border-l-2 border-muted bg-background/50 rounded overflow-hidden">
                  <button
                    onClick={() => setIsThinkingExpanded(!isThinkingExpanded)}
                    className="w-full flex items-center justify-between px-2 py-1.5 text-[10px] font-semibold text-muted font-mono uppercase bg-background/30 hover:bg-background/80"
                  >
                    <span>深度思考中...</span>
                    {isThinkingExpanded ? (
                      <ChevronUp className="w-3.5 h-3.5" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5" />
                    )}
                  </button>
                  {isThinkingExpanded && (
                    <div className="p-2 text-xs text-muted font-mono whitespace-pre-wrap select-text max-h-[160px] overflow-y-auto border-t border-border/20">
                      {reasoningStream}
                    </div>
                  )}
                </div>
              )}
              {contentStream && (
                <div className="select-text">
                  <MarkdownRenderer content={contentStream} />
                </div>
              )}
            </div>
          </div>
        )}

        {/* Phase Action Block (Checkpoint) */}
        {isWaitingApproval && (
          <div className="border border-indigo-200 dark:border-indigo-900/60 bg-indigo-50/40 dark:bg-indigo-950/20 rounded p-4 space-y-3">
            <div className="flex items-center gap-2 text-accent">
              <CheckCircle2 className="w-4 h-4" />
              <span className="text-xs font-semibold">
                {approvalPhase === "style_review" ? "请确认样式提取结果" : "请确认 Markdown 草稿"}
              </span>
            </div>
            <p className="text-xs text-muted">
              {approvalPhase === "style_review"
                ? "确认后将锁定制定的模板样式，并进入草稿拟定阶段；若不通过，请提交反馈修改意见。"
                : "确认后将启动 AST 编译逻辑并写入 Word 模板中；若不通过，请在下方输入您的微调说明。"}
            </p>

            <div className="flex flex-col gap-2 pt-1.5">
              <button
                onClick={handleApproveAction}
                disabled={!isConnected}
                className="w-full h-8 bg-accent hover:bg-accent-hover disabled:bg-muted-bg disabled:text-muted text-white text-xs font-medium rounded transition-colors duration-150 flex items-center justify-center cursor-pointer"
              >
                {isConnected ? "同意并进入下一阶段" : "已断开连接，请刷新并重试"}
              </button>

              <div className="flex items-center gap-1.5 border border-border bg-card rounded p-1">
                <input
                  type="text"
                  placeholder={
                    isConnected
                      ? "在此输入您的修改建议..."
                      : "连接已断开，无法提交反馈..."
                  }
                  value={feedbackValue}
                  onChange={(e) => setFeedbackValue(e.target.value)}
                  disabled={!isConnected}
                  className="flex-1 bg-transparent px-2 py-1 text-xs border-0 outline-0 focus:ring-0 select-text disabled:text-muted"
                />
                <button
                  onClick={handleRejectAction}
                  disabled={!feedbackValue.trim() || !isConnected}
                  className="h-6 px-2.5 bg-red-500 hover:bg-red-600 disabled:bg-muted-bg disabled:text-muted text-white text-[10px] font-medium rounded transition-colors duration-150 cursor-pointer"
                >
                  反馈修改
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Real-time Tool Execution Drawer Console */}
      <div className="border-t border-border bg-background flex flex-col">
        <button
          onClick={() => setIsLogDrawerExpanded(!isLogDrawerExpanded)}
          className="h-8 px-4 flex items-center justify-between hover:bg-muted-bg/50 transition-colors"
        >
          <div className="flex items-center gap-2 text-muted">
            <Terminal className="w-3.5 h-3.5" />
            <span className="text-[10px] font-mono font-semibold uppercase tracking-wider">工具调用日志 ({toolLogs.length})</span>
          </div>
          {isLogDrawerExpanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-muted" />
          ) : (
            <ChevronUp className="w-3.5 h-3.5 text-muted" />
          )}
        </button>

        {isLogDrawerExpanded && (
          <div
            ref={logScrollRef}
            className="h-28 overflow-y-auto px-4 py-2 border-t border-border font-mono text-[10px] text-muted space-y-1.5 bg-background select-text"
          >
            {toolLogs.length === 0 ? (
              <p className="text-muted/50 italic">暂无工具运行调用...</p>
            ) : (
              toolLogs.map((log) => (
                <div key={log.id} className="flex items-start gap-1">
                  <span className="text-muted/60">{`>`}</span>
                  <div className="flex-1">
                    <span className="text-foreground font-semibold">{log.name}</span>
                    <span className="text-muted/70 font-light truncate max-w-[200px] inline-block align-bottom ml-1">{`(${log.arguments})`}</span>
                    <span
                      className={`ml-2 px-1 rounded-sm text-[8px] uppercase tracking-wide inline-block ${
                        log.status === "running"
                          ? "bg-amber-100 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400"
                          : log.status === "success"
                          ? "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400"
                          : "bg-red-100 dark:bg-red-950/40 text-red-600 dark:text-red-400"
                      }`}
                    >
                      {log.status === "running" ? "运行中" : log.status === "success" ? "成功" : "失败"}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Input Prompts Area */}
      <form
        onSubmit={handleSubmit}
        className="p-3 border-t border-border bg-muted-bg/30 flex items-center gap-2"
      >
        <input
          type="text"
          placeholder={
            isWaitingApproval
              ? "审批挂起中，请完成上方确认或反馈意见..."
              : "请输入文档排版或段落修改需求..."
          }
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          disabled={isWaitingApproval}
          className="flex-1 min-h-[36px] bg-card border border-border focus:border-accent rounded px-3 py-1.5 text-xs placeholder:text-muted/50 outline-0 disabled:bg-muted-bg/50 disabled:text-muted select-text"
        />
        <button
          type="submit"
          disabled={!inputValue.trim() || isWaitingApproval}
          className="w-9 h-9 bg-accent hover:bg-accent-hover disabled:bg-muted-bg disabled:text-muted text-white rounded flex items-center justify-center transition-colors duration-150 cursor-pointer"
        >
          <Send className="w-4.5 h-4.5" />
        </button>
      </form>
    </div>
  );
}
