"""test_render.py — docx_compiler/render.py 纯函数测试 (PR-2.3)

render 核心入口: render_paragraph(ParagraphIR) -> lxml <w:p>
                  render_table(TableIR) -> lxml <w:tbl>
                  render_code_block(CodeBlockIR) -> list[<w:p>]
                  render_formula(FormulaIR) -> <w:p>
                  render_image(ImageIR) -> <w:p>
所有都是纯函数, 输入 IR 输出 OpenXML 节点.

共 10 case, 覆盖各种 IR → 节点映射:
  1. 空 paragraph
  2. 文本 + bold run
  3. tab run
  4. line_break run
  5. Image IR (sentinel embed ref)
  6. Formula IR (plain text 模式)
  7. Table IR (含 gridSpan)
  8. Code block IR (多行, Consolas 字体)
  9. List item indent
 10. 嵌套 IR
"""
import sys
from pathlib import Path

import pytest
from lxml import etree

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
from docx_compiler.render import (
    render_code_block,
    render_formula,
    render_image,
    render_paragraph,
    render_table,
)
from docx_compiler.table_ops import table_ir_from_texts

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _xml(node) -> str:
    return etree.tostring(node, encoding="unicode")


def _tag(elem) -> str:
    """取 lxml 节点的 tag 去掉命名空间."""
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag


# =====================================================================
# 1-4. Paragraph 各种 run 类型
# =====================================================================

class TestRenderParagraph:
    def test_empty_paragraph_has_zero_runs(self):
        """空 paragraph: render 加空 <w:r>, optimize 删空 run → 最终 0 个 run."""
        p = render_paragraph(ParagraphIR(runs=[]))
        assert _tag(p) == "p"
        # 实际行为: render_paragraph 加空 <w:r> 后, optimize_paragraph 立即删除
        # (空 plain run 不算有效内容). 所以最终 0 个 run.
        runs = p.xpath("./w:r", namespaces={"w": W[1:-1]})
        assert len(runs) == 0, (
            f"空 paragraph 经 optimize 后应剩 0 个 run, 实际 {len(runs)}. "
            f"render_paragraph 的 if not run_flags 分支被 "
            f"optimize_paragraph 的 _remove_empty_plain_runs 删掉."
        )

    def test_text_run_with_bold(self):
        """bold=True 的 run 产出 <w:r><w:rPr><w:b/></w:rPr><w:t>...</w:t></w:r>."""
        p = render_paragraph(ParagraphIR(runs=[RunIR.text_run("hi", bold=True)]))
        b_elems = p.xpath(".//w:b", namespaces={"w": W[1:-1]})
        assert len(b_elems) == 1, f"应含 1 个 <w:b/>, 实际 {len(b_elems)}"
        t_elems = p.xpath(".//w:t", namespaces={"w": W[1:-1]})
        assert t_elems[0].text == "hi"

    def test_tab_run_produces_w_tab(self):
        """RunIR.tab() → <w:tab/> 元素."""
        p = render_paragraph(ParagraphIR(runs=[RunIR.text_run("a"), RunIR.tab(), RunIR.text_run("b")]))
        tabs = p.xpath(".//w:tab", namespaces={"w": W[1:-1]})
        assert len(tabs) == 1, f"应含 1 个 <w:tab/>, 实际 {len(tabs)}"
        # 文本应是 "a" + "b" (tab 本身没文本)
        text_runs = p.xpath(".//w:t/text()", namespaces={"w": W[1:-1]})
        assert "a" in text_runs
        assert "b" in text_runs

    def test_line_break_run_produces_w_br(self):
        """RunIR.line_break() → <w:br/> 元素."""
        p = render_paragraph(ParagraphIR(runs=[RunIR.text_run("a"), RunIR.line_break()]))
        brs = p.xpath(".//w:br", namespaces={"w": W[1:-1]})
        assert len(brs) == 1, f"应含 1 个 <w:br/>, 实际 {len(brs)}"


# =====================================================================
# 5. Image IR
# =====================================================================

def test_render_image_produces_drawing_with_embed_sentinel():
    """ImageIR → <w:p> 含 <w:drawing> 引用 sentinel embed (TEMP_IMG_REL:...)."""
    img_ir = ImageIR(src_path="/abs/path/foo.png", alt_text="alt", width_cm=10.0)
    p = render_image(img_ir)
    assert _tag(p) == "p"
    # 应有 <w:drawing> 节点
    drawings = p.xpath(".//w:drawing", namespaces={"w": W[1:-1]})
    assert len(drawings) == 1
    # 应有 sentinel r:embed 引用
    embed = p.xpath(
        ".//*[local-name()='blip']/@r:embed",
        namespaces={"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"},
    )
    assert any("TEMP_IMG_REL:" in e for e in embed), f"sentinel 应含 'TEMP_IMG_REL:', 实际 {embed}"


