// v3 实时 DOCX 预览 — 类型定义
// 镜像后端 src/agent.py:_maybe_emit_docx_preview 返回的事件 payload 形状
// 数据流: 后端 agent.py:622 之后 yield {"type": "docx_preview_ready", ...} → use-agent-session.ts onmessage case → setDocxPreviewInfo → useDocxPreview

export type DocxDiagnosticLevel = "info" | "warning" | "error";

export interface DocxDiagnostic {
  level: DocxDiagnosticLevel;
  code: string;                // e.g. "FORMULA_RENDERED_AS_TEXT" | "LIST_ITEM_DEGRADED" | "HTML_BLOCK_REJECTED"
  message: string;
  block_id?: string;
  line_start?: number;
  line_end?: number;
  action_index?: number;
  action_type?: string;
}

export interface ParagraphChange {
  paragraph_index: number;      // 1-based
  before: string;
  after: string;
  contains_marker?: boolean;
}

export interface ChangedFile {
  path: string;                // e.g. "word/document.xml"
  status: "added" | "removed" | "changed";
  before_size: number;
  after_size: number;
  delta?: number;
}

export interface SupportSummary {
  native: number;
  degraded: number;
  rejected: number;
}

export interface DocxPreviewReady {
  type: "docx_preview_ready";
  preview_path: string;        // workspace 相对路径 (output_path from markdown_to_word)
  input_path: string;          // workspace 相对路径 (原 docx)
  docx_mtime_ms: number;       // 缓存破坏用 (?v=<mtime>)
  paragraph_changes: ParagraphChange[];
  changed_files: ChangedFile[];
  diagnostics: DocxDiagnostic[];
  action_count: number;
  support_summary: SupportSummary;
}

// 渲染状态机 (useDocxPreview 内部)
export type DocxPreviewStatus =
  | "idle"          // 还没有任何 preview_ready 事件
  | "loading"       // 正在 fetch + render (debounce 后)
  | "ready"         // 渲染成功
  | "fallback_text" // 渲染失败, 降级到 read_docx_structure 文本骨架
  | "error";        // fetch 失败 (断网等)
