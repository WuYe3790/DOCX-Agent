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
  paragraph_index: number;      // 1-based, 后端 <w:body>/<w:p> 直接子段序号 (不含表格/页眉内段)
  before: string;
  after: string;
  // v3.4: 锚文本 (= after || before, .strip()).
  // 前端按内容匹配 docx-preview 渲染的 <p>, 而不是按 idx — 因为 docx-preview
  // 的 <p> 流含表格 cell / 页眉页脚段, 与后端 paragraph_index 段落定义不一致.
  // optional: 向后兼容 history 里旧 payload (未带此字段时 fallback 到 index 匹配).
  anchor_text?: string;
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
