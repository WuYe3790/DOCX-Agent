"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, X, Download } from "lucide-react";
import MarkdownRenderer from "./markdown-renderer";
import DocxPreviewPanel from "./docx-preview-panel";
import type { DraftFile } from "../lib/draft-types";
import type { DocxPreviewReady } from "../lib/docx-preview-types";

interface PreviewPanelProps {
  show: boolean;
  files: DraftFile[];
  activeFilename: string | null;
  onSelectFile: (name: string) => void;
  onClose: () => void;
  sessionId?: string | null;
  // v3: tab 切换 (MD 草稿 vs DOCX 实时)
  previewMode: "md" | "docx";
  onPreviewModeChange: (mode: "md" | "docx") => void;
  docxPreviewInfo: DocxPreviewReady | null;
}

/**
 * 侧边栏分屏预览面板（仿 Claude Artifacts 风格）
 * - show=true 时宽度从 0 平滑展开至 50%；show=false 时收缩回 0
 * - 使用 AnimatePresence 包裹条件渲染，exit 动画保证退场丝滑
 * - 顶部 tab strip 支持多 MD 草稿文件切换（极简白底卡片激活风格）
 *   · min-w-max + whitespace-nowrap: tab 完整展开, 文件名不换行
 *   · 三层 CSS 隐藏滚动条 (webkit / IE / Firefox), 保留滚动能力 (macOS 风)
 * - 主体采用 A4 白纸居中卡片样式，内部复用 MarkdownRenderer
 * - files 为空时显示空态 (与 session-sidebar.tsx:91-96 一致风格)
 *   · 找不到 activeFile 时降级为 files[0] (防御性, 不会出现 "选中态指向不存在的文件")
 *
 * v3 扩展:
 * - 顶部新增 "草稿 (MD)" / "DOCX 实时" 二选一 tab
 * - 切换到 DOCX 时渲染 DocxPreviewPanel (内部用 docx-preview 浏览器渲染)
 * - 收到 docx_preview_ready 时由 page.tsx 切到 DOCX tab + 展开预览
 */
