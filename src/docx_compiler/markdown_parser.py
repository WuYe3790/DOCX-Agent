import re
from dataclasses import dataclass, field

try:
    from markdown_it import MarkdownIt
except ModuleNotFoundError:
    MarkdownIt = None


@dataclass
class MarkdownBlock:
    block_id: str = ""
    text: str = ""
    line_start: int = 1
    line_end: int = 1
    raw: str = ""
    support: str | None = None

    @property
    def block_type(self) -> str:
        raise NotImplementedError

    def to_dict(self) -> dict:
        data = {
            "block_id": self.block_id,
            "type": self.block_type,
            "text": self.text,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "raw": self.raw,
        }
        if self.support:
            data["support"] = self.support
        return data


@dataclass
class HeadingBlock(MarkdownBlock):
    level: int = 2

    @property
    def block_type(self) -> str:
        return "heading1" if self.level == 1 else "heading2"

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["heading_level"] = self.level
        return data


@dataclass
class ParagraphBlock(MarkdownBlock):
    inline_formulas: list[str] = field(default_factory=list)

    @property
    def block_type(self) -> str:
        return "paragraph"

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["inline_formulas"] = list(self.inline_formulas)
        return data


@dataclass
class ListItemBlock(ParagraphBlock):
    marker: str = "-"
    ordered: bool = False
    indent_level: int = 0

    @property
    def block_type(self) -> str:
        return "list_item"

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "marker": self.marker,
                "ordered": self.ordered,
                "indent_level": self.indent_level,
            }
        )
        return data


@dataclass
class TableCellBlock:
    text: str = ""
    header: bool = False

    def to_dict(self) -> dict:
        return {"text": self.text, "header": self.header}


@dataclass
class TableBlock(MarkdownBlock):
    rows: list[list[TableCellBlock]] = field(default_factory=list)
    header_row_count: int = 0

    @property
    def block_type(self) -> str:
        return "table"

    def to_dict(self) -> dict:
        data = super().to_dict()
        rows = [[cell.to_dict() for cell in row] for row in self.rows]
        data.update(
            {
                "rows": rows,
                "header_row_count": self.header_row_count,
                "column_count": max((len(row) for row in rows), default=0),
            }
        )
        return data


@dataclass
class CodeBlock(MarkdownBlock):
    language: str | None = None

    @property
    def block_type(self) -> str:
        return "code_block"

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["info"] = self.language
        return data


@dataclass
class FormulaBlock(MarkdownBlock):
    source_format: str = "latex"
    display: bool = True

    @property
    def block_type(self) -> str:
        return "formula_block"

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({"source_format": self.source_format, "display": self.display})
        return data


@dataclass
class HtmlBlock(MarkdownBlock):
    @property
    def block_type(self) -> str:
        return "html_block"


def parse_markdown_blocks(markdown_text: str) -> list[MarkdownBlock]:
    if MarkdownIt is None:
        raise RuntimeError("markdown-it-py is required for Markdown AST parsing")
    return _parse_markdown_blocks_with_markdown_it(markdown_text)


def blocks_to_dicts(blocks: list[MarkdownBlock | dict]) -> list[dict]:
    return [block.to_dict() if isinstance(block, MarkdownBlock) else dict(block) for block in blocks]


def _parse_markdown_blocks_with_markdown_it(markdown_text: str) -> list[MarkdownBlock]:
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
            blocks.append(
                _block_from_token(HeadingBlock, _inline_text(inline), token, lines, level=level)
            )
            index = _skip_until(tokens, index, "heading_close") + 1
            continue

        if token.type == "paragraph_open":
            inline = _next_inline(tokens, index)
            formula = _formula_block_from_token(token, inline, lines)
            if formula is not None and not list_stack:
                blocks.append(formula)
                index = _skip_until(tokens, index, "paragraph_close") + 1
                continue
            if list_stack:
                blocks.append(
                    _block_from_token(
                        ListItemBlock,
                        _inline_text(inline),
                        token,
                        lines,
                        marker=list_stack[-1].get("current_marker") or _next_list_marker(list_stack[-1]),
                        ordered=list_stack[-1].get("ordered", False),
                        indent_level=max(0, len(list_stack) - 1),
                        inline_formulas=_inline_formula_sources(_inline_text(inline)),
                    )
                )
            else:
                blocks.append(
                    _block_from_token(
                        ParagraphBlock,
                        _inline_text(inline),
                        token,
                        lines,
                        inline_formulas=_inline_formula_sources(_inline_text(inline)),
                    )
                )
            index = _skip_until(tokens, index, "paragraph_close") + 1
            continue

        if token.type == "table_open":
            end_index = _skip_until(tokens, index, "table_close")
            blocks.append(_table_block_from_tokens(tokens, index, end_index, lines))
            index = end_index + 1
            continue

        if token.type == "fence":
            blocks.append(
                _block_from_token(
                    CodeBlock,
                    token.content,
                    token,
                    lines,
                    support="degraded",
                    language=(token.info or "").strip() or None,
                )
            )
            index += 1
            continue

        if token.type == "code_block":
            blocks.append(_block_from_token(CodeBlock, token.content, token, lines, support="degraded"))
            index += 1
            continue

        if token.type == "html_block":
            blocks.append(_block_from_token(HtmlBlock, token.content, token, lines, support="rejected"))
            index += 1
            continue

        index += 1

    for block_index, block in enumerate(blocks, start=1):
        block.block_id = f"B{block_index:03d}"
    return blocks


def _block_from_token(block_cls, text: str, token, lines: list[str], **extra) -> MarkdownBlock:
    line_start, line_end = _line_range(token)
    raw = _raw_text(token, lines)
    return block_cls(text=text, line_start=line_start, line_end=line_end, raw=raw, **extra)


def _table_block_from_tokens(tokens, start_index: int, end_index: int, lines: list[str]) -> TableBlock:
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
            current_cell = TableCellBlock(header=item.type == "th_open")
            continue
        if item.type in {"th_close", "td_close"}:
            if current_row is not None and current_cell is not None:
                current_row.append(current_cell)
            current_cell = None
            continue
        if item.type == "inline" and current_cell is not None:
            current_cell.text = _inline_text(item)

    line_start, line_end = _line_range(token)
    raw = _raw_text(token, lines)
    return TableBlock(
        text=raw,
        line_start=line_start,
        line_end=line_end,
        raw=raw,
        rows=rows,
        header_row_count=1 if header_row_count else 0,
    )


def _formula_block_from_token(token, inline, lines: list[str]) -> FormulaBlock | None:
    raw = _raw_text(token, lines).strip()
    if not raw.startswith("$$") or not raw.endswith("$$") or len(raw) < 4:
        return None
    source = raw[2:-2].strip()
    if not source:
        source = _inline_text(inline).strip("$").strip()
    line_start, line_end = _line_range(token)
    return FormulaBlock(
        text=source,
        line_start=line_start,
        line_end=line_end,
        raw=_raw_text(token, lines),
        support="degraded",
        source_format="latex",
        display=True,
    )


def _inline_formula_sources(text: str) -> list[str]:
    if not text:
        return []
    return [match.group(1).strip() for match in re.finditer(r"(?<!\\)\$([^$\n]+?)(?<!\\)\$", text) if match.group(1).strip()]


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
