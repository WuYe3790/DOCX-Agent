try:
    from docx_compiler.diagnostics import diagnostics_to_dicts, support_summary
    from docx_compiler.lower import diagnostics_for_blocks, normalize_block_support
except ModuleNotFoundError:
    from src.docx_compiler.diagnostics import diagnostics_to_dicts, support_summary
    from src.docx_compiler.lower import diagnostics_for_blocks, normalize_block_support

from .common import json_result, parse_markdown_blocks, read_markdown_text


def parse_markdown_draft(markdown_path: str) -> str:
    """把 Markdown 草稿解析成简单 IR，供模型确认样式映射和目标位置。"""
    try:
        target, content = read_markdown_text(markdown_path)
    except (FileNotFoundError, ValueError) as exc:
        return json_result({"status": "error", "message": str(exc)})

    blocks = normalize_block_support(parse_markdown_blocks(content))
    diagnostics = diagnostics_for_blocks(blocks)
    unsupported = [block for block in blocks if block.get("support") == "rejected"]
    type_counts = {}
    for block in blocks:
        block_type = block["type"]
        type_counts[block_type] = type_counts.get(block_type, 0) + 1

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
                    "raw": block["raw"],
                    "support": block.get("support", "rejected"),
                }
                for block in unsupported
            ],
            "blocks": blocks,
            "layout_ir_preview": [
                {
                    "block_id": block["block_id"],
                    "block_type": block["type"],
                    "line_start": block["line_start"],
                    "line_end": block["line_end"],
                    "runs": _preview_runs(block),
                    "table": _preview_table(block),
                    "indent": _preview_indent(block),
                    "supported": block.get("supported", True),
                    "support": block.get("support", "native"),
                    "diagnostics": [
                        diagnostic.to_dict()
                        for diagnostic in diagnostics
                        if diagnostic.block_id == block["block_id"]
                    ],
                }
                for block in blocks
            ],
            "style_mapping_hint": {
                "heading1": "章节标题样本，如 S002",
                "heading2": "子标题样本，如 S004",
                "paragraph": "正文样本，如 S001",
                "list_item": "正文样本，如 S001",
                "table_cell": "表格内普通文本样本；未提供时使用 paragraph",
                "code_block": "代码块样本；未提供时使用 paragraph",
                "formula": "公式文本 fallback 样本；未提供时使用 paragraph",
            },
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
