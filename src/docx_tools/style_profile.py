import json
from pathlib import Path


FIXED_ROLES = ("title", "section_heading", "body", "table_cell", "placeholder")

ROLE_TO_BLOCK_TYPES: dict[str, tuple[str, ...]] = {
    "title": ("heading1",),
    "section_heading": ("heading2", "heading3"),
    "body": ("paragraph", "list_item", "code_block", "formula_block", "image"),
    "table_cell": ("table_cell",),
}

_DERIVATION_ORDER = ("body", "section_heading", "title", "table_cell")


def load_style_sample(style_profile_path: str, sample_id: str) -> dict:
    profile = json.loads(Path(style_profile_path).read_text(encoding="utf-8"))
    for sample in profile.get("style_samples", []):
        if sample.get("sample_id") == sample_id:
            return sample
    raise ValueError(f"sample_id not found in style profile: {sample_id}")


def propose_role_bindings(profile: dict) -> tuple[dict[str, str], list[str]]:
    """按 (context, top candidate_role_hint) 启发式分配 5 个标准角色。

    返回 (proposed_bindings, warnings)。proposed_bindings 中只包含能匹配上的角色；
    无法判定的角色会被跳过并加 warning 提醒调用方补全。
    """
    samples = profile.get("style_samples") or []
    if not samples:
        return {}, ["style_profile 中没有 style_samples，无法自动建议。"]

    candidates: dict[str, list[tuple[int, str]]] = {role: [] for role in FIXED_ROLES}
    for sample in samples:
        context = sample.get("context")
        hints = sample.get("candidate_role_hints") or []
        top_hint = hints[0]["role"] if hints else None
        sample_id = sample.get("sample_id")
        occurrences = int(sample.get("total_occurrences") or 0)
        if not sample_id or not top_hint:
            continue

        if context == "normal_paragraph":
            if top_hint == "cover_or_document_title":
                candidates["title"].append((occurrences, sample_id))
            elif top_hint == "section_heading":
                candidates["section_heading"].append((occurrences, sample_id))
            elif top_hint == "body_text":
                candidates["body"].append((occurrences, sample_id))
        if top_hint == "blue_placeholder_or_prompt":
            candidates["placeholder"].append((occurrences, sample_id))
        if context in ("table_cell_first_column", "table_cell_other_column") and top_hint in (
            "table_label_cell",
            "table_value_cell",
        ):
            candidates["table_cell"].append((occurrences, sample_id))

    proposed: dict[str, str] = {}
    warnings: list[str] = []
    for role in FIXED_ROLES:
        cands = sorted(candidates[role], key=lambda item: (-item[0], item[1]))
        if not cands:
            warnings.append(f"role '{role}' 没有可匹配的样本，需要手动绑定。")
            continue
        proposed[role] = cands[0][1]

    return proposed, warnings


def derive_style_mapping_from_bindings(style_profile_path: str) -> dict[str, str]:
    """从 style_profile 的 role_bindings 推导 block_type -> sample_id 映射。

    无 role_bindings 时返回空 dict，调用方应回退到默认行为。
    """
    try:
        profile = json.loads(Path(style_profile_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    bindings = profile.get("role_bindings")
    if not isinstance(bindings, dict) or not bindings:
        return {}

    style_mapping: dict[str, str] = {}
    for role in _DERIVATION_ORDER:
        sample_id = bindings.get(role)
        if not sample_id or role not in ROLE_TO_BLOCK_TYPES:
            continue
        for block_type in ROLE_TO_BLOCK_TYPES[role]:
            style_mapping[block_type] = sample_id
    return style_mapping

