import json
from pathlib import Path

try:
    from docx_tools.clear_table_cell import clear_table_cell
    from docx_tools.delete_table_row import delete_table_row
    from docx_tools.delete_text import delete_text
    from docx_tools.insert_paragraph_after import insert_paragraph_after
    from docx_tools.insert_paragraph_after_like_sample import insert_paragraph_after_like_sample
    from docx_tools.insert_table_after_paragraph import insert_table_after_paragraph
    from docx_tools.insert_table_column_after import insert_table_column_after
    from docx_tools.insert_table_in_cell import insert_table_in_cell
    from docx_tools.insert_table_row_after import insert_table_row_after
    from docx_tools.insert_text_at import insert_text_at
    from docx_tools.insert_text_in_table_cell import insert_text_in_table_cell
    from docx_tools.merge_table_cells_horizontal import merge_table_cells_horizontal
    from docx_tools.replace_table_cell_like_sample import replace_table_cell_like_sample
    from docx_tools.replace_table_cell_text import replace_table_cell_text
    from docx_tools.replace_text import replace_text
    from docx_tools.replace_text_like_sample import replace_text_like_sample
    from docx_tools.set_paragraph_indent import set_paragraph_indent
    from docx_tools.set_text_format import set_text_format
except ModuleNotFoundError:
    from src.docx_tools.clear_table_cell import clear_table_cell
    from src.docx_tools.delete_table_row import delete_table_row
    from src.docx_tools.delete_text import delete_text
    from src.docx_tools.insert_paragraph_after import insert_paragraph_after
    from src.docx_tools.insert_paragraph_after_like_sample import insert_paragraph_after_like_sample
    from src.docx_tools.insert_table_after_paragraph import insert_table_after_paragraph
    from src.docx_tools.insert_table_column_after import insert_table_column_after
    from src.docx_tools.insert_table_in_cell import insert_table_in_cell
    from src.docx_tools.insert_table_row_after import insert_table_row_after
    from src.docx_tools.insert_text_at import insert_text_at
    from src.docx_tools.insert_text_in_table_cell import insert_text_in_table_cell
    from src.docx_tools.merge_table_cells_horizontal import merge_table_cells_horizontal
    from src.docx_tools.replace_table_cell_like_sample import replace_table_cell_like_sample
    from src.docx_tools.replace_table_cell_text import replace_table_cell_text
    from src.docx_tools.replace_text import replace_text
    from src.docx_tools.replace_text_like_sample import replace_text_like_sample
    from src.docx_tools.set_paragraph_indent import set_paragraph_indent
    from src.docx_tools.set_text_format import set_text_format

from .apply_markdown_ir_after_paragraph import apply_markdown_ir_after_paragraph
from .apply_markdown_ir_to_table_cell import apply_markdown_ir_to_table_cell
from .common import json_result


