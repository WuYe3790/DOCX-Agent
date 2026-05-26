"use client";

import React from "react";
import { Check, Lock, Play } from "lucide-react";

interface WorkflowProgressProps {
  currentState: "style_review" | "md_draft" | "word_editing";
  styleApproved: boolean;
  draftApproved: boolean;
}

export default function WorkflowProgress({
  currentState,
  styleApproved,
  draftApproved,
}: WorkflowProgressProps) {
  const steps = [
    {
      id: "style_review",
      label: "样式审核",
      desc: "提取文档格式与模板特征",
      isCurrent: currentState === "style_review",
      isCompleted: styleApproved || currentState === "md_draft" || currentState === "word_editing",
      isLocked: false,
    },
    {
      id: "md_draft",
      label: "Markdown 草稿",
      desc: "大模型生成与内容微调",
      isCurrent: currentState === "md_draft",
      isCompleted: draftApproved || currentState === "word_editing",
      isLocked: !styleApproved && currentState === "style_review",
    },
    {
      id: "word_editing",
      label: "Word 编译写入",
      desc: "AST 编译、增量写入与 Diff 对比",
      isCurrent: currentState === "word_editing",
      isCompleted: false,
      isLocked: !draftApproved,
    },
  ];

  return (
    <div className="w-full bg-card border-b border-border py-3 px-6 flex items-center justify-between">
      <div className="flex items-center gap-1">
        <span className="text-sm font-semibold tracking-tight text-foreground">
          DOCX-Agent 工作站
        </span>
        <span className="text-xs text-muted border border-border px-1.5 py-0.5 rounded font-mono">
          v1.0.0
        </span>
      </div>

      <div className="flex items-center gap-6 md:gap-12 select-none">
        {steps.map((step, idx) => (
          <React.Fragment key={step.id}>
            {/* Step Element */}
            <div className="flex items-center gap-3">
              {/* Icon Container */}
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center border text-xs transition-colors duration-200 ${
                  step.isCurrent
                    ? "bg-accent border-accent text-white"
                    : step.isCompleted
                    ? "bg-muted-bg border-border text-accent"
                    : "bg-muted-bg border-border text-muted"
                }`}
              >
                {step.isCompleted ? (
                  <Check className="w-3.5 h-3.5" />
                ) : step.isCurrent ? (
                  <Play className="w-3 h-3 fill-current" />
                ) : step.isLocked ? (
                  <Lock className="w-3 h-3" />
                ) : (
                  <span>{idx + 1}</span>
                )}
              </div>

              {/* Text info */}
              <div className="text-left">
                <p
                  className={`text-xs font-semibold ${
                    step.isCurrent
                      ? "text-accent"
                      : step.isLocked
                      ? "text-muted"
                      : "text-foreground"
                  }`}
                >
                  {step.label}
                </p>
                <p className="text-[10px] text-muted hidden md:block">
                  {step.desc}
                </p>
              </div>
            </div>

            {/* Separator arrow */}
            {idx < steps.length - 1 && (
              <span className="text-muted/40 font-mono text-xs hidden md:inline">
                ➔
              </span>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}
