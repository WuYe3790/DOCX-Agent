"use client";

// v3 实时 DOCX 预览 — 容器组件
// 视觉规范 (按 plan 落地时的细节建议):
//   - HighlightOverlay: 玻璃拟态 (backdrop-blur + 半透明白/蓝底 + 左侧高饱和度边框)
//   - DiagnosticBadges: 悬浮阴影 (shadow-lg + hover:shadow-xl, 按 level 区分颜色)
//   - SkeletonOverlay: animate-pulse 占位卡片, 避免 docx-preview 异步渲染时的视觉闪烁
//   - 容器顶层 isolation: isolate 防止 Tailwind v4 样式穿透到 docx-preview DOM
// 数据流:
//   - props.info (DocxPreviewReady 事件) → useDocxPreview hook
//   - hook 返回 bodyRef / styleRef / status / paragraphChanges / diagnostics
//   - 本组件负责把这些渲染成 A4 卡片 + 顶部 diff 计数 + 右侧 diagnostics 浮层

import { useEffect, useMemo } from "react";
import { FileText, X, AlertCircle, AlertTriangle, Info, Download } from "lucide-react";
import { useDocxPreview } from "../hooks/use-docx-preview";
import type {
  DocxDiagnostic,
  DocxPreviewReady,
} from "../lib/docx-preview-types";

interface DocxPreviewPanelProps {
  show: boolean;
  sessionId: string | null;
  info: DocxPreviewReady | null;
  onClose: () => void;
}

