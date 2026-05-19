from .common import (
    apply_sample_format_to_paragraph,
    apply_sample_format_to_run,
    json_result,
    load_document_xml,
    paragraph_location,
    paragraph_text,
    paragraphs,
    replace_text_range_in_paragraph,
    split_text_for_paragraphs,
    write_document_xml,
)
from .replace_text import _following_paragraphs, _insert_extra_paragraphs
from .style_profile import load_style_sample


def replace_text_like_sample(
    docx_path: str,
    output_path: str,
    old_text: str,
    new_text: str,
    style_profile_path: str,
    sample_id: str,
    occurrence: int = 1,
    newline_mode: str = "paragraphs",
) -> str:
    """替换文本，并把新文本格式设置为指定样式样本。"""
    style_sample = load_style_sample(style_profile_path, sample_id)
    root = load_document_xml(docx_path)
    current_occurrence = 0

    for paragraph_index, paragraph in enumerate(paragraphs(root), start=1):
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
            replacement_text, extra_paragraphs = split_text_for_paragraphs(new_text, newline_mode)
            change = replace_text_range_in_paragraph(paragraph, hit, hit + len(old_text), replacement_text)
            if change.get("run") is not None:
                apply_sample_format_to_run(change["run"], style_sample)
            apply_sample_format_to_paragraph(paragraph, style_sample)
            inserted_paragraph_count = 0
            if extra_paragraphs:
                inserted_paragraph_count = _insert_extra_paragraphs(paragraph, extra_paragraphs)
                for inserted in _following_paragraphs(paragraph, inserted_paragraph_count):
                    apply_sample_format_to_paragraph(inserted, style_sample)
            after_text = paragraph_text(paragraph)
            change_for_result = {key: value for key, value in change.items() if key != "run"}
            write_document_xml(docx_path, output_path, root)
            return json_result(
                {
                    "status": "ok",
                    "docx_path": docx_path,
                    "output_path": output_path,
                    "old_text": old_text,
                    "new_text": new_text,
                    "sample_id": sample_id,
                    "style_profile_path": style_profile_path,
                    "paragraph_index": paragraph_index,
                    "location": paragraph_location(paragraph),
                    "before_paragraph_text": before_text,
                    "after_paragraph_text": after_text,
                    "inserted_paragraph_count": inserted_paragraph_count,
                    "change": change_for_result,
                }
            )

    return json_result({"status": "not_found", "docx_path": docx_path, "old_text": old_text, "occurrence": occurrence})


tools_schema = {
    "type": "function",
    "function": {
        "name": "replace_text_like_sample",
        "description": "替换指定文本，并按 style_profile_path 中的 sample_id 仿写段落和字符格式。适合标题、正文、占位符等格式敏感替换。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "old_text": {"type": "string", "description": "要替换的原文本"},
                "new_text": {"type": "string", "description": "替换后的新文本"},
                "style_profile_path": {"type": "string", "description": "analyze_docx_style_samples 输出的样式画像 JSON 路径"},
                "sample_id": {"type": "string", "description": "要仿写的样式样本 ID，如 S001"},
                "occurrence": {"type": "integer", "description": "第几个匹配项，1-based，默认 1"},
                "newline_mode": {
                    "type": "string",
                    "description": "新文本包含换行时的处理方式：paragraphs 拆成多个段落，inline 替换为空格；默认 paragraphs",
                    "enum": ["paragraphs", "inline"],
                },
            },
            "required": ["docx_path", "output_path", "old_text", "new_text", "style_profile_path", "sample_id"],
        },
    },
}