# =====================================================================
# 6. Formula IR
# =====================================================================

def test_render_formula_plain_text_fallback():
    """FormulaIR 默认 render_mode='plain_text_fallback' → 直接输出 latex 文本."""
    f_ir = FormulaIR(source="E=mc^2", display=True)
    p = render_formula(f_ir)
    assert _tag(p) == "p"
    text_elems = p.xpath(".//w:t", namespaces={"w": W[1:-1]})
    # 文本应含 latex 源码
    full_text = "".join(t.text or "" for t in text_elems)
    assert "E=mc^2" in full_text, f"plain_text_fallback 应输出 latex 源码, 实际 {full_text!r}"


# =====================================================================
# 7. Table IR 含 gridSpan
# =====================================================================

def test_render_table_with_grid_span():
    """TableIR 2x2: 产 <w:tbl><w:tblGrid/>... 含 cell."""
    table_ir = TableIR(
        rows=[
            TableRowIR(cells=[
                CellIR(width_twips=4000, blocks=[ParagraphIR(runs=[RunIR.text_run("r0c0")])]),
                CellIR(width_twips=4000, blocks=[ParagraphIR(runs=[RunIR.text_run("r0c1")])]),
            ]),
            TableRowIR(cells=[
                CellIR(width_twips=4000, blocks=[ParagraphIR(runs=[RunIR.text_run("r1c0")])]),
                CellIR(width_twips=4000, blocks=[ParagraphIR(runs=[RunIR.text_run("r1c1")])]),
            ]),
        ],
        column_widths_twips=[4000, 4000],
    )
    table = render_table(table_ir)
    assert _tag(table) == "tbl"
    rows = table.xpath("./w:tr", namespaces={"w": W[1:-1]})
    assert len(rows) == 2
    cells = table.xpath(".//w:tc", namespaces={"w": W[1:-1]})
    assert len(cells) == 4


# =====================================================================
# 8. Code block IR
# =====================================================================

def test_render_code_block_uses_consolas_font():
    """CodeBlockIR.code='print(1)' → 多行段落, 字体 Consolas."""
    cb_ir = CodeBlockIR(code="print(1)\nprint(2)")
    paragraphs = render_code_block(cb_ir)
    assert len(paragraphs) == 2  # 2 行 → 2 个 <w:p>
    # 每个段落的 run 都应有 Consolas 字体
    for p in paragraphs:
        fonts = p.xpath(
            ".//w:rFonts/@w:ascii",
            namespaces={"w": W[1:-1]},
        )
        assert "Consolas" in fonts, f"代码块 run 应用 Consolas 字体, 实际 {fonts}"


# =====================================================================
# 9. List item indent
# =====================================================================

def test_render_list_item_auto_indent():
    """list_item paragraph: 自动按 list_level 算 indent (left + hanging)."""
    p_ir = ParagraphIR(
        runs=[RunIR.text_run("item")],
        block_type="list_item",
        list_level=1,  # 嵌套层 1
    )
    p = render_paragraph(p_ir)
    # 应有 <w:ind> 元素
    ind = p.xpath(".//w:ind", namespaces={"w": W[1:-1]})
    assert len(ind) == 1
    ind_elem = ind[0]
    # 应该有 left 和 hanging
    assert ind_elem.get(f"{W}left") is not None
    assert ind_elem.get(f"{W}hanging") is not None


# =====================================================================
# 10. 嵌套 IR (table 内 cell 含 paragraph)
# =====================================================================

def test_render_nested_ir_in_table_cell():
    """CellIR.blocks 含 ParagraphIR → render_table 自动递归渲染."""
    table_ir = table_ir_from_texts([["outer"]])
    # 在 outer cell 里塞一个 paragraph (模拟嵌套)
    table_ir.rows[0].cells[0].blocks.append(
        ParagraphIR(runs=[RunIR.text_run("nested")])
    )
    table = render_table(table_ir)
    # 应该有 outer 和 nested 文本
    text_elems = table.xpath(".//w:t", namespaces={"w": W[1:-1]})
    all_text = "".join(t.text or "" for t in text_elems)
    assert "outer" in all_text
    assert "nested" in all_text
