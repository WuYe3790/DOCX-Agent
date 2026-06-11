"use client";

import { useState, useRef, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FolderUp,
  X,
  Upload,
  FileText,
  Trash2,
  Check,
  Folder,
  FolderOpen,
  ChevronRight,
  ChevronDown
} from "lucide-react";

export interface WorkspaceFile {
  name: string;
  path: string;  // 相对 workspace 的正斜杠路径
  size: number;
  mtime: number;
}

export interface FileNode {
  name: string;
  path: string;  // 相对 workspace 的完整 POSIX 路径
  type: "file" | "directory";
  children?: FileNode[];
  size?: number;
  mtime?: number;
}

interface WorkspacePanelProps {
  show: boolean;
  files: WorkspaceFile[];
  activeDocxName: string | null;
  isUploading: boolean;
  onSelectDocx: (name: string) => void;
  onUpload: (file: File) => Promise<void>;
  onDelete: (name: string) => Promise<void>;
  onClose: () => void;
}

/**
 * 递归构建目录树
 */
function buildFileTree(files: WorkspaceFile[]): FileNode[] {
  const root: FileNode[] = [];

  files.forEach((file) => {
    const parts = file.path.split("/");
    let currentLevel = root;

    parts.forEach((part, index) => {
      const isLast = index === parts.length - 1;
      const pathSoFar = parts.slice(0, index + 1).join("/");

      let existingNode = currentLevel.find((node) => node.name === part);

      if (!existingNode) {
        existingNode = {
          name: part,
          path: pathSoFar,
          type: isLast ? "file" : "directory",
          children: isLast ? undefined : [],
        };
        if (isLast) {
          existingNode.size = file.size;
          existingNode.mtime = file.mtime;
        }
        currentLevel.push(existingNode);
      }

      if (existingNode.children) {
        currentLevel = existingNode.children;
      }
    });
  });

  // 文件夹排在前面，文件排在后面，按名称排序
  const sortTree = (nodes: FileNode[]) => {
    nodes.sort((a, b) => {
      if (a.type !== b.type) {
        return a.type === "directory" ? -1 : 1;
      }
      return a.name.localeCompare(b.name);
    });
    nodes.forEach((node) => {
      if (node.children) {
        sortTree(node.children);
      }
    });
  };

  sortTree(root);
  return root;
}

/**
 * 侧边栏文件工作区面板 (VS Code 树形管理器风格)
 */
