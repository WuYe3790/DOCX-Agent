"use client";

import React, { useState, useEffect, useRef } from "react";
import { Upload, FileText, CheckCircle2, ArrowRight, Play, AlertCircle, RefreshCw } from "lucide-react";
import WorkflowProgress from "../components/workflow-progress";
import ChatPanel from "../components/chat-panel";
import StyleGallery from "../components/style-gallery";
import EditorPanel from "../components/editor-panel";
import DiffViewer from "../components/diff-viewer";

interface Message {
  role: "system" | "user" | "assistant" | "tool";
  content?: string;
  reasoning_content?: string;
}

interface ToolLog {
  name: string;
  arguments: string;
  result?: string;
  status: "running" | "success" | "error";
  id: string;
}

interface CandidateHint {
  role: string;
  evidence_count: number;
}

interface ExampleParagraph {
  text: string;
  paragraph_index: number;
  location: string;
}

interface StyleSample {
  sample_id: string;
  context: string;
  format: {
    bold: boolean;
    italic: boolean;
    color: string | null;
    font_size_half_points: number | null;
    font_ascii: string | null;
    font_east_asia: string | null;
  };
  paragraph_format?: {
    align: string | null;
    indent_left_chars?: number;
  };
  total_occurrences: number;
  candidate_role_hints: CandidateHint[];
  examples: ExampleParagraph[];
}

interface ASTBlock {
  block_id: string;
  block_type: string;
  text?: string;
  line_start: number;
  line_end: number;
  support: "native" | "degraded" | "rejected";
}

interface Diagnostic {
  severity: "info" | "warning" | "error";
  message: string;
  line_start?: number;
  line_end?: number;
  block_id?: string;
}

interface ChangedFile {
  path: string;
  status: "added" | "removed" | "changed";
  before_size: number;
  after_size: number;
  delta?: number;
}

interface ParagraphChange {
  paragraph_index: number;
  before: string;
  after: string;
  contains_marker?: boolean;
}

