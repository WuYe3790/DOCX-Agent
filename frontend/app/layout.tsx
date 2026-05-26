import type { Metadata } from "next";
import "./globals.css";
import "katex/dist/katex.min.css"; // CSS for math formula styling

export const metadata: Metadata = {
  title: "DOCX-Agent 智能排版工作站",
  description: "AI 驱动的 Word 文档样式样本提取与 Markdown 编译排版工作站",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      className="h-full antialiased"
    >
      <body className="h-full bg-background text-foreground min-h-full flex flex-col font-sans">
        {children}
      </body>
    </html>
  );
}
