"""Phase 1 单元测试: src/workspace/guard.py 路径解析层

覆盖:
- validate_session_id 黑名单
- resolve_workspace_path 5 层防御
- safe_workspace_filename 清洗
- unique_workspace_target 重名
- build_workspace_tree 限制
"""
import os
import sys
import shutil
import tempfile
from pathlib import Path

import pytest

# tests/ 是子目录, src/ 在仓库根
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from workspace import (  # noqa: E402
    WorkspacePathError,
    safe_workspace_filename,
    unique_workspace_target,
    build_workspace_tree,
    validate_session_id,
    resolve_workspace_path,
    workspace_dir,
)


@pytest.fixture
def tmp_sessions_root(monkeypatch, tmp_path):
    """重定向 WORKSPACE_ROOT 到 tmp_path, 避免污染 out/sessions"""
    import workspace.guard as guard
    monkeypatch.setattr(guard, "WORKSPACE_ROOT", tmp_path / "sessions")
    return tmp_path / "sessions"


# === validate_session_id ===

class TestValidateSessionId:
    def test_valid_session_id(self):
        validate_session_id("session-20260611-143022")
        validate_session_id("abc123")

    def test_empty_rejected(self):
        with pytest.raises(WorkspacePathError) as exc:
            validate_session_id("")
        assert exc.value.code == "name_invalid"

    def test_path_separator_rejected(self):
        with pytest.raises(WorkspacePathError) as exc:
            validate_session_id("foo/bar")
        assert exc.value.code == "name_invalid"
        with pytest.raises(WorkspacePathError):
            validate_session_id("foo\\bar")

    def test_parent_traversal_rejected(self):
        with pytest.raises(WorkspacePathError) as exc:
            validate_session_id("foo..bar")
        assert exc.value.code == "name_invalid"

    def test_too_long_rejected(self):
        with pytest.raises(WorkspacePathError):
            validate_session_id("a" * 101)

    def test_nul_rejected(self):
        with pytest.raises(WorkspacePathError):
            validate_session_id("foo\x00bar")

    def test_control_char_rejected(self):
        with pytest.raises(WorkspacePathError):
            validate_session_id("foo\nbar")


# === resolve_workspace_path ===

