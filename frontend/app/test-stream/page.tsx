"use client";

import { useState } from "react";

// === 最小化 React WebSocket 事件流测试页 ===
// 故意只用 useState 直接 append——避开 setMessages + useRef + 闭包的所有复杂度
// 目的: 验证 React 能否正常接收流式事件, 排除后端问题

interface Event {
  idx: number;
  time: string;
  type: string;
  detail: string;
  cum?: string;
}

// === module-scoped 累加器 ===
// 函数体内的 let 每次 render 会被重置, 所以必须放组件外
// 单一真相: 每次 component 重新 render, 这里不变
let moduleCumReasoning = "";
let moduleCumContent = "";

export default function TestStreamPage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [status, setStatus] = useState<"disconnected" | "connected">("disconnected");
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [prompt, setPrompt] = useState(
    "请阅读 J:\\学习\\大三下\\计算机劳动实践\\实验13\\实验报告13.docx 并完成编写, 要求保留已有内容"
  );
  const [url, setUrl] = useState("ws://127.0.0.1:8000/api/ws/agent");

  const log = (type: string, data: any) => {
    const time = new Date().toISOString().slice(11, 23);
    // 关键: idx 用 functional setState 计算, 不用闭包 events.length
    // 避免 React strict mode 双调用导致的 duplicate key
    setEvents((prev) => {
      const idx = prev.length + 1;
      let detail = "";
      let cum: string | undefined;

      if (type === "reasoning" || type === "content") {
        const delta = data?.delta || "";
        if (type === "reasoning") {
          moduleCumReasoning += delta;
          cum = `[cum reasoning: ${moduleCumReasoning.length} chars]`;
        } else {
          moduleCumContent += delta;
          cum = `[cum content: ${moduleCumContent.length} chars]`;
        }
        detail = `delta (${delta.length} chars): ${JSON.stringify(delta.length > 100 ? delta.slice(0, 100) + "..." : delta)}`;
      } else if (type === "tool_start") {
        detail = `name=${data?.name}\nargs=${data?.arguments}`;
      } else if (type === "tool_end") {
        detail = `result: ${(data?.result || "").slice(0, 200)}${(data?.result || "").length > 200 ? "..." : ""}`;
      } else if (type === "wait_approval") {
        detail = `phase=${data?.phase}\ncontent: ${(data?.content || "").slice(0, 200)}${(data?.content || "").length > 200 ? "..." : ""}`;
      } else if (type === "done") {
        detail = `content: ${(data?.content || "").slice(0, 200)}${(data?.content || "").length > 200 ? "..." : ""}`;
      } else if (type === "round_start") {
        detail = `token_count=${data?.token_count || "?"}`;
      } else if (type === "error") {
        detail = data?.message || JSON.stringify(data);
      } else {
        detail = JSON.stringify(data);
      }

      return [...prev, { idx, time, type, detail, cum }];
    });
  };

  const start = () => {
    if (ws) {
      try { ws.close(); } catch (e) {}
    }
    setEvents([]);
    moduleCumReasoning = "";
    moduleCumContent = "";

    log("__sys__", { msg: "开始会话" });

    const socket = new WebSocket(url);
    socket.onopen = () => {
      setStatus("connected");
      log("__sys__", { msg: "WS 已连接, 发送 start" });
      socket.send(JSON.stringify({ type: "start", prompt, docx_path: "" }));
    };
    socket.onmessage = (e) => {
      let data: any;
      try { data = JSON.parse(e.data); } catch { return; }
      log(data.type || "unknown", data);
    };
    socket.onerror = (e) => {
      log("__error__", { error: String(e) });
    };
    socket.onclose = () => {
      setStatus("disconnected");
      log("__sys__", { msg: "WS 关闭" });
    };
    setWs(socket);
  };

  const approve = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      alert("WS 未连接");
      return;
    }
    log("__sys__", { msg: "发送 approve=true" });
    ws.send(JSON.stringify({ type: "approve", approved: true, feedback: "" }));
  };

  const clear = () => {
    setEvents([]);
    moduleCumReasoning = "";
    moduleCumContent = "";
  };

  return (
    <div style={{ fontFamily: "monospace", fontSize: "12px", padding: "16px", background: "#fafafa", minHeight: "100vh" }}>
      <h1 style={{ fontSize: "14px", margin: "0 0 12px 0" }}>
        🧪 React 最小化事件流测试
      </h1>

      <div style={{ background: "white", border: "1px solid #ddd", padding: "12px", marginBottom: "12px" }}>
        <div>
          <input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            style={{ width: "500px", padding: "4px 8px", marginRight: "8px" }}
          />
          <button onClick={start} style={{ padding: "4px 12px", marginRight: "4px" }}>▶ 开始</button>
          <button onClick={approve} style={{ padding: "4px 12px", marginRight: "4px" }}>✓ 同意</button>
          <button onClick={clear} style={{ padding: "4px 12px" }}>🗑 清空</button>
        </div>
        <div style={{ marginTop: "8px" }}>
          WS URL: <input value={url} onChange={(e) => setUrl(e.target.value)} style={{ width: "300px", padding: "2px 6px" }} />
          &nbsp;&nbsp; 状态:{" "}
          <span style={{ background: status === "connected" ? "#d4edda" : "#f8d7da", padding: "2px 8px", borderRadius: "3px" }}>
            {status}
          </span>
          &nbsp;&nbsp; 事件: <span>{events.length}</span>
        </div>
      </div>

      <div style={{ background: "white", border: "1px solid #ddd", maxHeight: "80vh", overflowY: "auto" }}>
        {events.map((e) => (
          <div
            key={e.idx}
            style={{
              padding: "3px 8px",
              borderBottom: "1px solid #eee",
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
              fontSize: "11px",
            }}
          >
            <span style={{ color: "#999", display: "inline-block", minWidth: "40px" }}>#{String(e.idx).padStart(4, "0")}</span>
            <span style={{ color: "#666", display: "inline-block", minWidth: "90px" }}>{e.time}</span>
            <span
              style={{
                fontWeight: "bold",
                display: "inline-block",
                minWidth: "110px",
                color:
                  e.type === "reasoning" ? "#888" :
                  e.type === "content" ? "#b8860b" :
                  e.type === "tool_start" ? "#228b22" :
                  e.type === "tool_end" ? "#8b008b" :
                  e.type === "wait_approval" || e.type === "done" ? "#cc0000" :
                  "#333",
              }}
            >[{e.type}]</span>
            <span style={{ marginLeft: "8px", color: "#444" }}>{e.detail}</span>
            {e.cum && <span style={{ marginLeft: "8px", color: "#008888", fontSize: "10px" }}>{e.cum}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
