import json
from collections import Counter
from pathlib import Path

from .common import json_result
from .style_profile import FIXED_ROLES, propose_role_bindings


def bind_styles_to_roles(
    style_profile_path: str,
    bindings: dict[str, str] | None = None,
    auto_propose: bool = False,
) -> str:
    """把 sample_id 绑定到 6 个标准角色，写入 style_profile.json 的 role_bindings 字段。"""
    profile_path = Path(style_profile_path)
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return json_result(
            {
                "status": "error",
                "message": f"无法读取样式画像: {exc}",
                "style_profile_path": str(profile_path),
            }
        )

    samples = profile.get("style_samples") or []
    available_sample_ids = sorted(
        {sample.get("sample_id") for sample in samples if sample.get("sample_id")}
    )

    warnings: list[str] = []
    if auto_propose and not bindings:
        bindings, warnings = propose_role_bindings(profile)
    elif auto_propose and bindings:
        warnings.append("auto_propose=True 时已同时传入 bindings，忽略 auto_propose，仅校验 bindings。")
    bindings = bindings or {}

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
                "style_profile_path": str(profile_path),
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
                "style_profile_path": str(profile_path),
            }
        )

    duplicates = [sample_id for sample_id, count in Counter(bindings.values()).items() if count > 1]
    if duplicates:
        offenders = {
            sample_id: sorted(role for role, sid in bindings.items() if sid == sample_id)
            for sample_id in duplicates
        }
        return json_result(
            {
                "status": "error",
                "message": f"以下 sample_id 被绑定到多个角色: {offenders}",
                "available_sample_ids": available_sample_ids,
                "fixed_roles": list(FIXED_ROLES),
                "style_profile_path": str(profile_path),
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
            "style_profile_path": str(profile_path),
            "role_bindings": dict(bindings),
            "available_sample_ids": available_sample_ids,
            "fixed_roles": list(FIXED_ROLES),
            "warnings": warnings,
        }
    )


tools_schema = {
    "type": "function",
    "function": {
        "name": "bind_styles_to_roles",
        "description": (
            "把 sample_id 绑定到 5 个标准角色（title / section_heading / body / "
            "table_cell / placeholder），写入样式画像 JSON 的 role_bindings 字段。"
            "markdown_to_word 收到 style_profile_path 但未传 style_mapping 时，会从该字段自动推导格式映射。"
            "auto_propose=True 时根据候选角色提示自动建议，可再用显式 bindings 覆盖。"
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
                    "description": "标准角色到 sample_id 的映射，例如 {\"title\": \"S001\", \"body\": \"S003\"}",
                    "additionalProperties": {"type": "string"},
                },
                "auto_propose": {
                    "type": "boolean",
                    "description": "为 True 时使用启发式自动建议；可与 bindings 配合先用 auto_propose 再覆盖",
                    "default": False,
                },
            },
            "required": ["style_profile_path"],
        },
    },
}
