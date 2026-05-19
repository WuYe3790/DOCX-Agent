from .common import (
    cell_text,
    clear_cell_to_empty_paragraph,
    get_cell_by_index,
    get_row_by_index,
    get_table_by_index,
    json_result,
    load_document_xml,
    table_summary,
    write_document_xml,
)


def clear_table_cell(
    docx_path: str,
    output_path: str,
    table_index: int,
    row_index: int,
    cell_index: int,
) -> str:
    """清空指定表格单元格内容，保留单元格结构和一个空段落。"""
    root = load_document_xml(docx_path)
    try:
        table = get_table_by_index(root, table_index)
        row = get_row_by_index(table, row_index)
        cell = get_cell_by_index(row, cell_index)
    except IndexError as exc:
        return json_result({"status": "error", "message": str(exc)})

    before_table = table_summary(table)
    before_text = cell_text(cell)
    paragraph = clear_cell_to_empty_paragraph(cell)
    after_text = cell_text(cell)
    write_document_xml(docx_path, output_path, root)

    return json_result(
        {
            "status": "ok",
            "docx_path": docx_path,
            "output_path": output_path,
            "table_index": table_index,
            "row_index": row_index,
            "cell_index": cell_index,
            "before_text": before_text,
            "after_text": after_text,
            "kept_empty_paragraph": paragraph.tag.endswith("}p"),
            "before_table": before_table,
            "after_table": table_summary(table),
        }
    )


tools_schema = {
    "type": "function",
    "function": {
        "name": "clear_table_cell",
        "description": "清空指定表格单元格内容，但保留单元格、单元格属性和一个空段落。适合用户说清空某个单元格而不是删除行列的场景。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "table_index": {"type": "integer", "description": "第几个表格，按 //w:tbl 计数，1-based；注意嵌套表格也会计数"},
                "row_index": {"type": "integer", "description": "第几行，1-based"},
                "cell_index": {"type": "integer", "description": "第几个单元格，1-based"},
            },
            "required": ["docx_path", "output_path", "table_index", "row_index", "cell_index"],
        },
    },
}
