import json
import re
from pathlib import Path


DRAFT_ROOT = Path("out") / "drafts"


def json_result(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def draft_path(path: str) -> Path:
    raw = Path(path)
    if not raw.suffix:
        raw = raw.with_suffix(".md")
    if not raw.parent or str(raw.parent) == ".":
        raw = DRAFT_ROOT / raw

    resolved_root = DRAFT_ROOT.resolve()
    resolved_path = raw.resolve()
    if resolved_root != resolved_path and resolved_root not in resolved_path.parents:
        raise ValueError("Markdown 草稿只能写入或读取 out/drafts 目录")
    if resolved_path.suffix.lower() != ".md":
        raise ValueError("Markdown 草稿路径必须以 .md 结尾")
    return raw


def read_markdown_text(path: str) -> tuple[Path, str]:
    target = draft_path(path)
    if not target.exists():
        raise FileNotFoundError(f"Markdown 草稿不存在: {target}")
    return target, target.read_text(encoding="utf-8")


def parse_markdown_blocks(markdown_text: str) -> list[dict]:
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks = []
    paragraph_lines = []
    paragraph_start = None
    table_lines = []
    table_start = None
    in_code_block = False
    code_lines = []
    code_start = None

    def flush_paragraph(end_line: int):
        nonlocal paragraph_lines, paragraph_start
        if not paragraph_lines:
            return
        text = " ".join(line.strip() for line in paragraph_lines if line.strip())
        if text:
            blocks.append(_block("paragraph", text, paragraph_start, end_line, "\n".join(paragraph_lines)))
        paragraph_lines = []
        paragraph_start = None

    def flush_table(end_line: int):
        nonlocal table_lines, table_start
        if not table_lines:
            return
        blocks.append(_block("table", "\n".join(table_lines), table_start, end_line, "\n".join(table_lines), supported=False))
        table_lines = []
        table_start = None

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph(line_number - 1)
            flush_table(line_number - 1)
            if in_code_block:
                code_lines.append(line)
                blocks.append(_block("code_block", "\n".join(code_lines), code_start, line_number, "\n".join(code_lines), supported=False))
                code_lines = []
                code_start = None
                in_code_block = False
            else:
                in_code_block = True
                code_start = line_number
                code_lines = [line]
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if _is_table_line(stripped):
            flush_paragraph(line_number - 1)
            if not table_lines:
                table_start = line_number
            table_lines.append(line)
            continue

        flush_table(line_number - 1)

        if not stripped:
            flush_paragraph(line_number - 1)
            continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            flush_paragraph(line_number - 1)
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            flush_paragraph(line_number - 1)
            level = len(heading_match.group(1))
            block_type = "heading1" if level == 1 else "heading2"
            blocks.append(
                _block(
                    block_type,
                    heading_match.group(2).strip(),
                    line_number,
                    line_number,
                    line,
                    heading_level=level,
                )
            )
            continue

        list_match = re.match(r"^([-*+]|\d+[.)])\s+(.+)$", stripped)
        if list_match:
            flush_paragraph(line_number - 1)
            indent_spaces = len(line) - len(line.lstrip(" "))
            blocks.append(
                _block(
                    "list_item",
                    list_match.group(2).strip(),
                    line_number,
                    line_number,
                    line,
                    marker=list_match.group(1),
                    indent_level=indent_spaces // 2,
                )
            )
            continue

        if paragraph_start is None:
            paragraph_start = line_number
        paragraph_lines.append(line)

    if in_code_block:
        blocks.append(_block("code_block", "\n".join(code_lines), code_start, len(lines), "\n".join(code_lines), supported=False))
    flush_table(len(lines))
    flush_paragraph(len(lines))

    for index, block in enumerate(blocks, start=1):
        block["block_id"] = f"B{index:03d}"
    return blocks


def _block(block_type: str, text: str, line_start: int, line_end: int, raw: str, supported: bool = True, **extra) -> dict:
    data = {
        "type": block_type,
        "text": text,
        "line_start": line_start,
        "line_end": line_end,
        "raw": raw,
        "supported": supported,
    }
    data.update(extra)
    return data


def _is_table_line(stripped: str) -> bool:
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2
