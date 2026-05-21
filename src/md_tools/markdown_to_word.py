import json
from pathlib import Path

try:
    from docx_tools.clear_table_cell import clear_table_cell
    from docx_tools.delete_table_row import delete_table_row
    from docx_tools.insert_table_after_paragraph import insert_table_after_paragraph
    from docx_tools.insert_table_column_after import insert_table_column_after
    from docx_tools.insert_table_in_cell import insert_table_in_cell
    from docx_tools.merge_table_cells_horizontal import merge_table_cells_horizontal
    from docx_tools.set_paragraph_indent import set_paragraph_indent
except ModuleNotFoundError:
    from src.docx_tools.clear_table_cell import clear_table_cell
    from src.docx_tools.delete_table_row import delete_table_row
    from src.docx_tools.insert_table_after_paragraph import insert_table_after_paragraph
    from src.docx_tools.insert_table_column_after import insert_table_column_after
    from src.docx_tools.insert_table_in_cell import insert_table_in_cell
    from src.docx_tools.merge_table_cells_horizontal import merge_table_cells_horizontal
    from src.docx_tools.set_paragraph_indent import set_paragraph_indent

from .apply_markdown_ir_to_table_cell import apply_markdown_ir_to_table_cell
from .common import json_result


def markdown_to_word(
    docx_path: str,
    output_path: str,
    actions: list[dict],
    markdown_path: str | None = None,
    style_profile_path: str | None = None,
    style_mapping: dict | None = None,
) -> str:
    """编译型 DOCX 写入入口：把 Markdown 片段和结构动作统一编译到 Word。"""
    if not actions:
        return json_result({"status": "error", "message": "actions 不能为空"})

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_paths = _temp_paths(output, len(actions))
    current_input = docx_path
    action_results = []

    try:
        for index, action in enumerate(actions, start=1):
            current_output = output_path if index == len(actions) else str(temp_paths[index - 1])
            try:
                result = _run_action(
                    action=action,
                    action_index=index,
                    docx_path=current_input,
                    output_path=current_output,
                    default_markdown_path=markdown_path,
                    default_style_profile_path=style_profile_path,
                    default_style_mapping=style_mapping or {},
                )
            except (KeyError, TypeError, ValueError) as exc:
                result = json_result({"status": "error", "message": f"action {index} 参数错误: {exc}"})
            parsed = _parse_tool_result(result)
            action_results.append(
                {
                    "action_index": index,
                    "type": _action_type(action),
                    "status": parsed.get("status"),
                    "output_path": current_output,
                    "result": parsed,
                }
            )
            if parsed.get("status") != "ok":
                return json_result(
                    {
                        "status": "error",
                        "message": f"action {index} failed",
                        "failed_action": action,
                        "actions": action_results,
                    }
                )
            current_input = current_output
    finally:
        for temp_path in temp_paths:
            if str(temp_path) != output_path and temp_path.exists():
                temp_path.unlink()

    return json_result(
        {
            "status": "ok",
            "docx_path": docx_path,
            "output_path": output_path,
            "markdown_path": markdown_path,
            "style_profile_path": style_profile_path,
            "style_mapping": style_mapping or {},
            "action_count": len(actions),
            "actions": action_results,
        }
    )


