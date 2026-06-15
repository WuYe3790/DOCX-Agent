"""test_like_sample_smoke.py — 3 个 *_like_sample 工具冒烟测试 (PR-3.3)

按用户 review 建议, 不测内部启发式, 只测:
  (a) 不抛 Exception
  (b) 返回合法 JSON
  (c) 含 status 字段

9 case: 3 工具 × 3 case (合法输入/sample 不存在/越界)
"""
import json
import sys
from pathlib import Path

import pytest

pytest_plugins = ["_docx_factory"]
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from docx_tools.insert_paragraph_after_like_sample import (
    insert_paragraph_after_like_sample,
)
from docx_tools.replace_table_cell_like_sample import (
    replace_table_cell_like_sample,
)
from docx_tools.replace_text_like_sample import replace_text_like_sample

from _docx_factory import _build_docx_with_table, _build_full_docx


def _ws(tmp_root, session_id: str) -> Path:
    return tmp_root / session_id / "workspace"


def _write_minimal_style_profile(profile_path: Path, sample_ids: list[str]) -> None:
    """写最小 style_profile.json, 含指定 sample_id."""
    profile = {
        "version": "1.0",
        "style_samples": [
            {
                "sample_id": sid,
                "format": {"bold": False, "italic": False},
                "paragraph_format": {"alignment": "left"},
                "context": "test sample",
            }
            for sid in sample_ids
        ],
        "role_bindings": {},
    }
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_safe(s):
    """工具可能抛, 也可能返回 JSON 字符串. 统一处理."""
    if s is None:
        return None
    try:
        return json.loads(s)
    except (TypeError, json.JSONDecodeError):
        return None


# =====================================================================
# replace_text_like_sample: 3 case
# =====================================================================

class TestReplaceTextLikeSampleSmoke:
    def test_legal_input_does_not_crash(self, tmp_root, session_id):
        """合法 sample + 存在 anchor → 不抛, 返回合法 JSON 含 status."""
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx", ["hello world"])
        _write_minimal_style_profile(
            _ws(tmp_root, session_id) / "profile.json", ["S001"]
        )
        # replace_text_like_sample 需要 docx_path/output_path/style_profile_path/sample_id/old_text/new_text
        try:
            s = replace_text_like_sample(
                session_id, "in.docx", "out.docx",
                old_text="world", new_text="WORLD",
                style_profile_path="profile.json", sample_id="S001",
            )
            result = _parse_safe(s)
            assert result is not None, f"应返回合法 JSON, 实际 {s!r}"
            assert "status" in result
        except Exception as e:
            # 允许工具内部一些 helper 抛, 但工具本身应 return JSON
            pytest.fail(f"工具抛 Exception 而非返回 JSON: {type(e).__name__}: {e}")

    def test_sample_id_not_in_profile_raises_value_error(self, tmp_root, session_id):
        """不存在的 sample_id → 当前行为: load_style_sample 抛 ValueError.

        注: 这是 *_like_sample 工具的已知行为, 跟 json_result 不一样, 工具
        没 try/except 包装. smoke 测试锁住此行为, 未来想改成友好 JSON 错误时
        调整测试断言即可.
        """
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx", ["x"])
        _write_minimal_style_profile(
            _ws(tmp_root, session_id) / "profile.json", ["S001"]
        )
        with pytest.raises(ValueError, match="sample_id not found"):
            replace_text_like_sample(
                session_id, "in.docx", "out.docx",
                old_text="x", new_text="Y",
                style_profile_path="profile.json", sample_id="NONEXISTENT",
            )

    def test_session_id_none_raises_value_error(self, tmp_root, session_id):
        """session_id=None → 抛 ValueError (resolve_workspace_path 严格校验).

        这跟其他工具"自动 mkdir" 行为不同, 是 *_like_sample 工具的特例.
        """
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx", ["x"])
        _write_minimal_style_profile(
            _ws(tmp_root, session_id) / "profile.json", ["S001"]
        )
        # session_id=None 在 resolve_workspace_path 会抛 (validate_session_id 拒绝空)
        with pytest.raises(Exception):
            replace_text_like_sample(
                None, "in.docx", "out.docx",
                old_text="x", new_text="Y",
                style_profile_path="profile.json", sample_id="S001",
            )


# =====================================================================
# insert_paragraph_after_like_sample: 3 case
# =====================================================================

