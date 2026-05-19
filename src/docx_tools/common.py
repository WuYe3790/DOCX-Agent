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
