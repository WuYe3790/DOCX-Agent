from .common import (
    apply_sample_format_to_paragraph,
    json_result,
    load_document_xml,
    make_paragraph_like,
    paragraph_location,
    paragraph_text,
    paragraphs as iter_paragraphs,
    W,
    write_document_xml,
)
from .insert_paragraph_after import _select_style_paragraph
from .style_profile import load_style_sample


def insert_paragraphs_after_with_samples(
    docx_path: str,
    output_path: str,
    anchor_text: str,
    paragraphs: list[dict],
    style_profile_path: str,
    occurrence: int = 1,
    style_source: str = "previous",
) -> str:
    """在锚点段落后插入多段文字，每段按自己的 sample_id 仿写格式。"""
    items = _validate_paragraph_items(paragraphs)
    root = load_document_xml(docx_path)
    current_occurrence = 0

    for paragraph_index, anchor_paragraph in enumerate(iter_paragraphs(root), start=1):
        logical_text = paragraph_text(anchor_paragraph)
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

            style_paragraph = _select_style_paragraph(anchor_paragraph, style_source)
            if style_paragraph is None:
                style_paragraph = _empty_paragraph_like(anchor_paragraph)

            inserted = []
            current = anchor_paragraph
            for item in items:
                style_sample = load_style_sample(style_profile_path, item["sample_id"])
                new_paragraph = make_paragraph_like(style_paragraph, item["text"])
                current.addnext(new_paragraph)
                apply_sample_format_to_paragraph(new_paragraph, style_sample)
                inserted.append({"text": item["text"], "sample_id": item["sample_id"]})
                current = new_paragraph

            write_document_xml(docx_path, output_path, root)
            return json_result(
                {
                    "status": "ok",
                    "docx_path": docx_path,
                    "output_path": output_path,
                    "anchor_text": anchor_text,
                    "style_profile_path": style_profile_path,
                    "anchor_paragraph_index": paragraph_index,
                    "inserted_paragraph_count": len(inserted),
                    "inserted_paragraphs": inserted,
                    "location": paragraph_location(anchor_paragraph),
                }
            )

    return json_result({"status": "not_found", "docx_path": docx_path, "anchor_text": anchor_text, "occurrence": occurrence})


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


def _empty_paragraph_like(paragraph):
    from lxml import etree

    return etree.Element(f"{W}p", nsmap=paragraph.nsmap)


tools_schema = {
    "type": "function",
    "function": {
        "name": "insert_paragraphs_after_with_samples",
        "description": "在锚点段落后一次插入多段内容；每段都必须提供 text 和 sample_id，适合标题、子标题、正文混合的大块写入。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "anchor_text": {"type": "string", "description": "用于定位段落的文本"},
                "paragraphs": {
                    "type": "array",
                    "description": "要插入的段落列表；每一项单独指定 text 和 sample_id。标题用标题样本，正文用正文样本。",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "该段落文本"},
                            "sample_id": {"type": "string", "description": "该段落要仿写的样式样本 ID，如 S001、S004"},
                        },
                        "required": ["text", "sample_id"],
                    },
                },
                "style_profile_path": {"type": "string", "description": "analyze_docx_style_samples 输出的样式画像 JSON 路径"},
                "occurrence": {"type": "integer", "description": "第几个匹配项，1-based，默认 1"},
                "style_source": {
                    "type": "string",
                    "description": "段落骨架来源：previous 复制锚点段落，next 复制后一段，empty 不复制段落/run 样式；默认 previous",
                    "enum": ["previous", "next", "empty"],
                },
            },
            "required": ["docx_path", "output_path", "anchor_text", "paragraphs", "style_profile_path"],
        },
    },
}
