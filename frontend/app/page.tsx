"use client";

import React, { useState, useEffect, useRef } from "react";
import { Terminal } from "lucide-react";
// PanelLeft/Send 已迁到 ChatHeader/ChatInput, RefreshCw/Plus/Trash2 等在 SessionSidebar 内部
// motion/AnimatePresence 已迁到 ChatMessageBlocks/ChatInput
// MarkdownRenderer/ReasoningPanel 已迁入 ChatMessageBlocks
import PreviewPanel from "../components/preview-panel";
import SessionSidebar from "../components/session-sidebar";
import AnimatedLivePanel from "../components/animated-live-panel";
import ChatHeader from "../components/chat-header";
import ChatMessageBlocks from "../components/chat-message-blocks";
import ApprovalCheckpoint from "../components/approval-checkpoint";
import ChatInput from "../components/chat-input";
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
      isScrolledToBottom.current = true;
      if (currentSessionId) {
        startAgentSession(prompt, docxPath, currentSessionId);
      } else {
        startAgentSession(prompt, "");
      }
      return;
    }

    if (isWaitingApproval) return;

    // 修复 2: 用户发了 prompt, 应该跟读
    isScrolledToBottom.current = true;
    if (!sendContinue(prompt)) {
      // WS 在 check 后断了, 尝试恢复
      if (currentSessionId) {
        startAgentSession(prompt, docxPath, currentSessionId);
      } else {
        startAgentSession(prompt, "");
      }
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

          {/* === 4 种类型化消息块的渲染 (user / reasoning / content / toolGroup) === */}
          <ChatMessageBlocks
            blocks={renderBlocks}
            isGenerating={isGenerating}
            selectedToolId={selectedToolId}
            onSelectTool={setSelectedToolId}
          />

          {/* === 实时流式 AnimatedLivePanel === */}
          <AnimatedLivePanel reasoning={liveReasoning} content={liveContent} time={thinkTime} />

          {/* 旧的文档流内指示器已移除: 替换为 footer 上方悬浮胶囊(见下) */}

          {/* Inline Phase Checkpoint (Waiting Approval) */}
          <ApprovalCheckpoint
            isWaitingApproval={isWaitingApproval}
            approvalPhase={approvalPhase}
            isConnected={isConnected}
            feedbackValue={feedbackValue}
            onChangeFeedback={setFeedbackValue}
            onApprove={handleApproveAction}
            onReject={handleRejectAction}
          />

          <div ref={chatEndRef} />
          </div>
        </div>

        {/* Input Prompt Box area */}
        <ChatInput
          inputValue={inputValue}
          isConnected={isConnected}
          isWaitingApproval={isWaitingApproval}
          isGenerating={isGenerating}
          liveReasoning={liveReasoning}
          liveContent={liveContent}
          onChangeInput={setInputValue}
          onSubmit={handleSendPrompt}
        />
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
