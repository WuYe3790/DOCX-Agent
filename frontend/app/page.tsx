"use client";

import React, { useState, useEffect, useRef } from "react";
import { Terminal, Send, CheckCircle2, User } from "lucide-react";
// PanelLeft 已迁到 ChatHeader, RefreshCw/Plus/Trash2 等在 SessionSidebar 内部
import { motion, AnimatePresence } from "framer-motion";
import MarkdownRenderer from "../components/markdown-renderer";
import PreviewPanel from "../components/preview-panel";
import SessionSidebar from "../components/session-sidebar";
import ReasoningPanel from "../components/reasoning-panel";
import AnimatedLivePanel from "../components/animated-live-panel";
import ChatHeader from "../components/chat-header";
// v2: 删 IndexedDB lib/sessions — 改用 HTTP fetch + WS resume (后端是 source of truth)
import type { SessionMeta } from "../lib/session-types";
import type { DraftFile } from "../lib/draft-types";
import type { Message, RenderBlock } from "../lib/message-types";
import { useAgentSession } from "../hooks/use-agent-session";

export default function Home() {
  // === 本地 UI state (不被 hook 管) ===
  const [inputValue, setInputValue] = useState<string>("");
  const [feedbackValue, setFeedbackValue] = useState<string>("");

  // === 草稿预览侧栏 (md_draft 阶段自动展开) ===
  const [showPreview, setShowPreview] = useState<boolean>(false);
  const [draftFiles, setDraftFiles] = useState<DraftFile[]>([]);
  const [activeFilename, setActiveFilename] = useState<string | null>(null);

  // === 会话管理 (v2: 后端持久化, 前端只维护"当前激活的 session_id") ===
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [sessionSidebarOpen, setSessionSidebarOpen] = useState<boolean>(false);

  // === 工具选择 UI state (本地) ===
  const [, setExpandedTools] = useState<Set<string>>(new Set());
  const [selectedToolId, setSelectedToolId] = useState<string | null>(null);

  // === Refs ===
  const chatEndRef = useRef<HTMLDivElement>(null);
  // === 滚动意图侦测 (修复 2) ===
  const isScrolledToBottom = useRef<boolean>(true);

  // === Agent hook (WS 生命周期 + 实时流 + approval state) ===
  //   回调函数让 hook 在 onmessage 处理时能触发 page UI 侧栏联动
  //   (hook 不越界管 UI state, 保持单一职责)
  const agent = useAgentSession({
    onRefreshSessions: () => { void refreshSessions(); },
    onFetchDrafts: (sessionId) => { void fetchDrafts(sessionId); },
    onResetDrafts: () => resetDrafts(),
    onShowPreview: (show) => setShowPreview(show),
  });
  const {
    messages,
    isConnected,
    isGenerating,
    isWaitingApproval,
    approvalPhase,
    docxPath,
    tokenCount,
    liveReasoning,
    liveContent,
    thinkTime,
    currentSessionId,
    start: startAgentSession,
    stop: stopAgentSession,
    sendContinue,
    sendApprove,
    resetForCreate,
    resetForWorkspace,
    hasActiveConnection,
  } = agent;

  // === v2.2: 启动时只拉列表 (sidebar 用), 不自动 resume 任何 session ===
  // 用户期望: 进页面默认空 UI, 由用户主动从 sidebar 选 / 新建
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/sessions");
        if (res.ok) {
          const list: SessionMeta[] = await res.json();
          setSessions(list);
        } else {
          console.warn("fetch /api/sessions failed:", res.status);
          setSessions([]);
        }
      } catch (e) {
        console.warn("session list fetch error:", e);
        setSessions([]);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // === v2: 重新拉列表 (删除/创建后用) ===
  const refreshSessions = async () => {
    try {
      const res = await fetch("/api/sessions");
      if (res.ok) {
        const list: SessionMeta[] = await res.json();
        setSessions(list);
      }
    } catch (e) {
      console.warn("refreshSessions failed:", e);
    }
  };

  // === v2: 拉取指定 session 的所有 MD 草稿 (元数据 + 内容) ===
  const fetchDrafts = async (sessionId: string) => {
    if (!sessionId) return;
    try {
      const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/drafts`);
      if (res.ok) {
        const data: { files: DraftFile[] } = await res.json();
        setDraftFiles(data.files);
        setActiveFilename((prev) => {
          if (prev && data.files.some((f) => f.name === prev)) return prev;
          const latest = data.files[data.files.length - 1];
          return latest?.name ?? null;
        });
      } else {
        console.warn("fetchDrafts failed:", res.status);
      }
    } catch (e) {
      console.warn("fetchDrafts error:", e);
    }
  };

  // === 清空草稿列表 + 选中 (切会话 / 新建 / 重置时复用) ===
  const resetDrafts = () => {
    setDraftFiles([]);
    setActiveFilename(null);
  };

  // === v2: 切会话 = 关闭旧 WS + 通过 resume 拉新 (Bug B 完整修复) ===
  const handleSelectSession = (id: string) => {
    if (id === currentSessionId) {
      setSessionSidebarOpen(false);
      return;
    }
    // 1. 关旧 WS
    stopAgentSession();
    // 2. WS resume 重建 (后端发 history frame, onmessage 处理覆盖 state)
    startAgentSession("", "", id);
    setSessionSidebarOpen(false);
  };

  // === v2: 新建会话 = 清空前端 state + 留空等用户发首条消息 (发时走 start) ===
  const handleCreateSession = () => {
    // Bug A 修复: 重置所有 approval + UI 状态, 避免旧 session 的状态泄漏到新 session
    setFeedbackValue("");
    setExpandedTools(new Set());
    setSelectedToolId(null);
    setSessionSidebarOpen(false);
    resetDrafts();
    // 重置 agent state (含 WS 关闭 + 全部 agent state)
    resetForCreate();
    // v2 fix: 新建空 session (前端), 主动刷列表让 sidebar 立即看到
    void refreshSessions();
  };

  // === v2: 删除 = HTTP DELETE + 重新拉列表 + 切到下一个 / 留空 ===
  const handleDeleteSession = async (id: string) => {
    if (!confirm("确认删除该会话? 此操作不可恢复。")) return;
    try {
      const res = await fetch(`/api/sessions/${id}`, { method: "DELETE" });
      if (!res.ok) console.warn("DELETE session failed:", res.status);
    } catch (e) {
      console.warn("delete session error:", e);
    }
    await refreshSessions();
    if (id === currentSessionId) {
      // 删的是当前, 切到下一个或留空
      const remaining = sessions.filter((s) => s.id !== id);
      if (remaining.length > 0) {
        handleSelectSession(remaining[0].id);
      } else {
        handleCreateSession();
      }
    }
  };

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    // 阈值 150px: 离底部 150px 内算"在底部"
    isScrolledToBottom.current = scrollHeight - scrollTop - clientHeight < 150;
  };

  // Auto-scroll chat window (修复 2: 滚动意图侦测)
  useEffect(() => {
    if (!isScrolledToBottom.current) return;
    chatEndRef.current?.scrollIntoView({
      behavior: isGenerating ? "auto" : "smooth",  // 流式用 auto 避免动画排队
    });
  }, [messages, isWaitingApproval, liveReasoning, liveContent, isGenerating]);

  const resetWorkspace = async () => {
    // 重置 agent state (partial: 不重置 isConnected / tokenCount / currentSessionId / currentSessionInfo)
    resetForWorkspace();
    // 重置 page UI state
    setExpandedTools(new Set());
    setSelectedToolId(null);
    setShowPreview(false);
    resetDrafts();
    setInputValue("");
    setFeedbackValue("");
    isScrolledToBottom.current = true;  // 重置, 准备跟读
  };

  const handleSendPrompt = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim()) return;
    const prompt = inputValue.trim();
    setInputValue("");

    if (!hasActiveConnection()) {
      // 新会话, 用户应跟读
      isScrolledToBottom.current = true;
      startAgentSession(prompt, "");
      return;
    }

    if (isWaitingApproval) return;

    // 修复 2: 用户发了 prompt, 应该跟读
    isScrolledToBottom.current = true;
    if (!sendContinue(prompt)) {
      // WS 在 check 后断了, 回退到 start
      startAgentSession(prompt, "");
    }
  };

  const handleApprove = (approved: boolean, feedback?: string) => {
    if (!sendApprove(approved, feedback)) {
      alert("与 Agent 的连接已断开，请重新输入需求开始新会话。");
      return;
    }
    isScrolledToBottom.current = true;  // 修复 2: 审批完成, 用户应跟读下一阶段
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
  const renderBlocks: RenderBlock[] = [];
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
      <ChatHeader
        docxPath={docxPath}
        isConnected={isConnected}
        tokenCount={tokenCount}
        hasDraftFiles={draftFiles.length > 0}
        showPreview={showPreview}
        sidebarOpen={sessionSidebarOpen}
        currentSessionId={currentSessionId}
        onToggleSidebar={() => {
          const nextOpen = !sessionSidebarOpen;
          setSessionSidebarOpen(nextOpen);
          // v2 fix: sidebar 打开时**懒加载**拉列表, 保证 UI 总是看到最新 session
          if (nextOpen) void refreshSessions();
        }}
        onTogglePreview={() => {
          // 主动点开时: 先拉最新数据再 toggle, 避免拿到陈旧列表
          if (!showPreview && currentSessionId) {
            void fetchDrafts(currentSessionId);
          }
          setShowPreview((v) => !v);
        }}
        onResetWorkspace={resetWorkspace}
      />

      {/* 主区域: 横向 flex 父容器, 左侧 sidebar, 中 chat+input, 右侧 preview */}
      <div className="flex-1 w-full flex overflow-hidden">
        <SessionSidebar
          show={sessionSidebarOpen}
          sessions={sessions}
          currentSessionId={currentSessionId}
          onSelect={handleSelectSession}
          onCreate={handleCreateSession}
          onDelete={handleDeleteSession}
          onClose={() => setSessionSidebarOpen(false)}
        />
        {/* 左侧: 聊天列表 + 输入框 */}
        <div className="flex-1 flex flex-col min-w-[400px]">
          {/* Main Chat Flow Container (修复 2: onScroll 绑定) */}
          <div
            className="flex-1 w-full overflow-y-auto"
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
                              onClick={() => setSelectedToolId(isExpanded ? null : (tool.id ?? null))}
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
          files={draftFiles}
          activeFilename={activeFilename}
          onSelectFile={setActiveFilename}
          onClose={() => setShowPreview(false)}
        />
      </div>
    </div>
  );
}
