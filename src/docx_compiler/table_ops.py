import copy

from lxml import etree

try:
    from docx_tools.common import (
        NS,
        W,
        append_run_to_paragraph,
        cell_text,
        get_cell_by_index,
        get_row_by_index,
        get_table_by_index,
        load_document_xml,
        paragraphs,
        row_cells,
        table_rows,
        table_summary,
        write_document_xml,
    )
except ModuleNotFoundError:
    from src.docx_tools.common import (
        NS,
        W,
        append_run_to_paragraph,
        cell_text,
        get_cell_by_index,
        get_row_by_index,
        get_table_by_index,
        load_document_xml,
        paragraphs,
        row_cells,
        table_rows,
        table_summary,
        write_document_xml,
    )

from .ir import CellIR, ParagraphIR, RunIR, TableIR, TableRowIR
from .render import render_table


def table_ir_from_texts(cell_texts: list[list[str]], column_widths_twips: list[int] | None = None) -> TableIR:
    rows = []
    for row_texts in cell_texts:
        cells = []
        for text in row_texts:
            cells.append(CellIR(blocks=[ParagraphIR(runs=[RunIR.text_run(text or "")])]))
        rows.append(TableRowIR(cells=cells))
    return TableIR(rows=rows, column_widths_twips=column_widths_twips or [])


def insert_table_after_paragraph_op(
    docx_path: str,
    output_path: str,
    paragraph_index: int,
    cell_texts: list[list[str]],
    column_widths_twips: list[int] | None = None,
) -> dict:
    root = load_document_xml(docx_path)
    all_paragraphs = paragraphs(root)
    if paragraph_index < 1 or paragraph_index > len(all_paragraphs):
        raise IndexError(f"paragraph_index out of range: {paragraph_index}, paragraph_count={len(all_paragraphs)}")
    table_ir = table_ir_from_texts(cell_texts, column_widths_twips)
    table = render_table(table_ir)
    all_paragraphs[paragraph_index - 1].addnext(table)
    write_document_xml(docx_path, output_path, root)
    return {
        "docx_path": docx_path,
        "output_path": output_path,
        "paragraph_index": paragraph_index,
        "inserted_table_rows": len(table_ir.rows),
        "inserted_table_cols": max((len(row.cells) for row in table_ir.rows), default=0),
    }


def insert_table_in_cell_op(
    docx_path: str,
    output_path: str,
    table_index: int,
    row_index: int,
    cell_index: int,
    cell_texts: list[list[str]],
    column_widths_twips: list[int] | None = None,
) -> dict:
    root = load_document_xml(docx_path)
    table = get_table_by_index(root, table_index)
    row = get_row_by_index(table, row_index)
    cell = get_cell_by_index(row, cell_index)
    before_summary = table_summary(table)
    nested = render_table(table_ir_from_texts(cell_texts, column_widths_twips))
    _append_nested_table(cell, nested)
    write_document_xml(docx_path, output_path, root)
    return {
        "docx_path": docx_path,
        "output_path": output_path,
        "table_index": table_index,
        "row_index": row_index,
        "cell_index": cell_index,
        "inserted_nested_rows": len(cell_texts),
        "inserted_nested_cols": max((len(row_texts) for row_texts in cell_texts), default=0),
        "outer_table_before": before_summary,
        "outer_table_after": table_summary(table),
    }


def insert_table_column_after_op(
    docx_path: str,
    output_path: str,
    table_index: int,
    column_index: int,
    cell_texts: list[str] | None = None,
    copy_from: str = "left",
) -> dict:
    root = load_document_xml(docx_path)
    table = get_table_by_index(root, table_index)
    rows = table_rows(table)
    if not rows:
        raise ValueError("target table has no rows")
    max_cells = max(len(row_cells(row)) for row in rows)
    if column_index < 1 or column_index > max_cells:
        raise IndexError(f"column_index out of range: {column_index}, column_count={max_cells}")

    before = table_summary(table)
    for row_index, row in enumerate(rows, start=1):
        cells = row_cells(row)
        if column_index > len(cells):
            continue
        source_cell = _select_column_source_cell(cells, column_index, copy_from)
        new_cell = copy.deepcopy(source_cell)
        _set_cell_single_text(new_cell, (cell_texts or [])[row_index - 1] if cell_texts and row_index <= len(cell_texts) else "")
        cells[column_index - 1].addnext(new_cell)
    _insert_grid_column_after(table, column_index)
    write_document_xml(docx_path, output_path, root)
    return {
        "docx_path": docx_path,
        "output_path": output_path,
        "table_index": table_index,
        "inserted_after_column_index": column_index,
        "inserted_column_index": column_index + 1,
        "copy_from": copy_from,
        "before_table": before,
        "after_table": table_summary(table),
    }


