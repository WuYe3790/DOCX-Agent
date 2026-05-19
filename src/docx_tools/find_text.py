from .common import json_result, load_document_xml, paragraph_location, paragraph_text, paragraphs


def find_text(docx_path: str, query: str) -> str:
    """在拼接后的逻辑段落文本中查找指定字符串。"""
    root = load_document_xml(docx_path)
    matches = []
    for paragraph_index, paragraph in enumerate(paragraphs(root), start=1):
        text = paragraph_text(paragraph)
        start = 0
        while True:
            hit = text.find(query, start)
            if hit == -1:
                break
            matches.append(
                {
                    "paragraph_index": paragraph_index,
                    "char_start": hit,
                    "char_end": hit + len(query),
                    "paragraph_text": text,
                    "location": paragraph_location(paragraph),
                }
            )
            start = hit + max(1, len(query))

    return json_result({"docx_path": docx_path, "query": query, "matches": matches})


tools_schema = {
    "type": "function",
    "function": {
        "name": "find_text",
        "description": "在 docx 的逻辑段落文本中查找字符串，返回段落序号、字符偏移和表格定位。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "要搜索的 .docx 文件路径"},
                "query": {"type": "string", "description": "要查找的文本"},
            },
            "required": ["docx_path", "query"],
        },
    },
}
