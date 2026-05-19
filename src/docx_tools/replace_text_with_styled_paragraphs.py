from .common import (
    apply_sample_format_to_run,
    apply_sample_paragraph_format,
    insert_paragraphs_after,
    json_result,
    load_document_xml,
    NS,
    paragraph_location,
    paragraph_text,
    paragraphs as iter_paragraphs,
    replace_text_range_in_paragraph,
    write_document_xml,
)
from .style_profile import load_style_sample


def replace_text_with_styled_paragraphs(
    docx_path: str,
    output_path: str,
    old_text: str,
    paragraphs: list[dict],
    style_profile_path: str,
    occurrence: int = 1,
) -> str:
    """把匹配文本替换为多段文字，每段按自己的 sample_id 仿写格式。"""
    items = _validate_paragraph_items(paragraphs)
    root = load_document_xml(docx_path)
    current_occurrence = 0

    for paragraph_index, paragraph in enumerate(iter_paragraphs(root), start=1):
        logical_text = paragraph_text(paragraph)
        search_from = 0
        while True:
            hit = logical_text.find(old_text, search_from)
            if hit == -1:
                break
            current_occurrence += 1
            if current_occurrence != occurrence:
                search_from = hit + max(1, len(old_text))
                continue

            before_text = paragraph_text(paragraph)
            first_item = items[0]
            first_sample = load_style_sample(style_profile_path, first_item["sample_id"])
            change = replace_text_range_in_paragraph(paragraph, hit, hit + len(old_text), first_item["text"])
            apply_sample_paragraph_format(paragraph, first_sample)
            if change.get("run") is not None:
                apply_sample_format_to_run(change["run"], first_sample)

            current = paragraph
            inserted = [{"text": first_item["text"], "sample_id": first_item["sample_id"]}]
            for item in items[1:]:
                sample = load_style_sample(style_profile_path, item["sample_id"])
                insert_paragraphs_after(current, [item["text"]], style_paragraph=current)
                current = current.getnext()
                apply_sample_paragraph_format(current, sample)
                for run in current.xpath("./w:r", namespaces=NS):
                    apply_sample_format_to_run(run, sample)
                inserted.append({"text": item["text"], "sample_id": item["sample_id"]})

            after_text = paragraph_text(paragraph)
            change_for_result = {key: value for key, value in change.items() if key != "run"}
            write_document_xml(docx_path, output_path, root)
            return json_result(
                {
                    "status": "ok",
                    "docx_path": docx_path,
                    "output_path": output_path,
                    "old_text": old_text,
                    "style_profile_path": style_profile_path,
                    "paragraph_index": paragraph_index,
                    "location": paragraph_location(paragraph),
                    "before_paragraph_text": before_text,
                    "after_paragraph_text": after_text,
                    "inserted_paragraph_count": len(items) - 1,
                    "paragraphs": inserted,
                    "change": change_for_result,
                }
            )

    return json_result({"status": "not_found", "docx_path": docx_path, "old_text": old_text, "occurrence": occurrence})


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
        "name": "replace_text_with_styled_paragraphs",
        "description": "把指定文本替换为多段内容；每段都必须提供 text 和 sample_id，适合把占位符替换成标题、子标题、正文混合的内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "old_text": {"type": "string", "description": "要替换的原文本"},
                "paragraphs": {
                    "type": "array",
                    "description": "替换后的段落列表；每一项单独指定 text 和 sample_id。标题、子标题、正文不要共用一个 sample_id。",
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
                "occurrence": {"type": "integer", "description": "第几个匹配项，1-based，默认 1"},
            },
            "required": ["docx_path", "output_path", "old_text", "paragraphs", "style_profile_path"],
        },
    },
}
