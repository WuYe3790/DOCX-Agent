# DOCX Agent

AI 驱动的 Word 文档编辑 Agent，基于 LLM 工具调用 + 直接 OpenXML 操作实现精细化的 `.docx` 编辑。无需 `python-docx`，直接操控底层 XML 和 ZIP 结构。

## 工作流程

Agent 采用三阶段状态机，LLM 在每阶段只能使用当前允许的工具集：

```
样式审核 (Style Review) → Markdown 草稿 (MD Draft) → Word 写入编译 (Word Editing)
```

| 阶段 | 职责 | 可用工具 |
|------|------|---------|
| **样式审核** | 只读分析模板格式特征与文档结构 | `analyze_docx_style_samples`, `read_docx_structure`, `ls` |
| **Markdown 草稿** | 按文档区域生成结构化 Markdown 内容 | `write_markdown_draft`, `read_markdown_draft`, `parse_markdown_draft`, `ls`, `read`, `analyze_image_content` |
| **Word 写入** | 编译 Markdown 写入 DOCX，diff 验证 | 全部编辑工具 + `markdown_to_word`, `diff_docx`, `read`, `analyze_image_content` |

## 核心能力

- **直接 XML 编辑**：基于 `lxml` + `zipfile` 直接读写 `word/document.xml`，精确操控段落、run、表格、样式
- **Markdown 编译器**：自定义 Markdown → AST → IR → OpenXML 多阶段编译管线，支持标题、段落、列表、表格、代码块、公式、图片等元素
- **图片插入**：支持本地图片嵌入，自动处理 DrawingML XML、关系链、Content Type 注册和媒体二进制注入
- **多模态识图**：自动适配多模态视觉模型（SenseNova）分析图表与截图内容
- **增量编辑**：支持替换、插入、删除文本/段落/表格行/列，保留原有格式或应用样式样本
- **样式感知**：提取模板中的格式样本，编辑时保持统一风格
- **变更验证**：编辑后自动 diff 对比原文档

## 支持的 LLM

| 提供商 | 默认模型 | 说明 |
|--------|---------|------|
| **DeepSeek** | `deepseek-v4-flash` | 支持 `thinking` 链 |
| **SenseNova (商汤)** | `sensenova-6.7-flash-lite` | 支持 `reasoning_effort`；多模态识图回退方案 |
| **OpenAI 兼容** | `gpt-4o` | 兼容标准 OpenAI API 的第三方服务 |

## 快速开始

### 环境要求

- Python 3.10+
- `lxml`
- `openai`
- `markdown-it-py`

### 配置

复制并编辑 `src/config.json`：

```json
{
  "provider": "deepseek",
  "providers": {
    "deepseek": {
      "api_key": "your-api-key",
      "base_url": "https://api.deepseek.com",
      "model": "deepseek-v4-flash",
      "thinking": "enabled"
    },
    "sensenova": {
      "api_key": "your-api-key",
      "base_url": "https://token.sensenova.cn/v1",
      "model": "sensenova-6.7-flash-lite",
      "reasoning_effort": "high"
    }
  }
}
```

也支持通过环境变量配置：

```powershell
$env:DEEPSEEK_API_KEY="your-key"
$env:LLM_PROVIDER="deepseek"
```

### 运行

```powershell
python src/docx_agent_demo.py
```

交互示例：

```
请输入你的文档编辑需求：
把 文档格式测试/cases/insert_text_001/docx/实验报告模板_v3_insert_text_001.docx 中的"依据实验指导书"后插入"测试文本"，另存为 out/demo.docx，并对比原文档。
```

### 运行日志

所有对话和工具调用记录在 `logs/docx_agent_<timestamp>.log`。

## 工具总览

### 基础工具 (`basic_tools/`)

| 工具 | 说明 |
|------|------|
| `ls` | 列出目录内容，辅助定位文件路径 |
| `read` | 读取文本/代码/Markdown 文件，支持 offset/limit 分页，自动检测编码 |
| `analyze_image_content` | 多模态图像识别，上传本地图片进行视觉分析 |

