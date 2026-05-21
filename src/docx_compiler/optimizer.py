from lxml import etree

try:
    from docx_tools.common import NS, W, set_text_preserve_space
except ModuleNotFoundError:
    from src.docx_tools.common import NS, W, set_text_preserve_space


NON_TEXT_RUN_CHILDREN = {f"{W}tab", f"{W}br", f"{W}drawing", f"{W}pict", f"{W}object"}


def optimize_tree(root) -> int:
    """Optimize all paragraphs under root without removing semantic run nodes."""
    changed = 0
    for paragraph in root.xpath(".//w:p", namespaces=NS):
        changed += optimize_paragraph(paragraph)
    return changed


def optimize_paragraph(paragraph) -> int:
    changed = 0
    changed += _remove_empty_plain_runs(paragraph)
    changed += _merge_adjacent_text_runs(paragraph)
    return changed


def _remove_empty_plain_runs(paragraph) -> int:
    removed = 0
    for run in list(paragraph.xpath("./w:r", namespaces=NS)):
        if _has_non_text_content(run):
            continue
        texts = run.xpath("./w:t", namespaces=NS)
        if any((text.text or "") for text in texts):
            continue
        parent = run.getparent()
        if parent is not None:
            parent.remove(run)
            removed += 1
    return removed


def _merge_adjacent_text_runs(paragraph) -> int:
    merged = 0
    previous = None
    for run in list(paragraph.xpath("./w:r", namespaces=NS)):
        if not _is_plain_text_run(run):
            previous = None
            continue
        if previous is not None and _rpr_key(previous) == _rpr_key(run):
            previous_text = previous.find(f"{W}t")
            current_text = run.find(f"{W}t")
            set_text_preserve_space(previous_text, (previous_text.text or "") + (current_text.text or ""))
            run.getparent().remove(run)
            merged += 1
            continue
        previous = run
    return merged


def _has_non_text_content(run) -> bool:
    for child in run:
        if child.tag in {f"{W}rPr", f"{W}t"}:
            continue
        if child.tag in NON_TEXT_RUN_CHILDREN:
            return True
        return True
    return False


def _is_plain_text_run(run) -> bool:
    texts = run.xpath("./w:t", namespaces=NS)
    if len(texts) != 1:
        return False
    for child in run:
        if child.tag not in {f"{W}rPr", f"{W}t"}:
            return False
    return True


def _rpr_key(run) -> bytes:
    rpr = run.find(f"{W}rPr")
    if rpr is None:
        return b""
    return etree.tostring(rpr)
