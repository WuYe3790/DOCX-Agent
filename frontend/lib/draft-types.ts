// 纯 type 文件 — 后端 GET /api/sessions/{id}/drafts 返回结构
// 被 app/page.tsx + components/preview-panel.tsx 复用

export interface DraftFile {
  name: string;      // "实验过程_合并.md"
  content: string;   // 完整 MD 内容
  size: number;      // bytes (用于显示 "X.X KB" tooltip / 排序)
  mtime: number;     // ms timestamp (后端已按 (mtime, name) tuple 升序, 前端可直接用)
}
