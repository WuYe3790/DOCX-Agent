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

import { useEffect, useMemo, useState } from "react";
import { FileText, X, AlertCircle, AlertTriangle, Info, Download, ChevronRight } from "lucide-react";
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
      if (change && change.before !== change.after) {
        // 区分"新增"(绿色) vs "修改"(蓝色)
        // 判定: before 为空 → 是新增段; 否则是修改
        if (change.before === "") {
          el.setAttribute("data-preview-state", "added");
          el.setAttribute("title", `新增内容: ${change.after.slice(0, 80)}...`);
        } else {
          el.setAttribute("data-preview-state", "modified");
          el.setAttribute("title", `修改前: ${change.before.slice(0, 80)}...`);
        }
      } else {
        el.setAttribute("data-preview-state", "unchanged");
        el.removeAttribute("title");
      }
    });
  }, [status, paragraphChanges, bodyRef]);

  const modifiedCount = useMemo(
    () => paragraphChanges.filter((c) => c.before !== c.after).length,
    [paragraphChanges],
  );

  // v3.1: 诊断面板默认折叠, 避免挡视野
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  // 新一次 preview 进来时自动重新展开 (用户想看), 5 秒后自动折叠
  useEffect(() => {
    if (status === "ready" && diagnostics.length > 0) {
      // 合法模式: 状态机由 input 驱动 (status/diagnostics 变化时重置 + 5s timeout)
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setShowDiagnostics(true);
      const t = setTimeout(() => setShowDiagnostics(false), 5000);
      return () => clearTimeout(t);
    }
  }, [status, diagnostics.length]);

  if (!show) return null;

  return (
    <div
      className="h-full flex flex-col isolate"
      data-testid="docx-preview-panel"
    >
      {/* === 局部样式: 玻璃拟态 + 闪烁高亮 ===
          注意: 段落是 docx-preview 在 bodyEl 里动态创建的 <p data-preview-state="modified">,
          CSS 选择器必须用 [data-preview-state="modified"] (之前用 .docx-preview-modified 类,
          永远不匹配, 玻璃拟态效果完全不显示) */}
      <style>{`
        [data-preview-state="modified"] {
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
        [data-preview-state="modified"]:hover {
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.14), rgba(99, 102, 241, 0.08)) !important;
        }
        [data-preview-state="modified"]::before {
          content: "✎";
          position: absolute;
          right: 4px;
          top: 4px;
          color: rgb(99, 102, 241);
          font-size: 10px;
          opacity: 0.6;
          pointer-events: none;
        }
        /* 区分"新增"和"修改" (绿色 vs 蓝色) */
        [data-preview-state="added"] {
          background: linear-gradient(135deg, rgba(16, 185, 129, 0.10), rgba(34, 197, 94, 0.04)) !important;
          border-left-color: rgb(16, 185, 129) !important;
        }
        [data-preview-state="added"]::before {
          content: "+";
          color: rgb(16, 185, 129);
        }
        [data-preview-state="added"]:hover {
          background: linear-gradient(135deg, rgba(16, 185, 129, 0.16), rgba(34, 197, 94, 0.08)) !important;
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
          {diagnostics.length > 0 && status === "ready" && (
            <button
              type="button"
              onClick={() => setShowDiagnostics((v) => !v)}
              className={`text-[10px] font-mono px-1.5 py-0.5 rounded shrink-0 transition-colors ${
                showDiagnostics
                  ? "bg-amber-200 dark:bg-amber-900/60 text-amber-800 dark:text-amber-200"
                  : "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 hover:bg-amber-200/70"
              }`}
              title={showDiagnostics ? "折叠诊断" : "展开诊断"}
              data-testid="diagnostics-toggle"
            >
              ⚠ {diagnostics.length} 诊断
              <ChevronRight className={`inline w-3 h-3 ml-0.5 transition-transform ${showDiagnostics ? "rotate-90" : ""}`} />
            </button>
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

      {/* === 状态层: idle / loading / error / fallback === */}
      {status === "idle" && <IdleState />}
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

      {/* === DOCX 主体容器 (A4 卡片) — 只在 ready 状态渲染 === */}
      {status === "ready" && (
        <div className="flex-1 overflow-y-auto p-4 md:p-6">
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
      )}

      {/* === 诊断 drawer (默认折叠, 点 header pill 展开; 5 秒后自动折叠) === */}
      {status === "ready" && diagnostics.length > 0 && showDiagnostics && (
        <DiagnosticDrawer
          diagnostics={diagnostics}
          onClose={() => setShowDiagnostics(false)}
        />
      )}
    </div>
  );
}

// === 子组件 ===

function IdleState() {
  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6">
      <div className="max-w-3xl mx-auto bg-white dark:bg-zinc-950 shadow-sm rounded-md p-8 md:p-12 min-h-[400px] border border-slate-200/40 dark:border-zinc-800/40 flex flex-col items-center justify-center text-center">
        <FileText className="w-12 h-12 mb-3 opacity-30 text-slate-400 dark:text-zinc-500" />
        <p className="text-sm font-medium text-slate-500 dark:text-zinc-400">
          暂无 DOCX 预览
        </p>
        <p className="text-xs mt-2 text-slate-400 dark:text-zinc-500 max-w-sm leading-relaxed">
          等待 LLM 完成首次 markdown_to_word 编辑后, 这里会自动出现最近编辑结果.
          <br />
          也可以切换到 &quot;草稿 (MD)&quot; tab 查看 markdown 草稿.
        </p>
      </div>
    </div>
  );
}

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

function DiagnosticDrawer({
  diagnostics,
  onClose,
}: {
  diagnostics: DocxDiagnostic[];
  onClose: () => void;
}) {
  return (
    <div
      // 关键 UX: 用 transform 滑入, 不阻塞主区; 顶栏 sticky 始终可点 X 关闭
      className="absolute inset-y-0 right-0 w-80 max-w-[90%] bg-white/95 dark:bg-zinc-900/95 backdrop-blur-md border-l border-slate-200/60 dark:border-zinc-800/60 shadow-2xl z-20 flex flex-col"
      data-testid="diagnostic-badges"
    >
      {/* sticky 顶部, 始终可见 (含 X 关闭按钮) */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200/60 dark:border-zinc-800/60 shrink-0">
        <div className="text-[10px] font-mono text-slate-600 dark:text-zinc-300 uppercase tracking-wider">
          诊断 ({diagnostics.length})
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded hover:bg-slate-100 dark:hover:bg-zinc-800 text-slate-500 dark:text-zinc-400"
          aria-label="关闭诊断"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      {/* 滚动列表, 显示全部 (不再限制 8 条) */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {diagnostics.map((d, idx) => (
          <DiagnosticBadge key={`${d.code}-${idx}`} diagnostic={d} />
        ))}
      </div>
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
