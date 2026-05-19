from .common import NS, json_result, load_document_xml, paragraph_location, paragraph_text, paragraphs, tables


def read_docx_structure(docx_path: str, max_items: int = 80) -> str:
    """读取 word/document.xml 中的段落文本和表格单元格文本。"""
    root = load_document_xml(docx_path)
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
    for table_index, table in enumerate(tables(root), start=1):
        rows = table.xpath("./w:tr", namespaces=NS)
        row_summaries = []
        for row_index, row in enumerate(rows, start=1):
            cells = row.xpath("./w:tc", namespaces=NS)
            row_summaries.append(
                {
                    "row_index": row_index,
                    "cells": [
                        "".join(t.text or "" for t in cell.xpath(".//w:t", namespaces=NS))
                        for cell in cells
                    ],
                }
            )
        table_items.append({"table_index": table_index, "rows": row_summaries})

    return json_result(
        {
            "docx_path": docx_path,
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
        "description": "读取 docx 的正文结构，返回非空段落、表格行列文本和定位信息。用于编辑前先定位。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "要读取的 .docx 文件路径"},
                "max_items": {"type": "integer", "description": "最多返回多少个非空段落，默认 80"},
            },
            "required": ["docx_path"],
        },
    },
}
