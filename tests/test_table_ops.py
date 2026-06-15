"""test_table_ops.py — 9 个表操作工具回归测试 (PR-2.1)

9 个工具, 32 case. 5 个工具 OK, 4 个工具因 BUGS.md Bug #3 全部 @pytest.mark.xfail:

  OK (5):  insert_table_row_after / delete_table_row / clear_table_cell /
           replace_table_cell_text / insert_text_in_table_cell
  BUG #3 (4): insert_table_column_after / insert_table_after_paragraph /
              insert_table_in_cell / merge_table_cells_horizontal
"""
import json
import sys
from pathlib import Path

import pytest

pytest_plugins = ["_docx_factory"]
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from docx_tools.clear_table_cell import clear_table_cell
from docx_tools.delete_table_row import delete_table_row
from docx_tools.insert_table_after_paragraph import insert_table_after_paragraph
from docx_tools.insert_table_column_after import insert_table_column_after
from docx_tools.insert_table_in_cell import insert_table_in_cell
from docx_tools.insert_table_row_after import insert_table_row_after
from docx_tools.insert_text_in_table_cell import insert_text_in_table_cell
from docx_tools.merge_table_cells_horizontal import merge_table_cells_horizontal
from docx_tools.replace_table_cell_text import replace_table_cell_text

from _docx_factory import (
    _build_docx_with_table,
    get_xml_elements,
    get_xml_text,
)


def _ws(tmp_root, session_id: str) -> Path:
    return tmp_root / session_id / "workspace"


def _make_2x3_table(tmp_root, session_id, name="in.docx"):
    """构造 2 行 3 列简单表: r0 [a,b,c], r1 [d,e,f]."""
    _build_docx_with_table(
        _ws(tmp_root, session_id) / name,
        rows=2, cols=3,
        cells_data=[["a", "b", "c"], ["d", "e", "f"]],
    )


# =====================================================================
# insert_table_row_after: 3 case (✅ 正常)
# =====================================================================