def _run_action(
    action: dict,
    action_index: int,
    docx_path: str,
    output_path: str,
    default_markdown_path: str | None,
    default_style_profile_path: str | None,
    default_style_mapping: dict,
) -> str:
    action_type = _action_type(action)
    if action_type in {"write_table_cell", "apply_markdown_ir_to_table_cell"}:
        target = action.get("target") or action
        markdown_path = action.get("markdown_path") or default_markdown_path
        style_profile_path = action.get("style_profile_path") or default_style_profile_path
        style_mapping = action.get("style_mapping") or default_style_mapping
        missing = [
            name
            for name, value in {
                "markdown_path": markdown_path,
                "style_profile_path": style_profile_path,
                "style_mapping": style_mapping,
                "table_index": target.get("table_index"),
                "row_index": target.get("row_index"),
                "cell_index": target.get("cell_index"),
            }.items()
            if value in (None, "", {})
        ]
        if missing:
            return json_result({"status": "error", "message": f"action {action_index} 缺少参数: {', '.join(missing)}"})
        return apply_markdown_ir_to_table_cell(
            docx_path=docx_path,
            output_path=output_path,
            table_index=int(target["table_index"]),
            row_index=int(target["row_index"]),
            cell_index=int(target["cell_index"]),
            markdown_path=markdown_path,
            style_profile_path=style_profile_path,
            style_mapping=style_mapping,
            include_block_ids=action.get("include_block_ids"),
            line_start=action.get("line_start"),
            line_end=action.get("line_end"),
        )

    if action_type == "clear_table_cell":
        target = action.get("target") or action
        return clear_table_cell(
            docx_path=docx_path,
            output_path=output_path,
            table_index=int(target["table_index"]),
            row_index=int(target["row_index"]),
            cell_index=int(target["cell_index"]),
        )

    if action_type == "delete_table_row":
        target = action.get("target") or action
        return delete_table_row(
            docx_path=docx_path,
            output_path=output_path,
            table_index=int(target["table_index"]),
            row_index=int(target["row_index"]),
        )

    if action_type == "set_paragraph_indent":
        target = action.get("target") or action
        return set_paragraph_indent(
            docx_path=docx_path,
            output_path=output_path,
            paragraph_index=int(target["paragraph_index"]),
            left_twips=action.get("left_twips"),
            first_line_twips=action.get("first_line_twips"),
            hanging_twips=action.get("hanging_twips"),
        )

    if action_type == "insert_table_after_paragraph":
        target = action.get("target") or action
        return insert_table_after_paragraph(
            docx_path=docx_path,
            output_path=output_path,
            paragraph_index=int(target["paragraph_index"]),
            cell_texts=action.get("cell_texts") or [],
            column_widths_twips=action.get("column_widths_twips"),
        )

    if action_type == "insert_table_in_cell":
        target = action.get("target") or action
        return insert_table_in_cell(
            docx_path=docx_path,
            output_path=output_path,
            table_index=int(target["table_index"]),
            row_index=int(target["row_index"]),
            cell_index=int(target["cell_index"]),
            cell_texts=action.get("cell_texts") or [],
            column_widths_twips=action.get("column_widths_twips"),
        )

    if action_type == "insert_table_column_after":
        target = action.get("target") or action
        return insert_table_column_after(
            docx_path=docx_path,
            output_path=output_path,
            table_index=int(target["table_index"]),
            column_index=int(target["column_index"]),
            cell_texts=action.get("cell_texts"),
            copy_from=action.get("copy_from", "left"),
        )

    if action_type == "merge_table_cells_horizontal":
        target = action.get("target") or action
        return merge_table_cells_horizontal(
            docx_path=docx_path,
            output_path=output_path,
            table_index=int(target["table_index"]),
            row_index=int(target["row_index"]),
            start_cell_index=int(target["start_cell_index"]),
            span=int(action.get("span", target.get("span", 0))),
        )

    return json_result({"status": "error", "message": f"unsupported action type: {action_type}"})


def _action_type(action: dict) -> str:
    return str(action.get("type") or action.get("kind") or "").strip()


def _parse_tool_result(result: str) -> dict:
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"status": "error", "message": "tool returned non-json result", "raw": result}


def _temp_paths(output_path: Path, action_count: int) -> list[Path]:
    if action_count <= 1:
        return []
    return [output_path.with_name(f".{output_path.stem}.step{index}{output_path.suffix}") for index in range(1, action_count)]


tools_schema = {
    "type": "function",
    "function": {
        "name": "markdown_to_word",
        "description": "唯一的 Word 写入入口：把一个或多个 Markdown 块和结构编辑动作编译到 DOCX。底层段落、表格、缩进、清空、删行等操作由工具内部执行。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "markdown_path": {"type": "string", "description": "默认 Markdown 草稿路径；各 action 可覆盖"},
                "style_profile_path": {"type": "string", "description": "默认样式画像 JSON 路径；各 action 可覆盖"},
                "style_mapping": {
                    "type": "object",
                    "description": "默认 Markdown block 类型到 sample_id 的映射，例如 paragraph/list_item -> S001",
                    "additionalProperties": {"type": "string"},
                },
                "actions": {
                    "type": "array",
                    "description": "编译动作列表。常用 type: write_table_cell, clear_table_cell, delete_table_row, set_paragraph_indent, insert_table_after_paragraph, insert_table_in_cell, insert_table_column_after, merge_table_cells_horizontal。write_table_cell 可用 include_block_ids 或 line_start/line_end 从同一 Markdown 文件选择局部块。",
                    "items": {"type": "object", "additionalProperties": True},
                },
            },
            "required": ["docx_path", "output_path", "actions"],
        },
    },
}