export default function PreviewPanel({
  show,
  files,
  activeFilename,
  onSelectFile,
  onClose,
  sessionId,
  previewMode,
  onPreviewModeChange,
  docxPreviewInfo,
}: PreviewPanelProps) {
  // 防御性: 找不到 activeFilename 对应文件时, 降级到第一个
  // 理论上 fetchDrafts() 已经保证一致, 但保险起见 (例如文件被外部删除)
  const activeFile = files.find((f) => f.name === activeFilename) ?? files[0] ?? null;

  // v3.5: showDocxDiagnostics 状态从 DocxPreviewPanel 提升到这里,
  // 让 ⚠ 诊断按钮能放在 file tab strip 区域 (DOCX 模式下, 与 ✎ N / preview_path / Download 同高),
  // 避免 DocxPreviewPanel 内部画 header 导致 DOCX 模式主体被下挤 56px.
  const [showDocxDiagnostics, setShowDocxDiagnostics] = useState(false);

  // v3.5: 新 docx 预览到来时自动展开诊断 (用户想看), 5 秒后自动折叠.
  // 状态提升后逻辑也在 preview-panel 做 (因为状态在这里).
  useEffect(() => {
    if (docxPreviewInfo && docxPreviewInfo.diagnostics.length > 0) {
      setShowDocxDiagnostics(true);
      const t = setTimeout(() => setShowDocxDiagnostics(false), 5000);
      return () => clearTimeout(t);
    }
  }, [docxPreviewInfo?.preview_path, docxPreviewInfo?.diagnostics.length]);

  // v3.5: modifiedCount 上提 (供 docx 信息条用)
  const docxModifiedCount = useMemo(
    () => (docxPreviewInfo?.paragraph_changes ?? []).filter((c) => c.before !== c.after).length,
    [docxPreviewInfo],
  );

  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.div
          key="preview-panel"
          initial={{ width: 0 }}
          animate={{ width: "50%" }}
          exit={{ width: 0 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className="h-full shrink-0 border-l border-slate-200/60 dark:border-zinc-800/60 bg-white/70 dark:bg-zinc-900/70 backdrop-blur-md shadow-2xl overflow-hidden"
        >
          <div className="h-full flex flex-col">
            {/* Header: FileText 图标 + 草稿预览标题 + 文件计数 + X 关闭 */}
            <div className="h-14 px-4 flex items-center justify-between border-b border-slate-200/60 dark:border-zinc-800/60 shrink-0 bg-white/40 dark:bg-zinc-900/40">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-indigo-400 dark:text-indigo-500" />
                <span className="text-xs font-mono font-semibold text-slate-700 dark:text-zinc-200 uppercase tracking-wider">
                  草稿预览
                </span>
                {files.length > 0 && (
                  <span className="text-[10px] font-mono text-slate-400 dark:text-zinc-500 ml-1">
                    ({files.length} 个文件)
                  </span>
                )}
              </div>
              <button
                onClick={onClose}
                className="p-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors text-slate-500 dark:text-zinc-400 hover:text-slate-700 dark:hover:text-zinc-200"
                aria-label="关闭预览"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* v3: 模式 tab (MD 草稿 vs DOCX 实时) */}
            <div className="flex items-center w-full h-10 px-2 bg-slate-50/50 dark:bg-zinc-950/50 border-b border-slate-200/60 dark:border-zinc-800/60">
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => onPreviewModeChange("md")}
                  className={`inline-flex items-center h-8 px-3 text-[12px] font-medium font-mono rounded-md transition-all duration-200 border bg-white dark:bg-zinc-800 ${
                    previewMode === "md"
                      ? "border-slate-300 dark:border-zinc-600 text-indigo-600 dark:text-indigo-400"
                      : "border-slate-200 dark:border-zinc-700 text-slate-500 dark:text-zinc-400 hover:text-slate-700 dark:hover:text-zinc-200"
                  }`}
                  data-testid="preview-mode-md"
                >
                  草稿 (MD)
                </button>
                <button
                  type="button"
                  onClick={() => onPreviewModeChange("docx")}
                  className={`inline-flex items-center h-8 px-3 text-[12px] font-medium font-mono rounded-md transition-all duration-200 border bg-white dark:bg-zinc-800 ${
                    previewMode === "docx"
                      ? "border-slate-300 dark:border-zinc-600 text-indigo-600 dark:text-indigo-400"
                      : "border-slate-200 dark:border-zinc-700 text-slate-500 dark:text-zinc-400 hover:text-slate-700 dark:hover:text-zinc-200"
                  }`}
                  data-testid="preview-mode-docx"
                >
                  DOCX 实时
                  {docxPreviewInfo && (
                    <span className="ml-1 text-[10px] text-indigo-500 dark:text-indigo-400">
                      ●
                    </span>
                  )}
                </button>
              </div>
            </div>

            {/* 文件 tab strip (v3.5: 高度始终 h-10, 内容按 previewMode 切换)
                - MD + 有文件: 渲染 MD 文件按钮 (选草稿)
                - DOCX + 有 docxPreviewInfo: 渲染 docx 信息条 (✎ N / ⚠ 诊断 / preview_path / Download)
                - 其它: 空白占位
                关键: 容器始终 h-10 + shrink-0, 切 tab 时主体内容位置不变. */}
            <div className="h-10 shrink-0 bg-slate-100/50 dark:bg-zinc-900/50 border-b border-slate-200/60 dark:border-zinc-800/60 overflow-x-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
              {previewMode === "md" && files.length > 0 ? (
                <div className="flex items-center gap-1 min-w-max h-10 px-2">
                  {files.map((file) => (
                    <button
                      key={file.name}
                      onClick={() => onSelectFile(file.name)}
                      title={`大小: ${(file.size / 1024).toFixed(1)} KB`}
                      className={`px-4 py-1.5 text-[13px] font-medium font-mono rounded-md transition-all duration-200 whitespace-nowrap ${
                        activeFilename === file.name
                          ? "bg-white dark:bg-zinc-800 text-indigo-600 dark:text-indigo-400 shadow-sm"
                          : "text-slate-500 dark:text-zinc-400 hover:text-slate-700 dark:hover:text-zinc-200 hover:bg-slate-200/50 dark:hover:bg-zinc-800/50"
                      }`}
                    >
                      {file.name}
                    </button>
                  ))}
                </div>
              ) : previewMode === "docx" && docxPreviewInfo ? (
                <div className="flex items-center gap-2 min-w-max h-10 px-3 text-[11px] font-mono text-slate-500 dark:text-zinc-400">
                  <span
                    className="truncate max-w-[40%]"
                    title={docxPreviewInfo.preview_path}
                    data-testid="docx-preview-path"
                  >
                    {docxPreviewInfo.preview_path}
                  </span>
                  {docxModifiedCount > 0 && (
                    <span
                      className="shrink-0 px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300"
                      data-testid="docx-modified-count"
                    >
                      ✎ {docxModifiedCount} 处修改
                    </span>
                  )}
                  {docxPreviewInfo.diagnostics.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setShowDocxDiagnostics((v) => !v)}
                      className={`shrink-0 px-1.5 py-0.5 rounded transition-colors ${
                        showDocxDiagnostics
                          ? "bg-amber-200 dark:bg-amber-900/60 text-amber-800 dark:text-amber-200"
                          : "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 hover:bg-amber-200/70"
                      }`}
                      title={showDocxDiagnostics ? "折叠诊断" : "展开诊断"}
                      data-testid="diagnostics-toggle"
                    >
                      ⚠ {docxPreviewInfo.diagnostics.length} 诊断
                    </button>
                  )}
                  {sessionId && (
                    <a
                      href={`/api/word/preview?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(docxPreviewInfo.preview_path)}&v=${docxPreviewInfo.docx_mtime_ms}&download=1`}
                      className="ml-auto shrink-0 p-1 rounded hover:bg-slate-200/70 dark:hover:bg-zinc-800/70 text-slate-500 dark:text-zinc-400"
                      aria-label="下载 docx"
                      title="下载原始 docx"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </a>
                  )}
                </div>
              ) : null}
            </div>

            {/* v3.6: 主体 wrapper 提升为 MD/DOCX 共用, 消除 DOM 嵌套深度差
                (subpixel 偏移 1-2px). 历史注释 (commit 52c3393 等) 仍适用:
                此 wrapper 是父级 h-full flex flex-col 的最后一个 flex-1 子元素,
                MD/DOCX 共用此层后, 卡片位置算法路径完全一致. */}
            <div className="flex-1 overflow-y-auto p-4 md:p-6">
              {previewMode === "md" ? (
                activeFile ? (
                  <div className="max-w-3xl mx-auto bg-white dark:bg-zinc-950 shadow-sm rounded-md p-8 md:p-12 min-h-[800px] border border-slate-200/40 dark:border-zinc-800/40">
                    <MarkdownRenderer content={activeFile.content} sessionId={sessionId} />
                  </div>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center text-slate-400 dark:text-zinc-500 px-6">
                    <FileText className="w-12 h-12 mb-3 opacity-40" />
                    <p className="text-sm font-medium">暂未生成草稿</p>
                    <p className="text-xs mt-1 text-slate-400/70 dark:text-zinc-500/70">
                      请在左侧对话中让 LLM 写入 Markdown 草稿
                    </p>
                  </div>
                )
              ) : (
                <DocxPreviewPanel
                  show={show}
                  sessionId={sessionId ?? null}
                  info={docxPreviewInfo}
                  onClose={onClose}
                  showDiagnostics={showDocxDiagnostics}
                  onShowDiagnosticsChange={setShowDocxDiagnostics}
                />
              )}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
