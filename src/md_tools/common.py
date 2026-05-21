import json
import re
from pathlib import Path

try:
    from markdown_it import MarkdownIt
except ModuleNotFoundError:
    MarkdownIt = None


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
    if MarkdownIt is not None:
        return _parse_markdown_blocks_with_markdown_it(markdown_text)
    return _parse_markdown_blocks_legacy(markdown_text)


def _parse_markdown_blocks_with_markdown_it(markdown_text: str) -> list[dict]:
    normalized = markdown_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    parser = MarkdownIt("commonmark").enable("table")
    tokens = parser.parse(normalized)
    blocks = []
    list_stack = []
    index = 0

    while index < len(tokens):
        token = tokens[index]

        if token.type in {"bullet_list_open", "ordered_list_open"}:
            list_stack.append(_list_context(token))
            index += 1
            continue

        if token.type in {"bullet_list_close", "ordered_list_close"}:
            if list_stack:
                list_stack.pop()
            index += 1
            continue

        if token.type == "list_item_open":
            if list_stack:
                list_stack[-1]["current_marker"] = _next_list_marker(list_stack[-1])
            index += 1
            continue

        if token.type == "heading_open":
            inline = _next_inline(tokens, index)
            level = int(token.tag[1:]) if token.tag.startswith("h") and token.tag[1:].isdigit() else 2
            block_type = "heading1" if level == 1 else "heading2"
            blocks.append(
                _block_from_token(
                    block_type,
                    _inline_text(inline),
                    token,
                    lines,
                    heading_level=level,
                )
            )
            index = _skip_until(tokens, index, "heading_close") + 1
            continue

        if token.type == "paragraph_open":
            inline = _next_inline(tokens, index)
            if list_stack:
                blocks.append(
                    _block_from_token(
                        "list_item",
                        _inline_text(inline),
                        token,
                        lines,
                        marker=list_stack[-1].get("current_marker") or _next_list_marker(list_stack[-1]),
                        ordered=list_stack[-1].get("ordered", False),
                        indent_level=max(0, len(list_stack) - 1),
                    )
                )
            else:
                blocks.append(_block_from_token("paragraph", _inline_text(inline), token, lines))
            index = _skip_until(tokens, index, "paragraph_close") + 1
            continue

        if token.type == "table_open":
            end_index = _skip_until(tokens, index, "table_close")
            blocks.append(_table_block_from_tokens(tokens, index, end_index, lines))
            index = end_index + 1
            continue

        if token.type == "fence":
            blocks.append(_block_from_token("code_block", token.content, token, lines, supported=False, info=token.info))
            index += 1
            continue

        if token.type == "code_block":
            blocks.append(_block_from_token("code_block", token.content, token, lines, supported=False))
            index += 1
            continue

        if token.type == "html_block":
            blocks.append(_block_from_token("html_block", token.content, token, lines, supported=False))
            index += 1
            continue

        index += 1

    for block_index, block in enumerate(blocks, start=1):
        block["block_id"] = f"B{block_index:03d}"
    return blocks


def _parse_markdown_blocks_legacy(markdown_text: str) -> list[dict]:
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
        raw = "\n".join(table_lines)
        blocks.append(
            _block(
                "table",
                raw,
                table_start,
                end_line,
                raw,
                supported=True,
                rows=_parse_pipe_table_rows(table_lines),
            )
        )
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


def _block_from_token(block_type: str, text: str, token, lines: list[str], supported: bool = True, **extra) -> dict:
    line_start, line_end = _line_range(token)
    raw = _raw_text(token, lines)
    return _block(block_type, text, line_start, line_end, raw, supported=supported, **extra)


def _table_block_from_tokens(tokens, start_index: int, end_index: int, lines: list[str]) -> dict:
    token = tokens[start_index]
    rows = []
    current_row = None
    current_cell = None
    header_row_count = 0

    for item in tokens[start_index + 1 : end_index]:
        if item.type == "thead_open":
            header_row_count = len(rows) + 1
            continue
        if item.type == "tr_open":
            current_row = []
            continue
        if item.type == "tr_close":
            if current_row is not None:
                rows.append(current_row)
            current_row = None
            continue
        if item.type in {"th_open", "td_open"}:
            current_cell = {"text": "", "header": item.type == "th_open"}
            continue
        if item.type in {"th_close", "td_close"}:
            if current_row is not None and current_cell is not None:
                current_row.append(current_cell)
            current_cell = None
            continue
        if item.type == "inline" and current_cell is not None:
            current_cell["text"] = _inline_text(item)

    line_start, line_end = _line_range(token)
    raw = _raw_text(token, lines)
    return _block(
        "table",
        raw,
        line_start,
        line_end,
        raw,
        supported=True,
        rows=rows,
        header_row_count=1 if header_row_count else 0,
        column_count=max((len(row) for row in rows), default=0),
    )


def _line_range(token) -> tuple[int, int]:
    if not token.map:
        return 1, 1
    return int(token.map[0]) + 1, int(token.map[1])


def _raw_text(token, lines: list[str]) -> str:
    if not token.map:
        return token.content or ""
    start, end = token.map
    return "\n".join(lines[start:end])


def _next_inline(tokens, start_index: int):
    index = start_index + 1
    while index < len(tokens):
        token = tokens[index]
        if token.type == "inline":
            return token
        if token.nesting < 0:
            return None
        index += 1
    return None


def _inline_text(token) -> str:
    if token is None:
        return ""
    return (token.content or "").replace("\n", " ").strip()


def _skip_until(tokens, start_index: int, token_type: str) -> int:
    index = start_index + 1
    while index < len(tokens):
        if tokens[index].type == token_type:
            return index
        index += 1
    return start_index


def _list_context(token) -> dict:
    if token.type == "ordered_list_open":
        start = token.attrGet("start") or "1"
        delimiter = token.markup or "."
        return {
            "ordered": True,
            "delimiter": delimiter,
            "next_number": int(start),
            "current_marker": None,
        }
    return {
        "ordered": False,
        "marker": token.markup or "-",
        "current_marker": None,
    }


def _next_list_marker(context: dict) -> str:
    if context.get("ordered"):
        number = int(context.get("next_number", 1))
        context["next_number"] = number + 1
        return f"{number}{context.get('delimiter') or '.'}"
    return context.get("marker") or "-"


def _parse_pipe_table_rows(table_lines: list[str]) -> list[list[dict]]:
    rows = []
    for index, line in enumerate(table_lines):
        cells = _split_pipe_row(line)
        if index == 1 and all(re.match(r"^:?-{3,}:?$", cell.strip()) for cell in cells):
            continue
        rows.append([{"text": cell.strip(), "header": index == 0} for cell in cells])
    return rows


def _split_pipe_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


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
