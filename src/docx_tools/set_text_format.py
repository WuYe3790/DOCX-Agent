from .common import (
    apply_format_policy_to_run,
    cleanup_empty_text_runs,
    isolate_text_range_in_paragraph,
    json_result,
    load_document_xml,
    paragraph_location,
    paragraph_text,
    paragraphs,
    write_document_xml,
)


def set_text_format(
    docx_path: str,
    output_path: str,
    target_text: str,
    occurrence: int = 1,
    format_policy: str = "custom",
    color: str | None = None,
    bold: bool | None = None,
    font_size_half_points: int | None = None,
    font_size_pt: float | None = None,
) -> str:
    """对指定文本应用字符格式，必要时会拆分 run 以只影响目标文本。"""
    root = load_document_xml(docx_path)
    current_occurrence = 0

    for paragraph_index, paragraph in enumerate(paragraphs(root), start=1):
        logical_text = paragraph_text(paragraph)
        search_from = 0
        while True:
            hit = logical_text.find(target_text, search_from)
            if hit == -1:
                break
            current_occurrence += 1
            if current_occurrence != occurrence:
                search_from = hit + max(1, len(target_text))
                continue

            before_text = paragraph_text(paragraph)
            runs = isolate_text_range_in_paragraph(paragraph, hit, hit + len(target_text))
            for run in runs:
                apply_format_policy_to_run(
                    run,
                    format_policy,
                    color=color,
                    bold=bold,
                    font_size_half_points=font_size_half_points,
                    font_size_pt=font_size_pt,
                )
            cleanup_empty_text_runs(paragraph)
            after_text = paragraph_text(paragraph)
            write_document_xml(docx_path, output_path, root)
            return json_result(
                {
                    "status": "ok",
                    "docx_path": docx_path,
                    "output_path": output_path,
                    "paragraph_index": paragraph_index,
                    "location": paragraph_location(paragraph),
                    "target_text": target_text,
                    "occurrence": occurrence,
                    "format_policy": format_policy,
                    "formatted_run_count": len(runs),
                    "before_paragraph_text": before_text,
                    "after_paragraph_text": after_text,
                }
            )

    return json_result(
        {
            "status": "not_found",
            "docx_path": docx_path,
            "target_text": target_text,
            "occurrence": occurrence,
        }
    )


tools_schema = {
    "type": "function",
    "function": {
        "name": "set_text_format",
        "description": "设置指定文本的字符格式。支持按逻辑段落文本查找，必要时拆分 run，只影响目标文本。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "target_text": {"type": "string", "description": "要设置格式的文本"},
                "occurrence": {"type": "integer", "description": "第几个匹配项，1-based，默认 1"},
                "format_policy": {
                    "type": "string",
                    "description": "格式策略：clear 清除直接格式，body 转正文格式，custom 使用显式格式；默认 custom",
                    "enum": ["clear", "body", "custom"],
                },
                "color": {"type": "string", "description": "custom 策略下的 RGB 颜色，如 FF0000 或 #FF0000"},
                "bold": {"type": "boolean", "description": "custom 策略下是否加粗"},
                "font_size_half_points": {"type": "integer", "description": "字号，单位为半磅，如 24 表示 12 磅"},
                "font_size_pt": {"type": "number", "description": "字号，单位为磅，如 12"},
            },
            "required": ["docx_path", "output_path", "target_text"],
        },
    },
}

