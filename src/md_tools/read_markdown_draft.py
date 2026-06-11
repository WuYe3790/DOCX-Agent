from .common import json_result, read_markdown_text


def read_markdown_draft(
    session_id: str,  # v2: 后端 dispatcher 隐式注入, LLM 不可见 (避坑 1)
    markdown_path: str,
    with_line_numbers: bool = True,
) -> str:
    """v2: 读取 session_workspace/drafts/ 下的 Markdown 草稿."""
    try:
        target, content = read_markdown_text(session_id, markdown_path)
    except (FileNotFoundError, ValueError) as exc:
        return json_result({"status": "error", "message": str(exc)})

    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if with_line_numbers:
        display = "\n".join(f"{index:04d}: {line}" for index, line in enumerate(lines, start=1))
    else:
        display = content
    return json_result(
        {
            "status": "ok",
            "markdown_path": str(target),
            "line_count": len(lines),
            "content": display,
        }
    )


tools_schema = {
    "type": "function",
    "function": {
        "name": "read_markdown_draft",
        "description": "读取 out/drafts 中的 Markdown 草稿，可返回带行号文本，方便审核和定位。",
        "parameters": {
            "type": "object",
            "properties": {
                "markdown_path": {"type": "string", "description": "Markdown 草稿路径，必须位于 out/drafts"},
                "with_line_numbers": {"type": "boolean", "description": "是否返回行号；默认 true"},
            },
            "required": ["markdown_path"],
        },
    },
}
