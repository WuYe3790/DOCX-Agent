try:
    from docx_compiler.diagnostics import diagnostics_to_dicts, support_summary
    from docx_compiler.lower import diagnostics_for_blocks, normalize_block_support
    from docx_compiler.markdown_parser import blocks_to_dicts, parse_markdown_blocks
except ModuleNotFoundError:
    from src.docx_compiler.diagnostics import diagnostics_to_dicts, support_summary
    from src.docx_compiler.lower import diagnostics_for_blocks, normalize_block_support
    from src.docx_compiler.markdown_parser import blocks_to_dicts, parse_markdown_blocks

from pathlib import Path

from .common import json_result, read_markdown_text


def parse_markdown_draft(
    session_id: str,  # v2: 后端 dispatcher 隐式注入, LLM 不可见 (避坑 1)
    markdown_path: str,
) -> str:
    """v2: 解析 session_dir/drafts/ 下的 Markdown 草稿成 IR."""
    try:
        session_dir = Path("out") / "sessions" / session_id
        target, content = read_markdown_text(markdown_path, session_dir)
    except (FileNotFoundError, ValueError) as exc:
        return json_result({"status": "error", "message": str(exc)})

    ast_blocks = normalize_block_support(parse_markdown_blocks(content))
    blocks = blocks_to_dicts(ast_blocks)
    diagnostics = diagnostics_for_blocks(ast_blocks)
    unsupported = [block for block in blocks if block.get("support") == "rejected"]
    type_counts = {}
    for block in blocks:
        block_type = block["type"]
        type_counts[block_type] = type_counts.get(block_type, 0) + 1

    # 过滤掉每个 block 的冗余字段，保留必要信息
    blocks_filtered = [
        {k: v for k, v in block.items() if k != "raw"}
        for block in blocks
    ]

    return json_result(
        {
            "status": "ok",
            "markdown_path": str(target),
            "block_count": len(blocks),
            "type_counts": type_counts,
            "unsupported_block_count": len(unsupported),
            "support_summary": support_summary(blocks),
            "diagnostics": diagnostics_to_dicts(diagnostics),
            "unsupported_blocks": [
                {
                    "block_id": block["block_id"],
                    "type": block["type"],
                    "line_start": block["line_start"],
                    "line_end": block["line_end"],
                    "support": block.get("support", "rejected"),
                }
                for block in unsupported
            ],
            "blocks": blocks_filtered,
        }
    )


tools_schema = {
    "type": "function",
    "function": {
        "name": "parse_markdown_draft",
        "description": "把 out/drafts 中的 Markdown 草稿解析成 IR。只做语法识别，不决定 Word 样式；模型需要基于 IR 决定 style_mapping。",
        "parameters": {
            "type": "object",
            "properties": {
                "markdown_path": {"type": "string", "description": "Markdown 草稿路径，必须位于 out/drafts"},
            },
            "required": ["markdown_path"],
        },
    },
}


def _preview_runs(block: dict) -> list[dict]:
    if block["type"] == "table":
        return []
    if block["type"] == "formula_block":
        return [{"kind": "text", "text": block.get("text", "")}]
    text = block.get("text") or ""
    if block["type"] == "list_item":
        marker = block.get("marker") or "-"
        text = f"{marker} {text}"
    runs = []
    parts = text.split("\t")
    for index, part in enumerate(parts):
        if part:
            runs.append({"kind": "text", "text": part})
        if index < len(parts) - 1:
            runs.append({"kind": "tab"})
    return runs


def _preview_indent(block: dict) -> dict | None:
    if block["type"] != "list_item":
        return None
    level = int(block.get("indent_level", 0))
    return {"left_twips": 360 * (level + 1), "hanging_twips": 180}


def _preview_table(block: dict) -> dict | None:
    if block["type"] != "table":
        return None
    return {
        "row_count": len(block.get("rows") or []),
        "column_count": block.get("column_count", 0),
        "rows": block.get("rows") or [],
    }