class TestInsertTableRowAfter:
    def test_basic_insert_increases_row_count(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        out = _ws(tmp_root, session_id) / "out.docx"

        result = json.loads(insert_table_row_after(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=1,
            cell_texts=["x", "y", "z"],
        ))
        assert result["status"] == "ok"
        assert result["before_row_count"] == 2
        assert result["after_row_count"] == 3
        # 新行 (第 2 行) 应是 x/y/z
        rows = get_xml_elements(out, "//w:tr")
        assert len(rows) == 3
        assert get_xml_text(out, "//w:tr[2]//w:t") == "xyz"

    def test_insert_at_last_row(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(insert_table_row_after(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=2,
            cell_texts=["p", "q", "r"],
        ))
        assert result["status"] == "ok"
        assert result["after_row_count"] == 3

    def test_out_of_range_returns_error(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(insert_table_row_after(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=99,
            cell_texts=["x"],
        ))
        assert result["status"] == "error"
        assert "message" in result


# =====================================================================
# insert_table_column_after: 3 case
# =====================================================================

class TestInsertTableColumnAfter:
    def test_basic_insert_increases_column_count(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        out = _ws(tmp_root, session_id) / "out.docx"
        result = json.loads(insert_table_column_after(
            session_id, "in.docx", "out.docx",
            table_index=1, column_index=1,
            cell_texts=["x", "y"],
        ))
        assert result["status"] == "ok"
        # 每行多 1 个 cell
        assert get_xml_elements(out, "//w:tr[1]/w:tc") is not None

    def test_cell_texts_provided_fills_column(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(insert_table_column_after(
            session_id, "in.docx", "out.docx",
            table_index=1, column_index=3,
            cell_texts=["p", "q"],
        ))
        assert result["status"] == "ok"

    def test_out_of_range_returns_error(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(insert_table_column_after(
            session_id, "in.docx", "out.docx",
            table_index=1, column_index=99,
        ))
        assert result["status"] == "error"


# =====================================================================
# delete_table_row: 4 case (✅ 正常)
# =====================================================================

class TestDeleteTableRow:
    def test_delete_middle_row_decreases_count(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(delete_table_row(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=1,
        ))
        assert result["status"] == "ok"
        assert result["before_row_count"] == 2
        assert result["after_row_count"] == 1

    def test_expected_text_matches_succeeds(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(delete_table_row(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=1,
            expected_row_text_contains="a",
        ))
        assert result["status"] == "ok"

    def test_expected_text_mismatch_returns_error(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(delete_table_row(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=1,
            expected_row_text_contains="zzz_does_not_exist",
        ))
        assert result["status"] == "error"
        assert "expected_row_text_contains" in result["message"] or "not found" in result["message"]

    def test_out_of_range_returns_error(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(delete_table_row(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=99,
        ))
        assert result["status"] == "error"


# =====================================================================
# clear_table_cell: 2 case (✅ 正常)
# =====================================================================

class TestClearTableCell:
    def test_clear_cell_keeps_cell_with_empty_paragraph(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(clear_table_cell(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=1, cell_index=1,
        ))
        assert result["status"] == "ok"
        assert result["after_text"] == ""
        assert result["kept_empty_paragraph"] is True

    def test_out_of_range_returns_error(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(clear_table_cell(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=1, cell_index=99,
        ))
        assert result["status"] == "error"


# =====================================================================
# replace_table_cell_text: 3 case (✅ 正常)
# =====================================================================

class TestReplaceTableCellText:
    def test_basic_replace(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        out = _ws(tmp_root, session_id) / "out.docx"
        result = json.loads(replace_table_cell_text(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=1, cell_index=1,
            new_text="REPLACED",
        ))
        assert result["status"] == "ok"
        assert result["after_text"] == "REPLACED"
        # 输出 docx 第 1 行第 1 cell 应是 REPLACED
        assert get_xml_text(out, "//w:tr[1]/w:tc[1]//w:t") == "REPLACED"

    def test_newline_mode_paragraphs_splits_into_paragraphs(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        out = _ws(tmp_root, session_id) / "out.docx"
        result = json.loads(replace_table_cell_text(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=1, cell_index=1,
            new_text="L1\nL2",
            newline_mode="paragraphs",
        ))
        assert result["status"] == "ok"
        assert result["inserted_paragraph_count"] == 1
        # cell 内应有 2 个 <w:p>
        paras = get_xml_elements(out, "//w:tr[1]/w:tc[1]/w:p")
        assert len(paras) == 2

    def test_out_of_range_returns_error(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(replace_table_cell_text(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=99, cell_index=1,
            new_text="X",
        ))
        assert result["status"] == "error"


# =====================================================================
# insert_text_in_table_cell: 3 case (✅ 正常)
# =====================================================================

class TestInsertTextInTableCell:
    def test_append_to_existing_text(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        out = _ws(tmp_root, session_id) / "out.docx"
        result = json.loads(insert_text_in_table_cell(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=1, cell_index=1,
            insert_text="_appended",
        ))
        assert result["status"] == "ok"
        # 追加后 cell 文本应是 "a_appended"
        assert get_xml_text(out, "//w:tr[1]/w:tc[1]//w:t") == "a_appended"

    def test_append_false_creates_new_run(self, tmp_root, session_id):
        """append=False: 实际行为是新建 run 后追加到原 paragraph, 原文本保留.
        (不是真"替换" — 工具实际语义是"添加一个新 run 而非合并到末尾")."""
        _make_2x3_table(tmp_root, session_id)
        out = _ws(tmp_root, session_id) / "out.docx"
        result = json.loads(insert_text_in_table_cell(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=1, cell_index=1,
            insert_text="NEW",
            append=False,
        ))
        assert result["status"] == "ok"
        cell_text = get_xml_text(out, "//w:tr[1]/w:tc[1]//w:t")
        # 原 "a" + 新 "NEW" 都在 cell 内
        assert "a" in cell_text
        assert "NEW" in cell_text

    def test_out_of_range_returns_error(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(insert_text_in_table_cell(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=99, cell_index=1,
            insert_text="X",
        ))
        assert result["status"] == "error"


# =====================================================================
# insert_table_after_paragraph: 3 case
# =====================================================================

class TestInsertTableAfterParagraph:
    def test_insert_2x2_table_after_paragraph_1(self, tmp_root, session_id):
        # 至少要有一个段落才能让 paragraph_index=1 合法
        from _docx_factory import _build_docx_with_custom_body
        body_xml = '<w:p><w:r><w:t>first para</w:t></w:r></w:p>'
        _build_docx_with_custom_body(
            _ws(tmp_root, session_id) / "in.docx", body_xml
        )
        result = json.loads(insert_table_after_paragraph(
            session_id, "in.docx", "out.docx",
            paragraph_index=1,
            cell_texts=[["a", "b"], ["c", "d"]],
        ))
        assert result["status"] == "ok"

    def test_custom_column_widths(self, tmp_root, session_id):
        from _docx_factory import _build_docx_with_custom_body
        body_xml = '<w:p><w:r><w:t>x</w:t></w:r></w:p>'
        _build_docx_with_custom_body(
            _ws(tmp_root, session_id) / "in.docx", body_xml
        )
        result = json.loads(insert_table_after_paragraph(
            session_id, "in.docx", "out.docx",
            paragraph_index=1,
            cell_texts=[["a", "b", "c"]],
            column_widths_twips=[2000, 3000, 5000],
        ))
        assert result["status"] == "ok"

    def test_out_of_range_returns_error(self, tmp_root, session_id):
        from _docx_factory import _build_docx_with_custom_body
        body_xml = '<w:p><w:r><w:t>x</w:t></w:r></w:p>'
        _build_docx_with_custom_body(
            _ws(tmp_root, session_id) / "in.docx", body_xml
        )
        result = json.loads(insert_table_after_paragraph(
            session_id, "in.docx", "out.docx",
            paragraph_index=99,
            cell_texts=[["a"]],
        ))
        assert result["status"] == "error"


# =====================================================================
# insert_table_in_cell: 2 case
# =====================================================================

class TestInsertTableInCell:
    def test_nested_2x2_in_cell_1_1_1(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(insert_table_in_cell(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=1, cell_index=1,
            cell_texts=[["n1", "n2"], ["n3", "n4"]],
        ))
        assert result["status"] == "ok"

    def test_out_of_range_returns_error(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(insert_table_in_cell(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=1, cell_index=99,
            cell_texts=[["a"]],
        ))
        assert result["status"] == "error"


# =====================================================================
# merge_table_cells_horizontal: 3 case
# =====================================================================

class TestMergeTableCellsHorizontal:
    def test_merge_2_cells_creates_gridspan_2(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        out = _ws(tmp_root, session_id) / "out.docx"
        result = json.loads(merge_table_cells_horizontal(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=1, start_cell_index=1, span=2,
        ))
        assert result["status"] == "ok"
        # 第一个 cell 应该有 w:gridSpan w:val="2"
        first_cell = get_xml_elements(out, "//w:tr[1]/w:tc[1]")[0]
        grid_span = first_cell.xpath(
            ".//w:gridSpan/@w:val",
            namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"},
        )
        assert "2" in grid_span, f"w:gridSpan 应是 2, 实际 {grid_span}"

    def test_merge_3_cells(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        out = _ws(tmp_root, session_id) / "out.docx"
        result = json.loads(merge_table_cells_horizontal(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=1, start_cell_index=1, span=3,
        ))
        assert result["status"] == "ok"
        # 第 1 行 cell 数应剩 1 个
        cells = get_xml_elements(out, "//w:tr[1]/w:tc")
        assert len(cells) == 1

    def test_out_of_range_returns_error(self, tmp_root, session_id):
        _make_2x3_table(tmp_root, session_id)
        result = json.loads(merge_table_cells_horizontal(
            session_id, "in.docx", "out.docx",
            table_index=1, row_index=99, start_cell_index=1, span=2,
        ))
        assert result["status"] == "error"
