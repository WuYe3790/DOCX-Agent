"use client";

// v3 实时 DOCX 预览 — 单一职责 hook
// 职责: 监听 info 变化 → 500ms debounce → fetch docx → renderAsync → 失败降级
// 设计要点:
//   - AbortController 防止 session 切走时旧 fetch 还在飞
//   - 500ms debounce (不是 200ms) 因为 docx-preview 渲染大型 DOM 时有闪烁
//   - 失败降级到 status="fallback_text" + textFallback 字段, 调用方显示 read_docx_structure 同款文本骨架
//   - 不在 hook 内做 highlight overlay / diagnostics badge (那是 DocxPreviewPanel 的事)

import { useEffect, useRef, useState } from "react";
import type {
  DocxPreviewReady,
  DocxPreviewStatus,
  ParagraphChange,
  DocxDiagnostic,
} from "../lib/docx-preview-types";

// docx-preview 是 CommonJS, 需用 default import
// 类型在 d.ts 里是函数, 我们手动声明最小签名
type DocxPreviewLib = {
  renderAsync: (
    data: Blob | ArrayBuffer | Uint8Array,
    bodyContainer: HTMLElement,
    styleContainer: HTMLElement | null,
    options?: Record<string, unknown>,
  ) => Promise<unknown>;
};

let docxPreviewModule: DocxPreviewLib | null = null;
async function loadDocxPreview(): Promise<DocxPreviewLib> {
  if (docxPreviewModule) return docxPreviewModule;
  const mod = (await import("docx-preview")) as unknown as { default: DocxPreviewLib };
  docxPreviewModule = mod.default;
  return docxPreviewModule;
}

const DEBOUNCE_MS = 500;

export interface UseDocxPreviewOpts {
  sessionId: string | null;
  info: DocxPreviewReady | null;
}

export interface UseDocxPreviewResult {
  status: DocxPreviewStatus;
  previewUrl: string | null;
  paragraphChanges: ParagraphChange[];
  diagnostics: DocxDiagnostic[];
  bodyRef: React.RefObject<HTMLDivElement | null>;
  styleRef: React.RefObject<HTMLDivElement | null>;
  textFallback: string | null;
  scrollToHighlight: (paragraphIndex: number) => void;
}

export function useDocxPreview(opts: UseDocxPreviewOpts): UseDocxPreviewResult {
  const { sessionId, info } = opts;

  const [status, setStatus] = useState<DocxPreviewStatus>("idle");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [paragraphChanges, setParagraphChanges] = useState<ParagraphChange[]>([]);
  const [diagnostics, setDiagnostics] = useState<DocxDiagnostic[]>([]);
  const [textFallback, setTextFallback] = useState<string | null>(null);

  const bodyRef = useRef<HTMLDivElement | null>(null);
  const styleRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    // 1. 清掉上一次的 debounce
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    // 2. 中止上一次的 fetch
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }

    if (!info || !sessionId) {
      // 合法模式: input 变化时重置 state; 项目 page.tsx:207/214 有相同 pattern
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStatus("idle");
      return;
    }

    // 3. 立即把元信息推给 UI (用于 badge / diff 计数)
    setParagraphChanges(info.paragraph_changes);
    setDiagnostics(info.diagnostics);
    setTextFallback(null);

    // 4. 构造 URL, mtime 用作 cache-busting
    const url = `/api/word/preview?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(info.preview_path)}&v=${info.docx_mtime_ms}`;
    setPreviewUrl(url);

    // 5. 500ms debounce
    setStatus("loading");
    debounceRef.current = setTimeout(() => {
      void renderDocx(url);
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };

    async function renderDocx(url: string) {
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await fetch(url, { signal: controller.signal });
        if (!res.ok) {
          setStatus("error");
          return;
        }
        const blob = await res.blob();

        if (controller.signal.aborted) return;

        // 等 body/style 容器挂上 (debounce 后 React 已重渲)
        // 轮询最多 200ms 防止 race
        const bodyEl = await waitForRef(bodyRef, 200);
        const styleEl = styleRef.current;  // 容器可空, docx-preview 会用 bodyEl 兜底
        if (!bodyEl) {
          setStatus("error");
          return;
        }

        // 清空旧内容
        bodyEl.innerHTML = "";
        if (styleEl) styleEl.innerHTML = "";

        // 加载 docx-preview (动态 import)
        const docx = await loadDocxPreview();

        if (controller.signal.aborted) return;

        try {
          await docx.renderAsync(blob, bodyEl, styleEl, {
            className: "docx",
            ignoreWidth: false,
            ignoreHeight: false,
            breakPages: true,
            renderHeaders: true,
            renderFooters: true,
            renderFootnotes: true,
            renderEndnotes: true,
            useBase64URL: true,  // 避免 URL.createObjectURL 泄漏
          });
          if (controller.signal.aborted) return;
          setStatus("ready");
        } catch (renderErr) {
          // 渲染失败: 降级 (调用方显示 fallback 文本)
          console.warn("[useDocxPreview] renderAsync failed, falling back:", renderErr);
          setTextFallback(
            "此文档包含无法在浏览器渲染的复杂元素 (OMath / 嵌入字体 / 形状等).\n" +
            "已显示结构骨架; 实际效果以 Word 打开为准。",
          );
          setStatus("fallback_text");
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // 中止 (session 切走 / 新的 preview 来了), 静默
          return;
        }
        console.warn("[useDocxPreview] fetch failed:", err);
        setStatus("error");
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
      }
    }
  }, [info, sessionId]);

  const scrollToHighlight = (paragraphIndex: number) => {
    const bodyEl = bodyRef.current;
    if (!bodyEl) return;
    // docx-preview 把段落渲染成 <p class="docx_p"> (default className="docx")
    // 取第 N 个段落 (1-based)
    const paragraphs = bodyEl.querySelectorAll("p.docx_p, p");
    const target = paragraphs[paragraphIndex - 1] as HTMLElement | undefined;
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      target.classList.add("docx-preview-highlight-flash");
      setTimeout(() => {
        target.classList.remove("docx-preview-highlight-flash");
      }, 3000);
    }
  };

  return {
    status,
    previewUrl,
    paragraphChanges,
    diagnostics,
    bodyRef,
    styleRef,
    textFallback,
    scrollToHighlight,
  };
}

async function waitForRef(
  ref: React.RefObject<HTMLDivElement | null>,
  maxMs: number,
): Promise<HTMLDivElement | null> {
  if (ref.current) return ref.current;
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    await new Promise((r) => setTimeout(r, 20));
    if (ref.current) return ref.current;
  }
  return null;
}
