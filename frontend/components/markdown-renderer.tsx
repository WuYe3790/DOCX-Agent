"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

interface MarkdownRendererProps {
  content: string;
  sessionId?: string | null;
}

export default function MarkdownRenderer({ content, sessionId }: MarkdownRendererProps) {
  // Post-process the markdown content to support custom alignment options:
  // e.g., converting "![description|center](path)" syntax to HTML alignments
  const processedContent = React.useMemo(() => {
    if (!content) return "";
    return content;
  }, [content]);

  return (
    <div className="prose-flat select-text">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          img: ({ src, alt }) => {
            if (!src || typeof src !== "string") return null;
            // Parse alignment from alt text, e.g. "alt|left", "alt|right", "alt|center"
            const parts = (alt || "").split("|");
            const imageAlt = parts[0] || "";
            const alignment = parts[1] || "center";

            let alignClass = "mx-auto block"; // default center
            if (alignment === "left") alignClass = "mr-auto block";
            if (alignment === "right") alignClass = "ml-auto block";

            // 如果是本地相对路径且存在 sessionId，重写为后端 API 的文件获取接口路径
            let resolvedSrc = src;
            if (
              !src.startsWith("http://") &&
              !src.startsWith("https://") &&
              !src.startsWith("data:") &&
              sessionId
            ) {
              const cleanSrc = src.startsWith("/") ? src.slice(1) : src;
              // 避免二次编码，且只对文件名段进行编码，保留路径中的斜杠 '/'
              const decodedSrc = decodeURIComponent(cleanSrc);
              const encodedPath = decodedSrc
                .split("/")
                .map((segment) => encodeURIComponent(segment))
                .join("/");
              resolvedSrc = `/api/sessions/${encodeURIComponent(sessionId)}/workspace/file/${encodedPath}`;
            }

            return (
              <span className={`block my-3 ${alignClass}`}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={resolvedSrc}
                  alt={imageAlt}
                  className="rounded border border-border shadow-sm max-h-[400px] object-contain inline-block"
                />
                {imageAlt && (
                  <span className="block text-center text-xs text-muted mt-1">
                    {imageAlt}
                  </span>
                )}
              </span>
            );
          },
        }}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  );
}
