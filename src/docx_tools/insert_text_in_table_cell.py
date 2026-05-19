import copy

from lxml import etree

from .common import NS, W, json_result, load_document_xml, paragraph_text, set_text_preserve_space, tables, write_document_xml


def insert_text_in_table_cell(
    docx_path: str,
    output_path: str,
    table_index: int,
    row_index: int,
    cell_index: int,
    insert_text: str,
    paragraph_index: int = 1,
    append: bool = True,
) -> str:
    """向表格单元格插入文本。表格、行、单元格索引都从 1 开始计数。"""
    root = load_document_xml(docx_path)
    all_tables = tables(root)
    if table_index < 1 or table_index > len(all_tables):
        return json_result({"status": "error", "message": "table_index out of range", "table_count": len(all_tables)})

    table = all_tables[table_index - 1]
    rows = table.xpath("./w:tr", namespaces=NS)
    if row_index < 1 or row_index > len(rows):
        return json_result({"status": "error", "message": "row_index out of range", "row_count": len(rows)})

    cells = rows[row_index - 1].xpath("./w:tc", namespaces=NS)
    if cell_index < 1 or cell_index > len(cells):
        return json_result({"status": "error", "message": "cell_index out of range", "cell_count": len(cells)})

    cell = cells[cell_index - 1]
    cell_paragraphs = cell.xpath("./w:p", namespaces=NS)
    if not cell_paragraphs:
        paragraph = etree.SubElement(cell, f"{W}p")
        cell_paragraphs = [paragraph]

    if paragraph_index < 1 or paragraph_index > len(cell_paragraphs):
        return json_result(
            {
                "status": "error",
                "message": "paragraph_index out of range",
                "paragraph_count": len(cell_paragraphs),
            }
        )

    paragraph = cell_paragraphs[paragraph_index - 1]
    before_text = paragraph_text(paragraph)
    existing_runs = paragraph.xpath("./w:r", namespaces=NS)

    if append and existing_runs:
        source_run = existing_runs[-1]
        new_run = _make_run_from_source(source_run, insert_text)
        paragraph.append(new_run)
        mode = "append_new_run"
    else:
        new_run = _make_run_from_paragraph(paragraph, insert_text)
        paragraph.append(new_run)
        mode = "create_run_in_cell_paragraph"

    write_document_xml(docx_path, output_path, root)
    return json_result(
        {
            "status": "ok",
            "docx_path": docx_path,
            "output_path": output_path,
            "table_index": table_index,
            "row_index": row_index,
            "cell_index": cell_index,
            "paragraph_index": paragraph_index,
            "mode": mode,
            "before_text": before_text,
            "after_text": paragraph_text(paragraph),
        }
    )


def _make_run_from_source(source_run, text: str):
    new_run = etree.Element(f"{W}r", nsmap=source_run.nsmap)
    rpr = source_run.find(f"{W}rPr")
    if rpr is not None:
        new_run.append(copy.deepcopy(rpr))
    text_node = etree.SubElement(new_run, f"{W}t")
    set_text_preserve_space(text_node, text)
    return new_run


def _make_run_from_paragraph(paragraph, text: str):
    new_run = etree.Element(f"{W}r", nsmap=paragraph.nsmap)
    paragraph_rpr = paragraph.find(f"{W}pPr/{W}rPr")
    if paragraph_rpr is not None:
        new_run.append(copy.deepcopy(paragraph_rpr))
    text_node = etree.SubElement(new_run, f"{W}t")
    set_text_preserve_space(text_node, text)
    return new_run


tools_schema = {
    "type": "function",
    "function": {
        "name": "insert_text_in_table_cell",
        "description": "向指定表格单元格插入文本。适合空白单元格或明确知道第几个表格、第几行、第几列的场景。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "table_index": {"type": "integer", "description": "第几个表格，按 //w:tbl 计数，1-based"},
                "row_index": {"type": "integer", "description": "第几行，1-based"},
                "cell_index": {"type": "integer", "description": "第几个单元格，1-based"},
                "insert_text": {"type": "string", "description": "要插入的文本"},
                "paragraph_index": {"type": "integer", "description": "单元格内第几个直接段落，默认 1"},
                "append": {"type": "boolean", "description": "是否追加到现有段落末尾，默认 true"},
            },
            "required": ["docx_path", "output_path", "table_index", "row_index", "cell_index", "insert_text"],
        },
    },
}
