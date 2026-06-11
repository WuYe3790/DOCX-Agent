from docx_compiler.table_ops import insert_table_after_paragraph_op

from .common import json_result, resolve_docx_io



def insert_table_after_paragraph(
    session_id: str,
    docx_path: str,
    output_path: str,
    paragraph_index: int,
    cell_texts: list[list[str]],
    column_widths_twips: list[int] | None = None,
) -> str:
    """在普通段落后插入新表格。"""
    input_path, output_path_resolved = resolve_docx_io(session_id, docx_path, output_path)
    try:
        result = insert_table_after_paragraph_op(
            docx_path=docx_path,
            output_path=output_path,
            paragraph_index=paragraph_index,
            cell_texts=cell_texts,
            column_widths_twips=column_widths_twips,
        )
    except (IndexError, ValueError) as exc:
        return json_result({"status": "error", "message": str(exc)})
    return json_result({"status": "ok", **result})


tools_schema = {
    "type": "function",
    "function": {
        "name": "insert_table_after_paragraph",
        "description": "在指定普通段落后创建一个新 Word 表格，生成完整 w:tbl/w:tblGrid/w:tr/w:tc 结构。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径 (相对 workspace 根)"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径 (相对 workspace 根)"},
                "paragraph_index": {"type": "integer", "description": "在哪个段落后插入，按 //w:p 计数，1-based"},
                "cell_texts": {
                    "type": "array",
                    "description": "二维数组，表示每行每列的文本",
                    "items": {"type": "array", "items": {"type": "string"}},
                },
                "column_widths_twips": {
                    "type": "array",
                    "description": "可选列宽数组，单位 twips",
                    "items": {"type": "integer"},
                },
            },
            "required": ["docx_path", "output_path", "paragraph_index", "cell_texts"],
        },
    },
}
