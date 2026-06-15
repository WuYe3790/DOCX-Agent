from docx_compiler.table_ops import insert_table_in_cell_op

from .common import json_result, resolve_docx_io



def insert_table_in_cell(
    session_id: str,
    docx_path: str,
    output_path: str,
    table_index: int,
    row_index: int,
    cell_index: int,
    cell_texts: list[list[str]],
    column_widths_twips: list[int] | None = None,
) -> str:
    """在表格单元格内插入嵌套表格。"""
    input_path, output_path_resolved = resolve_docx_io(session_id, docx_path, output_path)
    try:
        result = insert_table_in_cell_op(
            docx_path=str(input_path),
            output_path=str(output_path_resolved),
            table_index=table_index,
            row_index=row_index,
            cell_index=cell_index,
            cell_texts=cell_texts,
            column_widths_twips=column_widths_twips,
        )
    except (IndexError, ValueError) as exc:
        return json_result({"status": "error", "message": str(exc)})
    return json_result({"status": "ok", **result})


tools_schema = {
    "type": "function",
    "function": {
        "name": "insert_table_in_cell",
        "description": "在指定表格单元格内创建嵌套表格；外层表格行列结构保持不变。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径 (相对 workspace 根)"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径 (相对 workspace 根)"},
                "table_index": {"type": "integer", "description": "第几个表格，按 //w:tbl 计数，1-based；注意嵌套表格也会计数"},
                "row_index": {"type": "integer", "description": "第几行，1-based"},
                "cell_index": {"type": "integer", "description": "第几个单元格，1-based"},
                "cell_texts": {
                    "type": "array",
                    "description": "嵌套表格的二维文本数组",
                    "items": {"type": "array", "items": {"type": "string"}},
                },
                "column_widths_twips": {
                    "type": "array",
                    "description": "可选列宽数组，单位 twips",
                    "items": {"type": "integer"},
                },
            },
            "required": ["docx_path", "output_path", "table_index", "row_index", "cell_index", "cell_texts"],
        },
    },
}
