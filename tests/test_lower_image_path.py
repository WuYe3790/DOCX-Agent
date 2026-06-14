"""lower.py 图片路径解析单测

覆盖 _resolve_image_path 和 lower_markdown_blocks 对图片路径的处理:
- 相对路径 + session_id → 解析成 workspace 下的绝对路径
- 绝对路径 + session_id → 原样保留 (防御性)
- session_id=None → 原样保留 (向后兼容 / 测试场景)
- WorkspacePathError (越界 / .. / NUL) → fall back 原字符串

为什么单独建文件:
- 整个 tests/ 里此前没有任何 lower_markdown_blocks 的直接单元测试,
  这是给这个核心函数补上第一个保护网。
"""
import sys
from pathlib import Path

import pytest

# tests/ 是子目录, src/ 在仓库根
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from docx_compiler.lower import (  # noqa: E402
    _resolve_image_path,
    lower_markdown_blocks,
)
from docx_compiler.ir import ImageIR  # noqa: E402
from docx_compiler.markdown_parser import parse_markdown_blocks  # noqa: E402


@pytest.fixture
def tmp_sessions_root(monkeypatch, tmp_path):
    """重定向 WORKSPACE_ROOT 到 tmp_path, 避免污染 out/sessions。

    返回 (sessions_root, session_id)。
    session 目录会被自动创建 (workspace_dir 会 mkdir)。
    """
    import workspace.guard as guard
    monkeypatch.setattr(guard, "WORKSPACE_ROOT", tmp_path / "sessions")
    session_id = "test-lower-image-session"
    return tmp_path / "sessions", session_id


# === _resolve_image_path 直接单元测试 ===


class TestResolveImagePath:
    def test_relative_path_with_session_returns_absolute(self, tmp_sessions_root):
        sessions_root, session_id = tmp_sessions_root
        resolved = _resolve_image_path("media/foo.png", session_id)
        # 期望: <tmp>/sessions/<id>/workspace/media/foo.png
        expected_prefix = sessions_root / session_id / "workspace"
        assert Path(resolved).is_absolute()
        assert Path(resolved) == (expected_prefix / "media" / "foo.png").resolve()

    def test_absolute_path_with_session_passthrough(self, tmp_sessions_root):
        _, session_id = tmp_sessions_root
        # 平台无关的绝对路径: 用 tmp_path 派生
        abs_path = str(Path.cwd().resolve() / "some" / "absolute.png")
        result = _resolve_image_path(abs_path, session_id)
        assert result == abs_path  # 防御性: 不主动改写绝对路径

    def test_session_id_none_passthrough(self):
        # 旧调用方 / 测试场景: 不传 session_id, 路径原样
        assert _resolve_image_path("media/foo.png", None) == "media/foo.png"
        assert _resolve_image_path("./relative/bar.jpg", None) == "./relative/bar.jpg"

    def test_traversal_path_falls_back_to_raw(self, tmp_sessions_root):
        _, session_id = tmp_sessions_root
        # resolve_workspace_path 会对 '..' 段抛 WorkspacePathError, 我们应吞掉并 fall back
        result = _resolve_image_path("../../etc/passwd", session_id)
        assert result == "../../etc/passwd"  # 不抛, 不改, 让 render 层 silent skip


# === lower_markdown_blocks 集成: 图片 block 的 IR 字段 ===


class TestLowerMarkdownBlocksImage:
    """端到端从 markdown 文本到 ImageIR.src_path, 验证 session_id 正确穿透。"""

    def _lower_image_md(self, md_text, style_mapping, session_id=None):
        blocks = parse_markdown_blocks(md_text)
        result = lower_markdown_blocks(blocks, style_mapping, session_id=session_id)
        image_irs = [b for b in result.layout_blocks if isinstance(b, ImageIR)]
        assert len(image_irs) == 1, f"应有 1 个 ImageIR, 实际 {len(image_irs)}"
        return image_irs[0]

    def test_image_block_with_session_resolves_to_absolute(self, tmp_sessions_root):
        sessions_root, session_id = tmp_sessions_root
        image_ir = self._lower_image_md(
            "![alt](media/foo.png)\n",
            style_mapping={"image": "S001", "paragraph": "S001"},
            session_id=session_id,
        )
        expected = (sessions_root / session_id / "workspace" / "media" / "foo.png").resolve()
        assert Path(image_ir.src_path) == expected
        assert image_ir.alt_text == "alt"

    def test_image_block_without_session_preserves_relative(self, tmp_sessions_root):
        # session_id=None: 老路径, IR 保留相对字符串 (测试 / 兼容场景)
        image_ir = self._lower_image_md(
            "![alt](media/foo.png)\n",
            style_mapping={"image": "S001", "paragraph": "S001"},
            session_id=None,
        )
        assert image_ir.src_path == "media/foo.png"