export default function WorkspacePanel({
  show,
  files,
  activeDocxName,
  isUploading,
  onSelectDocx,
  onUpload,
  onDelete,
  onClose,
}: WorkspacePanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());

  const fileTree = useMemo(() => buildFileTree(files), [files]);

  const handleUploadClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInput = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      e.target.value = "";
      try {
        await onUpload(file);
      } catch (err) {
        console.warn("upload failed:", err);
      }
    },
    [onUpload],
  );

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files?.[0];
      if (!file) return;
      try {
        await onUpload(file);
      } catch (err) {
        console.warn("upload failed:", err);
      }
    },
    [onUpload],
  );

  const handleDeleteClick = useCallback(
    (name: string) => {
      if (confirmDelete === name) {
        setConfirmDelete(null);
        void onDelete(name);
      } else {
        setConfirmDelete(name);
        setTimeout(() => setConfirmDelete(null), 5000);
      }
    },
    [confirmDelete, onDelete],
  );

  const toggleFolder = useCallback((path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  // 递归渲染树形目录项
  const renderNode = (node: FileNode, level: number = 0) => {
    const isDir = node.type === "directory";
    const isExpanded = expandedPaths.has(node.path);

    if (isDir) {
      return (
        <div key={node.path} className="space-y-0.5">
          {/* 文件夹行 */}
          <div
            onClick={() => toggleFolder(node.path)}
            className="group flex items-center gap-1.5 py-1 px-2 rounded hover:bg-slate-100/70 dark:hover:bg-zinc-800/40 border border-transparent cursor-pointer transition-colors select-none"
            style={{ paddingLeft: `${Math.max(4, level * 14 + 4)}px` }}
          >
            <span className="text-slate-400 dark:text-zinc-500 shrink-0">
              {isExpanded ? (
                <ChevronDown className="w-3.5 h-3.5" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5" />
              )}
            </span>
            <span className="text-indigo-400 dark:text-indigo-500 shrink-0">
              {isExpanded ? (
                <FolderOpen className="w-4 h-4" />
              ) : (
                <Folder className="w-4 h-4" />
              )}
            </span>
            <span className="text-[12.5px] font-mono text-slate-700 dark:text-zinc-300 truncate">
              {node.name}
            </span>
          </div>

          {/* 子文件夹/文件列表 */}
          {isExpanded && node.children && (
            <div className="space-y-0.5">
              {node.children.map((child) => renderNode(child, level + 1))}
            </div>
          )}
        </div>
      );
    }

    // 文件行
    const isActive = activeDocxName === node.name;
    const isConfirming = confirmDelete === node.name;
    const isDocx = node.name.toLowerCase().endsWith(".docx");

    return (
      <div
        key={node.path}
        className={`group flex items-center gap-2.5 px-2 py-1.5 rounded transition-all ${
          isActive
            ? "bg-indigo-50/70 dark:bg-indigo-950/20 border border-indigo-200/50 dark:border-indigo-800/40"
            : "hover:bg-slate-100/70 dark:hover:bg-zinc-800/40 border border-transparent"
        }`}
        style={{ paddingLeft: `${Math.max(8, level * 14 + 18)}px` }}
      >
        {/* radio 选 active docx (仅 .docx 启用) */}
        <button
          onClick={() => onSelectDocx(node.name)}
          disabled={!isDocx}
          className={`shrink-0 w-3.5 h-3.5 rounded-full border flex items-center justify-center transition-colors ${
            isActive
              ? "border-indigo-500 bg-indigo-500 text-white"
              : isDocx
              ? "border-slate-300 dark:border-zinc-600 hover:border-indigo-400 cursor-pointer"
              : "border-slate-200 dark:border-zinc-700 opacity-20 cursor-not-allowed"
          }`}
          aria-label={`选中 ${node.name} 为主文档`}
          title={isDocx ? "设为主文档" : "非 .docx 文件"}
        >
          {isActive && <Check className="w-2.5 h-2.5 text-white stroke-[3px]" />}
        </button>
        <FileText className="w-3.5 h-3.5 text-slate-400 dark:text-zinc-500 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-[12.5px] font-mono text-slate-800 dark:text-zinc-200 truncate" title={node.path}>
            {node.name}
          </div>
        </div>
        <div className="text-[10px] text-slate-400 dark:text-zinc-500 font-mono shrink-0 select-none opacity-60 group-hover:opacity-0 group-hover:w-0 transition-all overflow-hidden">
          {node.size !== undefined ? (node.size / 1024).toFixed(1) : 0} KB
        </div>
        <button
          onClick={() => handleDeleteClick(node.name)}
          className={`shrink-0 p-1 rounded transition-colors hidden group-hover:flex ${
            isConfirming
              ? "bg-rose-500 text-white hover:bg-rose-600"
              : "text-slate-400 dark:text-zinc-500 hover:bg-rose-50 dark:hover:bg-rose-950/20 hover:text-rose-500"
          }`}
          aria-label={isConfirming ? "再次点击确认删除" : "删除"}
          title={isConfirming ? "再次点击确认删除" : "删除"}
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  };

  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.div
          key="workspace-panel"
          initial={{ width: 0 }}
          animate={{ width: "50%" }}
          exit={{ width: 0 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className="h-full shrink-0 border-l border-slate-200/60 dark:border-zinc-800/60 bg-white/70 dark:bg-zinc-900/70 backdrop-blur-md shadow-2xl overflow-hidden"
        >
          <div className="h-full flex flex-col">
            {/* Header */}
            <div className="h-14 px-4 flex items-center justify-between border-b border-slate-200/60 dark:border-zinc-800/60 shrink-0 bg-white/40 dark:bg-zinc-900/40">
              <div className="flex items-center gap-2">
                <FolderUp className="w-4 h-4 text-indigo-400 dark:text-indigo-500" />
                <span className="text-xs font-mono font-semibold text-slate-700 dark:text-zinc-200 uppercase tracking-wider">
                  文件工作区
                </span>
                {files.length > 0 && (
                  <span className="text-[10px] font-mono text-slate-400 dark:text-zinc-500 ml-1">
                    ({files.length} 个文件)
                  </span>
                )}
              </div>
              <button
                onClick={onClose}
                className="p-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors text-slate-500 dark:text-zinc-400 hover:text-slate-700 dark:hover:text-zinc-200"
                aria-label="关闭文件工作区"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* 上传按钮栏 (始终可见) */}
            <div className="px-4 py-3 border-b border-slate-200/60 dark:border-zinc-800/60 flex items-center gap-2">
              <button
                onClick={handleUploadClick}
                disabled={isUploading}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono font-semibold border border-indigo-200 dark:border-indigo-800 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded transition-colors cursor-pointer text-indigo-600 dark:text-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Upload className="w-3.5 h-3.5" />
                {isUploading ? "上传中..." : "上传文件"}
              </button>
              <span className="text-[10px] font-mono text-slate-400 dark:text-zinc-500">
                支持 .docx / .pdf / .png / .zip 等
              </span>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={handleFileInput}
                accept=".docx,.doc,.md,.txt,.png,.jpg,.jpeg,.gif,.webp,.json,.xml,.zip"
              />
            </div>

            {/* 主体: 空态 (drop zone) OR 文件列表树 */}
            <div className="flex-1 overflow-y-auto p-3">
              {files.length === 0 ? (
                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(true);
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={handleDrop}
                  className={`h-full flex flex-col items-center justify-center border-2 border-dashed rounded-lg transition-colors ${
                    dragOver
                      ? "border-indigo-400 bg-indigo-50/30 dark:bg-indigo-900/20"
                      : "border-slate-300 dark:border-zinc-700"
                  }`}
                >
                  <FolderUp className="w-12 h-12 mb-3 text-slate-300 dark:text-zinc-600" />
                  <p className="text-sm font-medium text-slate-500 dark:text-zinc-400">
                    拖拽文件到此处
                  </p>
                  <p className="text-xs mt-1 text-slate-400 dark:text-zinc-500">
                    或点击上方"上传文件"按钮
                  </p>
                  <p className="text-[10px] mt-4 text-slate-400/70 dark:text-zinc-500/70 font-mono">
                    .zip 上传后自动解压到子目录
                  </p>
                </div>
              ) : (
                <div className="space-y-0.5">
                  {fileTree.map((node) => renderNode(node, 0))}
                </div>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

