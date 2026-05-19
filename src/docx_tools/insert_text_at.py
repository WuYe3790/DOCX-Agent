from lxml import etree

from .common import (
    json_result,
    load_document_xml,
    make_run_like,
    paragraph_location,
    paragraph_text,
    paragraph_text_segments,
    paragraphs,
    set_text_preserve_space,
    write_document_xml,
)


def insert_text_at(
    docx_path: str,
    output_path: str,
    anchor_text: str,
    insert_text: str,
    offset: int = -1,
    occurrence: int = 1,
) -> str:
    """
    在 word/document.xml 中根据锚点附近的位置插入文字。

    offset 是相对 anchor_text 的字符偏移。
    使用 -1 表示插入到 anchor_text 后面。
    occurrence 是全文第几个匹配项，从 1 开始计数。
    """
    root = load_document_xml(docx_path)
    current_occurrence = 0

    for paragraph_index, paragraph in enumerate(paragraphs(root), start=1):
        logical_text = paragraph_text(paragraph)
        search_from = 0
        while True:
            anchor_start = logical_text.find(anchor_text, search_from)
            if anchor_start == -1:
                break
            current_occurrence += 1
            if current_occurrence != occurrence:
                search_from = anchor_start + max(1, len(anchor_text))
                continue

            if offset < 0:
                insert_at = anchor_start + len(anchor_text)
            else:
                if offset > len(anchor_text):
                    raise ValueError("offset cannot be greater than anchor_text length")
                insert_at = anchor_start + offset

            change = _insert_into_paragraph(paragraph, insert_at, insert_text)
            write_document_xml(docx_path, output_path, root)
            return json_result(
                {
                    "status": "ok",
                    "docx_path": docx_path,
                    "output_path": output_path,
                    "paragraph_index": paragraph_index,
                    "location": paragraph_location(paragraph),
                    "anchor_text": anchor_text,
                    "insert_text": insert_text,
                    "insert_at": insert_at,
                    "change": change,
                    "new_paragraph_text": paragraph_text(paragraph),
                }
            )

    return json_result(
        {
            "status": "not_found",
            "docx_path": docx_path,
            "anchor_text": anchor_text,
            "occurrence": occurrence,
        }
    )


def _insert_into_paragraph(paragraph, insert_at: int, insert_text: str):
    segments = paragraph_text_segments(paragraph)
    if not segments:
        raise ValueError("target paragraph has no text node; use insert_text_in_table_cell or paragraph creation")

    for segment in segments:
        if segment["start"] <= insert_at <= segment["end"]:
            local_offset = insert_at - segment["start"]
            original_text = segment["text"]
            text_node = segment["text_node"]
            source_run = segment["run"]
            parent = source_run.getparent()
            source_index = parent.index(source_run)

            if local_offset == len(original_text):
                new_run = make_run_like(source_run, insert_text)
                parent.insert(source_index + 1, new_run)
                return {"mode": "append_after_run", "source_text": original_text}

            if local_offset == 0:
                new_run = make_run_like(source_run, insert_text)
                parent.insert(source_index, new_run)
                return {"mode": "insert_before_run", "source_text": original_text}

            before = original_text[:local_offset]
            after = original_text[local_offset:]
            set_text_preserve_space(text_node, before)

            inserted_run = make_run_like(source_run, insert_text)
            after_run = etree.fromstring(etree.tostring(source_run))
            after_text_nodes = after_run.xpath(".//*[local-name()='t']")
            if not after_text_nodes:
                raise ValueError("source run clone has no text node")
            set_text_preserve_space(after_text_nodes[0], after)
            for extra_text_node in after_text_nodes[1:]:
                extra_text_node.getparent().remove(extra_text_node)

            parent.insert(source_index + 1, inserted_run)
            parent.insert(source_index + 2, after_run)
            return {"mode": "split_run", "before": before, "after": after}

    last_segment = segments[-1]
    new_run = make_run_like(last_segment["run"], insert_text)
    last_segment["run"].addnext(new_run)
    return {"mode": "append_at_paragraph_end"}


tools_schema = {
    "type": "function",
    "function": {
        "name": "insert_text_at",
        "description": "按锚点文本和字符偏移向 docx 插入文字，自动复制附近 run 格式。适合文本中间或末尾插入。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "anchor_text": {"type": "string", "description": "用于定位的原文"},
                "insert_text": {"type": "string", "description": "要插入的文本"},
                "offset": {
                    "type": "integer",
                    "description": "相对 anchor_text 的插入偏移；-1 表示插在 anchor_text 后面",
                },
                "occurrence": {"type": "integer", "description": "第几个匹配项，1-based，默认 1"},
            },
            "required": ["docx_path", "output_path", "anchor_text", "insert_text"],
        },
    },
}
