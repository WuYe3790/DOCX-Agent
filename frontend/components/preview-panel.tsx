"use client";

import { motion, AnimatePresence } from "framer-motion";
import { FileText, X } from "lucide-react";
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
                  className={`px-3 py-1.5 text-[12px] font-medium font-mono rounded-md transition-all duration-200 ${
                    previewMode === "md"
                      ? "bg-white dark:bg-zinc-800 text-indigo-600 dark:text-indigo-400 shadow-sm"
                      : "text-slate-500 dark:text-zinc-400 hover:text-slate-700 dark:hover:text-zinc-200"
                  }`}
                  data-testid="preview-mode-md"
                >
                  草稿 (MD)
                </button>
                <button
                  type="button"
                  onClick={() => onPreviewModeChange("docx")}
                  className={`px-3 py-1.5 text-[12px] font-medium font-mono rounded-md transition-all duration-200 ${
                    previewMode === "docx"
                      ? "bg-white dark:bg-zinc-800 text-indigo-600 dark:text-indigo-400 shadow-sm"
                      : "text-slate-500 dark:text-zinc-400 hover:text-slate-700 dark:hover:text-zinc-200"
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

            {/* Tab Strip — 极简白底卡片激活, 三层 CSS 隐藏滚动条 */}
            {previewMode === "md" && files.length > 0 && (
              <div className="flex items-center w-full h-10 px-2 bg-slate-100/50 dark:bg-zinc-900/50 border-b border-slate-200/60 dark:border-zinc-800/60 overflow-x-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
                <div className="flex items-center gap-1 min-w-max">
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
              </div>
            )}

            {/* 主体: 根据 previewMode 切换 MD / DOCX */}
            {previewMode === "md" ? (
              <div className="flex-1 overflow-y-auto p-4 md:p-6">
                {activeFile ? (
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
                )}
              </div>
            ) : (
              <DocxPreviewPanel
                show={show}
                sessionId={sessionId ?? null}
                info={docxPreviewInfo}
                onClose={onClose}
              />
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
