"use client";

import React, { useState, useRef, useEffect } from "react";
import dynamic from "next/dynamic";
import type { Monaco } from "@monaco-editor/react";
import { Play, FileCode, CheckCircle, AlertTriangle, XCircle, ArrowRight, Eye, Code } from "lucide-react";
import MarkdownRenderer from "./markdown-renderer";

const Editor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full flex items-center justify-center text-xs text-muted font-mono bg-card border border-border">
      加载编辑器中...
    </div>
  ),
});

interface Diagnostic {
  severity: "info" | "warning" | "error";
  message: string;
  line_start?: number;
  line_end?: number;
  block_id?: string;
}

interface ASTBlock {
  block_id: string;
  block_type: string;
  text?: string;
  line_start: number;
  line_end: number;
  support: "native" | "degraded" | "rejected";
  diagnostics?: Diagnostic[];
}

interface EditorPanelProps {
  markdownContent: string;
  onContentChange: (content: string) => void;
  astBlocks: ASTBlock[];
  diagnostics: Diagnostic[];
  onTriggerParse: () => void;
}

export default function EditorPanel({
  markdownContent,
  onContentChange,
  astBlocks,
  diagnostics,
  onTriggerParse,
}: EditorPanelProps) {
  const [viewMode, setViewMode] = useState<"split" | "edit" | "preview">("split");
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const editorRef = useRef<any>(null);
  const monacoRef = useRef<Monaco | null>(null);

  const handleEditorDidMount = (editor: any, monaco: Monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;

    // Apply editor options
    editor.updateOptions({
      minimap: { enabled: false },
      fontSize: 12,
      fontFamily: "var(--font-geist-mono), monospace",
      lineNumbers: "on",
      roundedSelection: false,
      scrollBeyondLastLine: false,
      automaticLayout: true,
      cursorStyle: "line",
      lineHeight: 18,
    });
  };

  // Sync AST compile diagnostics to Monaco inline markers
  useEffect(() => {
    if (!editorRef.current || !monacoRef.current) return;
    const monaco = monacoRef.current;
    const model = editorRef.current.getModel();
    if (!model) return;

    const markers = diagnostics.map((d) => ({
      severity:
        d.severity === "error"
          ? monaco.MarkerSeverity.Error
          : d.severity === "warning"
          ? monaco.MarkerSeverity.Warning
          : monaco.MarkerSeverity.Info,
      message: d.message,
      startLineNumber: d.line_start || 1,
      endLineNumber: d.line_end || d.line_start || 1,
      startColumn: 1,
      endColumn: 100,
    }));

    monaco.editor.setModelMarkers(model, "docx-compiler", markers);
  }, [diagnostics]);

  const scrollToLine = (line: number) => {
    if (editorRef.current) {
      editorRef.current.revealLineInCenter(line);
      editorRef.current.setPosition({ lineNumber: line, column: 1 });
      editorRef.current.focus();
    }
  };

  const supportColors = {
    native: "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400",
    degraded: "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400",
    rejected: "bg-red-500/10 border-red-500/30 text-red-600 dark:text-red-400",
  };

  const supportLabels = {
    native: "原生支持",
    degraded: "降级支持",
    rejected: "不支持",
  };

  return (
    <div className="w-full h-full flex flex-col bg-card select-none">
      {/* Editor Header Toolbar */}
      <div className="h-10 border-b border-border flex items-center justify-between px-4 bg-muted-bg/50">
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-foreground tracking-wide uppercase flex items-center gap-1.5">
            <FileCode className="w-3.5 h-3.5 text-muted" /> 草稿编辑器 & 预览
          </span>
          <button
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className="text-[10px] text-muted border border-border bg-card px-1.5 py-0.5 rounded hover:bg-muted-bg cursor-pointer transition-colors"
          >
            {isSidebarOpen ? "隐藏 AST 大纲" : "显示 AST 大纲"}
          </button>
        </div>

        {/* View mode buttons */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setViewMode("edit")}
            className={`px-2.5 py-0.5 text-[10px] font-medium border rounded cursor-pointer transition-all ${
              viewMode === "edit"
                ? "bg-accent border-accent text-white"
                : "bg-card border-border text-foreground hover:bg-muted-bg"
            }`}
          >
            <span className="flex items-center gap-1"><Code className="w-3 h-3" /> 编辑</span>
          </button>
          <button
            onClick={() => setViewMode("split")}
            className={`px-2.5 py-0.5 text-[10px] font-medium border rounded cursor-pointer transition-all ${
              viewMode === "split"
                ? "bg-accent border-accent text-white"
                : "bg-card border-border text-foreground hover:bg-muted-bg"
            }`}
          >
            <span>双栏分屏</span>
          </button>
          <button
            onClick={() => setViewMode("preview")}
            className={`px-2.5 py-0.5 text-[10px] font-medium border rounded cursor-pointer transition-all ${
              viewMode === "preview"
                ? "bg-accent border-accent text-white"
                : "bg-card border-border text-foreground hover:bg-muted-bg"
            }`}
          >
            <span className="flex items-center gap-1"><Eye className="w-3 h-3" /> 预览</span>
          </button>
          <button
            onClick={onTriggerParse}
            className="ml-2 px-2.5 py-0.5 text-[10px] font-semibold bg-emerald-500 border border-emerald-600 text-white rounded cursor-pointer hover:bg-emerald-600 flex items-center gap-1 transition-all"
          >
            <Play className="w-2.5 h-2.5 fill-current" /> 重新解析
          </button>
        </div>
      </div>

      {/* Main Workspace Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar AST tree */}
        {isSidebarOpen && (
          <div className="w-[200px] border-r border-border bg-muted-bg/30 flex flex-col">
            <div className="p-2 border-b border-border text-[9px] font-semibold text-muted tracking-wider uppercase bg-muted-bg/50">
              AST 语法结构树
            </div>
            <div className="flex-1 overflow-y-auto p-1.5 space-y-1.5 font-mono text-[10px]">
              {astBlocks.length === 0 ? (
                <p className="text-muted/50 italic p-2">未解析出 AST 块...</p>
              ) : (
                astBlocks.map((block) => (
                  <button
                    key={block.block_id}
                    onClick={() => scrollToLine(block.line_start)}
                    className="w-full text-left p-1.5 border border-border bg-card rounded hover:border-accent hover:bg-muted-bg/50 transition-all flex flex-col space-y-1 group"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-foreground group-hover:text-accent">
                        {block.block_id}
                      </span>
                      <span
                        className={`px-1 rounded-sm text-[8px] font-sans border ${
                          supportColors[block.support]
                        }`}
                      >
                        {supportLabels[block.support]}
                      </span>
                    </div>
                    <span className="text-foreground/70 font-semibold truncate block">
                      {block.block_type}
                    </span>
                    <span className="text-muted/50 text-[9px] block">
                      行 {block.line_start} - {block.line_end}
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        )}

        {/* Editor and Preview Split Area */}
        <div className="flex-1 flex overflow-hidden">
          {/* Monaco Editor Pane */}
          {(viewMode === "split" || viewMode === "edit") && (
            <div className="flex-1 h-full flex flex-col relative">
              <Editor
                height="100%"
                defaultLanguage="markdown"
                value={markdownContent}
                onChange={(val) => onContentChange(val || "")}
                onMount={handleEditorDidMount}
                theme="vs" // vs-dark in dark mode if configured
              />
            </div>
          )}

          {/* Markdown HTML Live Preview Pane */}
          {(viewMode === "split" || viewMode === "preview") && (
            <div className="flex-1 h-full overflow-y-auto p-6 bg-card border-l border-border select-text">
              <MarkdownRenderer content={markdownContent} />
            </div>
          )}
        </div>
      </div>

      {/* Compiler Diagnostics List at the Bottom */}
      {diagnostics.length > 0 && (
        <div className="border-t border-border bg-red-500/5 select-text">
          <div className="px-4 py-1.5 border-b border-border bg-red-500/10 flex items-center gap-1.5 text-red-600 dark:text-red-400">
            <AlertTriangle className="w-3.5 h-3.5" />
            <span className="text-[10px] font-bold tracking-wide uppercase">
              编译器语义诊断警告 ({diagnostics.length})
            </span>
          </div>
          <div className="max-h-20 overflow-y-auto px-4 py-1.5 space-y-1 font-mono text-[10px]">
            {diagnostics.map((diag, index) => (
              <button
                key={index}
                onClick={() => diag.line_start && scrollToLine(diag.line_start)}
                className="w-full text-left hover:text-red-500 flex items-start gap-2 py-0.5"
              >
                <span className="text-red-500 font-bold shrink-0">
                  {diag.severity === "error" ? <XCircle className="w-3 h-3 mt-0.5" /> : <AlertTriangle className="w-3 h-3 mt-0.5" />}
                </span>
                <span className="text-muted font-bold shrink-0">{`[行 ${diag.line_start || "?"}]`}</span>
                <span className="text-foreground shrink-0">{`(${diag.block_id || "通用"})`}</span>
                <span className="text-foreground/80 flex-1 truncate">{diag.message}</span>
                <ArrowRight className="w-3 h-3 text-muted/30 mt-0.5 shrink-0" />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
