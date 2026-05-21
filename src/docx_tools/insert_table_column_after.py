from docx_compiler.table_ops import insert_table_column_after_op

from .common import json_result


def insert_table_column_after(
    docx_path: str,
    output_path: str,
    table_index: int,
    column_index: int,
    cell_texts: list[str] | None = None,
    copy_from: str = "left",
) -> str:
    """在指定列右侧插入新列。"""
    try:
        result = insert_table_column_after_op(
            docx_path=docx_path,
            output_path=output_path,
            table_index=table_index,
            column_index=column_index,
            cell_texts=cell_texts,
            copy_from=copy_from,
        )
    except (IndexError, ValueError) as exc:
        return json_result({"status": "error", "message": str(exc)})
    return json_result({"status": "ok", **result})


tools_schema = {
    "type": "function",
    "function": {
        "name": "insert_table_column_after",
        "description": "在指定表格列右侧插入一列，并同步更新每行 w:tc 和 w:tblGrid。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "table_index": {"type": "integer", "description": "第几个表格，按 //w:tbl 计数，1-based；注意嵌套表格也会计数"},
                "column_index": {"type": "integer", "description": "在哪一列右侧插入，1-based"},
                "cell_texts": {
                    "type": "array",
                    "description": "新列每行文本；少于行数的后续单元格置空",
                    "items": {"type": "string"},
                },
                "copy_from": {
                    "type": "string",
                    "description": "复制左侧或右侧单元格属性，默认 left",
                    "enum": ["left", "right"],
                },
            },
            "required": ["docx_path", "output_path", "table_index", "column_index"],
        },
    },
}
