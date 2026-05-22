from lxml import etree

try:
    from docx_tools.common import (
        json_result,
        load_document_xml,
        paragraph_location,
        paragraph_text,
        paragraphs,
        write_document_xml,
        W,
    )
    from docx_tools.style_profile import load_style_sample
    from docx_compiler.diagnostics import diagnostics_to_dicts, has_errors
    from docx_compiler.lower import filter_blocks, lower_markdown_blocks, normalize_block_support
    from docx_compiler.markdown_parser import parse_markdown_blocks
    from docx_compiler.render import render_blocks_to_container
except ModuleNotFoundError:
    from src.docx_tools.common import (
        json_result,
        load_document_xml,
        paragraph_location,
        paragraph_text,
        paragraphs,
        write_document_xml,
        W,
    )
    from src.docx_tools.style_profile import load_style_sample
    from src.docx_compiler.diagnostics import diagnostics_to_dicts, has_errors
    from src.docx_compiler.lower import filter_blocks, lower_markdown_blocks, normalize_block_support
    from src.docx_compiler.markdown_parser import parse_markdown_blocks
    from src.docx_compiler.render import render_blocks_to_container

from .common import read_markdown_text


def apply_markdown_ir_after_paragraph(
    docx_path: str,
    output_path: str,
    paragraph_index: int,
    markdown_path: str,
    style_profile_path: str,
    style_mapping: dict,
    include_block_ids: list[str] | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
) -> str:
    """把 Markdown IR 渲染到指定普通段落之后。"""
    try:
        target, content = read_markdown_text(markdown_path)
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
    paragraph_list = list(paragraphs(root))
    if paragraph_index < 1 or paragraph_index > len(paragraph_list):
        return json_result({"status": "error", "message": f"paragraph_index out of range: {paragraph_index}, paragraph_count={len(paragraph_list)}"})
    anchor = paragraph_list[paragraph_index - 1]

    try:
        style_samples = {sample_id: load_style_sample(style_profile_path, sample_id) for sample_id in sorted(lowering.style_sample_ids)}
    except (FileNotFoundError, KeyError, ValueError) as exc:
        return json_result({"status": "error", "message": str(exc), "style_profile_path": style_profile_path})

    before_text = paragraph_text(anchor)
    temp_container = etree.Element(f"{W}body", nsmap=anchor.nsmap)
    rendered = render_blocks_to_container(temp_container, lowering.layout_blocks, style_samples=style_samples)

    current = anchor
    for element in rendered:
        temp_container.remove(element)
        current.addnext(element)
        current = element

    write_document_xml(docx_path, output_path, root)
    return json_result(
        {
            "status": "ok",
            "docx_path": docx_path,
            "output_path": output_path,
            "markdown_path": str(target),
            "paragraph_index": paragraph_index,
            "style_profile_path": style_profile_path,
            "style_mapping": style_mapping,
            "include_block_ids": include_block_ids,
            "line_start": line_start,
            "line_end": line_end,
            "anchor_text": before_text,
            "anchor_location": paragraph_location(anchor),
            "written_block_count": len(lowering.render_items),
            "written_blocks": lowering.render_items,
            "layout_ir_block_count": len(lowering.layout_blocks),
            "inserted_element_count": len(rendered),
            "support_summary": lowering.support_summary,
            "diagnostics": diagnostics,
        }
    )
