from docx_compiler.table_ops import merge_table_cells_horizontal_op

from .common import json_result, resolve_docx_io



def merge_table_cells_horizontal(
    session_id: str,
    docx_path: str,
    output_path: str,
    table_index: int,
    row_index: int,
    start_cell_index: int,
    span: int,
) -> str:
    """横向合并同一行连续单元格。"""
    input_path, output_path_resolved = resolve_docx_io(session_id, docx_path, output_path)
    try:
        result = merge_table_cells_horizontal_op(
            docx_path=docx_path,
            output_path=output_path,
            table_index=table_index,
            row_index=row_index,
            start_cell_index=start_cell_index,
            span=span,
        )
    except (IndexError, ValueError) as exc:
        return json_result({"status": "error", "message": str(exc)})
    return json_result({"status": "ok", **result})


tools_schema = {
    "type": "function",
    "function": {
        "name": "merge_table_cells_horizontal",
        "description": "横向合并指定行内连续单元格：首个单元格设置 w:gridSpan，后续 w:tc 删除。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径 (相对 workspace 根)"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径 (相对 workspace 根)"},
                "table_index": {"type": "integer", "description": "第几个表格，按 //w:tbl 计数，1-based；注意嵌套表格也会计数"},
                "row_index": {"type": "integer", "description": "第几行，1-based"},
                "start_cell_index": {"type": "integer", "description": "合并起始单元格，1-based"},
                "span": {"type": "integer", "description": "合并跨度，至少 2"},
            },
            "required": ["docx_path", "output_path", "table_index", "row_index", "start_cell_index", "span"],
        },
    },
}