def merge_table_cells_horizontal_op(
    docx_path: str,
    output_path: str,
    table_index: int,
    row_index: int,
    start_cell_index: int,
    span: int,
) -> dict:
    if span < 2:
        raise ValueError("span must be >= 2")
    root = load_document_xml(docx_path)
    table = get_table_by_index(root, table_index)
    row = get_row_by_index(table, row_index)
    cells = row_cells(row)
    end = start_cell_index + span - 1
    if start_cell_index < 1 or end > len(cells):
        raise IndexError(f"merge range out of range: start={start_cell_index}, span={span}, cell_count={len(cells)}")
    before = table_summary(table)
    first = cells[start_cell_index - 1]
    _set_grid_span(first, span)
    for cell in cells[start_cell_index:end]:
        row.remove(cell)
    write_document_xml(docx_path, output_path, root)
    return {
        "docx_path": docx_path,
        "output_path": output_path,
        "table_index": table_index,
        "row_index": row_index,
        "start_cell_index": start_cell_index,
        "span": span,
        "before_table": before,
        "after_table": table_summary(table),
    }


def set_paragraph_indent_op(
    docx_path: str,
    output_path: str,
    paragraph_index: int,
    left_twips: int | None = None,
    first_line_twips: int | None = None,
    hanging_twips: int | None = None,
) -> dict:
    root = load_document_xml(docx_path)
    all_paragraphs = paragraphs(root)
    if paragraph_index < 1 or paragraph_index > len(all_paragraphs):
        raise IndexError(f"paragraph_index out of range: {paragraph_index}, paragraph_count={len(all_paragraphs)}")
    paragraph = all_paragraphs[paragraph_index - 1]
    ppr = paragraph.find(f"{W}pPr")
    if ppr is None:
        ppr = etree.Element(f"{W}pPr")
        paragraph.insert(0, ppr)
    for child in list(ppr):
        if child.tag == f"{W}ind":
            ppr.remove(child)
    ind = etree.Element(f"{W}ind")
    if left_twips is not None:
        ind.set(f"{W}left", str(int(left_twips)))
    if first_line_twips is not None:
        ind.set(f"{W}firstLine", str(int(first_line_twips)))
    if hanging_twips is not None:
        ind.set(f"{W}hanging", str(int(hanging_twips)))
    ppr.append(ind)
    write_document_xml(docx_path, output_path, root)
    return {
        "docx_path": docx_path,
        "output_path": output_path,
        "paragraph_index": paragraph_index,
        "indent": {
            "left_twips": left_twips,
            "first_line_twips": first_line_twips,
            "hanging_twips": hanging_twips,
        },
    }


def _append_nested_table(cell, nested_table) -> None:
    trailing_paragraph = cell.xpath("./w:p[last()]", namespaces=NS)
    if trailing_paragraph:
        trailing_paragraph[0].addnext(nested_table)
    else:
        cell.append(nested_table)
    if cell[-1].tag != f"{W}p":
        cell.append(etree.Element(f"{W}p", nsmap=cell.nsmap))


def _select_column_source_cell(cells, column_index: int, copy_from: str):
    mode = (copy_from or "left").lower()
    if mode == "right" and column_index < len(cells):
        return cells[column_index]
    if mode not in {"left", "right"}:
        raise ValueError("copy_from must be left or right")
    return cells[column_index - 1]


def _set_cell_single_text(cell, text: str) -> None:
    tc_pr = cell.find(f"{W}tcPr")
    for child in list(cell):
        if child is not tc_pr:
            cell.remove(child)
    paragraph = etree.SubElement(cell, f"{W}p")
    if text:
        append_run_to_paragraph(paragraph, text)


def _insert_grid_column_after(table, column_index: int) -> None:
    grid = table.find(f"{W}tblGrid")
    if grid is None:
        grid = etree.Element(f"{W}tblGrid")
        tbl_pr = table.find(f"{W}tblPr")
        if tbl_pr is not None:
            tbl_pr.addnext(grid)
        else:
            table.insert(0, grid)
    cols = grid.xpath("./w:gridCol", namespaces=NS)
    new_col = copy.deepcopy(cols[column_index - 1]) if 1 <= column_index <= len(cols) else etree.Element(f"{W}gridCol")
    if cols and 1 <= column_index <= len(cols):
        cols[column_index - 1].addnext(new_col)
    else:
        grid.append(new_col)


def _set_grid_span(cell, span: int) -> None:
    tc_pr = cell.find(f"{W}tcPr")
    if tc_pr is None:
        tc_pr = etree.Element(f"{W}tcPr")
        cell.insert(0, tc_pr)
    for child in list(tc_pr):
        if child.tag == f"{W}gridSpan":
            tc_pr.remove(child)
    grid_span = etree.Element(f"{W}gridSpan")
    grid_span.set(f"{W}val", str(int(span)))
    tc_pr.append(grid_span)
