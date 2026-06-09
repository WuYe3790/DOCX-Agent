"use client";

import { CheckCircle2 } from "lucide-react";

interface ApprovalCheckpointProps {
  isWaitingApproval: boolean;
  approvalPhase: "style_review" | "md_draft" | "word_editing" | null;
  isConnected: boolean;
  feedbackValue: string;
  onChangeFeedback: (value: string) => void;
  onApprove: () => void;
  onReject: () => void;
}

// === ApprovalCheckpoint: 审批等待 UI ===
// 包含 CheckCircle2 + 文案 + 同意按钮 + 反馈输入框
// feedbackValue 由 page 持有 (避免组件内 state 撕裂数据流)
export default function ApprovalCheckpoint({
  isWaitingApproval,
  approvalPhase,
  isConnected,
  feedbackValue,
  onChangeFeedback,
  onApprove,
  onReject,
}: ApprovalCheckpointProps) {
  if (!isWaitingApproval) return null;

  return (
    <div className="mb-8 space-y-3">
      <div className="flex items-center gap-2">
        <CheckCircle2 className="w-3.5 h-3.5 text-indigo-400 dark:text-indigo-500 shrink-0" />
        <p className="text-xs text-slate-500 dark:text-zinc-400 leading-relaxed">
          {approvalPhase === "style_review"
            ? "样式已提取完毕，请确认后进入草稿拟定阶段；如需修改请输入反馈"
            : "草稿已生成，请确认后启动编译写入；若需调整请提交反馈"}
        </p>
      </div>

      <div className="flex flex-row items-center gap-3">
        <button
          onClick={onApprove}
          disabled={!isConnected}
          className="w-fit px-5 py-2 bg-indigo-500/10 hover:bg-indigo-500/20 disabled:bg-slate-100/60 dark:disabled:bg-zinc-800/60 disabled:text-slate-400 text-indigo-600 dark:text-indigo-400 text-[12px] font-medium rounded-full border border-indigo-500/20 hover:border-indigo-500/30 shadow-sm hover:shadow-md transition-all duration-150 flex items-center justify-center cursor-pointer shrink-0"
        >
          {isConnected ? "同意并进入下一阶段" : "已断开连接"}
        </button>

        <div className="flex-1 flex items-center gap-2 bg-slate-50/60 dark:bg-zinc-900/40 border border-slate-200/50 dark:border-zinc-700/50 rounded-full px-4 py-1.5">
          <input
            type="text"
            placeholder={isConnected ? "输入修改建议..." : ""}
            value={feedbackValue}
            onChange={(e) => onChangeFeedback(e.target.value)}
            disabled={!isConnected}
            className="flex-1 bg-transparent text-xs text-slate-600 dark:text-zinc-300 border-0 outline-0 focus:ring-0 select-text disabled:text-slate-400 placeholder:text-slate-400/60 dark:placeholder:text-zinc-600"
          />
          <button
            onClick={onReject}
            disabled={!feedbackValue.trim() || !isConnected}
            className={`shrink-0 text-[11px] font-medium px-3 py-1 rounded-full transition-all duration-150 cursor-pointer ${
              feedbackValue.trim() && isConnected
                ? "text-rose-500 hover:text-rose-600"
                : "text-slate-400 dark:text-zinc-600"
            } disabled:text-slate-300 dark:disabled:text-zinc-700 disabled:cursor-not-allowed`}
          >
            反馈
          </button>
        </div>
      </div>
    </div>
  );
}
