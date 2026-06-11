"use client";

import { useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FolderUp, X, Upload, FileText, Trash2, Check } from "lucide-react";

export interface WorkspaceFile {
  name: string;
  path: string;  // 相对 workspace 的正斜杠路径
  size: number;
  mtime: number;
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
 * 侧边栏文件工作区面板
 * - show=true 时宽度从 0 平滑展开至 50%; show=false 时收缩回 0
 * - 文件为空时显示 dashed drop zone (拖拽 / 点击上传)
 * - 文件非空时显示文件列表 (radio 选 active docx + trash 删除)
 * - 与 PreviewPanel 互斥显示在右侧 slot
 *
 * Phase 4 实现: 前端 WorkspacePanel — 上传 .docx / 选 active docx / 删除
 * 后端 API 详见 src/workspace/api.py
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

  const handleUploadClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInput = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      // 重置 input value 以便能重复选同一文件
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
      // 第一次点击进入 confirm 状态, 第二次(同 session 内)才真删
      if (confirmDelete === name) {
        setConfirmDelete(null);
        void onDelete(name);
      } else {
        setConfirmDelete(name);
        // 5 秒后自动取消 confirm
        setTimeout(() => setConfirmDelete(null), 5000);
      }
    },
    [confirmDelete, onDelete],
  );

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

            {/* 主体: 空态 (drop zone) OR 文件列表 */}
            <div className="flex-1 overflow-y-auto p-4">
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
                <div className="space-y-1.5">
                  {files.map((file) => {
                    const isActive = activeDocxName === file.name;
                    const isConfirming = confirmDelete === file.name;
                    return (
                      <div
                        key={file.path}
                        className={`group flex items-center gap-3 px-3 py-2 rounded-md transition-colors ${
                          isActive
                            ? "bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800"
                            : "hover:bg-slate-50 dark:hover:bg-zinc-800/50 border border-transparent"
                        }`}
                      >
                        {/* radio 选 active docx (仅 .docx 启用) */}
                        <button
                          onClick={() => onSelectDocx(file.name)}
                          disabled={!file.name.toLowerCase().endsWith(".docx")}
                          className={`shrink-0 w-4 h-4 rounded-full border-2 flex items-center justify-center transition-colors ${
                            isActive
                              ? "border-indigo-500 bg-indigo-500"
                              : file.name.toLowerCase().endsWith(".docx")
                              ? "border-slate-300 dark:border-zinc-600 hover:border-indigo-400 cursor-pointer"
                              : "border-slate-200 dark:border-zinc-700 opacity-40 cursor-not-allowed"
                          }`}
                          aria-label={`选中 ${file.name} 为主文档`}
                          title={file.name.toLowerCase().endsWith(".docx") ? "设为主文档" : "非 .docx 文件, 不可设为主文档"}
                        >
                          {isActive && <Check className="w-2.5 h-2.5 text-white" />}
                        </button>
                        <FileText className="w-4 h-4 text-slate-400 dark:text-zinc-500 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="text-[13px] font-mono truncate" title={file.path}>
                            {file.name}
                          </div>
                          <div className="text-[10px] text-slate-400 dark:text-zinc-500 font-mono">
                            {(file.size / 1024).toFixed(1)} KB
                            {file.path.includes("/") && ` · ${file.path}`}
                          </div>
                        </div>
                        <button
                          onClick={() => handleDeleteClick(file.name)}
                          className={`shrink-0 p-1.5 rounded-md transition-colors ${
                            isConfirming
                              ? "bg-rose-500 text-white"
                              : "text-slate-400 dark:text-zinc-500 hover:bg-rose-50 dark:hover:bg-rose-900/20 hover:text-rose-500"
                          }`}
                          aria-label={isConfirming ? "再次点击确认删除" : "删除文件"}
                          title={isConfirming ? "再次点击确认删除" : "删除"}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
