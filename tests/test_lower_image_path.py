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


# === lower_markdown_blocks 集成: 非图片 block 的 IR (PR-3.1 补 5 case) ===


class TestLowerMarkdownBlocksTable:
    """表格 markdown → TableIR, 含 rows/cells."""

    def _lower_table_md(self, md_text, style_mapping, session_id=None):
        blocks = parse_markdown_blocks(md_text)
        result = lower_markdown_blocks(blocks, style_mapping, session_id=session_id)
        return result

    def test_table_block_lowered_to_table_ir(self, tmp_sessions_root):
        """| h1 | h2 | 表 → TableIR, 含 1+ rows."""
        result = self._lower_table_md(
            "| 列1 | 列2 |\n| --- | --- |\n| a | b |",
            style_mapping={"table": "S001"},
        )
        # 找 layout_blocks 里的 TableIR
        from docx_compiler.ir import TableIR
        tables = [b for b in result.layout_blocks if isinstance(b, TableIR)]
        assert len(tables) == 1, f"应有 1 个 TableIR, 实际 {len(tables)}"
        assert len(tables[0].rows) >= 1


class TestLowerMarkdownBlocksList:
    """列表 markdown → ParagraphIR (list_item 类型), 带 list_level/marker."""

    def test_unordered_list_lowered_to_list_items(self, tmp_sessions_root):
        result = lower_markdown_blocks(
            parse_markdown_blocks("- a\n- b\n- c"),
            style_mapping={"list_item": "S001"},
        )
        from docx_compiler.ir import ParagraphIR
        items = [b for b in result.layout_blocks if isinstance(b, ParagraphIR)]
        assert len(items) == 3
        # 都应标 list_item 类型
        assert all(b.block_type == "list_item" for b in items)
        # 都应有 list_level (嵌套层)
        assert all(b.list_level is not None for b in items)


class TestLowerMarkdownBlocksCode:
    """代码块 markdown → CodeBlockIR, 含 code/language."""

    def test_fenced_code_lowered_to_code_block_ir(self, tmp_sessions_root):
        result = lower_markdown_blocks(
            parse_markdown_blocks("```python\nprint(1)\n```"),
            style_mapping={"code_block": "S001"},
        )
        from docx_compiler.ir import CodeBlockIR
        codes = [b for b in result.layout_blocks if isinstance(b, CodeBlockIR)]
        assert len(codes) == 1
        assert codes[0].language == "python"
        assert "print(1)" in codes[0].code


class TestLowerMarkdownBlocksFormula:
    """公式 markdown → FormulaIR, 含 source/source_format."""

    def test_display_formula_lowered_to_formula_ir(self, tmp_sessions_root):
        result = lower_markdown_blocks(
            parse_markdown_blocks("$$\nE=mc^2\n$$"),
            # 注意: lower.py:182 用 "formula" 这个 key, 不是 "formula_block"
            style_mapping={"formula": "S001"},
        )
        from docx_compiler.ir import FormulaIR
        formulas = [b for b in result.layout_blocks if isinstance(b, FormulaIR)]
        assert len(formulas) == 1
        assert formulas[0].source_format == "latex"
        assert "E=mc^2" in formulas[0].source


class TestLowerMarkdownBlocksMissingStyleMapping:
    """style_mapping 缺某 block type 的 key → diagnostic MISSING_STYLE_MAPPING."""

    def test_missing_style_mapping_key_adds_diagnostic(self, tmp_sessions_root):
        # 故意不给 paragraph style key
        result = lower_markdown_blocks(
            parse_markdown_blocks("plain paragraph"),
            style_mapping={},  # 缺所有 key
        )
        # 诊断里应有 MISSING_STYLE_MAPPING 错误
        from docx_compiler.diagnostics import has_errors
        assert has_errors(result.diagnostics), (
            "缺 style_mapping key 时应产生 error 级别 diagnostic"
        )
        # 检查诊断里含 "MISSING_STYLE_MAPPING" code
        codes = [d.code for d in result.diagnostics]
        assert any("MISSING_STYLE_MAPPING" in c for c in codes), (
            f"诊断 codes 应含 MISSING_STYLE_MAPPING, 实际 {codes}"
        )
