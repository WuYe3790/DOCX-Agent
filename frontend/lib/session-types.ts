// v2: 纯 type 文件, 不依赖 IndexedDB / localStorage
// 被 page.tsx + components/session-sidebar.tsx 复用

export interface SessionMeta {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
  workflowState?: string | null;
}
