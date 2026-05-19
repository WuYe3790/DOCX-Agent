import copy
import hashlib
import json
import zipfile
from pathlib import Path

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"
XML = f"{{{XML_NS}}}"


def json_result(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def load_document_xml(docx_path: str):
    with zipfile.ZipFile(docx_path, "r") as docx:
        xml_bytes = docx.read("word/document.xml")
    return etree.fromstring(xml_bytes)


def write_document_xml(input_docx: str, output_docx: str, document_root) -> None:
    output_path = Path(output_docx)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document_bytes = etree.tostring(
        document_root,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
    )

    with zipfile.ZipFile(input_docx, "r") as zin:
        with zipfile.ZipFile(output_docx, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "word/document.xml":
                    zout.writestr(item, document_bytes)
                else:
                    zout.writestr(item, zin.read(item.filename))


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def paragraph_text(paragraph) -> str:
    return "".join(t.text or "" for t in paragraph.xpath(".//w:t", namespaces=NS))


def paragraph_text_segments(paragraph):
    segments = []
    cursor = 0
    for text_node in paragraph.xpath(".//w:t", namespaces=NS):
        value = text_node.text or ""
        start = cursor
        end = start + len(value)
        run = nearest_ancestor(text_node, f"{W}r")
        segments.append(
            {
                "start": start,
                "end": end,
                "text_node": text_node,
                "run": run,
                "text": value,
            }
        )
        cursor = end
    return segments


def nearest_ancestor(node, tag):
    current = node.getparent()
    while current is not None:
        if current.tag == tag:
            return current
        current = current.getparent()
    return None


def paragraphs(document_root):
    return document_root.xpath("//w:p", namespaces=NS)


def tables(document_root):
    return document_root.xpath("//w:tbl", namespaces=NS)


def table_rows(table):
    return table.xpath("./w:tr", namespaces=NS)


def row_cells(row):
    return row.xpath("./w:tc", namespaces=NS)


def cell_paragraphs(cell):
    return cell.xpath("./w:p", namespaces=NS)


def cell_text(cell) -> str:
    return "".join(t.text or "" for t in cell.xpath(".//w:t", namespaces=NS))


def row_text(row) -> str:
    return "".join(cell_text(cell) for cell in row_cells(row))


def get_table_by_index(document_root, table_index: int):
    all_tables = tables(document_root)
    if table_index < 1 or table_index > len(all_tables):
        raise IndexError(f"table_index out of range: {table_index}, table_count={len(all_tables)}")
    return all_tables[table_index - 1]


def get_row_by_index(table, row_index: int):
    rows = table_rows(table)
    if row_index < 1 or row_index > len(rows):
        raise IndexError(f"row_index out of range: {row_index}, row_count={len(rows)}")
    return rows[row_index - 1]


def get_cell_by_index(row, cell_index: int):
    cells = row_cells(row)
    if cell_index < 1 or cell_index > len(cells):
        raise IndexError(f"cell_index out of range: {cell_index}, cell_count={len(cells)}")
    return cells[cell_index - 1]


def table_summary(table):
    return {
        "row_count": len(table_rows(table)),
        "rows": [
            {
                "row_index": row_index,
                "text": row_text(row),
                "cells": [cell_text(cell) for cell in row_cells(row)],
            }
            for row_index, row in enumerate(table_rows(table), start=1)
        ],
    }


def clear_cell_to_empty_paragraph(cell):
    """清空单元格内容，保留 tcPr，并确保至少有一个空段落。"""
    existing_paragraphs = cell_paragraphs(cell)
    source_ppr = None
    if existing_paragraphs:
        ppr = existing_paragraphs[0].find(f"{W}pPr")
        if ppr is not None:
            source_ppr = copy.deepcopy(ppr)

    for child in list(cell):
        if child.tag != f"{W}tcPr":
            cell.remove(child)

    paragraph = etree.Element(f"{W}p", nsmap=cell.nsmap)
    if source_ppr is not None:
        paragraph.append(source_ppr)
    cell.append(paragraph)
    return paragraph


def first_text_run(element):
    for run in element.xpath(".//w:r", namespaces=NS):
        if "".join(t.text or "" for t in run.xpath(".//w:t", namespaces=NS)):
            return run
    runs = element.xpath(".//w:r", namespaces=NS)
    return runs[0] if runs else None


def element_index_among_same_tag(element) -> int:
    parent = element.getparent()
    if parent is None:
        return -1
    same = [child for child in parent if child.tag == element.tag]
    return same.index(element) + 1


def paragraph_location(paragraph):
    table_cell = nearest_ancestor(paragraph, f"{W}tc")
    if table_cell is None:
        return {"kind": "paragraph", "body_index": body_child_index(paragraph)}

    row = nearest_ancestor(paragraph, f"{W}tr")
    table = nearest_ancestor(paragraph, f"{W}tbl")
    return {
        "kind": "table_cell",
        "body_index": body_child_index(table),
        "table_index_near_parent": element_index_among_same_tag(table),
        "row_index": element_index_among_same_tag(row),
        "cell_index": element_index_among_same_tag(table_cell),
    }


def body_child_index(element) -> int:
    current = element
    while current.getparent() is not None and current.getparent().tag != f"{W}body":
        current = current.getparent()
    parent = current.getparent()
    if parent is None:
        return -1
    return list(parent).index(current) + 1


def set_text_preserve_space(text_node, value: str) -> None:
    text_node.text = value
    if value.startswith(" ") or value.endswith(" "):
        text_node.set(f"{XML}space", "preserve")
    elif f"{XML}space" in text_node.attrib:
        del text_node.attrib[f"{XML}space"]


def make_run_like(source_run, text: str):
    new_run = etree.Element(f"{W}r", nsmap=source_run.nsmap)
    rpr = source_run.find(f"{W}rPr")
    if rpr is not None:
        new_run.append(copy.deepcopy(rpr))
    text_node = etree.SubElement(new_run, f"{W}t")
    set_text_preserve_space(text_node, text)
    return new_run


def append_run_to_paragraph(paragraph, text: str, source_run=None):
    if source_run is None:
        existing_runs = paragraph.xpath("./w:r", namespaces=NS)
        source_run = existing_runs[-1] if existing_runs else etree.Element(f"{W}r")
    new_run = make_run_like(source_run, text)
    paragraph.append(new_run)
    return new_run


def make_paragraph_like(style_paragraph, text: str):
    """复制一个段落的段落属性和最后一个文本 run 的格式，创建新段落。"""
    new_paragraph = etree.Element(f"{W}p", nsmap=style_paragraph.nsmap)
    ppr = style_paragraph.find(f"{W}pPr")
    if ppr is not None:
        new_paragraph.append(copy.deepcopy(ppr))

    new_run = etree.SubElement(new_paragraph, f"{W}r")
    source_run = select_source_run(style_paragraph)
    if source_run is not None:
        rpr = source_run.find(f"{W}rPr")
        if rpr is not None:
            new_run.append(copy.deepcopy(rpr))

    text_node = etree.SubElement(new_run, f"{W}t")
    set_text_preserve_space(text_node, text)
    return new_paragraph


def split_text_for_paragraphs(text: str, newline_mode: str = "paragraphs"):
    """按统一规则处理换行：拆段落或转为空格。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in normalized:
        return normalized, []

    mode = (newline_mode or "paragraphs").lower()
    if mode == "inline":
        return normalized.replace("\n", " "), []
    if mode != "paragraphs":
        raise ValueError("newline_mode must be paragraphs or inline")

    lines = normalized.split("\n")
    return lines[0], lines[1:]


def insert_paragraphs_after(anchor_paragraph, lines, style_paragraph=None) -> int:
    """在指定段落后连续插入多个段落，返回插入数量。"""
    if not lines:
        return 0
    current = anchor_paragraph
    source = style_paragraph if style_paragraph is not None else anchor_paragraph
    count = 0
    for line in lines:
        new_paragraph = make_paragraph_like(source, line)
        current.addnext(new_paragraph)
        current = new_paragraph
        count += 1
    return count


def select_source_run(paragraph):
    runs = paragraph.xpath("./w:r", namespaces=NS)
    for run in reversed(runs):
        if "".join(t.text or "" for t in run.xpath(".//w:t", namespaces=NS)):
            return run
    return runs[-1] if runs else None


def isolate_text_range_in_paragraph(paragraph, start: int, end: int):
    """把段落逻辑文本范围拆成独立 run，返回覆盖该范围的 run 列表。"""
    if start < 0 or end <= start:
        raise ValueError("invalid text range")

    segments = paragraph_text_segments(paragraph)
    affected = [seg for seg in segments if seg["end"] > start and seg["start"] < end]
    if not affected:
        raise ValueError("text range does not touch any text node")

    if affected[0]["text_node"] is affected[-1]["text_node"]:
        seg = affected[0]
        local_start = start - seg["start"]
        local_end = end - seg["start"]
        return _split_single_segment(seg, local_start, local_end)

    result_runs = []
    first = affected[0]
    first_local_start = start - first["start"]
    if first_local_start > 0:
        split_runs = _split_single_segment(first, first_local_start, len(first["text"]))
        result_runs.extend(split_runs)
    else:
        result_runs.append(first["run"])

    for seg in affected[1:-1]:
        if seg["run"] not in result_runs:
            result_runs.append(seg["run"])

    last = affected[-1]
    last_local_end = end - last["start"]
    if last_local_end < len(last["text"]):
        split_runs = _split_single_segment(last, 0, last_local_end)
        result_runs.extend([run for run in split_runs if run not in result_runs])
    elif last["run"] not in result_runs:
        result_runs.append(last["run"])

    cleanup_empty_text_runs(paragraph)
    return result_runs


def _split_single_segment(segment, local_start: int, local_end: int):
    text = segment["text"]
    run = segment["run"]
    parent = run.getparent()
    if parent is None:
        raise ValueError("run has no parent")

    before = text[:local_start]
    middle = text[local_start:local_end]
    after = text[local_end:]
    index = parent.index(run)
    parent.remove(run)

    inserted = []
    offset = 0
    if before:
        parent.insert(index + offset, make_run_like(run, before))
        offset += 1
    middle_run = make_run_like(run, middle)
    parent.insert(index + offset, middle_run)
    inserted.append(middle_run)
    offset += 1
    if after:
        parent.insert(index + offset, make_run_like(run, after))
    return inserted


def replace_text_range_in_paragraph(paragraph, start: int, end: int, replacement: str):
    """在一个段落的逻辑文本范围内替换内容，支持跨多个 run。"""
    if start < 0 or end < start:
        raise ValueError("invalid text range")

    segments = paragraph_text_segments(paragraph)
    if not segments:
        raise ValueError("target paragraph has no text node")

    affected = [seg for seg in segments if seg["end"] > start and seg["start"] < end]
    if not affected and start == end:
        raise ValueError("empty range replacement is not supported here; use insert_text_at")
    if not affected:
        raise ValueError("text range does not touch any text node")

    first = affected[0]
    last = affected[-1]
    first_local_start = max(0, start - first["start"])
    last_local_end = min(len(last["text"]), end - last["start"])

    if first["text_node"] is last["text_node"]:
        before = first["text"][:first_local_start]
        after = first["text"][last_local_end:]
        set_text_preserve_space(first["text_node"], before + replacement + after)
        cleanup_empty_text_runs(paragraph)
        return {
            "mode": "single_run_replace" if replacement else "single_run_delete",
            "before": before,
            "after": after,
            "affected_runs": 1,
            "run": first["run"],
        }

    before = first["text"][:first_local_start]
    after = last["text"][last_local_end:]
    set_text_preserve_space(first["text_node"], before + replacement + after)

    removed_runs = []
    first_run = first["run"]
    for segment in affected[1:]:
        run = segment["run"]
        if run is first_run:
            set_text_preserve_space(segment["text_node"], "")
            continue
        if id(run) in removed_runs:
            continue
        parent = run.getparent()
        if parent is not None and _can_remove_text_run(run):
            parent.remove(run)
            removed_runs.append(id(run))
        else:
            set_text_preserve_space(segment["text_node"], "")

    cleanup_empty_text_runs(paragraph)
    return {
        "mode": "multi_run_replace" if replacement else "multi_run_delete",
        "before": before,
        "after": after,
        "affected_runs": len({id(seg["run"]) for seg in affected}),
        "removed_runs": len(removed_runs),
        "run": first_run,
    }


def cleanup_empty_text_runs(paragraph) -> int:
    """清理没有文本且没有图片、换行、制表符等非文本内容的 run。"""
    removed = 0
    for run in list(paragraph.xpath("./w:r", namespaces=NS)):
        texts = run.xpath(".//w:t", namespaces=NS)
        has_text = any((t.text or "") for t in texts)
        if not has_text and _can_remove_text_run(run):
            parent = run.getparent()
            if parent is not None:
                parent.remove(run)
                removed += 1
    return removed


def _can_remove_text_run(run) -> bool:
    for child in run:
        if child.tag in {f"{W}rPr", f"{W}t"}:
            continue
        return False
    return True


def apply_format_policy_to_paragraph(paragraph, format_policy: str = "preserve", **custom):
    """对段落内所有直接文本 run 应用格式策略。"""
    changed = 0
    for run in paragraph.xpath("./w:r", namespaces=NS):
        if apply_format_policy_to_run(run, format_policy, **custom):
            changed += 1
    return changed


def apply_format_policy_to_run(run, format_policy: str = "preserve", **custom):
    """对单个 run 应用格式策略。"""
    policy = (format_policy or "preserve").lower()
    if policy == "preserve":
        return False
    if policy == "clear":
        clear_direct_run_format(run)
        return True
    if policy == "body":
        apply_body_format(run)
        return True
    if policy == "custom":
        apply_custom_run_format(run, **custom)
        return True
    raise ValueError("format_policy must be preserve, clear, body or custom")


def clear_direct_run_format(run):
    """清除常见直接字符格式，保留字体信息。"""
    rpr = run.find(f"{W}rPr")
    if rpr is None:
        return
    for tag in ("color", "b", "bCs", "i", "iCs", "sz", "szCs", "highlight", "u", "shd"):
        _remove_rpr_child(rpr, tag)
    _remove_empty_rpr(run)


def apply_body_format(run, font_size_half_points: int | None = None):
    """应用普通正文策略：去颜色、去加粗，必要时设置字号。"""
    rpr = _ensure_rpr(run)
    for tag in ("color", "b", "bCs", "highlight", "shd"):
        _remove_rpr_child(rpr, tag)
    if font_size_half_points is not None:
        set_run_font_size(run, font_size_half_points)
    _remove_empty_rpr(run)


def apply_custom_run_format(
    run,
    color: str | None = None,
    bold: bool | None = None,
    font_size_half_points: int | None = None,
    font_size_pt: float | None = None,
):
    """应用显式字符格式。字号优先使用 half-points；也可传 pt。"""
    if color is not None:
        set_run_color(run, color)
    if bold is not None:
        set_run_bold(run, bold)
    if font_size_half_points is None and font_size_pt is not None:
        font_size_half_points = int(round(font_size_pt * 2))
    if font_size_half_points is not None:
        set_run_font_size(run, font_size_half_points)
    _remove_empty_rpr(run)


def set_run_color(run, color: str | None):
    rpr = _ensure_rpr(run)
    _remove_rpr_child(rpr, "color")
    if color:
        elem = etree.Element(f"{W}color")
        elem.set(f"{W}val", color.upper().lstrip("#"))
        rpr.append(elem)


def set_run_bold(run, enabled: bool):
    rpr = _ensure_rpr(run)
    _remove_rpr_child(rpr, "b")
    _remove_rpr_child(rpr, "bCs")
    if enabled:
        rpr.append(etree.Element(f"{W}b"))
        rpr.append(etree.Element(f"{W}bCs"))


def set_run_font_size(run, half_points: int):
    rpr = _ensure_rpr(run)
    _remove_rpr_child(rpr, "sz")
    _remove_rpr_child(rpr, "szCs")
    for tag in ("sz", "szCs"):
        elem = etree.Element(f"{W}{tag}")
        elem.set(f"{W}val", str(int(half_points)))
        rpr.append(elem)


def _ensure_rpr(run):
    rpr = run.find(f"{W}rPr")
    if rpr is None:
        rpr = etree.Element(f"{W}rPr")
        run.insert(0, rpr)
    return rpr


def _remove_rpr_child(rpr, local_name: str):
    for child in list(rpr):
        if child.tag == f"{W}{local_name}":
            rpr.remove(child)


def _remove_empty_rpr(run):
    rpr = run.find(f"{W}rPr")
    if rpr is not None and len(rpr) == 0 and not rpr.attrib:
        run.remove(rpr)
