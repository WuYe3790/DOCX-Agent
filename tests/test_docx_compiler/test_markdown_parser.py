"""test_markdown_parser.py — docx_compiler/markdown_parser.py 纯函数测试 (PR-1.3)

parse_markdown_blocks(text) -> list[MarkdownBlock] 是编译器第一步.
无 I/O 依赖, 纯字符串 → 块列表.

陷阱 3 防御 (在写本测试前完成):
  - 生产 parser 用 MarkdownIt("commonmark").enable("table")
    → 只 commonmark + GFM table 两个扩展, 别测 HTML 原生块 (虽然 parser 注册了
      html_block, 但生成 HtmlBlock(support="rejected"), 视为拒绝)
  - 12 case 必须严格匹配生产扩展, 不测 markdown 标准未启用的语法 (e.g. 删除线,
    任务列表, 围栏代码块以外的 code_block)

共 12 case:
  1. H1-H6 标题 (注意: block_type 对 H3-H6 都映射为 "heading2", level 字段保留)
  2. 普通段落
  3. 软换行 (行末双空格)
  4. 无序列表
  5. 有序列表
  6. 嵌套列表
  7. 围栏代码块带语言
  8. 围栏代码块不带语言
  9. 图片 (在 paragraph 内, 由 inline 检测)
  10. GFM 表格
  11. 显示公式 ($$...$$)
  12. 空输入 → []
  13. 混合块 + block_id 自动编号
  14. HTML 块被识别为 HtmlBlock(support="rejected")
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from docx_compiler.markdown_parser import (
    CodeBlock,
    FormulaBlock,
    HeadingBlock,
    HtmlBlock,
    ImageBlock,
    ListItemBlock,
    ParagraphBlock,
    TableBlock,
    TableCellBlock,
    parse_markdown_blocks,
)


# =====================================================================
# 1. 标题
# =====================================================================

class TestHeadings:
    """H1-H6 标题: block_type 对 H1 是 "heading1", 其他都是 "heading2",
    实际层级保留在 .level 字段."""

    @pytest.mark.parametrize("marker,expected_level", [
        ("#", 1), ("##", 2), ("###", 3), ("####", 4), ("#####", 5), ("######", 6),
    ])
    def test_heading_levels(self, marker, expected_level):
        md = f"{marker} 标题文本"
        blocks = parse_markdown_blocks(md)
        assert len(blocks) == 1
        b = blocks[0]
        assert isinstance(b, HeadingBlock)
        assert b.text == "标题文本"
        # 简化映射: H1 → "heading1", 其他 → "heading2"
        if expected_level == 1:
            assert b.block_type == "heading1"
        else:
            assert b.block_type == "heading2"
        # level 字段保留真实层级
        assert b.level == expected_level


# =====================================================================
# 2. 普通段落
# =====================================================================

def test_plain_paragraph():
    """普通文本 → ParagraphBlock, text 保留原文 (含 inline 元素时是 plain 文本)."""
    blocks = parse_markdown_blocks("hello world")
    assert len(blocks) == 1
    b = blocks[0]
    assert isinstance(b, ParagraphBlock)
    assert b.text == "hello world"
    assert b.block_type == "paragraph"


# =====================================================================
# 3. 软换行 (行末双空格)
# =====================================================================

def test_soft_line_break():
    """行末双空格 → markdown soft break, 在 parser 端通常合并成单行 (看实现)."""
    # commonmark 默认: 软换行会被合并为单段
    blocks = parse_markdown_blocks("第一行  \n第二行")
    assert len(blocks) == 1
    assert isinstance(blocks[0], ParagraphBlock)
    # 文本内容 (具体分隔符由 parser 决定, 测的是 block 数 = 1)
    assert "第一行" in blocks[0].text
    assert "第二行" in blocks[0].text


# =====================================================================
# 4. 无序列表
# =====================================================================

def test_unordered_list():
    """- item 形式 → ListItemBlock, marker='-', ordered=False."""
    blocks = parse_markdown_blocks("- item 1\n- item 2\n- item 3")
    assert len(blocks) == 3
    for b in blocks:
        assert isinstance(b, ListItemBlock)
        assert b.marker == "-"
        assert b.ordered is False
        assert b.indent_level == 0
    assert [b.text for b in blocks] == ["item 1", "item 2", "item 3"]


# =====================================================================
# 5. 有序列表
# =====================================================================

def test_ordered_list():
    """1. item 形式 → ListItemBlock, ordered=True, marker 是 "1.", "2." etc."""
    blocks = parse_markdown_blocks("1. first\n2. second")
    assert len(blocks) == 2
    for b in blocks:
        assert isinstance(b, ListItemBlock)
        assert b.ordered is True
    # marker 含数字 + 点
    assert "1" in blocks[0].marker
    assert "2" in blocks[1].marker


# =====================================================================
# 6. 嵌套列表
# =====================================================================

def test_nested_list_indent_level():
    """2 空格缩进 → indent_level=1, 4 空格 → indent_level=2."""
    md = "- outer\n  - inner1\n  - inner2"
    blocks = parse_markdown_blocks(md)
    assert len(blocks) == 3
    assert blocks[0].indent_level == 0
    assert blocks[1].indent_level == 1
    assert blocks[2].indent_level == 1
    assert all(isinstance(b, ListItemBlock) for b in blocks)


# =====================================================================
# 7. 围栏代码块带语言
# =====================================================================

def test_fenced_code_block_with_language():
    """```python ... ``` → CodeBlock, language='python'."""
    md = "```python\nprint('hi')\n```"
    blocks = parse_markdown_blocks(md)
    assert len(blocks) == 1
    b = blocks[0]
    assert isinstance(b, CodeBlock)
    assert b.language == "python"
    assert "print('hi')" in b.text
    assert b.block_type == "code_block"


# =====================================================================
# 8. 围栏代码块不带语言
# =====================================================================

def test_fenced_code_block_no_language():
    """``` (无语言) ... ``` → CodeBlock, language=None."""
    md = "```\nraw code\n```"
    blocks = parse_markdown_blocks(md)
    assert len(blocks) == 1
    b = blocks[0]
    assert isinstance(b, CodeBlock)
    assert b.language is None
    # 注意: 围栏代码块 text 末尾保留 \\n, 不要用严格等值
    assert "raw code" in b.text


# =====================================================================
# 9. 图片 (在 paragraph 内)
# =====================================================================

def test_image_in_paragraph():
    """![alt](src) → ImageBlock, src 解码, alt 保留."""
    blocks = parse_markdown_blocks("![my picture](media/foo.png)")
    assert len(blocks) == 1
    b = blocks[0]
    assert isinstance(b, ImageBlock)
    assert b.src == "media/foo.png"  # URL 解码
    assert b.alt == "my picture"
    assert b.block_type == "image"


# =====================================================================
# 10. GFM 表格
# =====================================================================

def test_gfm_table():
    """| h1 | h2 | 形式 → TableBlock, 含 header_row."""
    md = (
        "| 列1 | 列2 |\n"
        "| --- | --- |\n"
        "| a   | b   |\n"
        "| c   | d   |"
    )
    blocks = parse_markdown_blocks(md)
    assert len(blocks) == 1
    b = blocks[0]
    assert isinstance(b, TableBlock)
    assert b.block_type == "table"
    # 表头行
    assert b.header_row_count >= 1
    # 至少 3 行 (1 表头 + 2 数据)
    assert len(b.rows) >= 3
    # 检查表头 cell
    header_row = b.rows[0]
    assert all(isinstance(c, TableCellBlock) for c in header_row)
    assert header_row[0].header is True
    assert header_row[0].text == "列1"


# =====================================================================
# 11. 显示公式
# =====================================================================

def test_display_formula():
    """$$ E=mc^2 $$ → FormulaBlock, display=True, source_format='latex'."""
    blocks = parse_markdown_blocks("$$\nE=mc^2\n$$")
    assert len(blocks) == 1
    b = blocks[0]
    assert isinstance(b, FormulaBlock)
    assert b.display is True
    assert b.source_format == "latex"
    assert "E=mc^2" in b.text or "E=mc^2" in b.raw


# =====================================================================
# 12. 空输入
# =====================================================================

def test_empty_input_returns_empty_list():
    """空字符串 → 空列表, 不抛."""
    assert parse_markdown_blocks("") == []


# =====================================================================
# 13. 混合块 + block_id 自动编号
# =====================================================================

def test_mixed_blocks_with_auto_block_id():
    """H1 + 段 + 列表 → 3 块, block_id 自动编为 B001 / B002 / B003."""
    md = "# 标题\n第一段\n- a\n- b"
    blocks = parse_markdown_blocks(md)
    assert len(blocks) == 4
    assert blocks[0].block_id == "B001"
    assert blocks[1].block_id == "B002"
    assert blocks[2].block_id == "B003"
    assert blocks[3].block_id == "B004"
    # 类型验证
    assert isinstance(blocks[0], HeadingBlock)
    assert isinstance(blocks[1], ParagraphBlock)
    assert isinstance(blocks[2], ListItemBlock)
    assert isinstance(blocks[3], ListItemBlock)


# =====================================================================
# 14. HTML 块被识别为 HtmlBlock(support="rejected")
# =====================================================================

def test_html_block_parsed_as_rejected():
    """<div>...</div> 等 HTML 块 → HtmlBlock, support='rejected' (不渲染)."""
    md = "<div>\nhello html\n</div>"
    blocks = parse_markdown_blocks(md)
    assert len(blocks) == 1
    b = blocks[0]
    assert isinstance(b, HtmlBlock)
    assert b.block_type == "html_block"
    # 关键: support 字段标 "rejected", 下游 render 看到这个标记应跳过
    assert b.support == "rejected"
