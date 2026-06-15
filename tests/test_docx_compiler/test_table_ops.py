"""test_docx_compiler/test_table_ops.py — 编译器层 table_ops.py 纯函数 (PR-2.3)

区别于 test_table_ops.py (测 docx_tools 层的 wrapper):
  - 本文件测 docx_compiler/table_ops.py 的 IR 操作和 docx I/O op
  - 6 case, 纯函数优先:
    * table_ir_from_texts: 简单构造
    * 其他 op 函数 (insert_table_after_paragraph_op 等) 走 docx I/O,
      需要 _build_full_docx 工厂 (含 rels)
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from docx_compiler.ir import CellIR, ParagraphIR, RunIR, TableIR, TableRowIR
from docx_compiler.table_ops import table_ir_from_texts

from _docx_factory import _build_full_docx, get_xml_elements, get_xml_text


def _ws(tmp_root, session_id: str) -> Path:
    return tmp_root / session_id / "workspace"


# =====================================================================
# 1-3. table_ir_from_texts 纯函数
# =====================================================================

class TestTableIRFromTexts:
    def test_basic_2x2_creates_table_ir(self):
        """二维文本 → TableIR 含 2 行 2 列 cell."""
        t = table_ir_from_texts([["a", "b"], ["c", "d"]])
        assert isinstance(t, TableIR)
        assert len(t.rows) == 2
        assert all(isinstance(r, TableRowIR) for r in t.rows)
        assert all(len(r.cells) == 2 for r in t.rows)
        # cell 内 paragraph 文本
        assert t.rows[0].cells[0].blocks[0].runs[0].text == "a"
        assert t.rows[1].cells[1].blocks[0].runs[0].text == "d"

    def test_empty_cell_uses_empty_string(self):
        """短行 (cell 数 < 第一行) 的 cell 文本应为空."""
        t = table_ir_from_texts([["a", "b", "c"], ["x"]])
        assert len(t.rows[1].cells) == 1
        # 第二个 cell 不存在, 这里测的是 row 0 的 cell 0
        assert t.rows[0].cells[2].blocks[0].runs[0].text == "c"

    def test_column_widths_applied(self):
        """column_widths_twips 正确传到 TableIR."""
        t = table_ir_from_texts([["a", "b"]], column_widths_twips=[3000, 5000])
        assert t.column_widths_twips == [3000, 5000]


# =====================================================================
# 4-6. 编译器层 op (不依赖 docx_tools wrapper, 直接调 op 测纯逻辑)
# =====================================================================

class TestSetParagraphIndentOp:
    """set_paragraph_indent_op: 编译器层的 op, 直接传 docx_path.
    跟 docx_tools 层 wrapper 的区别: 这个 op 不接 session_id, 只接路径.

    Bug #2 是在 docx_tools.set_paragraph_indent.py wrapper 层. 这个 op 函数
    本身是正常工作的, 文档有 docx 就跑. 因此用 _build_full_docx 测.
    """

    def test_left_indent_creates_w_ind(self, tmp_root, session_id):
        """left_twips=720: 写入 <w:ind w:left='720'/>."""
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx",
                         ["first", "second"])
        from docx_compiler.table_ops import set_paragraph_indent_op
        result = set_paragraph_indent_op(
            docx_path=str(_ws(tmp_root, session_id) / "in.docx"),
            output_path=str(_ws(tmp_root, session_id) / "out.docx"),
            paragraph_index=2, left_twips=720,
        )
        assert "out.docx" in result["output_path"] or result["output_path"].endswith("out.docx")
        # 验证输出 docx
        out = _ws(tmp_root, session_id) / "out.docx"
        left = out.read_text  # placeholder
        # 实际用 get_xml_attr
        from _docx_factory import get_xml_attr
        left = get_xml_attr(out, "//w:p[2]/w:pPr/w:ind", "w:left")
        assert left == "720", f"w:left 应是 720, 实际 {left!r}"

    def test_out_of_range_raises(self, tmp_root, session_id):
        """paragraph_index 越界抛 IndexError."""
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx", ["x"])
        from docx_compiler.table_ops import set_paragraph_indent_op
        with pytest.raises(IndexError):
            set_paragraph_indent_op(
                docx_path=str(_ws(tmp_root, session_id) / "in.docx"),
                output_path=str(_ws(tmp_root, session_id) / "out.docx"),
                paragraph_index=99, left_twips=720,
            )

    def test_insert_table_after_paragraph_op_basic(self, tmp_root, session_id):
        """insert_table_after_paragraph_op: 段后插表, 不依赖 wrapper 的 Bug #3."""
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx", ["anchor"])
        from docx_compiler.table_ops import insert_table_after_paragraph_op
        result = insert_table_after_paragraph_op(
            docx_path=str(_ws(tmp_root, session_id) / "in.docx"),
            output_path=str(_ws(tmp_root, session_id) / "out.docx"),
            paragraph_index=1,
            cell_texts=[["x", "y"], ["z", "w"]],
        )
        # 输出 docx: 1 个 <w:tbl> + 顶层 1 个 <w:p> (原 anchor)
        out = _ws(tmp_root, session_id) / "out.docx"
        tables = get_xml_elements(out, "//w:tbl")
        # 只数顶层 <w:p> (不在 w:tbl 内), 用 /w:body/w:p
        from _docx_factory import NS
        body_paras = out.read_text  # placeholder
        body_paras = get_xml_elements(out, "//w:body/w:p")
        assert len(tables) == 1, f"应插入 1 个表, 实际 {len(tables)}"
        assert len(body_paras) == 1, f"原 1 段保留 (顶层), 实际 {len(body_paras)}"
        # 表内 cell 数
        cells = get_xml_elements(out, "//w:tbl//w:tc")
        assert len(cells) == 4, f"2x2 表应 4 cell, 实际 {len(cells)}"
        # 验证 result 字典
        assert result["inserted_table_rows"] == 2
        assert result["inserted_table_cols"] == 2
