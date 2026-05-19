from .common import (
    apply_sample_format_to_paragraph,
    cell_text,
    clear_cell_to_empty_paragraph,
    get_cell_by_index,
    get_row_by_index,
    get_table_by_index,
    insert_paragraphs_after,
    json_result,
    load_document_xml,
    paragraph_text,
    table_summary,
    write_document_xml,
)
from .style_profile import load_style_sample


def replace_table_cell_with_styled_paragraphs(
    docx_path: str,
    output_path: str,
    table_index: int,
    row_index: int,
    cell_index: int,
    paragraphs: list[dict],
    style_profile_path: str,
) -> str:
    """替换单元格内容为多段文字，每段按自己的 sample_id 仿写格式。"""
    items = _validate_paragraph_items(paragraphs)
    root = load_document_xml(docx_path)
    try:
        table = get_table_by_index(root, table_index)
        row = get_row_by_index(table, row_index)
        cell = get_cell_by_index(row, cell_index)
    except IndexError as exc:
        return json_result({"status": "error", "message": str(exc)})

    before_table = table_summary(table)
    before_text = cell_text(cell)
    first_item = items[0]
    first_sample = load_style_sample(style_profile_path, first_item["sample_id"])

    first_paragraph = clear_cell_to_empty_paragraph(cell)
    insert_paragraphs_after(first_paragraph, [first_item["text"]], style_paragraph=first_paragraph)
    written_first = first_paragraph.getnext()
    if written_first is not None:
        cell.remove(first_paragraph)
        first_paragraph = written_first
    apply_sample_format_to_paragraph(first_paragraph, first_sample)

    current = first_paragraph
    inserted = [{"text": paragraph_text(first_paragraph), "sample_id": first_item["sample_id"]}]
    for item in items[1:]:
        sample = load_style_sample(style_profile_path, item["sample_id"])
        insert_paragraphs_after(current, [item["text"]], style_paragraph=current)
        current = current.getnext()
        apply_sample_format_to_paragraph(current, sample)
        inserted.append({"text": item["text"], "sample_id": item["sample_id"]})

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
            "style_profile_path": style_profile_path,
            "before_text": before_text,
            "after_text": after_text,
            "inserted_paragraph_count": len(inserted),
            "paragraphs": inserted,
            "before_table": before_table,
            "after_table": table_summary(table),
        }
    )


def _validate_paragraph_items(paragraphs: list[dict]) -> list[dict]:
    if not paragraphs:
        raise ValueError("paragraphs must not be empty")
    result = []
    for index, item in enumerate(paragraphs, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"paragraphs[{index}] must be an object")
        text = item.get("text")
        sample_id = item.get("sample_id")
        if text is None:
            raise ValueError(f"paragraphs[{index}].text is required")
        if not sample_id:
            raise ValueError(f"paragraphs[{index}].sample_id is required")
        result.append({"text": str(text), "sample_id": str(sample_id)})
    return result


tools_schema = {
    "type": "function",
    "function": {
        "name": "replace_table_cell_with_styled_paragraphs",
        "description": "按表格坐标替换单元格全部内容为多段文字；每段单独指定 sample_id，适合单元格里同时包含章节标题、子标题和正文。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "table_index": {"type": "integer", "description": "第几个表格，按 //w:tbl 计数，1-based；注意嵌套表格也会计数"},
                "row_index": {"type": "integer", "description": "第几行，1-based"},
                "cell_index": {"type": "integer", "description": "第几个单元格，1-based"},
                "paragraphs": {
                    "type": "array",
                    "description": "替换后的单元格段落列表；每一项单独指定 text 和 sample_id。",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "该段落文本"},
                            "sample_id": {"type": "string", "description": "该段落要仿写的样式样本 ID，如 S001、S002、S004"},
                        },
                        "required": ["text", "sample_id"],
                    },
                },
                "style_profile_path": {"type": "string", "description": "analyze_docx_style_samples 输出的样式画像 JSON 路径"},
            },
            "required": ["docx_path", "output_path", "table_index", "row_index", "cell_index", "paragraphs", "style_profile_path"],
        },
    },
}
