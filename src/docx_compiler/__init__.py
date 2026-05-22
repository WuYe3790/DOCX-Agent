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
from .optimizer import optimize_paragraph, optimize_tree
from .render import render_blocks_to_container, render_paragraph, render_table

__all__ = [
    "CellIR",
    "CodeBlockIR",
    "FormulaIR",
    "ParagraphIR",
    "ParagraphIndent",
    "RunIR",
    "TableIR",
    "TableRowIR",
    "optimize_paragraph",
    "optimize_tree",
    "render_blocks_to_container",
    "render_paragraph",
    "render_table",
]
