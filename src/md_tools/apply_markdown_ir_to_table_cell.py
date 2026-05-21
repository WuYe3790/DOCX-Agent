try:
    from docx_tools.common import (
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
    from docx_tools.style_profile import load_style_sample
    from docx_compiler.ir import CellIR, ParagraphIR, RunIR, TableIR, TableRowIR
    from docx_compiler.render import render_blocks_to_container
except ModuleNotFoundError:
    from src.docx_tools.common import (
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
    from src.docx_tools.style_profile import load_style_sample
    from src.docx_compiler.ir import CellIR, ParagraphIR, RunIR, TableIR, TableRowIR
    from src.docx_compiler.render import render_blocks_to_container

from .common import parse_markdown_blocks, read_markdown_text


SUPPORTED_TYPES = {"heading1", "heading2", "paragraph", "list_item", "table"}


def apply_markdown_ir_to_table_cell(
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
    """按模型提供的类型到 sample_id 映射，把 Markdown IR 写入 Word 表格单元格。"""
    try:
        target, content = read_markdown_text(markdown_path)
    except (FileNotFoundError, ValueError) as exc:
        return json_result({"status": "error", "message": str(exc)})

    all_blocks = parse_markdown_blocks(content)
    try:
        blocks = _filter_blocks(all_blocks, include_block_ids, line_start, line_end)
    except ValueError as exc:
        return json_result({"status": "error", "message": str(exc), "markdown_path": str(target)})

    unsupported = [block for block in blocks if block["type"] not in SUPPORTED_TYPES or not block.get("supported", True)]
    if unsupported:
        return json_result(
            {
                "status": "unsupported_markdown",
                "message": "暂不支持代码块、HTML 等复杂块；Markdown 表格、标题、正文和列表可直接编译。",
                "markdown_path": str(target),
                "selected_block_count": len(blocks),
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
                "hint": "可以用 include_block_ids 或 line_start/line_end 只选择不含表格的块，或用 write_markdown_draft 生成简化片段。",
            }
        )

    render_items, style_sample_ids = _build_render_items(blocks, style_mapping)
    if isinstance(render_items, str):
        return render_items
    if not render_items:
        return json_result({"status": "error", "message": "Markdown 草稿没有可写入内容", "markdown_path": str(target)})

    root = load_document_xml(docx_path)
    try:
        table = get_table_by_index(root, table_index)
        row = get_row_by_index(table, row_index)
        cell = get_cell_by_index(row, cell_index)
    except IndexError as exc:
        return json_result({"status": "error", "message": str(exc)})

    try:
        style_samples = {sample_id: load_style_sample(style_profile_path, sample_id) for sample_id in sorted(style_sample_ids)}
    except (FileNotFoundError, KeyError, ValueError) as exc:
        return json_result({"status": "error", "message": str(exc), "style_profile_path": style_profile_path})

    before_table = table_summary(table)
    before_text = cell_text(cell)
    layout_blocks = _items_to_layout_ir(render_items)

    clear_cell_to_empty_paragraph(cell)
    render_blocks_to_container(cell, layout_blocks, style_samples=style_samples, clear_existing=True)

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
            "written_block_count": len(render_items),
            "written_blocks": render_items,
            "layout_ir_block_count": len(layout_blocks),
            "before_table": before_table,
            "after_table": table_summary(table),
        }
    )


def _build_render_items(blocks: list[dict], style_mapping: dict):
    render_items = []
    style_sample_ids = set()
    for block in blocks:
        block_type = block["type"]
        sample_id = _sample_id_for_block(block, style_mapping)
        if not sample_id:
            return (
                json_result(
                    {
                        "status": "error",
                        "message": f"style_mapping 缺少 {block_type}",
                        "required_mapping_keys": sorted({block["type"] for block in blocks}),
                    }
                ),
                style_sample_ids,
            )
        if sample_id:
            style_sample_ids.add(sample_id)
        render_items.append(
            {
                "block_id": block["block_id"],
                "type": block_type,
                "text": _render_text(block),
                "sample_id": sample_id,
                "line_start": block["line_start"],
                "line_end": block["line_end"],
                "indent_level": block.get("indent_level", 0),
                "marker": block.get("marker"),
                "rows": block.get("rows"),
                "column_count": block.get("column_count"),
            }
        )
    return render_items, style_sample_ids


def _sample_id_for_block(block: dict, style_mapping: dict) -> str | None:
    block_type = block["type"]
    if block_type == "table":
        return style_mapping.get("table_cell") or style_mapping.get("paragraph") or style_mapping.get("table")
    return style_mapping.get(block_type)


def _filter_blocks(
    blocks: list[dict],
    include_block_ids: list[str] | None,
    line_start: int | None,
    line_end: int | None,
) -> list[dict]:
    if include_block_ids and (line_start is not None or line_end is not None):
        raise ValueError("include_block_ids 和 line_start/line_end 不能同时使用")
    if line_start is not None and line_end is not None and line_end < line_start:
        raise ValueError("line_end must be >= line_start")

    if include_block_ids:
        wanted = {str(block_id) for block_id in include_block_ids}
        selected = [block for block in blocks if block["block_id"] in wanted]
        missing = sorted(wanted - {block["block_id"] for block in selected})
        if missing:
            raise ValueError(f"include_block_ids not found: {', '.join(missing)}")
        return selected

    if line_start is not None or line_end is not None:
        start = line_start if line_start is not None else 1
        end = line_end if line_end is not None else 10**9
        return [block for block in blocks if block["line_start"] >= start and block["line_end"] <= end]

    return blocks


def _render_text(block: dict) -> str:
    if block["type"] == "list_item":
        marker = block.get("marker") or "-"
        return f"{marker} {block['text']}"
    return block["text"]


def _items_to_layout_ir(items: list[dict]) -> list[ParagraphIR | TableIR]:
    blocks = []
    previous = None
    for item in items:
        if previous is not None and item["line_start"] > previous["line_end"] + 1:
            blocks.append(ParagraphIR(runs=[]))
        if item["type"] == "table":
            blocks.append(_item_to_table_ir(item))
        else:
            blocks.append(
                ParagraphIR(
                    runs=_parse_inline_runs(item["text"]),
                    style_sample_id=item["sample_id"],
                    block_id=item["block_id"],
                    block_type=item["type"],
                    line_start=item["line_start"],
                    line_end=item["line_end"],
                    list_level=int(item.get("indent_level", 0)) if item["type"] == "list_item" else None,
                list_marker=item.get("marker"),
                )
            )
        previous = item
    return blocks


def _item_to_table_ir(item: dict) -> TableIR:
    rows = []
    for row in item.get("rows") or []:
        cells = []
        for cell in row:
            text = cell.get("text", "") if isinstance(cell, dict) else str(cell)
            cells.append(
                CellIR(
                    blocks=[
                        ParagraphIR(
                            runs=_parse_inline_runs(text),
                            style_sample_id=item.get("sample_id"),
                            block_id=item["block_id"],
                            block_type="table_cell",
                            line_start=item["line_start"],
                            line_end=item["line_end"],
                        )
                    ]
                )
            )
        rows.append(TableRowIR(cells=cells))
    return TableIR(rows=rows)


def _parse_inline_runs(text: str) -> list[RunIR]:
    """解析最小 Markdown 加粗语法；未闭合的 ** 按普通文本处理。"""
    runs = []
    cursor = 0
    while cursor < len(text):
        start = text.find("**", cursor)
        if start == -1:
            _append_text_runs(runs, text[cursor:], bold=False)
            break
        if start > cursor:
            _append_text_runs(runs, text[cursor:start], bold=False)
        end = text.find("**", start + 2)
        if end == -1:
            _append_text_runs(runs, text[start:], bold=False)
            break
        _append_text_runs(runs, text[start + 2 : end], bold=True)
        cursor = end + 2
    return runs


def _append_text_runs(runs: list[RunIR], text: str, bold: bool) -> None:
    token = []
    for char in text:
        if char == "\t":
            if token:
                runs.append(RunIR.text_run("".join(token), bold=bold))
                token = []
            runs.append(RunIR.tab())
        elif char == "\n":
            if token:
                runs.append(RunIR.text_run("".join(token), bold=bold))
                token = []
            runs.append(RunIR.line_break())
        else:
            token.append(char)
    if token:
        runs.append(RunIR.text_run("".join(token), bold=bold))


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
