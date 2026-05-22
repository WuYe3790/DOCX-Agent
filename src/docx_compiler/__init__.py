"""Small DOCX compiler backend for Markdown-like content and table layout."""

from .ir import (
    CellIR,
    CodeBlockIR,
    FormulaIR,
    ParagraphIR,
    ParagraphIndent,
    RunIR,
    TableIR,
    TableRowIR,
)
from .markdown_parser import (
    CodeBlock,
    FormulaBlock,
    HeadingBlock,
    HtmlBlock,
    ListItemBlock,
    MarkdownBlock,
    ParagraphBlock,
    TableBlock,
    TableCellBlock,
    blocks_to_dicts,
    parse_markdown_blocks,
)
from .optimizer import optimize_paragraph, optimize_tree
from .render import render_blocks_to_container, render_paragraph, render_table

__all__ = [
    "CellIR",
    "CodeBlockIR",
    "FormulaIR",
    "CodeBlock",
    "FormulaBlock",
    "HeadingBlock",
    "HtmlBlock",
    "ListItemBlock",
    "MarkdownBlock",
    "ParagraphIR",
    "ParagraphBlock",
    "ParagraphIndent",
    "TableBlock",
    "TableCellBlock",
    "blocks_to_dicts",
    "parse_markdown_blocks",
    "RunIR",
    "TableIR",
    "TableRowIR",
    "optimize_paragraph",
    "optimize_tree",
    "render_blocks_to_container",
    "render_paragraph",
    "render_table",
]