export default function DocxPreviewPanel({
  show,
  sessionId,
  info,
  onClose,
}: DocxPreviewPanelProps) {
  const {
    status,
    paragraphChanges,
    diagnostics,
    bodyRef,
    styleRef,
    textFallback,
    scrollToHighlight,
  } = useDocxPreview({ sessionId, info });

  // === 把 paragraphChanges 注入到 docx-preview 渲染出的 DOM ===
  // docx-preview 用 className="docx_p" 标段落, 我们按出现顺序设 data-paragraph-index + data-preview-state
  // CSS 在 <style> 标签里靠 [data-preview-state="modified"] 选
  useEffect(() => {
    if (status !== "ready") return;
    const bodyEl = bodyRef.current;
    if (!bodyEl) return;

    const paragraphs = bodyEl.querySelectorAll("p.docx_p, p");
    const changesByIndex = new Map<number, { before: string; after: string }>();
    for (const c of paragraphChanges) {
      changesByIndex.set(c.paragraph_index, { before: c.before, after: c.after });
    }

    paragraphs.forEach((el, idx) => {
      const n = idx + 1;  // 1-based
      const change = changesByIndex.get(n);
      el.setAttribute("data-paragraph-index", String(n));
      if (change) {
        // 简单的"修改"判定: 文本变了
        if (change.before !== change.after) {
          el.setAttribute("data-preview-state", "modified");
          el.setAttribute("title", `修改前: ${change.before.slice(0, 80)}...`);
        }
      } else {
        el.setAttribute("data-preview-state", "unchanged");
      }
    });
  }, [status, paragraphChanges, bodyRef]);

  const modifiedCount = useMemo(
    () => paragraphChanges.filter((c) => c.before !== c.after).length,
    [paragraphChanges],
  );

  if (!show) return null;

  return (
    <div
      className="h-full flex flex-col isolate"
      data-testid="docx-preview-panel"
    >
      {/* === 局部样式: 玻璃拟态 + 闪烁高亮 === */}
      <style>{`
        .docx-preview-modified {
          position: relative;
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.08), rgba(99, 102, 241, 0.04)) !important;
          backdrop-filter: blur(4px);
          -webkit-backdrop-filter: blur(4px);
          border-left: 3px solid rgb(99, 102, 241) !important;
          padding-left: 0.75rem !important;
          margin-left: -0.75rem !important;
          border-radius: 0 6px 6px 0;
          transition: background 0.3s ease;
        }
        .docx-preview-modified::before {
          content: "✎";
          position: absolute;
          right: 4px;
          top: 4px;
          color: rgb(99, 102, 241);
          font-size: 10px;
          opacity: 0.6;
        }
        .docx-preview-highlight-flash {
          animation: docx-flash 3s ease-out;
        }
        @keyframes docx-flash {
          0%, 100% { background: rgba(99, 102, 241, 0.1); }
          50% { background: rgba(99, 102, 241, 0.35); }
        }
      `}</style>

      {/* === Header === */}
      <div className="h-14 px-4 flex items-center justify-between border-b border-slate-200/60 dark:border-zinc-800/60 shrink-0 bg-white/40 dark:bg-zinc-900/40">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="w-4 h-4 text-indigo-400 dark:text-indigo-500 shrink-0" />
          <span className="text-xs font-mono font-semibold text-slate-700 dark:text-zinc-200 uppercase tracking-wider shrink-0">
            DOCX 实时
          </span>
          {info && (
            <span className="text-[10px] font-mono text-slate-500 dark:text-zinc-400 truncate" title={info.preview_path}>
              {info.preview_path}
            </span>
          )}
          {modifiedCount > 0 && (
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 shrink-0">
              ✎ {modifiedCount} 处修改
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {info && sessionId && (
            <a
              href={`/api/word/preview?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(info.preview_path)}&v=${info.docx_mtime_ms}&download=1`}
              className="p-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-zinc-800 text-slate-500 dark:text-zinc-400"
              aria-label="下载 docx"
              title="下载原始 docx"
            >
              <Download className="w-4 h-4" />
            </a>
          )}
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-zinc-800 text-slate-500 dark:text-zinc-400"
            aria-label="关闭预览"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* === 状态层: loading / error / fallback === */}
      {status === "loading" && <LoadingSkeleton />}
      {status === "error" && <ErrorState onRetry={() => window.location.reload()} />}
      {status === "fallback_text" && textFallback && <FallbackState text={textFallback} />}

      {/* === DOCX 样式注入区 (docx-preview 渲染 CSS / numbeings / fonts) === */}
      <div
        ref={styleRef}
        className="docx-preview-style-container"
        style={{ display: "none" }}  // 隐藏但保留, docx-preview 需要挂在 DOM 上
        aria-hidden="true"
      />

      {/* === DOCX 主体容器 (A4 卡片) === */}
      <div
        className={`flex-1 overflow-y-auto p-4 md:p-6 ${status === "ready" ? "" : "hidden"}`}
      >
        <div className="max-w-3xl mx-auto bg-white dark:bg-zinc-950 shadow-sm rounded-md p-8 md:p-12 min-h-[800px] border border-slate-200/40 dark:border-zinc-800/40">
          <div
            ref={bodyRef}
            className="docx docx-preview-body"
            onClick={(e) => {
              // 点击段落时, 滚动到下一个 modified 段
              const target = (e.target as HTMLElement).closest("p[data-preview-state='modified']") as HTMLElement | null;
              if (target) {
                const idx = Number(target.getAttribute("data-paragraph-index"));
                scrollToHighlight(idx);
              }
            }}
          />
        </div>
      </div>

      {/* === 诊断徽章层 (悬浮在主体右侧, 仅当有 diagnostics) === */}
      {status === "ready" && diagnostics.length > 0 && (
        <DiagnosticBadges diagnostics={diagnostics} />
      )}
    </div>
  );
}

// === 子组件 ===

function LoadingSkeleton() {
  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6">
      <div className="max-w-3xl mx-auto bg-white dark:bg-zinc-950 shadow-sm rounded-md p-8 md:p-12 min-h-[800px] border border-slate-200/40 dark:border-zinc-800/40 space-y-4">
        <div className="h-6 w-1/3 bg-slate-200 dark:bg-zinc-800 rounded animate-pulse" />
        <div className="h-4 w-full bg-slate-100 dark:bg-zinc-900 rounded animate-pulse" />
        <div className="h-4 w-5/6 bg-slate-100 dark:bg-zinc-900 rounded animate-pulse" />
        <div className="h-4 w-4/6 bg-slate-100 dark:bg-zinc-900 rounded animate-pulse" />
        <div className="h-32 w-full bg-slate-50 dark:bg-zinc-900/50 rounded animate-pulse" />
        <div className="h-4 w-full bg-slate-100 dark:bg-zinc-900 rounded animate-pulse" />
        <div className="h-4 w-3/4 bg-slate-100 dark:bg-zinc-900 rounded animate-pulse" />
        <p className="text-xs text-center text-slate-400 dark:text-zinc-500 mt-8">
          正在加载 DOCX 预览...
        </p>
      </div>
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-md text-center space-y-4">
        <AlertCircle className="w-12 h-12 mx-auto text-red-400" />
        <h3 className="text-sm font-semibold text-slate-700 dark:text-zinc-300">
          无法加载预览
        </h3>
        <p className="text-xs text-slate-500 dark:text-zinc-500 leading-relaxed">
          /api/word/preview 请求失败. 可能是网络断开、文件被删除或 session 失效.
        </p>
        <button
          onClick={onRetry}
          className="px-3 py-1.5 text-xs bg-indigo-500 hover:bg-indigo-600 text-white rounded shadow"
        >
          刷新页面
        </button>
      </div>
    </div>
  );
}

