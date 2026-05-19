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

