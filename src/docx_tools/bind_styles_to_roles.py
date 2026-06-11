import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from workspace.guard import resolve_workspace_path, WorkspacePathError, to_relative_path

from .common import json_result
from .style_profile import FIXED_ROLES


def bind_styles_to_roles(
    session_id: str,
    style_profile_path: str,
    bindings: dict[str, str],
) -> str:
    """把 sample_id 显式绑定到 5 个标准角色，写入 style_profile.json 的 role_bindings 字段。"""
    try:
        profile_path = resolve_workspace_path(session_id, style_profile_path, must_exist=True, must_be_file=True)
    except WorkspacePathError as e:
        return json_result(
            {
                "status": "error",
                "code": e.code,
                "message": e.user_message,
            }
        )

    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return json_result(
            {
                "status": "error",
                "message": f"无法读取样式画像: {exc}",
                "style_profile_path": to_relative_path(session_id, profile_path),
            }
        )

    samples = profile.get("style_samples") or []
    available_sample_ids = sorted(
        {sample.get("sample_id") for sample in samples if sample.get("sample_id")}
    )

    if not bindings:
        return json_result(
            {
                "status": "error",
                "message": (
                    "必须显式提供 bindings。请读取样式画像里的 style_samples 数组，"
                    "为 5 个标准角色各选一个最匹配的 sample_id。"
                ),
                "available_sample_ids": available_sample_ids,
                "fixed_roles": list(FIXED_ROLES),
                "style_profile_path": to_relative_path(session_id, profile_path),
            }
        )

    invalid_roles = sorted(set(bindings) - set(FIXED_ROLES))
    if invalid_roles:
        return json_result(
            {
                "status": "error",
                "message": (
                    f"使用了非标准角色 {invalid_roles}。合法角色: {list(FIXED_ROLES)}"
                ),
                "available_sample_ids": available_sample_ids,
                "fixed_roles": list(FIXED_ROLES),
                "style_profile_path": to_relative_path(session_id, profile_path),
            }
        )

    available_set = set(available_sample_ids)
    invalid_samples = sorted(set(bindings.values()) - available_set)
    if invalid_samples:
        return json_result(
            {
                "status": "error",
                "message": (
                    f"绑定的 sample_id {invalid_samples} 不在样式画像中。"
                    f"可用的 sample_id: {available_sample_ids}"
                ),
                "available_sample_ids": available_sample_ids,
                "fixed_roles": list(FIXED_ROLES),
                "style_profile_path": to_relative_path(session_id, profile_path),
            }
        )

    profile["role_bindings"] = dict(bindings)
    profile_path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return json_result(
        {
            "status": "ok",
            "style_profile_path": to_relative_path(session_id, profile_path),
            "role_bindings": dict(bindings),
            "available_sample_ids": available_sample_ids,
            "fixed_roles": list(FIXED_ROLES),
        }
    )


tools_schema = {
    "type": "function",
    "function": {
        "name": "bind_styles_to_roles",
        "description": (
            "把 sample_id 显式绑定到 5 个标准角色（title / section_heading / body / "
            "table_cell / placeholder），写入样式画像 JSON 的 role_bindings 字段。"
            "你必须先读取 style_samples 数组，根据每个 sample 的 format/paragraph_format/"
            "context 字段为 5 个标准角色各选一个最匹配的 sample_id，"
            "通过 bindings 参数显式传入。"
            "markdown_to_word 收到 style_profile_path 但未传 style_mapping 时，会从该字段自动推导格式映射。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "style_profile_path": {
                    "type": "string",
                    "description": "analyze_docx_style_samples 输出的样式画像 JSON 路径",
                },
                "bindings": {
                    "type": "object",
                    "description": (
                        "标准角色到 sample_id 的显式映射，必须从 style_samples 里选。"
                        "例如 {\"title\": \"S001\", \"section_heading\": \"S002\", "
                        "\"body\": \"S003\", \"table_cell\": \"S004\", \"placeholder\": \"S005\"}"
                    ),
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["style_profile_path", "bindings"],
        },
    },
}
