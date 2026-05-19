try:
    from docx_tools.common import (
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
        table_summary,
        write_document_xml,
    )
    from docx_tools.style_profile import load_style_sample
except ModuleNotFoundError:
    from src.docx_tools.common import (
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
        table_summary,
        write_document_xml,
    )
    from src.docx_tools.style_profile import load_style_sample

from .common import parse_markdown_blocks, read_markdown_text


SUPPORTED_TYPES = {"heading1", "heading2", "paragraph", "list_item"}


def apply_markdown_ir_to_table_cell(
    docx_path: str,
    output_path: str,
    table_index: int,
    row_index: int,
    cell_index: int,
    markdown_path: str,
    style_profile_path: str,
    style_mapping: dict,
) -> str:
    """按模型提供的类型到 sample_id 映射，把 Markdown IR 写入 Word 表格单元格。"""
    try:
        target, content = read_markdown_text(markdown_path)
    except (FileNotFoundError, ValueError) as exc:
        return json_result({"status": "error", "message": str(exc)})

    blocks = parse_markdown_blocks(content)
    unsupported = [block for block in blocks if block["type"] not in SUPPORTED_TYPES or not block.get("supported", True)]
    if unsupported:
        return json_result(
            {
                "status": "unsupported_markdown",
                "message": "第一版暂不支持 Markdown 表格、代码块等复杂块；请先改成标题、正文或列表。",
                "markdown_path": str(target),
                "unsupported_blocks": [
                    {
                        "block_id": block["block_id"],
                        "type": block["type"],
                        "line_start": block["line_start"],
                        "line_end": block["line_end"],
                        "raw": block["raw"],
                    }
                    for block in unsupported
                ],
            }
        )

    render_items = []
    for block in blocks:
        block_type = block["type"]
        sample_id = style_mapping.get(block_type)
        if not sample_id:
            return json_result(
                {
                    "status": "error",
                    "message": f"style_mapping 缺少 {block_type}",
                    "required_mapping_keys": sorted({block["type"] for block in blocks}),
                }
            )
        render_items.append(
            {
                "block_id": block["block_id"],
                "type": block_type,
                "text": _render_text(block),
                "sample_id": sample_id,
            }
        )

    if not render_items:
        return json_result({"status": "error", "message": "Markdown 草稿没有可写入内容", "markdown_path": str(target)})

    root = load_document_xml(docx_path)
    try:
        table = get_table_by_index(root, table_index)
        row = get_row_by_index(table, row_index)
        cell = get_cell_by_index(row, cell_index)
    except IndexError as exc:
        return json_result({"status": "error", "message": str(exc)})

    before_table = table_summary(table)
    before_text = cell_text(cell)
    first_item = render_items[0]
    first_sample = load_style_sample(style_profile_path, first_item["sample_id"])
    paragraph = clear_cell_to_empty_paragraph(cell)
    append_run_to_paragraph(paragraph, first_item["text"])
    apply_sample_format_to_paragraph(paragraph, first_sample)

    current = paragraph
    for item in render_items[1:]:
        insert_paragraphs_after(current, [item["text"]], style_paragraph=current)
        current = current.getnext()
        sample = load_style_sample(style_profile_path, item["sample_id"])
        apply_sample_format_to_paragraph(current, sample)

    after_text = cell_text(cell)
    write_document_xml(docx_path, output_path, root)
    return json_result(
        {
            "status": "ok",
            "docx_path": docx_path,
            "output_path": output_path,
            "markdown_path": str(target),
            "table_index": table_index,
            "row_index": row_index,
            "cell_index": cell_index,
            "style_profile_path": style_profile_path,
            "style_mapping": style_mapping,
            "before_text": before_text,
            "after_text": after_text,
            "written_block_count": len(render_items),
            "written_blocks": render_items,
            "before_table": before_table,
            "after_table": table_summary(table),
        }
    )


def _render_text(block: dict) -> str:
    if block["type"] == "list_item":
        marker = block.get("marker") or "-"
        return f"{marker} {block['text']}"
    return block["text"]


tools_schema = {
    "type": "function",
    "function": {
        "name": "apply_markdown_ir_to_table_cell",
        "description": "把 Markdown 草稿解析成 IR 后写入指定 Word 表格单元格；模型必须提供类型到 sample_id 的 style_mapping。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "table_index": {"type": "integer", "description": "第几个表格，按 //w:tbl 计数，1-based；注意嵌套表格也会计数"},
                "row_index": {"type": "integer", "description": "第几行，1-based"},
                "cell_index": {"type": "integer", "description": "第几个单元格，1-based"},
                "markdown_path": {"type": "string", "description": "out/drafts 中的 Markdown 草稿路径"},
                "style_profile_path": {"type": "string", "description": "analyze_docx_style_samples 输出的样式画像 JSON 路径"},
                "style_mapping": {
                    "type": "object",
                    "description": "Markdown IR 类型到样式样本 ID 的映射，例如 heading1->S002, heading2->S004, paragraph/list_item->S001",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": [
                "docx_path",
                "output_path",
                "table_index",
                "row_index",
                "cell_index",
                "markdown_path",
                "style_profile_path",
                "style_mapping",
            ],
        },
    },
}
