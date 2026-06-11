import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from workspace.guard import resolve_workspace_path, WorkspacePathError, to_relative_path

from .common import (
    NS,
    W,
    json_result,
    load_document_xml,
    nearest_ancestor,
    paragraph_location,
    paragraph_text,
    paragraphs,
    row_cells,
    tables,
)


def read_docx_structure(session_id: str, docx_path: str, max_items: int = 80) -> str:
    """v2: 读取 session workspace 内的 docx 的段落 + 表格结构 (沙箱化)"""
    try:
        docx_path_resolved = resolve_workspace_path(session_id, docx_path, must_exist=True, must_be_file=True)
    except WorkspacePathError as e:
        return json_result({"status": "error", "code": e.code, "message": e.user_message})
    root = load_document_xml(str(docx_path_resolved))
    para_items = []
    for index, paragraph in enumerate(paragraphs(root), start=1):
        text = paragraph_text(paragraph)
        if not text.strip():
            continue
        para_items.append(
            {
                "paragraph_index": index,
                "text": text,
                "location": paragraph_location(paragraph),
            }
        )
        if len(para_items) >= max_items:
            break

    table_items = []
    all_tables = tables(root)
    table_index_by_id = {id(table): index for index, table in enumerate(all_tables, start=1)}
    for table_index, table in enumerate(all_tables, start=1):
        rows = table.xpath("./w:tr", namespaces=NS)
        row_summaries = []
        for row_index, row in enumerate(rows, start=1):
            cells = row.xpath("./w:tc", namespaces=NS)
            row_summaries.append(
                {
                    "row_index": row_index,
                    "cells": [_cell_summary(cell, cell_index) for cell_index, cell in enumerate(cells, start=1)],
                }
            )
        table_items.append(
            {
                "table_index": table_index,
                "depth": _table_depth(table),
                "parent": _table_parent_location(table, table_index_by_id),
                "rows": row_summaries,
            }
        )

    return json_result(
        {
            "docx_path": to_relative_path(session_id, docx_path_resolved),
            "paragraph_count": len(paragraphs(root)),
            "table_count": len(tables(root)),
            "paragraphs": para_items,
            "tables": table_items,
        }
    )


tools_schema = {
    "type": "function",
    "function": {
        "name": "read_docx_structure",
        "description": "读取 session workspace 内 docx 的正文结构，返回非空段落、表格行列文本和定位信息。用于编辑前先定位。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "要读取的 .docx 文件路径 (相对 workspace 根)"},
                "max_items": {"type": "integer", "description": "最多返回多少个非空段落，默认 80"},
            },
            "required": ["docx_path"],
        },
    },
}


def _cell_summary(cell, cell_index: int) -> dict:
    direct_text = "".join(t.text or "" for t in cell.xpath("./w:p//w:t", namespaces=NS))
    all_text = "".join(t.text or "" for t in cell.xpath(".//w:t", namespaces=NS))
    nested_tables = cell.xpath("./w:tbl", namespaces=NS)
    return {
        "cell_index": cell_index,
        "direct_text": direct_text,
        "text": all_text,
        "nested_table_count": len(nested_tables),
    }


def _table_depth(table) -> int:
    depth = 0
    current = table.getparent()
    while current is not None:
        if current.tag == f"{W}tbl":
            depth += 1
        current = current.getparent()
    return depth


def _table_parent_location(table, table_index_by_id: dict) -> dict | None:
    parent_cell = nearest_ancestor(table, f"{W}tc")
    if parent_cell is None:
        return None
    parent_row = nearest_ancestor(parent_cell, f"{W}tr")
    parent_table = nearest_ancestor(parent_row, f"{W}tbl") if parent_row is not None else None
    if parent_row is None or parent_table is None:
        return None
    return {
        "table_index": table_index_by_id.get(id(parent_table)),
        "row_index": _index_in_parent(parent_row, f"{W}tr"),
        "cell_index": _cell_index_in_row(parent_cell),
    }


def _index_in_parent(element, tag: str) -> int | None:
    parent = element.getparent()
    if parent is None:
        return None
    same = [child for child in parent if child.tag == tag]
    return same.index(element) + 1 if element in same else None


def _cell_index_in_row(cell) -> int | None:
    row = nearest_ancestor(cell, f"{W}tr")
    if row is None:
        return None
    cells = row_cells(row)
    return cells.index(cell) + 1 if cell in cells else None