function FallbackState({ text }: { text: string }) {
  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6">
      <div className="max-w-3xl mx-auto bg-amber-50/40 dark:bg-amber-950/20 shadow-sm rounded-md p-8 md:p-12 min-h-[400px] border border-amber-200/40 dark:border-amber-800/40">
        <div className="flex items-center gap-2 mb-4">
          <AlertTriangle className="w-4 h-4 text-amber-500" />
          <h3 className="text-sm font-semibold text-amber-700 dark:text-amber-300">
            渲染降级
          </h3>
        </div>
        <pre className="text-xs text-slate-600 dark:text-slate-400 whitespace-pre-wrap font-mono">
          {text}
        </pre>
      </div>
    </div>
  );
}

function DiagnosticBadges({ diagnostics }: { diagnostics: DocxDiagnostic[] }) {
  return (
    <div
      className="absolute top-20 right-6 w-72 max-h-[60vh] overflow-y-auto space-y-2 z-10"
      data-testid="diagnostic-badges"
    >
      <div className="text-[10px] font-mono text-slate-500 dark:text-zinc-400 uppercase tracking-wider px-1">
        诊断 ({diagnostics.length})
      </div>
      {diagnostics.slice(0, 8).map((d, idx) => (
        <DiagnosticBadge key={`${d.code}-${idx}`} diagnostic={d} />
      ))}
      {diagnostics.length > 8 && (
        <div className="text-[10px] text-slate-400 text-center">
          还有 {diagnostics.length - 8} 条...
        </div>
      )}
    </div>
  );
}

function DiagnosticBadge({ diagnostic }: { diagnostic: DocxDiagnostic }) {
  const Icon = diagnostic.level === "error" ? AlertCircle
    : diagnostic.level === "warning" ? AlertTriangle
    : Info;
  const colorClass = diagnostic.level === "error"
    ? "bg-red-50/90 dark:bg-red-950/80 border-red-300/60 dark:border-red-800/60 text-red-700 dark:text-red-300"
    : diagnostic.level === "warning"
    ? "bg-amber-50/90 dark:bg-amber-950/80 border-amber-300/60 dark:border-amber-800/60 text-amber-700 dark:text-amber-300"
    : "bg-blue-50/90 dark:bg-blue-950/80 border-blue-300/60 dark:border-blue-800/60 text-blue-700 dark:text-blue-300";

  return (
    <div
      className={`backdrop-blur-md border rounded-md p-2 shadow-lg hover:shadow-xl transition-shadow ${colorClass}`}
      data-testid="diagnostic-badge"
    >
      <div className="flex items-start gap-1.5">
        <Icon className="w-3.5 h-3.5 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-[10px] font-mono font-semibold uppercase tracking-wider opacity-80">
            {diagnostic.code}
          </div>
          <div className="text-xs leading-snug mt-0.5">
            {diagnostic.message}
          </div>
          {diagnostic.block_id && (
            <div className="text-[10px] font-mono opacity-60 mt-1">
              block: {diagnostic.block_id}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
