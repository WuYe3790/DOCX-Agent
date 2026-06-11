from .common import (
    apply_sample_format_to_paragraph,
    insert_paragraphs_after,
    json_result,
    load_document_xml,
    make_paragraph_like,
    paragraph_location,
    paragraph_text,
    paragraphs,
    split_text_for_paragraphs,
    W,
    write_document_xml,
    resolve_docx_io,
)
from .insert_paragraph_after import _select_style_paragraph
from .style_profile import load_style_sample

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from workspace.guard import to_relative_path, resolve_workspace_path


def insert_paragraph_after_like_sample(
    session_id: str,
    docx_path: str,
    output_path: str,
    anchor_text: str,
    new_text: str,
    style_profile_path: str,
    sample_id: str,
    occurrence: int = 1,
    style_source: str = "previous",
    newline_mode: str = "paragraphs",
) -> str:
    """在锚点段落后插入新段落，并按指定样式样本设置格式。"""
    input_path, output_path_resolved = resolve_docx_io(session_id, docx_path, output_path)
    style_sample = load_style_sample(session_id, style_profile_path, sample_id)
    root = load_document_xml(str(input_path))
    current_occurrence = 0

    for paragraph_index, paragraph in enumerate(paragraphs(root), start=1):
        logical_text = paragraph_text(paragraph)
        if anchor_text not in logical_text:
            continue

        search_from = 0
        while True:
            hit = logical_text.find(anchor_text, search_from)
            if hit == -1:
                break
            current_occurrence += 1
            if current_occurrence != occurrence:
                search_from = hit + max(1, len(anchor_text))
                continue

            first_text, extra_paragraphs = split_text_for_paragraphs(new_text, newline_mode)
            style_paragraph = _select_style_paragraph(paragraph, style_source)
            if style_paragraph is None:
                style_paragraph = _empty_paragraph_like(paragraph)
            new_paragraph = make_paragraph_like(style_paragraph, first_text)
            paragraph.addnext(new_paragraph)
            apply_sample_format_to_paragraph(new_paragraph, style_sample)
            inserted_extra_count = insert_paragraphs_after(new_paragraph, extra_paragraphs, new_paragraph)
            current = new_paragraph
            for _ in range(inserted_extra_count):
                current = current.getnext()
                if current is not None:
                    apply_sample_format_to_paragraph(current, style_sample)
            write_document_xml(str(input_path), str(output_path_resolved), root)
            return json_result(
                {
                    "status": "ok",
                    "docx_path": to_relative_path(session_id, input_path),
                    "output_path": to_relative_path(session_id, output_path_resolved),
                    "anchor_text": anchor_text,
                    "new_text": new_text,
                    "sample_id": sample_id,
                    "style_profile_path": to_relative_path(session_id, resolve_workspace_path(session_id, style_profile_path)),
                    "anchor_paragraph_index": paragraph_index,
                    "inserted_paragraph_count": 1 + inserted_extra_count,
                    "location": paragraph_location(paragraph),
                }
            )

    return json_result({
        "status": "not_found",
        "docx_path": to_relative_path(session_id, input_path),
        "anchor_text": anchor_text,
        "occurrence": occurrence,
    })


def _empty_paragraph_like(paragraph):
    from lxml import etree

    return etree.Element(f"{W}p", nsmap=paragraph.nsmap)


tools_schema = {
    "type": "function",
    "function": {
        "name": "insert_paragraph_after_like_sample",
        "description": "在包含锚点文本的段落后新增段落，并按 style_profile_path 中的 sample_id 仿写段落和字符格式。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径 (相对 workspace 根)"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径 (相对 workspace 根)"},
                "anchor_text": {"type": "string", "description": "用于定位段落的文本"},
                "new_text": {"type": "string", "description": "新增段落文本"},
                "style_profile_path": {"type": "string", "description": "analyze_docx_style_samples 输出的样式画像 JSON 路径"},
                "sample_id": {"type": "string", "description": "要仿写的样式样本 ID，如 S001"},
                "occurrence": {"type": "integer", "description": "第几个匹配项，1-based，默认 1"},
                "style_source": {
                    "type": "string",
                    "description": "段落骨架来源：previous 复制锚点段落，next 复制后一段，empty 不复制段落/run 样式；默认 previous",
                    "enum": ["previous", "next", "empty"],
                },
                "newline_mode": {
                    "type": "string",
                    "description": "新增文本包含换行时的处理方式：paragraphs 拆成多个连续段落，inline 替换为空格；默认 paragraphs",
                    "enum": ["paragraphs", "inline"],
                },
            },
            "required": ["docx_path", "output_path", "anchor_text", "new_text", "style_profile_path", "sample_id"],
        },
    },
}
