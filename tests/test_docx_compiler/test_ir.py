"""test_ir.py — docx_compiler/ir.py 纯 dataclass 测试 (PR-1.3)

ir.py 是编译器地基, 全是 @dataclass 没有任何 I/O 依赖, 测试成本最低.
共 6 case:

  - RunIR 三个工厂方法 (text_run / tab / line_break)
  - ParagraphIndent.is_empty() 三种状态
  - field(default_factory=list) 不共享状态 (重要: 防止用户态改一处影响全部)
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from docx_compiler.ir import (
    CodeBlockIR,
    FormulaIR,
    ImageIR,
    ParagraphIndent,
    ParagraphIR,
    RunIR,
    TableIR,
    TableRowIR,
    CellIR,
)


# =====================================================================
# RunIR 工厂方法: 3 case
# =====================================================================

class TestRunIRFactories:
    """RunIR 的三个 @classmethod 工厂."""

    def test_text_run_factory_creates_text_kind(self):
        """text_run() → RunIR(kind='text', text=<输入>)."""
        run = RunIR.text_run("hello", bold=True, italic=True)
        assert run.text == "hello"
        assert run.kind == "text"
        assert run.bold is True
        assert run.italic is True

    def test_tab_factory_creates_tab_kind(self):
        """tab() → RunIR(kind='tab'), text 默认为空."""
        run = RunIR.tab()
        assert run.kind == "tab"
        assert run.text == ""  # default
        assert run.bold is False  # default

    def test_line_break_factory_creates_break_kind(self):
        """line_break() → RunIR(kind='break'), text 默认为空."""
        run = RunIR.line_break()
        assert run.kind == "break"
        assert run.text == ""


# =====================================================================
# ParagraphIndent.is_empty(): 2 case
# =====================================================================

class TestParagraphIndentIsEmpty:
    """ParagraphIndent 的 is_empty() 边界."""

    def test_all_none_returns_true(self):
        """三字段全 None → is_empty() == True (调用方应不写 <w:ind> 节点)."""
        ind = ParagraphIndent()
        assert ind.is_empty() is True

    def test_any_field_set_returns_false(self):
        """任一字段非 None → is_empty() == False."""
        assert ParagraphIndent(left_twips=720).is_empty() is False
        assert ParagraphIndent(first_line_twips=480).is_empty() is False
        assert ParagraphIndent(hanging_twips=240).is_empty() is False
        # 多个字段也 False
        assert ParagraphIndent(left_twips=720, first_line_twips=480).is_empty() is False


# =====================================================================
# field(default_factory=list) 不共享状态: 1 case
# =====================================================================

class TestDataclassListFieldIsolation:
    """验证 dataclass 字段用 default_factory=list 时, 每次 new 实例 list 是独立对象.

    这条很重要: 如果写成 field(default=[]) 会导致所有实例共享同一 list,
    改一处全改. Python dataclass 用 default_factory=list 强制每次新建.
    """

    def test_runs_list_not_shared_between_paragraph_instances(self):
        """两个 ParagraphIR 实例的 runs list 互不影响."""
        p1 = ParagraphIR()
        p2 = ParagraphIR()
        # 初始都为空
        assert p1.runs == []
        assert p2.runs == []
        # 改 p1 不会影响 p2
        p1.runs.append(RunIR.text_run("hello"))
        assert p1.runs == [RunIR.text_run("hello")]
        assert p2.runs == [], f"p2.runs 仍应为空, 实际 {p2.runs}"

    def test_table_rows_and_cells_not_shared(self):
        """TableIR / TableRowIR / CellIR 同理: 不共享 list."""
        t1 = TableIR()
        t2 = TableIR()
        t1.rows.append(TableRowIR())
        assert t1.rows == [TableRowIR()]
        assert t2.rows == []

        cell1 = CellIR()
        cell2 = CellIR()
        cell1.blocks.append(ParagraphIR())
        assert len(cell1.blocks) == 1
        assert cell2.blocks == []


# =====================================================================
# IR 多态性 smoke: 1 case (覆盖各种 IR 子类型能正常构造)
# =====================================================================

class TestIRPolymorphism:
    """smoke: 各 IR 子类型能正常构造, 字段默认值符合预期."""

    def test_all_ir_subtypes_construct_with_defaults(self):
        """9 个 IR 类型都能用默认值构造 (说明 dataclass 装饰正确)."""
        instances = [
            RunIR(),
            ParagraphIR(),
            ParagraphIndent(),
            CellIR(),
            TableRowIR(),
            TableIR(),
            CodeBlockIR(code="print(1)"),
            FormulaIR(source="E=mc^2"),
            ImageIR(src_path="media/foo.png"),
        ]
        for inst in instances:
            assert inst is not None
        # 关键字段默认值检查
        assert CodeBlockIR(code="x").language is None
        assert CodeBlockIR(code="x").render_mode == "code_paragraphs"
        assert FormulaIR(source="x").source_format == "latex"
        assert FormulaIR(source="x").display is True
        assert ImageIR(src_path="x").alt_text == ""
        assert ImageIR(src_path="x").alignment == "center"
        assert ParagraphIR().block_type == "paragraph"
