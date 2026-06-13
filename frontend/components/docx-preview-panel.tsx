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
import { FileText, X, AlertCircle, AlertTriangle, Info } from "lucide-react";
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
  // v3.5: DiagnosticDrawer 开关提升到 preview-panel,
  // 让 ⚠ N 诊断 按钮能放在 file tab strip 区域 (与 ✎ N / preview_path / Download 同高度),
  // 避免在 DocxPreviewPanel 内部多画一个 header 导致 DOCX 模式主体被下挤 56px.
  showDiagnostics: boolean;
  onShowDiagnosticsChange: (show: boolean) => void;
}

export default function DocxPreviewPanel({
  show,
  sessionId,
  info,
  onClose,
  showDiagnostics,
  onShowDiagnosticsChange,
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
  // v3.4: 改用 anchor_text 内容匹配, 不再按 idx 取 <p>.
  //
  // 为什么不能用 idx:
  //   - 后端 paragraph_index 只数 <w:body>/<w:p> 直接子段 (不含表格 cell / 页眉 / 页脚)
  //   - docx-preview 渲染的 <p class="docx_p"> 流包含表格 cell 内段 + 页眉/页脚段
  //     (renderHeaders/Footers 默认开, 见 use-docx-preview.ts:162-165)
  //   - 实验报告这种"封面是表格"的文档, 表格内段几十个, idx 偏移巨大,
  //     绿/蓝高亮落到无关段 — 用户实际看到的现象 (v3.3 LCS 修复后仍有此问题)
  //
  // 新算法:
  //   1. 把每条 change 按 anchor_text (= after || before, 已 strip) 入桶 queueByAnchor
  //   2. 遍历所有 <p.docx_p>, 取 textContent.trim() 作为 key 查桶
  //   3. 桶里有待消费 change → 取队首 (FIFO, 容忍同文本多次出现, 按 DOM 顺序配对)
  //   4. 没命中 → 标 unchanged
  //
  // Fallback: 旧 payload (history 里) 可能没 anchor_text → 退回 idx 匹配 (维持原行为)
  // 跳过: deleted 段 (after=""), 因 docx 里这段不存在, 没有 DOM 节点可标
  useEffect(() => {
    if (status !== "ready") return;
    const bodyEl = bodyRef.current;
    if (!bodyEl) return;

    // v3.4.1: selector 必须用 "p" 选所有段, 不能用 "p.docx_p"
    // 原因: 实测 docx-preview 源码 renderClass (docx-preview.mjs:3830) 只在段引用
    //       Word 样式名时才加 class (格式 "docx_标题1"); 纯段不加任何 class.
    //       之前注释说"docx-preview 用 className=docx_p 标段落"是错的, .docx_p
    //       从未匹配任何元素 — 老 selector "p.docx_p, p" 实际靠 `, p` 兜底.
    //
    // 错标隔离:
    //   - 页眉/页脚在 docx-preview 单独的 header/footer 容器, 在 bodyEl 外, 不会被选到
    //   - 表格 cell 内段虽在 bodyEl 内, 但靠 anchor_text 内容过滤天然不命中
    //     (后端 paragraph_changes 只覆盖 body 顶层段)
    const paragraphs = Array.from(bodyEl.querySelectorAll<HTMLElement>("p"));

    // === 分两套路径: anchor_text 优先, 缺失时 fallback 到 idx ===
    const hasAnchor = paragraphChanges.some((c) => typeof c.anchor_text === "string");

    type Bucket = { before: string; after: string; state: "added" | "modified" };
    const queueByAnchor = new Map<string, Bucket[]>();
    const changesByIndex = new Map<number, Bucket>();

    for (const c of paragraphChanges) {
      if (c.before === c.after) continue;          // no-op
      if (c.after === "") continue;                // deleted 段无 DOM 节点, 跳过
      const state: Bucket["state"] = c.before === "" ? "added" : "modified";
      const bucket: Bucket = { before: c.before, after: c.after, state };

      if (hasAnchor) {
        const anchor = (c.anchor_text ?? c.after).trim();
        if (!anchor) continue;
        const q = queueByAnchor.get(anchor) ?? [];
        q.push(bucket);
        queueByAnchor.set(anchor, q);
      } else {
        // fallback: 老 payload 用 idx
        changesByIndex.set(c.paragraph_index, bucket);
      }
    }

    paragraphs.forEach((el, idx) => {
      const n = idx + 1;
      el.setAttribute("data-paragraph-index", String(n));

      let hit: Bucket | undefined;
      if (hasAnchor) {
        const text = (el.textContent ?? "").trim();
        const q = text ? queueByAnchor.get(text) : undefined;
        if (q && q.length > 0) hit = q.shift();
      } else {
        hit = changesByIndex.get(n);
      }

      if (hit) {
        el.setAttribute("data-preview-state", hit.state);
        el.setAttribute(
          "title",
          hit.state === "added"
            ? `新增内容: ${hit.after.slice(0, 80)}...`
            : `修改前: ${hit.before.slice(0, 80)}...`,
        );
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

  // v3.5: showDiagnostics 状态提升到 preview-panel (避免在内部 header 重复画 chrome).
  // 新一次 preview 进来时自动重新展开 (用户想看), 5 秒后自动折叠
  useEffect(() => {
    if (status === "ready" && diagnostics.length > 0) {
      // 合法模式: 状态机由 input 驱动 (status/diagnostics 变化时重置 + 5s timeout)
      // eslint-disable-next-line react-hooks/set-state-in-effect
      onShowDiagnosticsChange(true);
      const t = setTimeout(() => onShowDiagnosticsChange(false), 5000);
      return () => clearTimeout(t);
    }
  }, [status, diagnostics.length, onShowDiagnosticsChange]);

  if (!show) return null;

  return (
    <div
      className="flex-1 flex flex-col isolate relative"
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

      {/* === DOCX 主体容器 (A4 卡片) ===
          关键: bodyRef 容器必须 **始终挂载** (用 hidden class 切换可见性),
          否则 useDocxPreview hook 在 status="loading" 时拿不到 bodyRef.current,
          waitForRef 超时 → setStatus("error") → 前端报"无法加载预览"
          (后端 200 OK 但前端失败的死锁; commit 52c3393 改成条件渲染时引入,
          此处恢复). IdleState/LoadingSkeleton 是覆盖层, 与本容器并存不冲突. */}
      <div
        className={`flex-1 overflow-y-auto p-4 md:p-6 ${status === "ready" ? "" : "hidden"}`}
      >
        <div className="max-w-3xl mx-auto bg-white dark:bg-zinc-950 shadow-sm rounded-md p-8 md:p-12 min-h-[800px] border border-slate-200/40 dark:border-zinc-800/40">
          <div
            ref={bodyRef}
            className="docx docx-preview-body"
          />
        </div>
      </div>

      {/* === 诊断 drawer (默认折叠, 点 header pill 展开; 5 秒后自动折叠) === */}
      {status === "ready" && diagnostics.length > 0 && showDiagnostics && (
        <DiagnosticDrawer
          diagnostics={diagnostics}
          onClose={() => onShowDiagnosticsChange(false)}
        />
      )}
    </div>
  );
}

// === 子组件 ===

function IdleState() {
  return (
    // v3.6: 外层 flex-1 overflow-y-auto p-4 md:p-6 由 preview-panel.tsx 提供,
    // 此处只渲染卡片本体; min-h 与 MD 模式对齐 (400 → 800), 防止切 tab 时卡片跳动.
    <div className="max-w-3xl mx-auto bg-white dark:bg-zinc-950 shadow-sm rounded-md p-8 md:p-12 min-h-[800px] border border-slate-200/40 dark:border-zinc-800/40 flex flex-col items-center justify-center text-center">
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
  );
}

function LoadingSkeleton() {
  return (
    // v3.6: 外层 flex-1 overflow-y-auto p-4 md:p-6 由 preview-panel.tsx 提供,
    // 此处只渲染卡片本体; min-h-[800px] 保持与 MD 模式一致.
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
    // v3.6: 外层 flex-1 overflow-y-auto p-4 md:p-6 由 preview-panel.tsx 提供,
    // 此处只渲染卡片本体; min-h 与 MD 模式对齐 (400 → 800).
    <div className="max-w-3xl mx-auto bg-amber-50/40 dark:bg-amber-950/20 shadow-sm rounded-md p-8 md:p-12 min-h-[800px] border border-amber-200/40 dark:border-amber-800/40">
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
