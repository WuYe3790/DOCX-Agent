# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DOCX Agent — AI-driven Word document editor using LLM tool calling + direct OpenXML manipulation. No `python-docx` dependency; operates directly on ZIP-wrapped XML.

## Build Commands

```powershell
# Python backend
pip install -r requirements.txt
python src/server.py                    # Start API + WebSocket server (http://127.0.0.1:8000)
python src/docx_agent_demo.py            # Interactive CLI demo

# Frontend (Next.js)
cd frontend
npm install
npm run dev                             # Development server on localhost:3000
```

## Architecture

### Three-Stage State Machine

LLM uses only tools permitted for the current stage:

```
样式审核 (Style Review) → Markdown 草稿 (MD Draft) → Word 写入编译 (Word Editing)
```

| Stage | Tools |
|-------|-------|
| Style Review | `analyze_docx_style_samples`, `read_docx_structure`, `ls` |
| MD Draft | `write_markdown_draft`, `read_markdown_draft`, `parse_markdown_draft`, `ls`, `read`, `analyze_image_content` |
| Word Editing | All editing tools + `markdown_to_word`, `diff_docx` |

### Core Systems

**Tool Registry** (`src/docx_tools/registry.py`): All 28+ DOCX editing tools registered here. Tools grouped into `basic_tools/`, `md_tools/`, and `docx_tools/` with tool schemas exported via `TOOLS_SCHEMA`.

**Markdown Compiler Pipeline** (`src/docx_compiler/`):
```
Markdown text → markdown-it-py → MarkdownBlock AST → lower → Layout IR → render → OpenXML lxml tree → .docx
```
Key files: `ir.py` (ParagraphIR, TableIR, ImageIR, etc.), `markdown_parser.py` (AST), `lower.py` (AST→IR), `render.py` (IR→OpenXML).

**LLM Adapter** (`src/llm_adapter.py`): Abstract layer supporting DeepSeek (with `thinking`), SenseNova (with `reasoning_effort`), and OpenAI-compatible APIs. Model selection via `config.json` or `LLM_PROVIDER`/`DEEPSEEK_API_KEY` env vars.

**Server** (`src/server.py`): FastAPI + WebSocket for browser-based interactive editing with real-time state machine visualization. All sessions logged to `logs/docx_agent_<timestamp>.log`.

### Key Constraints

- Table operations: `table_index` counts all `//w:tbl` elements including nested tables; verify with `read_docx_structure` (depth, parent coords, `direct_text`) before operating.
- Paragraph operations: must pass both `paragraph_index` and `anchor_text` to prevent misalignment.
- Image analysis: always use `analyze_image_content` for visual content; never infer from filenames.
- Image generation: `generate_image` 工具内部封装了 sub-agent 审核循环 (商汤 vision 模型当审核员), 自动迭代重生直到图片质量合格。子 agent 的 reasoning 完整保留在 session log, 主 LLM 只看到最终路径。Schema 用 size enum (11 种 2K 尺寸) 约束 LLM 避免 400 错误;`max_iterations` 上限 5 防止 WS 假死。
- Large files: use `read` with `offset`/`limit` (max ~500 lines per call).
- Run preservation: when inserting text, prefer preserving original run formatting.

## Directory Structure

```
src/
├── docx_agent_demo.py     # CLI entry point
├── server.py             # FastAPI + WebSocket server
├── llm_adapter.py        # LLM provider abstraction
├── config.json           # API keys and provider config (gitignored)
├── basic_tools/          # ls, read, analyze_image_content, generate_image
│   ├── _media.py        # 共享: 图片下载/编码/消息构造
│   └── ...
├── agents/               # 内部 sub-agent 编排层 (主 agent 看不到)
│   └── image_refiner.py # 生成图审核-重生 sub-agent
├── md_tools/             # Markdown draft and markdown_to_word compiler
├── docx_tools/           # 28+ DOCX editing tools + registry
│   ├── registry.py      # TOOLS_SCHEMA and call_tool
│   ├── common.py        # Shared XML/ZIP utilities
│   ├── diff_docx.py     # XML/text diff
│   └── *.py             # Individual tool implementations
├── docx_compiler/        # Markdown → DOCX compiler
│   ├── ir.py            # Intermediate representation types
│   ├── markdown_parser.py
│   ├── lower.py         # AST → IR lowering + diagnostics
│   ├── render.py        # IR → OpenXML rendering
│   ├── optimizer.py     # XML optimization
│   └── table_ops.py     # Table operations
├── llm_adapter/          # LLM provider 抽象
│   ├── constants.py     # SENSENOVA_U1_VALID_SIZES 等模型枚举
│   ├── provider.py      # LLMClient 主类 (含 create_image_generation)
│   └── ...
frontend/
├── app/                  # Next.js app router pages
├── AGENTS.md             # Next.js breaking changes notice (important!)
└── ...
文档格式测试/               # Test cases with before/after DOCX pairs
out/drafts/              # Generated markdown drafts and output DOCX
logs/                    # Session logs
```

## Frontend Note

This project uses a **non-standard Next.js version** with breaking API changes. Before modifying frontend code, read `frontend/AGENTS.md` and the Next.js guides in `node_modules/next/dist/docs/`.