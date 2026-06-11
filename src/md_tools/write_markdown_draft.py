from .common import draft_path, json_result


def write_markdown_draft(
    session_id: str,  # v2: 后端 dispatcher 隐式注入, LLM 不可见 (避坑 1)
    output_path: str,
    content: str,
    overwrite: bool = True,
) -> str:
    """v2: 把模型生成的 Markdown 草稿写入 session_workspace/drafts/ (沙箱化)."""
    try:
        target = draft_path(session_id, output_path)
    except ValueError as exc:
        return json_result({"status": "error", "message": str(exc)})
    if target.exists() and not overwrite:
        return json_result({"status": "error", "message": f"草稿已存在: {target}"})
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return json_result(
        {
            "status": "ok",
            "markdown_path": str(target),
            "line_count": len(lines),
            "char_count": len(content),
            "preview": "\n".join(lines[:20]),
        }
    )


tools_schema = {
    "type": "function",
    "function": {
        "name": "write_markdown_draft",
        "description": "把待写入 Word 的内容先写成 Markdown 草稿，文件只能放在 out/drafts 目录。适合先生成可审核内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "output_path": {"type": "string", "description": "Markdown 草稿路径；可传文件名，默认写入 out/drafts，必须为 .md"},
                "content": {"type": "string", "description": "完整 Markdown 草稿内容"},
                "overwrite": {"type": "boolean", "description": "目标已存在时是否覆盖；默认 true"},
            },
            "required": ["output_path", "content"],
        },
    },
}
