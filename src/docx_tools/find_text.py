import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from workspace.guard import resolve_workspace_path, WorkspacePathError

from .common import json_result, load_document_xml, paragraph_location, paragraph_text, paragraphs


def find_text(session_id: str, docx_path: str, query: str) -> str:
    """v2: 在 session workspace 内的 docx 中查找指定字符串 (沙箱化)"""
    try:
        docx_path_resolved = resolve_workspace_path(session_id, docx_path, must_exist=True, must_be_file=True)
    except WorkspacePathError as e:
        return json_result({"status": "error", "code": e.code, "message": e.user_message})
    root = load_document_xml(str(docx_path_resolved))
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

    return json_result({"docx_path": str(docx_path_resolved), "query": query, "matches": matches})


tools_schema = {
    "type": "function",
    "function": {
        "name": "find_text",
        "description": "在 session workspace 内的 docx 逻辑段落文本中查找字符串，返回段落序号、字符偏移和表格定位。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "要搜索的 .docx 文件路径 (相对 workspace 根)"},
                "query": {"type": "string", "description": "要查找的文本"},
            },
            "required": ["docx_path", "query"],
        },
    },
}
