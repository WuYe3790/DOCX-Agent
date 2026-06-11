try:
    from docx_tools.common import (
        cell_text,
        get_cell_by_index,
        get_row_by_index,
        get_table_by_index,
        json_result,
        load_document_xml,
        table_summary,
        write_document_xml,
    )
    from docx_tools.style_profile import load_style_sample
    from docx_compiler.diagnostics import diagnostics_to_dicts, has_errors
    from docx_compiler.lower import filter_blocks, lower_markdown_blocks, normalize_block_support
    from docx_compiler.markdown_parser import parse_markdown_blocks
    from docx_compiler.render import render_blocks_to_container
except ModuleNotFoundError:
    from src.docx_tools.common import (
        cell_text,
        get_cell_by_index,
        get_row_by_index,
        get_table_by_index,
        json_result,
        load_document_xml,
        table_summary,
        write_document_xml,
    )
    from src.docx_tools.style_profile import load_style_sample
    from src.docx_compiler.diagnostics import diagnostics_to_dicts, has_errors
    from src.docx_compiler.lower import filter_blocks, lower_markdown_blocks, normalize_block_support
    from src.docx_compiler.markdown_parser import parse_markdown_blocks
    from src.docx_compiler.render import render_blocks_to_container

from .common import read_markdown_text


def apply_markdown_ir_to_table_cell(
    session_id: str,  # v2: 后端 dispatcher 隐式注入, LLM 不可见 (避坑 1)
    docx_path: str,
    output_path: str,
    table_index: int,
    row_index: int,
    cell_index: int,
    markdown_path: str,
    style_profile_path: str,
    style_mapping: dict,
    include_block_ids: list[str] | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
) -> str:
    """v2: 按模型提供的类型到 sample_id 映射, 把 Markdown IR 写入 Word 表格单元格 (草稿从 session_workspace/drafts/ 读)."""
    try:
        target, content = read_markdown_text(session_id, markdown_path)
    except (FileNotFoundError, ValueError) as exc:
        return json_result({"status": "error", "message": str(exc)})

    all_blocks = normalize_block_support(parse_markdown_blocks(content))
    try:
        blocks = filter_blocks(all_blocks, include_block_ids, line_start, line_end)
    except ValueError as exc:
        return json_result({"status": "error", "message": str(exc), "markdown_path": str(target)})

    lowering = lower_markdown_blocks(blocks, style_mapping)
    diagnostics = diagnostics_to_dicts(lowering.diagnostics)
    if has_errors(lowering.diagnostics):
        return json_result(
            {
                "status": "rejected_markdown",
                "message": "Markdown 语义检查失败，存在无法写入的块或缺失样式映射。",
                "markdown_path": str(target),
                "selected_block_count": len(blocks),
                "support_summary": lowering.support_summary,
                "diagnostics": diagnostics,
                "hint": "可以用 include_block_ids 或 line_start/line_end 只选择可写入的块，或补充 style_mapping。",
            }
        )

    if not lowering.render_items:
        return json_result({"status": "error", "message": "Markdown 草稿没有可写入内容", "markdown_path": str(target)})

    root = load_document_xml(docx_path)
    try:
        table = get_table_by_index(root, table_index)
        row = get_row_by_index(table, row_index)
        cell = get_cell_by_index(row, cell_index)
    except IndexError as exc:
        return json_result({"status": "error", "message": str(exc)})

    try:
        style_samples = {sample_id: load_style_sample(style_profile_path, sample_id) for sample_id in sorted(lowering.style_sample_ids)}
    except (FileNotFoundError, KeyError, ValueError) as exc:
        return json_result({"status": "error", "message": str(exc), "style_profile_path": style_profile_path})

    before_table = table_summary(table)
    before_text = cell_text(cell)
    render_blocks_to_container(cell, lowering.layout_blocks, style_samples=style_samples, clear_existing=True)

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
            "include_block_ids": include_block_ids,
            "line_start": line_start,
            "line_end": line_end,
            "before_text": before_text,
            "after_text": after_text,
            "written_block_count": len(lowering.render_items),
            "written_blocks": lowering.render_items,
            "layout_ir_block_count": len(lowering.layout_blocks),
            "support_summary": lowering.support_summary,
            "diagnostics": diagnostics,
            "before_table": before_table,
            "after_table": table_summary(table),
        }
    )


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
                "include_block_ids": {
                    "type": "array",
                    "description": "可选。只渲染指定 block_id 列表，例如 [\"B012\", \"B013\"]；未选中的表格等不支持块会被忽略",
                    "items": {"type": "string"},
                },
                "line_start": {"type": "integer", "description": "可选。只渲染 line_start 到 line_end 范围内完整包含的块"},
                "line_end": {"type": "integer", "description": "可选。只渲染 line_start 到 line_end 范围内完整包含的块"},
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
