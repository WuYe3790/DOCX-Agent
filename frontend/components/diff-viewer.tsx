"use client";

import React, { useMemo } from "react";
import { FileDiff, ArrowRight, FileArchive, Download } from "lucide-react";

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

interface DiffViewerProps {
  changedFiles: ChangedFile[];
  paragraphChanges: ParagraphChange[];
  finalDocxPath: string;
  onDownload: () => void;
}

// Simple standalone LCS-based character diff algorithm in TypeScript
type DiffToken = {
  type: "added" | "removed" | "equal";
  value: string;
};

function getCharDiff(before: string, after: string): DiffToken[] {
  const bChars = Array.from(before);
  const aChars = Array.from(after);
  const m = bChars.length;
  const n = aChars.length;

  // DP table for LCS
  const dp: number[][] = Array(m + 1)
    .fill(0)
    .map(() => Array(n + 1).fill(0));

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (bChars[i - 1] === aChars[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  // Backtrack to build diff tokens
  const tokens: DiffToken[] = [];
  let i = m,
    j = n;

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && bChars[i - 1] === aChars[j - 1]) {
      tokens.unshift({ type: "equal", value: bChars[i - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      tokens.unshift({ type: "added", value: aChars[j - 1] });
      j--;
    } else {
      tokens.unshift({ type: "removed", value: bChars[i - 1] });
      i--;
    }
  }

  // Merge consecutive tokens of same type to prevent DOM cluttering
  const mergedTokens: DiffToken[] = [];
  for (const t of tokens) {
    const last = mergedTokens[mergedTokens.length - 1];
    if (last && last.type === t.type) {
      last.value += t.value;
    } else {
      mergedTokens.push({ ...t });
    }
  }

  return mergedTokens;
}

export default function DiffViewer({
  changedFiles,
  paragraphChanges,
  finalDocxPath,
  onDownload,
}: DiffViewerProps) {
  // Renders the diffed inline text
  const renderInlineDiff = (before: string, after: string) => {
    const tokens = getCharDiff(before, after);
    return (
      <div className="whitespace-pre-wrap select-text leading-relaxed">
        {tokens.map((token, idx) => {
          if (token.type === "added") {
            return (
              <span
                key={idx}
                className="bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 font-semibold px-0.5 rounded-sm"
              >
                {token.value}
              </span>
            );
          }
          if (token.type === "removed") {
            return (
              <span
                key={idx}
                className="bg-red-100 dark:bg-red-950/40 text-red-700 dark:text-red-400 line-through px-0.5 rounded-sm decoration-red-500/55"
              >
                {token.value}
              </span>
            );
          }
          return <span key={idx}>{token.value}</span>;
        })}
      </div>
    );
  };

  const fileStatusColors = {
    added: "text-emerald-500 border-emerald-500/25 bg-emerald-500/10",
    removed: "text-red-500 border-red-500/25 bg-red-500/10",
    changed: "text-amber-500 border-amber-500/25 bg-amber-500/10",
  };

  const fileStatusLabels = {
    added: "新增",
    removed: "删除",
    changed: "修改",
  };

  return (
    <div className="w-full h-full flex flex-col bg-card select-none">
      {/* Diff View Header */}
      <div className="h-10 border-b border-border flex items-center justify-between px-4 bg-muted-bg/50">
        <span className="text-xs font-semibold text-foreground tracking-wide uppercase flex items-center gap-1.5">
          <FileDiff className="w-3.5 h-3.5 text-muted" /> 文档编译差异对比 (Diff Viewer)
        </span>
        {finalDocxPath && (
          <button
            onClick={onDownload}
            className="px-2.5 py-0.5 text-[10px] font-semibold bg-accent hover:bg-accent-hover text-white rounded cursor-pointer flex items-center gap-1 transition-all"
          >
            <Download className="w-3 h-3" /> 下载最终版 Word
          </button>
        )}
      </div>

      {/* Split Layout Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Side: Zip Container Member Files */}
        <div className="w-[200px] border-r border-border bg-muted-bg/30 flex flex-col shrink-0">
          <div className="p-2 border-b border-border text-[9px] font-semibold text-muted tracking-wider uppercase bg-muted-bg/50 flex items-center gap-1">
            <FileArchive className="w-3.5 h-3.5" /> DOCX ZIP 内部容器树
          </div>
          <div className="flex-1 overflow-y-auto p-1.5 space-y-1.5 font-mono text-[10px]">
            {changedFiles.length === 0 ? (
              <p className="text-muted/50 italic p-2">无内部文件修改...</p>
            ) : (
              changedFiles.map((file, idx) => (
                <div
                  key={idx}
                  className="p-1.5 border border-border bg-card rounded flex flex-col space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <span
                      className={`px-1 rounded-sm text-[8px] font-sans border font-bold ${
                        fileStatusColors[file.status]
                      }`}
                    >
                      {fileStatusLabels[file.status]}
                    </span>
                    {file.delta !== undefined && (
                      <span className="text-[9px] text-muted">
                        {file.delta > 0 ? `+${file.delta}` : file.delta} B
                      </span>
                    )}
                  </div>
                  <span className="text-foreground truncate block font-bold" title={file.path}>
                    {file.path.split("/").pop()}
                  </span>
                  <span className="text-muted/50 text-[8px] block truncate" title={file.path}>
                    {file.path}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Side: Side-by-Side Changed Paragraphs */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 select-text">
          <div className="text-[10px] text-muted border-l-2 border-border pl-2.5 mb-2 leading-relaxed">
            注意：Word 文档编译排版仅针对内容和样式规则进行写入。
            <br />
            下方展示了包含文本和语法块变动的段落（限制前 100 处变更）。
          </div>

          {paragraphChanges.length === 0 ? (
            <div className="border border-border rounded p-8 text-center text-xs text-muted italic">
              编译写入前后未检测到段落内容发生文字变化。
            </div>
          ) : (
            paragraphChanges.map((change) => (
              <div
                key={change.paragraph_index}
                className="border border-border rounded bg-card overflow-hidden flex flex-col"
              >
                {/* Paragraph Row Header */}
                <div className="px-3 py-1.5 bg-muted-bg/40 border-b border-border flex items-center justify-between text-[10px] font-mono">
                  <span className="text-foreground font-bold">段落 #{change.paragraph_index}</span>
                  {change.contains_marker && (
                    <span className="text-[9px] font-sans bg-amber-50 border border-amber-200 text-amber-600 px-1 py-0.25 rounded">
                      包含标识锚点
                    </span>
                  )}
                </div>

                {/* Compare row (Split screen or stacked inline) */}
                <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-border">
                  {/* Before Panel */}
                  <div className="p-3 bg-red-500/2">
                    <p className="text-[9px] text-red-500/70 font-semibold uppercase tracking-wider mb-1 font-mono">修改前 (Before)</p>
                    <p className="text-xs text-foreground/70 whitespace-pre-wrap select-text">
                      {change.before || <span className="text-muted/40 italic">空段落</span>}
                    </p>
                  </div>

                  {/* After Panel with character highlights */}
                  <div className="p-3 bg-emerald-500/2 select-text">
                    <p className="text-[9px] text-emerald-500/70 font-semibold uppercase tracking-wider mb-1 font-mono">修改后 / 变化对比 (After & Diff)</p>
                    <div className="text-xs text-foreground">
                      {change.before !== change.after ? (
                        renderInlineDiff(change.before, change.after)
                      ) : (
                        <p className="whitespace-pre-wrap select-text">{change.after}</p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
