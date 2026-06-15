from .common import (
    json_result,
    load_document_xml,
    paragraph_location,
    paragraph_text,
    paragraphs,
    replace_text_range_in_paragraph,
    write_document_xml,
    resolve_docx_io,
)


def delete_text(
    session_id: str,
    docx_path: str,
    output_path: str,
    target_text: str,
    occurrence: int = 1,
    trim_surrounding_spaces: bool = False,
) -> str:
    """删除指定文本，支持跨 run 命中，删除后清理空文本 run。"""
    input_path, output_path_resolved = resolve_docx_io(session_id, docx_path, output_path)
    root = load_document_xml(str(input_path))
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

            delete_start = hit
            delete_end = hit + len(target_text)
            if trim_surrounding_spaces:
                delete_start, delete_end = _extend_spaces(logical_text, delete_start, delete_end)

            before_text = paragraph_text(paragraph)
            change = replace_text_range_in_paragraph(paragraph, delete_start, delete_end, "")
            after_text = paragraph_text(paragraph)
            write_document_xml(str(input_path), str(output_path_resolved), root)
            return json_result(
                {
                    "status": "ok",
                    "docx_path": str(input_path),
                    "output_path": str(output_path_resolved),
                    "paragraph_index": paragraph_index,
                    "location": paragraph_location(paragraph),
                    "target_text": target_text,
                    "actual_deleted_text": logical_text[delete_start:delete_end],
                    "occurrence": occurrence,
                    "trim_surrounding_spaces": trim_surrounding_spaces,
                    "before_paragraph_text": before_text,
                    "after_paragraph_text": after_text,
                    "change": {k: v for k, v in change.items() if k != "run"},
                }
            )

    return json_result(
        {
            "status": "not_found",
            "docx_path": str(input_path),
            "target_text": target_text,
            "occurrence": occurrence,
        }
    )


def _extend_spaces(text: str, start: int, end: int):
    while start > 0 and text[start - 1].isspace():
        start -= 1
    while end < len(text) and text[end].isspace():
        end += 1
    return start, end


tools_schema = {
    "type": "function",
    "function": {
        "name": "delete_text",
        "description": "删除 docx 中的指定文本，按段落逻辑文本查找，支持目标文本跨多个 run，并清理空文本 run。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径 (相对 workspace 根)"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径 (相对 workspace 根)"},
                "target_text": {"type": "string", "description": "要删除的文本"},
                "occurrence": {"type": "integer", "description": "第几个匹配项，1-based，默认 1"},
                "trim_surrounding_spaces": {
                    "type": "boolean",
                    "description": "是否同时删除目标文本左右紧邻空白；删除占位符时可设为 true，默认 false",
                },
            },
            "required": ["docx_path", "output_path", "target_text"],
        },
    },
}
