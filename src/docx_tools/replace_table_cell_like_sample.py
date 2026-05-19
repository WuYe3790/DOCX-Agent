from .common import (
    apply_sample_format_to_paragraph,
    append_run_to_paragraph,
    cell_text,
    clear_cell_to_empty_paragraph,
    get_cell_by_index,
    get_row_by_index,
    get_table_by_index,
    insert_paragraphs_after,
    json_result,
    load_document_xml,
    split_text_for_paragraphs,
    table_summary,
    write_document_xml,
)
from .style_profile import load_style_sample


def replace_table_cell_like_sample(
    docx_path: str,
    output_path: str,
    table_index: int,
    row_index: int,
    cell_index: int,
    new_text: str,
    style_profile_path: str,
    sample_id: str,
    newline_mode: str = "paragraphs",
) -> str:
    """替换表格单元格全部文本，并按指定样式样本设置格式。"""
    style_sample = load_style_sample(style_profile_path, sample_id)
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
    first_text, extra_paragraphs = split_text_for_paragraphs(new_text, newline_mode)
    if first_text:
        append_run_to_paragraph(paragraph, first_text)
        apply_sample_format_to_paragraph(paragraph, style_sample)

    inserted_paragraph_count = insert_paragraphs_after(paragraph, extra_paragraphs, style_paragraph=paragraph)
    current = paragraph
    for _ in range(inserted_paragraph_count):
        current = current.getnext()
        if current is not None:
            apply_sample_format_to_paragraph(current, style_sample)

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
            "new_text": new_text,
            "sample_id": sample_id,
            "style_profile_path": style_profile_path,
            "before_text": before_text,
            "after_text": after_text,
            "inserted_paragraph_count": inserted_paragraph_count,
            "before_table": before_table,
            "after_table": table_summary(table),
        }
    )


tools_schema = {
    "type": "function",
    "function": {
        "name": "replace_table_cell_like_sample",
        "description": "按表格坐标替换单元格全部文本，并按 style_profile_path 中的 sample_id 仿写段落和字符格式。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "table_index": {"type": "integer", "description": "第几个表格，按 //w:tbl 计数，1-based；注意嵌套表格也会计数"},
                "row_index": {"type": "integer", "description": "第几行，1-based"},
                "cell_index": {"type": "integer", "description": "第几个单元格，1-based"},
                "new_text": {"type": "string", "description": "替换后的单元格文本"},
                "style_profile_path": {"type": "string", "description": "analyze_docx_style_samples 输出的样式画像 JSON 路径"},
                "sample_id": {"type": "string", "description": "要仿写的样式样本 ID，如 S001"},
                "newline_mode": {
                    "type": "string",
                    "description": "新文本包含换行时的处理方式：paragraphs 拆成多个单元格内段落，inline 替换为空格；默认 paragraphs",
                    "enum": ["paragraphs", "inline"],
                },
            },
            "required": [
                "docx_path",
                "output_path",
                "table_index",
                "row_index",
                "cell_index",
                "new_text",
                "style_profile_path",
                "sample_id",
            ],
        },
    },
}
