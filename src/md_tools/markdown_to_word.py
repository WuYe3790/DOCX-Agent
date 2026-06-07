import json
from pathlib import Path

try:
    from docx_tools.style_profile import derive_style_mapping_from_bindings
except ModuleNotFoundError:
    from src.docx_tools.style_profile import derive_style_mapping_from_bindings

from .apply_markdown_ir_after_paragraph import apply_markdown_ir_to_paragraph
from .apply_markdown_ir_to_table_cell import apply_markdown_ir_to_table_cell
from .common import json_result


ACTION_GUIDE = """
可用 actions 只有两个:
- write_markdown_to_paragraph: 把 Markdown block 编译写入普通正文段落流（支持编译段落、标题、列表、表格等所有 Markdown 元素并在段落位置动态创建对应的 Word 元素）。target 必须同时传入 paragraph_index 和 anchor_text 定位，以防文本错位插入；mode 默认为 replace，也可设为 after。
- write_markdown_to_table_cell: 把 Markdown block 编译写入表格单元格。target 使用 table_index、row_index、cell_index。
两个 action 都可用 include_block_ids 或 line_start/line_end 选择 Markdown 局部块。
规则: 填充或替换占位段落时，用 write_markdown_to_paragraph 的 mode=replace。
不要把 temporary_output_path 当作下一次输入。
""".strip()


def markdown_to_word(
    session_id: str,  # v2: 后端 dispatcher 隐式注入, LLM 不可见 (避坑 1)
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
    if style_profile_path and not style_mapping:
        style_mapping = derive_style_mapping_from_bindings(style_profile_path)
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
                    session_id=session_id,  # v2: 透传到 apply_* (需读 session_dir/drafts/)
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
                    "temporary_output_path": None if is_final_action else current_output,
                }
            )
            if parsed.get("status") != "ok":
                error_msg = parsed.get("result", {}).get("message") or parsed.get("message") or ""
                return json_result(
                    {
                        "status": "error",
                        "message": f"action {index} failed: {error_msg}",
                        "failed_action": action,
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
    session_id: str,  # v2: 透传到 apply_* (需读 session_dir/drafts/)
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
            session_id,
            docx_path,
            output_path,
            default_markdown_path,
            default_style_profile_path,
            default_style_mapping,
        )
    if action_type == "write_markdown_to_paragraph":
        return _run_markdown_paragraph_action(
            payload,
            action_index,
            session_id,
            docx_path,
            output_path,
            default_markdown_path,
            default_style_profile_path,
            default_style_mapping,
        )

    return json_result({"status": "error", "message": f"unsupported action type: {action_type}", "action_guide": ACTION_GUIDE})


def _run_markdown_table_cell_action(
    payload: dict,
    action_index: int,
    session_id: str,  # v2
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
        session_id=session_id,  # v2
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


def _run_markdown_paragraph_action(
    payload: dict,
    action_index: int,
    session_id: str,  # v2
    docx_path: str,
    output_path: str,
    default_markdown_path: str | None,
    default_style_profile_path: str | None,
    default_style_mapping: dict,
) -> str:
    markdown_path = payload.get("markdown_path") or default_markdown_path
    style_profile_path = payload.get("style_profile_path") or default_style_profile_path
    style_mapping = payload.get("style_mapping") or default_style_mapping
    mode = payload.get("mode", "replace")
    has_anchor = payload.get("paragraph_index") is not None and payload.get("anchor_text") is not None
    missing = _missing_required(
        {
            **payload,
            "markdown_path": markdown_path,
            "style_profile_path": style_profile_path,
            "style_mapping": style_mapping,
            "target": "ok" if has_anchor else None,
        },
        ["markdown_path", "style_profile_path", "style_mapping", "target"],
    )
    if missing:
        # 特殊处理，当 target 缺失时，说明缺少定位参数中的一个或两个，给出更清晰的说明
        if "target" in missing:
            missing.remove("target")
            missing.extend(["paragraph_index", "anchor_text"])
        return json_result({"status": "error", "message": f"action {action_index} 缺少必填定位参数: {', '.join(missing)}，write_markdown_to_paragraph 必须同时传入 paragraph_index 和 anchor_text 以防文本错位", "action_guide": ACTION_GUIDE})
    return apply_markdown_ir_to_paragraph(
        session_id=session_id,  # v2
        docx_path=docx_path,
        output_path=output_path,
        markdown_path=markdown_path,
        style_profile_path=style_profile_path,
        style_mapping=style_mapping,
        paragraph_index=payload.get("paragraph_index"),
        anchor_text=payload.get("anchor_text"),
        occurrence=int(payload.get("occurrence", 1)),
        mode=mode,
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


def _response_result(parsed: dict, is_final_action: bool, output_path: str) -> dict:
    result = dict(parsed)
    if not is_final_action:
        result["output_path"] = None
        result["temporary_output_path"] = output_path
        result["temporary_output_cleaned"] = True
        result["hint"] = "这是 markdown_to_word 的中间输出，调用结束后会被清理；后续 action 会自动接收它，不要在新的工具调用中引用该路径。"
    return result


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
        "description": "统一 Word 写入入口。只接收 Markdown 编译型写入 action。\n" + ACTION_GUIDE,
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "markdown_path": {"type": "string", "description": "默认 Markdown 草稿路径；Markdown 类 action 可覆盖"},
                "style_profile_path": {"type": "string", "description": "默认样式画像 JSON 路径；action 可覆盖"},
                "style_mapping": {
                    "type": "object",
                    "description": "默认 Markdown block 类型到 sample_id 的映射，例如 paragraph/list_item -> S001。若省略且提供了 style_profile_path，工具会从 profile 的 role_bindings 自动推导。",
                    "additionalProperties": {"type": "string"},
                },
                "actions": {
                    "type": "array",
                    "description": "顺序执行的 Markdown 写入动作数组。每个 action 必须有 type；坐标字段可直接放在 action 上，也可放在 target 对象中。可用 include_block_ids 或 line_start/line_end 选择局部块。",
                    "items": {"type": "object", "additionalProperties": True},
                },
            },
            "required": ["docx_path", "output_path", "actions"],
        },
    },
}
