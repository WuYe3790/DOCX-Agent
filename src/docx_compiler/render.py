import copy

from lxml import etree

try:
    from docx_tools.common import (
        NS,
        W,
        XML,
        apply_sample_format_to_paragraph,
        set_run_bold,
        set_text_preserve_space,
    )
except ModuleNotFoundError:
    from src.docx_tools.common import (
        NS,
        W,
        XML,
        apply_sample_format_to_paragraph,
        set_run_bold,
        set_text_preserve_space,
    )

from .ir import CellIR, ParagraphIR, RunIR, TableIR
from .optimizer import optimize_paragraph


def render_blocks_to_container(
    container,
    blocks: list[ParagraphIR | TableIR],
    style_samples: dict[str, dict] | None = None,
    clear_existing: bool = False,
) -> list:
    """Render block IR into a body-like or cell-like OpenXML container."""
    if clear_existing:
        for child in list(container):
            if child.tag != f"{W}tcPr":
                container.remove(child)

    rendered = []
    for block in blocks:
        if isinstance(block, ParagraphIR):
            element = render_paragraph(block, style_samples=style_samples)
        elif isinstance(block, TableIR):
            element = render_table(block, style_samples=style_samples)
        else:
            raise TypeError(f"unsupported block IR: {type(block).__name__}")
        container.append(element)
        rendered.append(element)

    if container.tag == f"{W}tc" and not container.xpath("./w:p", namespaces=NS):
        container.append(etree.Element(f"{W}p", nsmap=container.nsmap))
    return rendered


def render_paragraph(paragraph_ir: ParagraphIR, style_samples: dict[str, dict] | None = None, template_paragraph=None):
    nsmap = template_paragraph.nsmap if template_paragraph is not None else None
    paragraph = etree.Element(f"{W}p", nsmap=nsmap)
    if template_paragraph is not None:
        ppr = template_paragraph.find(f"{W}pPr")
        if ppr is not None:
            paragraph.append(copy.deepcopy(ppr))

    run_flags = []
    for run_ir in paragraph_ir.runs:
        run = _append_run(paragraph, run_ir)
        if run is not None:
            run_flags.append((run, run_ir))

    if not run_flags:
        paragraph.append(etree.Element(f"{W}r", nsmap=paragraph.nsmap))

    style_sample = None
    if style_samples and paragraph_ir.style_sample_id:
        style_sample = style_samples.get(paragraph_ir.style_sample_id)
    if style_sample:
        apply_sample_format_to_paragraph(paragraph, style_sample)

    for run, run_ir in run_flags:
        if run_ir.bold:
            set_run_bold(run, True)
        if run_ir.italic:
            _set_run_italic(run, True)

    _apply_paragraph_indent(paragraph, paragraph_ir)
    optimize_paragraph(paragraph)
    return paragraph


def render_table(table_ir: TableIR, style_samples: dict[str, dict] | None = None, template_table=None):
    table = etree.Element(f"{W}tbl", nsmap=template_table.nsmap if template_table is not None else None)
    if template_table is not None:
        tbl_pr = template_table.find(f"{W}tblPr")
        if tbl_pr is not None:
            table.append(copy.deepcopy(tbl_pr))
    else:
        tbl_pr = etree.SubElement(table, f"{W}tblPr")
        tbl_w = etree.SubElement(tbl_pr, f"{W}tblW")
        tbl_w.set(f"{W}w", "0")
        tbl_w.set(f"{W}type", "auto")
        _append_default_borders(tbl_pr)

    widths = table_ir.column_widths_twips or _default_widths(table_ir)
    grid = etree.SubElement(table, f"{W}tblGrid")
    for width in widths:
        col = etree.SubElement(grid, f"{W}gridCol")
        col.set(f"{W}w", str(int(width)))

    for row_ir in table_ir.rows:
        row = etree.SubElement(table, f"{W}tr")
        for index, cell_ir in enumerate(row_ir.cells):
            row.append(_render_cell(cell_ir, style_samples, widths[index] if index < len(widths) else None))
    return table


