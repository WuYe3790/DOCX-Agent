// 从 page.tsx 提取的纯类型定义
// 编译时被擦除, 运行时无影响

export interface Message {
  role: "user" | "assistant" | "tool";
  content?: string;
  reasoning_content?: string;
  toolName?: string;
  toolArgs?: string;
  toolResult?: string;
  toolStatus?: "running" | "success" | "error";
  id?: string;
}

export interface TokenInfo {
  token_count: number;
}

// === renderBlocks 派生数组的类型化 (原 page.tsx 行 817-823) ===
// 4 种渲染块: user / reasoning / content / toolGroup
// toolGroup 内的 tools 数组用锁死的 startIndex 生成 id 以保持 React key 稳定
export type RenderBlockType = "user" | "reasoning" | "content" | "toolGroup";

export interface RenderBlock {
  type: RenderBlockType;
  content?: string;
  tools?: Message[];
  id: string;
  autoCollapse?: boolean;
}