### Markdown 工具 (`md_tools/`)

| 工具 | 说明 |
|------|------|
| `write_markdown_draft` | 写入 Markdown 草稿到 `out/drafts/` |
| `read_markdown_draft` | 读取草稿（可选行号） |
| `parse_markdown_draft` | 解析草稿为 AST，含 block_id 和诊断信息 |
| `markdown_to_word` | 编译器入口，按 actions 将 Markdown 编译写入 DOCX |
| `apply_markdown_ir_to_table_cell` | 将 Markdown 编译写入表格单元格 |

### DOCX 编辑工具 (`docx_tools/`)

| 工具 | 说明 |
|------|------|
| `analyze_docx_style_samples` | 提取文档格式样本，分组并分配 sample_id |
| `read_docx_structure` | 读取段落文本、表格结构、位置坐标 |
| `find_text` | 搜索文本，返回段落索引和字符偏移 |
| `insert_text_at` | 在锚点偏移处插入文本 |
| `insert_text_in_table_cell` | 在表格单元格内插入文本 |
| `replace_text` | 替换文档文本（支持跨 run 匹配） |
| `delete_text` | 删除指定文本（支持跨 run 删除） |
| `insert_paragraph_after` | 在锚点段落后插入新段落 |
| `insert_image_after_paragraph` | 在段落后插入本地图片 |
| `set_text_format` | 设置字符格式（清除/正文/自定义） |
| `set_paragraph_indent` | 设置段落缩进 |
| `diff_docx` | 对比两个 .docx 文件的 XML 和文本差异 |
| `unzip_docx` | 解压 .docx 以供源码检查 |
| `replace_text_like_sample` | 按样式样本替换文本 |
| `insert_paragraph_after_like_sample` | 按样式样本插入段落 |
| `replace_table_cell_like_sample` | 按样式样本替换单元格文本 |
| `replace_table_cell_text` | 替换表格单元格文本 |
| `insert_table_row_after` | 在指定行后插入表格行 |
| `insert_table_after_paragraph` | 在段落后插入表格 |
| `insert_table_in_cell` | 在单元格内插入嵌套表格 |
| `insert_table_column_after` | 在指定列后插入列 |
| `merge_table_cells_horizontal` | 水平合并单元格 |
| `clear_table_cell` | 清空单元格内容 |
| `delete_table_row` | 删除表格行 |

## 编译器架构

```
Markdown 文本
    ↓ markdown-it-py 分词
MarkdownBlock AST（HeadingBlock, ParagraphBlock, TableBlock, ImageBlock...）
    ↓ normalize_block_support + diagnostics
    ↓ lower
Layout IR（ParagraphIR, TableIR, CodeBlockIR, FormulaIR, ImageIR...）
    ↓ render
OpenXML lxml 元素树
    ↓ write_document_xml
输出 .docx
```

## 目录结构

```
src/
├── docx_agent_demo.py         # 主入口：交互式 Agent
├── llm_adapter.py             # LLM 客户端抽象层
├── config.json                # API 配置（不纳入版本控制）
├── basic_tools/               # 基础工具（ls, read, analyze_image_content）
├── md_tools/                  # Markdown 草稿与编译器入口
├── docx_tools/                # DOCX 编辑工具（28 个工具 + registry）
├── docx_compiler/             # Markdown → DOCX 编译器后端
│   ├── ir.py                  # 中间表示（ParagraphIR, ImageIR 等）
│   ├── markdown_parser.py     # Markdown 解析器
│   ├── lower.py               # AST → IR 降级 + 诊断
│   ├── render.py              # IR → OpenXML 渲染
│   ├── optimizer.py           # XML 优化器
│   ├── diagnostics.py         # 诊断系统
│   └── table_ops.py           # 表格操作
├── 文档格式测试/               # 测试用例与模板
├── out/                       # 输出目录
└── logs/                      # 运行日志
```
