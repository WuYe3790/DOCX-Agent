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