class TestResolveWorkspacePath:
    def test_relative_file_inside_workspace(self, tmp_sessions_root):
        session_id = "s1"
        ws = tmp_sessions_root / session_id / "workspace"
        ws.mkdir(parents=True)
        (ws / "report.docx").write_bytes(b"PK\x03\x04fake")

        result = resolve_workspace_path(session_id, "report.docx", must_exist=True, must_be_file=True)
        assert result == (ws / "report.docx").resolve()

    def test_dot_dot_traversal_rejected(self, tmp_sessions_root):
        session_id = "s1"
        (tmp_sessions_root / session_id / "workspace").mkdir(parents=True)
        with pytest.raises(WorkspacePathError) as exc:
            resolve_workspace_path(session_id, "../escape.txt")
        assert exc.value.code == "traversal"

    def test_windows_absolute_rejected(self, tmp_sessions_root):
        session_id = "s1"
        (tmp_sessions_root / session_id / "workspace").mkdir(parents=True)
        with pytest.raises(WorkspacePathError) as exc:
            resolve_workspace_path(session_id, "C:\\Windows\\System32\\config\\SAM")
        assert exc.value.code == "absolute"

    def test_posix_absolute_rejected(self, tmp_sessions_root):
        session_id = "s1"
        (tmp_sessions_root / session_id / "workspace").mkdir(parents=True)
        with pytest.raises(WorkspacePathError) as exc:
            resolve_workspace_path(session_id, "/etc/passwd")
        assert exc.value.code == "absolute"

    def test_empty_path_rejected(self, tmp_sessions_root):
        session_id = "s1"
        (tmp_sessions_root / session_id / "workspace").mkdir(parents=True)
        with pytest.raises(WorkspacePathError) as exc:
            resolve_workspace_path(session_id, "")
        assert exc.value.code == "name_invalid"

    def test_not_found_when_must_exist(self, tmp_sessions_root):
        session_id = "s1"
        (tmp_sessions_root / session_id / "workspace").mkdir(parents=True)
        with pytest.raises(WorkspacePathError) as exc:
            resolve_workspace_path(session_id, "missing.docx", must_exist=True)
        assert exc.value.code == "not_found"

    def test_must_exist_false_allows_new(self, tmp_sessions_root):
        session_id = "s1"
        (tmp_sessions_root / session_id / "workspace").mkdir(parents=True)
        result = resolve_workspace_path(session_id, "new_file.md", must_exist=False)
        assert result.name == "new_file.md"

    def test_must_be_file_on_dir_rejected(self, tmp_sessions_root):
        session_id = "s1"
        ws = tmp_sessions_root / session_id / "workspace"
        ws.mkdir(parents=True)
        (ws / "subdir").mkdir()
        with pytest.raises(WorkspacePathError) as exc:
            resolve_workspace_path(session_id, "subdir", must_exist=True, must_be_file=True)
        assert exc.value.code == "not_file"

    def test_must_be_dir_on_file_rejected(self, tmp_sessions_root):
        session_id = "s1"
        ws = tmp_sessions_root / session_id / "workspace"
        ws.mkdir(parents=True)
        (ws / "file.txt").write_text("hi")
        with pytest.raises(WorkspacePathError) as exc:
            resolve_workspace_path(session_id, "file.txt", must_exist=True, must_be_dir=True)
        assert exc.value.code == "not_dir"

    def test_dot_dot_in_basename_allowed(self, tmp_sessions_root):
        """'report..docx' 这种 .. 在 basename 内是合法的 (仅整段 == '..' 才拒绝)"""
        session_id = "s1"
        ws = tmp_sessions_root / session_id / "workspace"
        ws.mkdir(parents=True)
        (ws / "report..docx").write_bytes(b"PK")
        result = resolve_workspace_path(session_id, "report..docx", must_exist=True, must_be_file=True)
        assert result.exists()

    def test_subdirectory_path_allowed(self, tmp_sessions_root):
        """LLM 调 read_docx_structure('docs/report.docx') 应该被允许"""
        session_id = "s1"
        ws = tmp_sessions_root / session_id / "workspace"
        ws.mkdir(parents=True)
        (ws / "docs").mkdir()
        (ws / "docs" / "report.docx").write_bytes(b"PK")
        result = resolve_workspace_path(session_id, "docs/report.docx", must_exist=True, must_be_file=True)
        assert result.name == "report.docx"

    def test_nul_in_path_rejected(self, tmp_sessions_root):
        session_id = "s1"
        (tmp_sessions_root / session_id / "workspace").mkdir(parents=True)
        with pytest.raises(WorkspacePathError) as exc:
            resolve_workspace_path(session_id, "foo\x00.txt")
        assert exc.value.code == "name_invalid"

    def test_symlink_rejected_by_default(self, tmp_sessions_root):
        """默认 allow_symlinks=False, symlink 越界被拒"""
        session_id = "s1"
        ws = tmp_sessions_root / session_id / "workspace"
        ws.mkdir(parents=True)
        # 创建指向 workspace 外部的 symlink
        outside = tmp_sessions_root.parent / "outside.txt"
        outside.write_text("secret")
        try:
            (ws / "link").symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlink not supported on this platform")

        with pytest.raises(WorkspacePathError) as exc:
            resolve_workspace_path(session_id, "link", must_exist=True, must_be_file=True)
        assert exc.value.code == "symlink"

    def test_cross_session_isolation(self, tmp_sessions_root):
        """A 的 session_id 不能解析 B 的 workspace 路径 (即使用了 .. 也跳不出去)"""
        a_id = "session-A"
        b_id = "session-B"
        (tmp_sessions_root / a_id / "workspace").mkdir(parents=True)
        (tmp_sessions_root / b_id / "workspace").mkdir(parents=True)
        (tmp_sessions_root / b_id / "workspace" / "secret.txt").write_text("B's secret")

        # 尝试用 A 的 session_id 访问 B 的文件
        with pytest.raises(WorkspacePathError) as exc:
            resolve_workspace_path(a_id, "../session-B/workspace/secret.txt", must_exist=True, must_be_file=True)
        assert exc.value.code == "traversal"


# === safe_workspace_filename ===

