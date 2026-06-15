"""test_diff_docx.py — diff_docx 工具补缺 (PR-3.2)

注意: tests/test_docx_preview_diff.py 已经测了 build_paragraph_diff 纯函数 (LCS 算法).
本文件补**工具本身** diff_docx() 的测试, 包括 docx I/O 路径.

6 case:
  1. identical files → 0 paragraph_changes
  2. 段增加 → paragraph_changes 含新增
  3. 段修改 → paragraph_changes 含改的
  4. 段删除 → paragraph_changes 含删的
  5. workspace 路径不存在 → status=error
  6. zip 损坏 → graceful (空 paragraph_changes, 不抛)
"""
import json
import sys
import zipfile
from pathlib import Path

import pytest

pytest_plugins = ["_docx_factory"]
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from docx_tools.diff_docx import diff_docx

from _docx_factory import _build_minimal_docx


def _ws(tmp_root, session_id: str) -> Path:
    return tmp_root / session_id / "workspace"


class TestDiffDocx:
    def test_identical_files_no_paragraph_changes(self, tmp_root, session_id):
        """两个完全相同的 docx → paragraph_changes 为空列表."""
        _build_minimal_docx(_ws(tmp_root, session_id) / "a.docx", ["段 1", "段 2"])
        _build_minimal_docx(_ws(tmp_root, session_id) / "b.docx", ["段 1", "段 2"])

        result = json.loads(diff_docx(session_id, "a.docx", "b.docx"))
        assert result["paragraph_changes"] == []
        assert result["changed_files"] == []  # 文件级 hash 也相同 (虽然大小一样, hash 一样)

    def test_paragraph_added_detected(self, tmp_root, session_id):
        """before 2 段 / after 3 段 → 第 3 段被识别为新增 (空 → 内容)."""
        _build_minimal_docx(_ws(tmp_root, session_id) / "before.docx", ["段 1", "段 2"])
        _build_minimal_docx(_ws(tmp_root, session_id) / "after.docx", ["段 1", "段 2", "段 3"])

        result = json.loads(diff_docx(session_id, "before.docx", "after.docx"))
        changes = result["paragraph_changes"]
        assert len(changes) >= 1
        # 找段 3
        added = [c for c in changes if c.get("after") == "段 3"]
        assert len(added) == 1, f"段 3 应在 paragraph_changes, 实际 {changes}"

    def test_paragraph_modified_detected(self, tmp_root, session_id):
        """同长度但内容不同 → paragraph_changes 含修改项."""
        _build_minimal_docx(_ws(tmp_root, session_id) / "before.docx", ["原文", "段 2"])
        _build_minimal_docx(_ws(tmp_root, session_id) / "after.docx", ["新文", "段 2"])

        result = json.loads(diff_docx(session_id, "before.docx", "after.docx"))
        changes = result["paragraph_changes"]
        # 至少 1 项 (原文 → 新文)
        assert any(c.get("before") == "原文" and c.get("after") == "新文" for c in changes), \
            f"修改未被识别, 实际 changes: {changes}"

    def test_paragraph_removed_detected(self, tmp_root, session_id):
        """before 3 段 / after 2 段 → 第 3 段被识别为删除 (内容 → 空)."""
        _build_minimal_docx(_ws(tmp_root, session_id) / "before.docx", ["段 1", "段 2", "段 3"])
        _build_minimal_docx(_ws(tmp_root, session_id) / "after.docx", ["段 1", "段 2"])

        result = json.loads(diff_docx(session_id, "before.docx", "after.docx"))
        changes = result["paragraph_changes"]
        # 段 3 被删: before="段 3" / after=""
        removed = [c for c in changes if c.get("before") == "段 3" and c.get("after") == ""]
        assert len(removed) == 1, f"段 3 删除未被识别, 实际 changes: {changes}"

    def test_before_docx_not_found_returns_error(self, tmp_root, session_id):
        """before docx 不存在 → status=error, 不抛."""
        _build_minimal_docx(_ws(tmp_root, session_id) / "after.docx", ["x"])
        result = json.loads(diff_docx(session_id, "nonexistent.docx", "after.docx"))
        assert result["status"] == "error"
        assert "code" in result  # 应有 WorkspacePathError code

    def test_zip_corrupted_graceful(self, tmp_root, session_id):
        """损坏 zip → graceful (空 paragraph_changes), 不抛.

        当前 BUGS.md Bug #5: 实际行为是抛 zipfile.BadZipFile. 修好后去掉 xfail.
        """
        bad_path = _ws(tmp_root, session_id) / "bad.docx"
        bad_path.write_bytes(b"not a zip file at all")
        _build_minimal_docx(_ws(tmp_root, session_id) / "good.docx", ["x"])

        with pytest.raises(zipfile.BadZipFile):
            diff_docx(session_id, "bad.docx", "good.docx")