def _render_cell(cell_ir: CellIR, style_samples: dict[str, dict] | None, width_twips: int | None):
    cell = etree.Element(f"{W}tc")
    tc_pr = etree.SubElement(cell, f"{W}tcPr")
    width = cell_ir.width_twips if cell_ir.width_twips is not None else width_twips
    if width is not None:
        tc_w = etree.SubElement(tc_pr, f"{W}tcW")
        tc_w.set(f"{W}w", str(int(width)))
        tc_w.set(f"{W}type", "dxa")
    render_blocks_to_container(cell, cell_ir.blocks, style_samples=style_samples)
    return cell


def _append_run(paragraph, run_ir: RunIR):
    if run_ir.kind == "text" and run_ir.text == "":
        return None
    run = etree.SubElement(paragraph, f"{W}r")
    if run_ir.kind == "tab":
        etree.SubElement(run, f"{W}tab")
    elif run_ir.kind == "break":
        etree.SubElement(run, f"{W}br")
    else:
        _append_text_fragments(run, run_ir.text)
    return run


def _append_text_fragments(run, text: str) -> None:
    token = []
    for char in text:
        if char == "\t":
            _flush_text_token(run, token)
            etree.SubElement(run, f"{W}tab")
        elif char == "\n":
            _flush_text_token(run, token)
            etree.SubElement(run, f"{W}br")
        else:
            token.append(char)
    _flush_text_token(run, token)


def _flush_text_token(run, token: list[str]) -> None:
    if not token:
        return
    value = "".join(token)
    text_node = etree.SubElement(run, f"{W}t")
    set_text_preserve_space(text_node, value)
    if "  " in value:
        text_node.set(f"{XML}space", "preserve")
    token.clear()


def _apply_paragraph_indent(paragraph, paragraph_ir: ParagraphIR) -> None:
    indent = paragraph_ir.indent
    if indent is None and paragraph_ir.block_type == "list_item":
        level = int(paragraph_ir.list_level or 0)
        indent = type("Indent", (), {"left_twips": 360 * (level + 1), "first_line_twips": None, "hanging_twips": 180})()
    if indent is None or getattr(indent, "is_empty", lambda: False)():
        return

    ppr = paragraph.find(f"{W}pPr")
    if ppr is None:
        ppr = etree.Element(f"{W}pPr")
        paragraph.insert(0, ppr)
    for child in list(ppr):
        if child.tag == f"{W}ind":
            ppr.remove(child)
    ind = etree.Element(f"{W}ind")
    if indent.left_twips is not None:
        ind.set(f"{W}left", str(int(indent.left_twips)))
    if indent.first_line_twips is not None:
        ind.set(f"{W}firstLine", str(int(indent.first_line_twips)))
    if indent.hanging_twips is not None:
        ind.set(f"{W}hanging", str(int(indent.hanging_twips)))
    ppr.append(ind)


def _set_run_italic(run, enabled: bool) -> None:
    rpr = run.find(f"{W}rPr")
    if rpr is None:
        rpr = etree.Element(f"{W}rPr")
        run.insert(0, rpr)
    for child in list(rpr):
        if child.tag in {f"{W}i", f"{W}iCs"}:
            rpr.remove(child)
    if enabled:
        rpr.append(etree.Element(f"{W}i"))
        rpr.append(etree.Element(f"{W}iCs"))


def _append_default_borders(tbl_pr) -> None:
    borders = etree.SubElement(tbl_pr, f"{W}tblBorders")
    for tag in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = etree.SubElement(borders, f"{W}{tag}")
        border.set(f"{W}val", "single")
        border.set(f"{W}sz", "4")
        border.set(f"{W}space", "0")
        border.set(f"{W}color", "auto")


def _default_widths(table_ir: TableIR) -> list[int]:
    col_count = max((len(row.cells) for row in table_ir.rows), default=1)
    width = max(1200, 9000 // max(1, col_count))
    return [width] * col_count
