// IndexedDB 持久化层: 会话管理
// 关键: onupgradeneeded 是唯一能 createObjectStore 的事件

const DB_NAME = "docx-agent";
const DB_VERSION = 1;
const STORE_NAME = "sessions";
const CURRENT_SESSION_KEY = "docx-agent:currentSessionId";

export interface Session {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  docxPath: string;
  messages: any[];            // 完整消息历史 (用 any 避免循环依赖)
  previewContent: string;
  approvalPhase: "style_review" | "md_draft" | "word_editing" | null;
  isWaitingApproval: boolean;
}

export interface SessionMeta {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
}

// === 数据库连接 ===

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    // 关键: onupgradeneeded 是唯一能 createObjectStore 的事件
    // 第一次打开 (无库) 或 version 提升时触发
    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("IndexedDB blocked by another connection"));
  });
}

// 通用 promisify 包装
function promisifyRequest<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

// === CRUD ===

/** 列出所有 session 的元数据, 按 updatedAt 倒序 (最新在最上) */
export async function listSessions(): Promise<SessionMeta[]> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, "readonly");
    const store = tx.objectStore(STORE_NAME);
    const all = await promisifyRequest<Session[]>(store.getAll() as IDBRequest<Session[]>);
    db.close();
    return all
      .map((s) => ({
        id: s.id,
        title: s.title,
        createdAt: s.createdAt,
        updatedAt: s.updatedAt,
        messageCount: s.messages?.length ?? 0,
      }))
      .sort((a, b) => b.updatedAt - a.updatedAt);
  } catch (e) {
    console.warn("listSessions failed:", e);
    return [];
  }
}

/** 获取单个 session 的完整内容 (含 messages) */
export async function getSession(id: string): Promise<Session | null> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, "readonly");
    const store = tx.objectStore(STORE_NAME);
    const session = await promisifyRequest<Session | undefined>(
      store.get(id) as IDBRequest<Session | undefined>
    );
    db.close();
    return session ?? null;
  } catch (e) {
    console.warn("getSession failed:", e);
    return null;
  }
}

/** 新建 session (默认空) */
export async function createSession(partial: Partial<Session> = {}): Promise<Session> {
  const now = Date.now();
  const newSession: Session = {
    id: partial.id ?? `session-${formatTimestamp(now)}`,
    title: partial.title ?? "新会话",
    createdAt: now,
    updatedAt: now,
    docxPath: partial.docxPath ?? "",
    messages: partial.messages ?? [],
    previewContent: partial.previewContent ?? "",
  };
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);
    await promisifyRequest(store.add(newSession));
    db.close();
  } catch (e) {
    console.warn("createSession failed:", e);
  }
  return newSession;
}

/** 局部更新 session (id 不可变) */
export async function updateSession(
  id: string,
  partial: Partial<Session>
): Promise<Session | null> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);
    const existing = await promisifyRequest<Session | undefined>(
      store.get(id) as IDBRequest<Session | undefined>
    );
    if (!existing) {
      db.close();
      return null;
    }
    const updated: Session = { ...existing, ...partial, id };   // id 不可变
    await promisifyRequest(store.put(updated));
    db.close();
    return updated;
  } catch (e) {
    console.warn("updateSession failed:", e);
    return null;
  }
}

/** 删除 session */
export async function deleteSession(id: string): Promise<void> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);
    await promisifyRequest(store.delete(id));
    db.close();
  } catch (e) {
    console.warn("deleteSession failed:", e);
  }
}

// === localStorage helpers (存当前 session id) ===

export function getCurrentSessionId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(CURRENT_SESSION_KEY);
  } catch {
    return null;
  }
}

export function setCurrentSessionId(id: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (id === null) {
      localStorage.removeItem(CURRENT_SESSION_KEY);
    } else {
      localStorage.setItem(CURRENT_SESSION_KEY, id);
    }
  } catch (e) {
    console.warn("setCurrentSessionId failed:", e);
  }
}

// === 辅助 ===

// 生成 session-{YYYYMMDD-HHMMSS} 格式 ID
function formatTimestamp(ts: number): string {
  const d = new Date(ts);
  const pad = (n: number) => n.toString().padStart(2, "0");
  return (
    d.getFullYear().toString() +
    pad(d.getMonth() + 1) +
    pad(d.getDate()) +
    "-" +
    pad(d.getHours()) +
    pad(d.getMinutes()) +
    pad(d.getSeconds())
  );
}