TABLE_SHAPE_ALIASES = {"rows", "cols", "n_rows", "n_cols", "rows_count", "cols_count"}
ACTION_GUIDE = """
常用 actions:
- 写 Markdown: write_markdown_after_paragraph(target.paragraph_index), write_markdown_to_table_cell(target.table_index,row_index,cell_index)。可用 include_block_ids 或 line_start/line_end 选择局部块。
- 文本: delete_text(target_text), replace_text(old_text,new_text), insert_text_at(anchor_text,insert_text)。
- 表格: insert_table_after_paragraph(target.paragraph_index,cell_texts), insert_table_in_cell(target.table_index,row_index,cell_index,cell_texts), insert_table_row_after, insert_table_column_after, merge_table_cells_horizontal, clear_table_cell, delete_table_row。
- 格式: set_text_format(target_text), set_paragraph_indent(target.paragraph_index)。
规则: 删除占位文字优先用 delete_text；创建表格只用 cell_texts，不要用 rows/n_rows/rows_count；不要把 temporary_output_path 当作下一次输入。
""".strip()


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
        return json_result({"status": "error", "message": "actions 不能为空", "action_guide": ACTION_GUIDE})

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_paths = _temp_paths(output, len(actions))
    current_input = docx_path
    action_results = []
    diagnostics = []
    support_summary = {"native": 0, "degraded": 0, "rejected": 0}

    try:
        for index, action in enumerate(actions, start=1):
            is_final_action = index == len(actions)
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
                result = json_result({"status": "error", "message": f"action {index} 参数错误: {exc}", "action_guide": ACTION_GUIDE})
            parsed = _parse_tool_result(result)
            action_type = _action_type(action)
            for diagnostic in parsed.get("diagnostics") or []:
                item = dict(diagnostic)
                item["action_index"] = index
                item["action_type"] = action_type
                diagnostics.append(item)
            for key, value in (parsed.get("support_summary") or {}).items():
                if key in support_summary:
                    support_summary[key] += int(value)
            action_results.append(
                {
                    "action_index": index,
                    "type": action_type,
                    "status": parsed.get("status"),
                    "output_path": current_output if is_final_action else None,
                    "temporary_output_path": None if is_final_action else current_output,
                    "temporary_output_cleaned": not is_final_action,
                    "result": _response_result(parsed, is_final_action, current_output),
                }
            )
            if parsed.get("status") != "ok":
                return json_result(
                    {
                        "status": "error",
                        "message": f"action {index} failed",
                        "failed_action": action,
                        "diagnostics": diagnostics,
                        "support_summary": support_summary,
                        "actions": action_results,
                        "action_guide": ACTION_GUIDE,
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
            "diagnostics": diagnostics,
            "support_summary": support_summary,
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
    payload = _action_payload(action)
    if not payload.get("style_profile_path") and default_style_profile_path:
        payload["style_profile_path"] = default_style_profile_path

    if action_type == "write_markdown_to_table_cell":
        return _run_markdown_table_cell_action(
            payload,
            action_index,
            docx_path,
            output_path,
            default_markdown_path,
            default_style_profile_path,
            default_style_mapping,
        )
    if action_type == "write_markdown_after_paragraph":
        return _run_markdown_after_paragraph_action(
            payload,
            action_index,
            docx_path,
            output_path,
            default_markdown_path,
            default_style_profile_path,
            default_style_mapping,
        )

    if action_type in TABLE_ACTIONS:
        invalid = sorted(TABLE_SHAPE_ALIASES & set(payload))
        if invalid:
            return json_result(
                {
                    "status": "error",
                    "message": f"action {action_index} 不支持参数: {', '.join(invalid)}；请使用 cell_texts",
                    "action_guide": ACTION_GUIDE,
                }
            )
        if "cell_texts" in TABLE_ACTIONS[action_type]["required"] and not payload.get("cell_texts"):
            return json_result({"status": "error", "message": f"action {action_index} 缺少参数: cell_texts；cell_texts 不能为空"})

    spec = ACTIONS.get(action_type)
    if spec is None:
        return json_result({"status": "error", "message": f"unsupported action type: {action_type}", "action_guide": ACTION_GUIDE})
    validation_payload = {**payload, "__allow_empty_required__": spec.get("allow_empty_required", [])}
    missing = _missing_required(validation_payload, spec["required"])
    if missing:
        return json_result({"status": "error", "message": f"action {action_index} 缺少参数: {', '.join(missing)}", "action_guide": ACTION_GUIDE})
    kwargs = _kwargs_for_action(payload, spec["required"], spec["optional"])
    return spec["func"](docx_path=docx_path, output_path=output_path, **kwargs)


def _run_markdown_table_cell_action(
    payload: dict,
    action_index: int,
    docx_path: str,
    output_path: str,
    default_markdown_path: str | None,
    default_style_profile_path: str | None,
    default_style_mapping: dict,
) -> str:
    markdown_path = payload.get("markdown_path") or default_markdown_path
    style_profile_path = payload.get("style_profile_path") or default_style_profile_path
    style_mapping = payload.get("style_mapping") or default_style_mapping
    missing = _missing_required(
        {
            **payload,
            "markdown_path": markdown_path,
            "style_profile_path": style_profile_path,
            "style_mapping": style_mapping,
        },
        ["markdown_path", "style_profile_path", "style_mapping", "table_index", "row_index", "cell_index"],
    )
    if missing:
        return json_result({"status": "error", "message": f"action {action_index} 缺少参数: {', '.join(missing)}", "action_guide": ACTION_GUIDE})
    return apply_markdown_ir_to_table_cell(
        docx_path=docx_path,
        output_path=output_path,
        table_index=int(payload["table_index"]),
        row_index=int(payload["row_index"]),
        cell_index=int(payload["cell_index"]),
        markdown_path=markdown_path,
        style_profile_path=style_profile_path,
        style_mapping=style_mapping,
        include_block_ids=payload.get("include_block_ids"),
        line_start=payload.get("line_start"),
        line_end=payload.get("line_end"),
    )


def _run_markdown_after_paragraph_action(
    payload: dict,
    action_index: int,
    docx_path: str,
    output_path: str,
    default_markdown_path: str | None,
    default_style_profile_path: str | None,
    default_style_mapping: dict,
) -> str:
    markdown_path = payload.get("markdown_path") or default_markdown_path
    style_profile_path = payload.get("style_profile_path") or default_style_profile_path
    style_mapping = payload.get("style_mapping") or default_style_mapping
    missing = _missing_required(
        {
            **payload,
            "markdown_path": markdown_path,
            "style_profile_path": style_profile_path,
            "style_mapping": style_mapping,
        },
        ["markdown_path", "style_profile_path", "style_mapping", "paragraph_index"],
    )
    if missing:
        return json_result({"status": "error", "message": f"action {action_index} 缺少参数: {', '.join(missing)}", "action_guide": ACTION_GUIDE})
    return apply_markdown_ir_after_paragraph(
        docx_path=docx_path,
        output_path=output_path,
        paragraph_index=int(payload["paragraph_index"]),
        markdown_path=markdown_path,
        style_profile_path=style_profile_path,
        style_mapping=style_mapping,
        include_block_ids=payload.get("include_block_ids"),
        line_start=payload.get("line_start"),
        line_end=payload.get("line_end"),
    )


def _action_payload(action: dict) -> dict:
    target = action.get("target") or {}
    if not isinstance(target, dict):
        target = {}
    payload = {**target, **action}
    payload.pop("target", None)
    payload.pop("type", None)
    payload.pop("kind", None)
    return payload


def _missing_required(payload: dict, required: list[str]) -> list[str]:
    allow_empty = set(payload.get("__allow_empty_required__", []))
    missing = []
    for name in required:
        value = payload.get(name)
        if value is None or value == {}:
            missing.append(name)
            continue
        if value == "" and name not in allow_empty:
            missing.append(name)
    return missing


def _kwargs_for_action(payload: dict, required: list[str], optional: list[str]) -> dict:
    kwargs = {}
    for name in required + optional:
        if name in payload:
            kwargs[name] = _coerce_action_value(name, payload[name])
    return kwargs


def _response_result(parsed: dict, is_final_action: bool, output_path: str) -> dict:
    result = dict(parsed)
    if not is_final_action:
        result["output_path"] = None
        result["temporary_output_path"] = output_path
        result["temporary_output_cleaned"] = True
        result["hint"] = "这是 markdown_to_word 的中间输出，调用结束后会被清理；后续 action 会自动接收它，不要在新的工具调用中引用该路径。"
    return result


def _coerce_action_value(name: str, value):
    if name in INTEGER_FIELDS and value is not None:
        return int(value)
    return value


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


INTEGER_FIELDS = {
    "table_index",
    "row_index",
    "cell_index",
    "column_index",
    "paragraph_index",
    "start_cell_index",
    "span",
    "occurrence",
    "offset",
    "left_twips",
    "first_line_twips",
    "hanging_twips",
    "font_size_half_points",
}
FORMAT_OPTIONS = ["newline_mode", "format_policy", "color", "bold", "font_size_half_points", "font_size_pt"]
ACTIONS = {
    "replace_text": {
        "func": replace_text,
        "required": ["old_text", "new_text"],
        "optional": ["occurrence", *FORMAT_OPTIONS],
        "allow_empty_required": ["new_text"],
    },
    "replace_text_like_sample": {
        "func": replace_text_like_sample,
        "required": ["old_text", "new_text", "style_profile_path", "sample_id"],
        "optional": ["occurrence", "newline_mode"],
    },
    "insert_text_at": {
        "func": insert_text_at,
        "required": ["anchor_text", "insert_text"],
        "optional": ["offset", "occurrence", *FORMAT_OPTIONS],
    },
    "delete_text": {
        "func": delete_text,
        "required": ["target_text"],
        "optional": ["occurrence", "trim_surrounding_spaces"],
    },
    "set_text_format": {
        "func": set_text_format,
        "required": ["target_text"],
        "optional": ["occurrence", "format_policy", "color", "bold", "font_size_half_points", "font_size_pt"],
    },
    "insert_paragraph_after": {
        "func": insert_paragraph_after,
        "required": ["anchor_text", "new_text"],
        "optional": ["occurrence", "style_source", *FORMAT_OPTIONS],
    },
    "insert_paragraph_after_like_sample": {
        "func": insert_paragraph_after_like_sample,
        "required": ["anchor_text", "new_text", "style_profile_path", "sample_id"],
        "optional": ["occurrence", "style_source", "newline_mode"],
    },
    "replace_table_cell_text": {
        "func": replace_table_cell_text,
        "required": ["table_index", "row_index", "cell_index", "new_text"],
        "optional": FORMAT_OPTIONS,
    },
    "replace_table_cell_like_sample": {
        "func": replace_table_cell_like_sample,
        "required": ["table_index", "row_index", "cell_index", "new_text", "style_profile_path", "sample_id"],
        "optional": ["newline_mode"],
    },
    "insert_text_in_table_cell": {
        "func": insert_text_in_table_cell,
        "required": ["table_index", "row_index", "cell_index", "insert_text"],
        "optional": ["paragraph_index", "append", *FORMAT_OPTIONS],
    },
    "clear_table_cell": {
        "func": clear_table_cell,
        "required": ["table_index", "row_index", "cell_index"],
        "optional": [],
    },
    "delete_table_row": {
        "func": delete_table_row,
        "required": ["table_index", "row_index"],
        "optional": ["expected_row_text_contains"],
    },
    "insert_table_row_after": {
        "func": insert_table_row_after,
        "required": ["table_index", "row_index", "cell_texts"],
        "optional": ["copy_from", *FORMAT_OPTIONS],
    },
    "insert_table_after_paragraph": {
        "func": insert_table_after_paragraph,
        "required": ["paragraph_index", "cell_texts"],
        "optional": ["column_widths_twips"],
    },
    "insert_table_in_cell": {
        "func": insert_table_in_cell,
        "required": ["table_index", "row_index", "cell_index", "cell_texts"],
        "optional": ["column_widths_twips"],
    },
    "insert_table_column_after": {
        "func": insert_table_column_after,
        "required": ["table_index", "column_index"],
        "optional": ["cell_texts", "copy_from"],
    },
    "merge_table_cells_horizontal": {
        "func": merge_table_cells_horizontal,
        "required": ["table_index", "row_index", "start_cell_index", "span"],
        "optional": [],
    },
    "set_paragraph_indent": {
        "func": set_paragraph_indent,
        "required": ["paragraph_index"],
        "optional": ["left_twips", "first_line_twips", "hanging_twips"],
    },
}
TABLE_ACTIONS = {
    key: ACTIONS[key]
    for key in {
        "insert_table_after_paragraph",
        "insert_table_in_cell",
        "insert_table_row_after",
    }
}


tools_schema = {
    "type": "function",
    "function": {
        "name": "markdown_to_word",
        "description": "统一 Word 写入入口。用 actions 顺序执行 Markdown 编译写入、文本编辑、段落编辑、表格结构编辑和格式编辑；底层写入工具不应由 agent 直接调用。\n" + ACTION_GUIDE,
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "markdown_path": {"type": "string", "description": "默认 Markdown 草稿路径；Markdown 类 action 可覆盖"},
                "style_profile_path": {"type": "string", "description": "默认样式画像 JSON 路径；Markdown 类和样式仿写类 action 可覆盖"},
                "style_mapping": {
                    "type": "object",
                    "description": "默认 Markdown block 类型到 sample_id 的映射，例如 paragraph/list_item -> S001",
                    "additionalProperties": {"type": "string"},
                },
                "actions": {
                    "type": "array",
                    "description": "顺序执行的写入动作数组。每个 action 必须有 type；坐标字段可直接放在 action 上，也可放在 target 对象中。Markdown 类 action 可用 include_block_ids 或 line_start/line_end 选择局部块。",
                    "items": {"type": "object", "additionalProperties": True},
                },
            },
            "required": ["docx_path", "output_path", "actions"],
        },
    },
}