export default function Home() {
  // Global context states
  const [activeFile, setActiveFile] = useState<string>("");
  const [docxPath, setDocxPath] = useState<string>("");
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [workflowState, setWorkflowState] = useState<"style_review" | "md_draft" | "word_editing">("style_review");
  const [styleApproved, setStyleApproved] = useState<boolean>(false);
  const [draftApproved, setDraftApproved] = useState<boolean>(false);

  // Streaming WebSocket states
  const [messages, setMessages] = useState<Message[]>([]);
  const [reasoningStream, setReasoningStream] = useState<string>("");
  const [contentStream, setContentStream] = useState<string>("");
  const [toolLogs, setToolLogs] = useState<ToolLog[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isWaitingApproval, setIsWaitingApproval] = useState<boolean>(false);
  const [approvalPhase, setApprovalPhase] = useState<"style_review" | "md_draft" | "word_editing" | null>(null);

  // Extracted layout visual data states
  const [styleSamples, setStyleSamples] = useState<StyleSample[]>([]);
  const [styleMapping, setStyleMapping] = useState<Record<string, string>>({
    paragraph: "S001",
    heading1: "S002",
    heading2: "S003",
    heading3: "S004",
    list_item: "S001",
    table_cell: "S001",
    code_block: "S001",
    formula: "S001",
  });
  const [markdownContent, setMarkdownContent] = useState<string>("");
  const [astBlocks, setAstBlocks] = useState<ASTBlock[]>([]);
  const [diagnostics, setDiagnostics] = useState<Diagnostic[]>([]);
  const [changedFiles, setChangedFiles] = useState<ChangedFile[]>([]);
  const [paragraphChanges, setParagraphChanges] = useState<ParagraphChange[]>([]);
  const [finalDocxPath, setFinalDocxPath] = useState<string>("");

  const wsRef = useRef<WebSocket | null>(null);

  // Initialize or reset variables
  const resetWorkspace = () => {
    setActiveFile("");
    setDocxPath("");
    setWorkflowState("style_review");
    setStyleApproved(false);
    setDraftApproved(false);
    setMessages([]);
    setReasoningStream("");
    setContentStream("");
    setToolLogs([]);
    setStyleSamples([]);
    setMarkdownContent("");
    setAstBlocks([]);
    setDiagnostics([]);
    setChangedFiles([]);
    setParagraphChanges([]);
    setFinalDocxPath("");
    setIsWaitingApproval(false);
    setApprovalPhase(null);
    if (wsRef.current) {
      wsRef.current.close();
    }
  };

  // Connect to Python Agent WebSocket
  const startAgentSession = (initialPrompt: string, path: string) => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    const socket = new WebSocket("ws://127.0.0.1:8000/api/ws/agent");
    wsRef.current = socket;

    socket.onopen = () => {
      setIsConnected(true);
      // Send initial trigger payload
      socket.send(
        JSON.stringify({
          type: "start",
          prompt: initialPrompt,
          docx_path: path,
        })
      );
      // Append initial prompt to chat message window
      setMessages([{ role: "user", content: initialPrompt }]);
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case "round_start":
          setWorkflowState(data.workflow_state);
          setReasoningStream("");
          setContentStream("");
          break;

        case "reasoning":
          setReasoningStream((prev) => prev + data.delta);
          break;

        case "content":
          setContentStream((prev) => prev + data.delta);
          break;

        case "tool_start":
          const newLog: ToolLog = {
            id: Math.random().toString(36).substring(7),
            name: data.name,
            arguments: data.arguments,
            status: "running",
          };
          setToolLogs((prev) => [...prev, newLog]);
          break;

        case "tool_end":
          setToolLogs((prev) =>
            prev.map((log) => {
              if (log.name === data.name && log.status === "running") {
                // Parse results dynamically to update UI features
                try {
                  const resultObj = JSON.parse(data.result);
                  if (data.name === "parse_markdown_draft" && resultObj.status === "ok") {
                    if (resultObj.blocks) setAstBlocks(resultObj.blocks);
                    if (resultObj.diagnostics) setDiagnostics(resultObj.diagnostics);
                  } else if (data.name === "write_markdown_draft" && resultObj.status === "ok") {
                    // Extract draft text from tool arguments if present
                    try {
                      const argsObj = JSON.parse(log.arguments);
                      if (argsObj.text) setMarkdownContent(argsObj.text);
                    } catch {}
                  } else if (data.name === "diff_docx" && resultObj.status === "ok") {
                    if (resultObj.changed_files) setChangedFiles(resultObj.changed_files);
                    if (resultObj.paragraph_changes) setParagraphChanges(resultObj.paragraph_changes);
                  } else if (data.name === "markdown_to_word" && resultObj.status === "ok") {
                    if (resultObj.output_path) setFinalDocxPath(resultObj.output_path);
                  }
                } catch (e) {
                  console.error("Failed to parse tool result JSON payload", e);
                }

                return {
                  ...log,
                  status: data.result.includes('"status": "error"') ? "error" : "success",
                  result: data.result,
                };
              }
              return log;
            })
          );
          break;

        case "wait_approval":
          // Flush the streaming content to messages history
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: data.content,
              reasoning_content: reasoningStream || undefined,
            },
          ]);
          setReasoningStream("");
          setContentStream("");
          setApprovalPhase(data.phase);
          setIsWaitingApproval(true);
          break;

        case "done":
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: data.content,
              reasoning_content: reasoningStream || undefined,
            },
          ]);
          setReasoningStream("");
          setContentStream("");
          setIsWaitingApproval(false);
          setApprovalPhase(null);
          break;

        case "error":
          alert(`Agent 运行报错: ${data.message}`);
          break;
      }
    };

    socket.onclose = () => {
      setIsConnected(false);
    };

    socket.onerror = (err) => {
      console.error("WebSocket error", err);
      setIsConnected(false);
    };
  };

  const handleSendPrompt = (prompt: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    if (isWaitingApproval) return; // Wait for approval checkpoint buttons instead

    setMessages((prev) => [...prev, { role: "user", content: prompt }]);
    wsRef.current.send(JSON.stringify({ type: "continue", prompt }));
  };

  const handleApprove = (approved: boolean, feedback?: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    wsRef.current.send(
      JSON.stringify({
        type: "approve",
        approved,
        feedback: feedback || "",
      })
    );

    setIsWaitingApproval(false);

    if (approved) {
      if (approvalPhase === "style_review") {
        setStyleApproved(true);
        setWorkflowState("md_draft");
      } else if (approvalPhase === "md_draft") {
        setDraftApproved(true);
        setWorkflowState("word_editing");
      }
    }
    setApprovalPhase(null);
  };

  // Style Mapping Gallery Callback
  const handleMappingChange = (markdownType: string, sampleId: string) => {
    setStyleMapping((prev) => ({
      ...prev,
      [markdownType]: sampleId,
    }));
  };

  // Upload DOCX Template API
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const file = files[0];
    setIsUploading(true);
    resetWorkspace();

    const formData = new FormData();
    formData.append("file", file);

    try {
      // 1. Upload file to REST server
      const uploadRes = await fetch("http://127.0.0.1:8000/api/upload", {
        method: "POST",
        body: formData,
      });

      if (!uploadRes.ok) {
        throw new Error("上传失败，请确保 FastAPI 后端服务已启动并在 8000 端口运行。");
      }

      const uploadData = await uploadRes.json();
      const path = uploadData.absolute_path;

      setActiveFile(file.name);
      setDocxPath(path);

      // 2. Perform layout style extraction
      const styleRes = await fetch("http://127.0.0.1:8000/api/style/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ docx_path: path }),
      });

      if (styleRes.ok) {
        const styleData = await styleRes.json();
        if (styleData.style_samples) {
          setStyleSamples(styleData.style_samples);
        }
      }

      // 3. Launch Agent websocket interaction
      const initialPrompt = `把 ${file.name} 进行样式审核与文档结构分析，提炼出排版属性标签`;
      startAgentSession(initialPrompt, path);
    } catch (err: any) {
      alert(err.message || "上传文件过程中发生错误");
    } finally {
      setIsUploading(false);
    }
  };

  // Local Monaco content modifications trigger manual parsing
  const handleContentChange = (content: string) => {
    setMarkdownContent(content);
  };

  const handleTriggerParse = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8000/api/draft/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ markdown_content: markdownContent }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.blocks) setAstBlocks(data.blocks);
        if (data.diagnostics) setDiagnostics(data.diagnostics);
      }
    } catch (e) {
      console.error("Failed to parse draft manually", e);
    }
  };

  // Download Output docx
  const handleDownload = () => {
    if (!finalDocxPath) return;
    window.open(`http://127.0.0.1:8000/api/download?path=${encodeURIComponent(finalDocxPath)}`, "_blank");
  };

  return (
    <div className="w-full h-screen flex flex-col bg-background text-foreground overflow-hidden">
      {/* Workflow Progress Bar */}
      <WorkflowProgress
        currentState={workflowState}
        styleApproved={styleApproved}
        draftApproved={draftApproved}
      />

      {/* Main Area divided into: Left (Console) and Right (Workspace) */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Side Column: Interactive Chat and Logging console (1/3 weight) */}
        <div className="w-80 lg:w-[380px] h-full shrink-0">
          <ChatPanel
            messages={messages}
            reasoningStream={reasoningStream}
            contentStream={contentStream}
            toolLogs={toolLogs}
            isWaitingApproval={isWaitingApproval}
            approvalPhase={approvalPhase}
            onSendPrompt={handleSendPrompt}
            onApprove={handleApprove}
            isConnected={isConnected}
          />
        </div>

        {/* Right Side Column: Multi-tab workspace depending on state (2/3 weight) */}
        <div className="flex-1 h-full overflow-hidden bg-muted-bg/15">
          {!docxPath ? (
            /* Upload File Initial State Layout */
            <div className="w-full h-full flex flex-col items-center justify-center p-6 text-center select-none">
              <div className="border-2 border-dashed border-border hover:border-accent bg-card rounded-md max-w-md w-full p-8 transition-colors flex flex-col items-center justify-center space-y-4">
                <div className="w-12 h-12 rounded-full bg-muted-bg flex items-center justify-center text-muted">
                  {isUploading ? (
                    <RefreshCw className="w-6 h-6 animate-spin text-accent" />
                  ) : (
                    <Upload className="w-6 h-6" />
                  )}
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-foreground">
                    {isUploading ? "正在分析排版模板中..." : "载入 Word 文档模板开始排版"}
                  </h3>
                  <p className="text-xs text-muted mt-1 leading-relaxed">
                    拖拽或点击上传带有排版样式的 `.docx` 模板文档，Agent 会自动启动三阶段状态机编译工作流。
                  </p>
                </div>
                {!isUploading && (
                  <label className="px-4 py-1.5 bg-accent hover:bg-accent-hover text-white text-xs font-semibold rounded cursor-pointer transition-colors shadow-sm inline-block">
                    选择文件
                    <input
                      type="file"
                      accept=".docx,.docm"
                      className="hidden"
                      onChange={handleFileUpload}
                    />
                  </label>
                )}
              </div>
            </div>
          ) : (
            /* Dynamic workspace panels active per phase */
            <div className="w-full h-full">
              {workflowState === "style_review" && (
                <StyleGallery
                  styleSamples={styleSamples}
                  styleMapping={styleMapping}
                  onMappingChange={handleMappingChange}
                />
              )}

              {workflowState === "md_draft" && (
                <EditorPanel
                  markdownContent={markdownContent}
                  onContentChange={handleContentChange}
                  astBlocks={astBlocks}
                  diagnostics={diagnostics}
                  onTriggerParse={handleTriggerParse}
                />
              )}

              {workflowState === "word_editing" && (
                <DiffViewer
                  changedFiles={changedFiles}
                  paragraphChanges={paragraphChanges}
                  finalDocxPath={finalDocxPath}
                  onDownload={handleDownload}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
