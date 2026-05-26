"use client";

import React from "react";
import { Check, Edit, FileText, Settings } from "lucide-react";

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

interface StyleGalleryProps {
  styleSamples: StyleSample[];
  styleMapping: Record<string, string>;
  onMappingChange: (markdownType: string, sampleId: string) => void;
}

const MARKDOWN_TYPES = [
  { id: "paragraph", label: "正文段落 (Paragraph)" },
  { id: "heading1", label: "一级标题 (Heading 1)" },
  { id: "heading2", label: "二级标题 (Heading 2)" },
  { id: "heading3", label: "三级标题 (Heading 3)" },
  { id: "list_item", label: "列表项目 (List Item)" },
  { id: "table_cell", label: "表格单元格 (Table Cell)" },
  { id: "code_block", label: "代码块 (Code Block)" },
  { id: "formula", label: "公式段落 (Formula)" },
];

export default function StyleGallery({
  styleSamples,
  styleMapping,
  onMappingChange,
}: StyleGalleryProps) {
  return (
    <div className="w-full h-full flex flex-col bg-card select-none">
      {/* Gallery Header */}
      <div className="h-10 border-b border-border flex items-center justify-between px-4 bg-muted-bg/50">
        <span className="text-xs font-semibold text-foreground tracking-wide uppercase flex items-center gap-1.5">
          <Settings className="w-3.5 h-3.5 text-muted" /> 模板格式审核与角色绑定
        </span>
        <span className="text-[10px] text-muted">
          已分析出 {styleSamples.length} 组核心格式样本
        </span>
      </div>

      {/* Main Grid View */}
      <div className="flex-1 overflow-y-auto p-4 grid grid-cols-1 xl:grid-cols-2 gap-4">
        {styleSamples.map((sample) => {
          // Find currently bound markdown types
          const boundTypes = Object.entries(styleMapping)
            .filter(([_, value]) => value === sample.sample_id)
            .map(([key, _]) => MARKDOWN_TYPES.find((t) => t.id === key)?.label || key);

          const fontSizePt = sample.format.font_size_half_points
            ? sample.format.font_size_half_points / 2
            : "默认";

          return (
            <div
              key={sample.sample_id}
              className="border border-border rounded bg-card hover:border-muted hover:shadow-sm transition-all duration-150 p-4 flex flex-col space-y-3"
            >
              {/* Header: Sample ID & Occurrences */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono font-bold bg-muted-bg border border-border px-2 py-0.5 rounded text-foreground">
                    {sample.sample_id}
                  </span>
                  <span className="text-[10px] text-muted font-light">
                    出现 {sample.total_occurrences} 次
                  </span>
                </div>

                {/* Display role tags */}
                <div className="flex flex-wrap gap-1">
                  {boundTypes.map((typeLabel, idx) => (
                    <span
                      key={idx}
                      className="text-[9px] font-semibold bg-indigo-50 border border-indigo-200 dark:bg-indigo-950/40 dark:border-indigo-900/60 text-accent px-1.5 py-0.5 rounded"
                    >
                      {typeLabel.split(" ")[0]}
                    </span>
                  ))}
                </div>
              </div>

              {/* Format characteristics */}
              <div className="grid grid-cols-3 gap-2 bg-muted-bg/30 p-2 rounded text-[10px] text-muted font-mono">
                <div>
                  <span className="block text-[8px] text-muted/60 uppercase">中文字体</span>
                  <span className="font-semibold text-foreground truncate block">
                    {sample.format.font_east_asia || "默认/等线"}
                  </span>
                </div>
                <div>
                  <span className="block text-[8px] text-muted/60 uppercase">西文字体</span>
                  <span className="font-semibold text-foreground truncate block">
                    {sample.format.font_ascii || "默认/Calibri"}
                  </span>
                </div>
                <div>
                  <span className="block text-[8px] text-muted/60 uppercase">字号粗体</span>
                  <span className="font-semibold text-foreground block">
                    {fontSizePt} pt {sample.format.bold ? "• 粗体" : ""}
                  </span>
                </div>
              </div>

              {/* Example Text Block */}
              {sample.examples && sample.examples[0] && (
                <div className="flex-1 flex flex-col justify-between">
                  <div className="border border-border/40 bg-background/50 rounded p-2.5 min-h-[50px] relative">
                    <p
                      className="text-xs text-foreground/80 line-clamp-3 select-text select-text"
                      style={{
                        fontWeight: sample.format.bold ? "bold" : "normal",
                        fontStyle: sample.format.italic ? "italic" : "normal",
                      }}
                    >
                      “{sample.examples[0].text}”
                    </p>
                    <span className="absolute bottom-1 right-2 text-[8px] text-muted/40 font-mono">
                      段落 {sample.examples[0].paragraph_index} | {sample.examples[0].location}
                    </span>
                  </div>
                </div>
              )}

              {/* Binding controller */}
              <div className="pt-2 border-t border-border/50 flex flex-col md:flex-row md:items-center justify-between gap-2">
                <div className="flex items-center gap-1 text-[10px] text-muted">
                  <FileText className="w-3.5 h-3.5" />
                  <span>绑定目标 Markdown 格式：</span>
                </div>

                <div className="flex flex-wrap gap-1">
                  {MARKDOWN_TYPES.map((type) => {
                    const isSelected = styleMapping[type.id] === sample.sample_id;
                    return (
                      <button
                        key={type.id}
                        onClick={() => onMappingChange(type.id, sample.sample_id)}
                        className={`text-[9px] px-2 py-0.5 border rounded cursor-pointer transition-colors ${
                          isSelected
                            ? "bg-accent border-accent text-white"
                            : "bg-background border-border text-foreground hover:bg-muted-bg"
                        }`}
                      >
                        {type.label.split(" ")[0]}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