class TestSafeWorkspaceFilename:
    def test_plain_name_kept(self):
        assert safe_workspace_filename("report.docx") == "report.docx"

    def test_path_prefix_stripped(self):
        """上传时的完整路径只取 basename"""
        assert safe_workspace_filename("/etc/passwd") == "passwd"
        assert safe_workspace_filename("C:\\Users\\foo\\bar.txt") == "bar.txt"

    def test_hidden_file_rejected(self):
        with pytest.raises(WorkspacePathError) as exc:
            safe_workspace_filename(".hidden")
        assert exc.value.code == "name_invalid"

    def test_empty_rejected(self):
        with pytest.raises(WorkspacePathError):
            safe_workspace_filename("")

    def test_control_char_rejected(self):
        with pytest.raises(WorkspacePathError):
            safe_workspace_filename("foo\x01bar.txt")

    def test_nul_rejected(self):
        with pytest.raises(WorkspacePathError):
            safe_workspace_filename("foo\x00.txt")

    def test_long_filename_truncated(self):
        long = "a" * 300 + ".docx"
        result = safe_workspace_filename(long)
        assert len(result) <= 200
        assert result.endswith(".docx")

    def test_long_no_extension_truncated(self):
        long = "a" * 300
        result = safe_workspace_filename(long)
        assert len(result) <= 200
        assert "." not in result


# === unique_workspace_target ===

class TestUniqueWorkspaceTarget:
    def test_no_collision_returns_original(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        result = unique_workspace_target(ws, "new.docx")
        assert result == ws / "new.docx"

    def test_collision_appends_suffix(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "report.docx").write_text("v1")
        result = unique_workspace_target(ws, "report.docx")
        assert result == ws / "report__1.docx"

    def test_double_collision(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "report.docx").write_text("v1")
        (ws / "report__1.docx").write_text("v2")
        result = unique_workspace_target(ws, "report.docx")
        assert result == ws / "report__2.docx"

    def test_no_extension_collision(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "Makefile").write_text("v1")
        result = unique_workspace_target(ws, "Makefile")
        assert result == ws / "Makefile__1"


# === build_workspace_tree ===

class TestBuildWorkspaceTree:
    def test_empty_workspace(self, tmp_sessions_root):
        session_id = "s1"
        (tmp_sessions_root / session_id / "workspace").mkdir(parents=True)
        assert build_workspace_tree(session_id) == []

    def test_flat_files_listed(self, tmp_sessions_root):
        session_id = "s1"
        ws = tmp_sessions_root / session_id / "workspace"
        ws.mkdir(parents=True)
        (ws / "a.docx").write_text("a")
        (ws / "b.docx").write_text("b")
        (ws / "c.txt").write_text("c")
        result = build_workspace_tree(session_id)
        assert "a.docx" in result
        assert "b.docx" in result
        assert "c.txt" in result

    def test_max_depth_limit(self, tmp_sessions_root):
        session_id = "s1"
        ws = tmp_sessions_root / session_id / "workspace"
        ws.mkdir(parents=True)
        # depth 5: a/b/c/d/e/f.txt
        deep = ws / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        (deep / "f.txt").write_text("deep")
        # max_depth=2 应该截断在 a/ 看到
        result = build_workspace_tree(session_id, max_depth=2)
        # 应该有 a/ 但不会有 f.txt
        assert "a/" in result
        assert not any("f.txt" in line for line in result)

    def test_max_files_truncates(self, tmp_sessions_root):
        session_id = "s1"
        ws = tmp_sessions_root / session_id / "workspace"
        ws.mkdir(parents=True)
        for i in range(50):
            (ws / f"f{i}.docx").write_text("x")
        result = build_workspace_tree(session_id, max_files=5)
        # 实际文件条目 ≤ 5
        file_entries = [l for l in result if not l.startswith("...")]
        assert len(file_entries) <= 5
        # 截断提示
        assert any(l.startswith("...(还有") for l in result)

    def test_hidden_files_excluded(self, tmp_sessions_root):
        session_id = "s1"
        ws = tmp_sessions_root / session_id / "workspace"
        ws.mkdir(parents=True)
        (ws / ".hidden").write_text("x")
        (ws / "visible.txt").write_text("x")
        result = build_workspace_tree(session_id)
        assert "visible.txt" in result
        assert not any(".hidden" in l for l in result)
