from .common import (
    get_row_by_index,
    get_table_by_index,
    json_result,
    load_document_xml,
    row_text,
    table_rows,
    table_summary,
    write_document_xml,
)


def delete_table_row(
    docx_path: str,
    output_path: str,
    table_index: int,
    row_index: int,
    expected_row_text_contains: str = "",
) -> str:
    """删除指定表格整行。"""
    root = load_document_xml(docx_path)
    try:
        table = get_table_by_index(root, table_index)
        row = get_row_by_index(table, row_index)
    except IndexError as exc:
        return json_result({"status": "error", "message": str(exc)})

    before_table = table_summary(table)
    before_text = row_text(row)
    if expected_row_text_contains and expected_row_text_contains not in before_text:
        return json_result(
            {
                "status": "error",
                "message": "expected_row_text_contains not found in target row",
                "table_index": table_index,
                "row_index": row_index,
                "expected_row_text_contains": expected_row_text_contains,
                "actual_row_text": before_text,
                "before_table": before_table,
            }
        )

    table.remove(row)
    write_document_xml(docx_path, output_path, root)

    return json_result(
        {
            "status": "ok",
            "docx_path": docx_path,
            "output_path": output_path,
            "table_index": table_index,
            "deleted_row_index": row_index,
            "deleted_row_text": before_text,
            "before_row_count": len(before_table["rows"]),
            "after_row_count": len(table_rows(table)),
            "before_table": before_table,
            "after_table": table_summary(table),
        }
    )


tools_schema = {
    "type": "function",
    "function": {
        "name": "delete_table_row",
        "description": "删除指定表格的完整行，直接移除 <w:tr>。适合用户明确要求删除整行时使用，不适合只清空内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "table_index": {"type": "integer", "description": "第几个表格，按 //w:tbl 计数，1-based；注意嵌套表格也会计数"},
                "row_index": {"type": "integer", "description": "第几行，1-based"},
                "expected_row_text_contains": {
                    "type": "string",
                    "description": "可选安全校验：目标行文本必须包含该字符串，否则不删除",
                },
            },
            "required": ["docx_path", "output_path", "table_index", "row_index"],
        },
    },
}