class TestInsertParagraphAfterLikeSampleSmoke:
    def test_legal_input_does_not_crash(self, tmp_root, session_id):
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx", ["anchor"])
        _write_minimal_style_profile(
            _ws(tmp_root, session_id) / "profile.json", ["S001"]
        )
        try:
            s = insert_paragraph_after_like_sample(
                session_id, "in.docx", "out.docx",
                anchor_text="anchor", new_text="NEW",
                style_profile_path="profile.json", sample_id="S001",
            )
            result = _parse_safe(s)
            assert result is not None
            assert "status" in result
        except Exception as e:
            pytest.fail(f"工具抛 Exception: {type(e).__name__}: {e}")

    def test_anchor_not_found_does_not_crash(self, tmp_root, session_id):
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx", ["x"])
        _write_minimal_style_profile(
            _ws(tmp_root, session_id) / "profile.json", ["S001"]
        )
        try:
            s = insert_paragraph_after_like_sample(
                session_id, "in.docx", "out.docx",
                anchor_text="nonexistent", new_text="Y",
                style_profile_path="profile.json", sample_id="S001",
            )
            result = _parse_safe(s)
            assert result is not None
            assert "status" in result
        except Exception as e:
            pytest.fail(f"工具抛 Exception: {type(e).__name__}: {e}")

    def test_returns_valid_json_structure(self, tmp_root, session_id):
        """返回 JSON 必有 status 字段 (可解析)."""
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx", ["a"])
        _write_minimal_style_profile(
            _ws(tmp_root, session_id) / "profile.json", ["S001"]
        )
        s = insert_paragraph_after_like_sample(
            session_id, "in.docx", "out.docx",
            anchor_text="a", new_text="b",
            style_profile_path="profile.json", sample_id="S001",
        )
        result = _parse_safe(s)
        assert isinstance(result, dict), f"应返回 dict, 实际 {type(result).__name__}"
        assert "status" in result


# =====================================================================
# replace_table_cell_like_sample: 3 case
# =====================================================================

class TestReplaceTableCellLikeSampleSmoke:
    def test_legal_input_does_not_crash(self, tmp_root, session_id):
        _build_docx_with_table(
            _ws(tmp_root, session_id) / "in.docx", 2, 2,
            cells_data=[["a", "b"], ["c", "d"]],
        )
        _write_minimal_style_profile(
            _ws(tmp_root, session_id) / "profile.json", ["S001"]
        )
        try:
            s = replace_table_cell_like_sample(
                session_id, "in.docx", "out.docx",
                table_index=1, row_index=1, cell_index=1,
                new_text="REPLACED",
                style_profile_path="profile.json", sample_id="S001",
            )
            result = _parse_safe(s)
            assert result is not None
            assert "status" in result
        except Exception as e:
            pytest.fail(f"工具抛 Exception: {type(e).__name__}: {e}")

    def test_cell_out_of_range_does_not_crash(self, tmp_root, session_id):
        _build_docx_with_table(
            _ws(tmp_root, session_id) / "in.docx", 2, 2,
            cells_data=[["a", "b"], ["c", "d"]],
        )
        _write_minimal_style_profile(
            _ws(tmp_root, session_id) / "profile.json", ["S001"]
        )
        try:
            s = replace_table_cell_like_sample(
                session_id, "in.docx", "out.docx",
                table_index=1, row_index=1, cell_index=99,  # 越界
                new_text="X",
                style_profile_path="profile.json", sample_id="S001",
            )
            result = _parse_safe(s)
            assert result is not None
            assert "status" in result
        except Exception as e:
            pytest.fail(f"工具抛 Exception: {type(e).__name__}: {e}")

    def test_empty_sample_id_raises(self, tmp_root, session_id):
        """sample_id="" → 抛 (load_style_sample 严格校验)."""
        _build_docx_with_table(
            _ws(tmp_root, session_id) / "in.docx", 2, 2,
            cells_data=[["a", "b"], ["c", "d"]],
        )
        _write_minimal_style_profile(
            _ws(tmp_root, session_id) / "profile.json", ["S001"]
        )
        with pytest.raises(Exception):
            replace_table_cell_like_sample(
                session_id, "in.docx", "out.docx",
                table_index=1, row_index=1, cell_index=1,
                new_text="X",
                style_profile_path="profile.json", sample_id="",
            )
