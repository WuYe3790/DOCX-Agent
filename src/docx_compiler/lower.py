from __future__ import annotations

from dataclasses import dataclass, field

from .diagnostics import Diagnostic, SupportStatus, support_summary
from .ir import CellIR, CodeBlockIR, FormulaIR, ParagraphIR, RunIR, TableIR, TableRowIR
from .markdown_parser import MarkdownBlock, blocks_to_dicts


NATIVE_BLOCK_TYPES = {"heading1", "heading2", "paragraph", "table"}
DEGRADED_BLOCK_TYPES = {"list_item", "code_block", "formula_block"}
REJECTED_BLOCK_TYPES = {"html_block"}


@dataclass
class LoweringResult:
    source_blocks: list[dict] = field(default_factory=list)
    layout_blocks: list[ParagraphIR | TableIR | CodeBlockIR | FormulaIR] = field(default_factory=list)
    render_items: list[dict] = field(default_factory=list)
    style_sample_ids: set[str] = field(default_factory=set)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def support_summary(self) -> dict:
        return support_summary(self.source_blocks or self.render_items)


def normalize_block_support(blocks: list[MarkdownBlock | dict]) -> list[dict]:
    normalized = []
    for block in blocks_to_dicts(blocks):
        item = dict(block)
        support = block_support(item)
        item["support"] = support
        item["supported"] = support != "rejected"
        normalized.append(item)
    return normalized


def block_support(block: dict) -> SupportStatus:
    explicit = block.get("support")
    if explicit in {"native", "degraded", "rejected"}:
        return explicit
    block_type = block.get("type")
    if block_type in NATIVE_BLOCK_TYPES:
        return "native"
    if block_type in DEGRADED_BLOCK_TYPES:
        return "degraded"
    if block_type in REJECTED_BLOCK_TYPES:
        return "rejected"
    return "native" if block.get("supported", True) else "rejected"


def diagnostics_for_blocks(blocks: list[dict]) -> list[Diagnostic]:
    diagnostics = []
    for block in normalize_block_support(blocks):
        support = block["support"]
        if block.get("inline_formulas"):
            diagnostics.append(_diagnostic(block, "warning", "INLINE_FORMULA_RENDERED_AS_TEXT", "行内公式已识别，但当前保留为文本写入，暂未转换为 Word 原生 OMML。", "degraded"))
        if support == "native":
            continue
        if block["type"] == "list_item":
            diagnostics.append(_diagnostic(block, "warning", "LIST_ITEM_DEGRADED", "列表项按文本 marker 和段落缩进写入，暂未生成 Word 原生 numbering.xml。", support))
        elif block["type"] == "code_block":
            diagnostics.append(_diagnostic(block, "warning", "CODE_BLOCK_DEGRADED", "代码块将按等宽段落写入，暂未做语法高亮。", support))
        elif block["type"] == "formula_block":
            diagnostics.append(_diagnostic(block, "warning", "FORMULA_RENDERED_AS_TEXT", "公式已识别，但当前按文本写入，暂未转换为 Word 原生 OMML。", support))
        elif block["type"] == "html_block":
            diagnostics.append(_diagnostic(block, "error", "HTML_BLOCK_REJECTED", "HTML 块暂不支持写入 Word。", support))
        else:
            diagnostics.append(_diagnostic(block, "error", "MARKDOWN_BLOCK_REJECTED", f"暂不支持的 Markdown 块类型: {block['type']}。", "rejected"))
    return diagnostics


def filter_blocks(
    blocks: list[dict],
    include_block_ids: list[str] | None,
    line_start: int | None,
    line_end: int | None,
) -> list[dict]:
    if include_block_ids and (line_start is not None or line_end is not None):
        raise ValueError("include_block_ids 和 line_start/line_end 不能同时使用")
    if line_start is not None and line_end is not None and line_end < line_start:
        raise ValueError("line_end must be >= line_start")

    if include_block_ids:
        wanted = {str(block_id) for block_id in include_block_ids}
        selected = [block for block in blocks if block["block_id"] in wanted]
        missing = sorted(wanted - {block["block_id"] for block in selected})
        if missing:
            raise ValueError(f"include_block_ids not found: {', '.join(missing)}")
        return selected

    if line_start is not None or line_end is not None:
        start = line_start if line_start is not None else 1
        end = line_end if line_end is not None else 10**9
        overlapping = [
            block
            for block in blocks
            if block["line_start"] <= end
            and block["line_end"] >= start
            and not (block["line_start"] >= start and block["line_end"] <= end)
        ]
        if overlapping:
            ids = ", ".join(block["block_id"] for block in overlapping)
            raise ValueError(f"line range cuts through block(s): {ids}")
        return [block for block in blocks if block["line_start"] >= start and block["line_end"] <= end]

    return blocks


def lower_markdown_blocks(blocks: list[dict], style_mapping: dict) -> LoweringResult:
    result = LoweringResult()
    normalized = normalize_block_support(blocks)
    result.source_blocks = normalized
    result.diagnostics.extend(diagnostics_for_blocks(normalized))

    previous = None
    for block in normalized:
        if block["support"] == "rejected":
            continue
        sample_id = _sample_id_for_block(block, style_mapping)
        if not sample_id:
            result.diagnostics.append(
                _diagnostic(
                    block,
                    "error",
                    "MISSING_STYLE_MAPPING",
                    f"style_mapping 缺少 {block['type']}，也没有可用 fallback。",
                    block["support"],
                )
            )
            continue
        result.style_sample_ids.add(sample_id)
        render_item = _render_item(block, sample_id)
        result.render_items.append(render_item)
        if previous is not None and render_item["line_start"] > previous["line_end"] + 1:
            result.layout_blocks.append(ParagraphIR(runs=[]))
        result.layout_blocks.append(_item_to_layout_ir(render_item))
        previous = render_item

    return result


def _render_item(block: dict, sample_id: str) -> dict:
    return {
        "block_id": block["block_id"],
        "type": block["type"],
        "text": _render_text(block),
        "sample_id": sample_id,
        "line_start": block["line_start"],
        "line_end": block["line_end"],
        "indent_level": block.get("indent_level", 0),
        "marker": block.get("marker"),
        "rows": block.get("rows"),
        "column_count": block.get("column_count"),
        "support": block["support"],
        "language": block.get("info") or block.get("language"),
        "source_format": block.get("source_format"),
        "display": block.get("display"),
    }


def _sample_id_for_block(block: dict, style_mapping: dict) -> str | None:
    block_type = block["type"]
    if block_type == "table":
        return style_mapping.get("table_cell") or style_mapping.get("paragraph") or style_mapping.get("table")
    if block_type == "code_block":
        return style_mapping.get("code_block") or style_mapping.get("paragraph")
    if block_type == "formula_block":
        return style_mapping.get("formula") or style_mapping.get("paragraph")
    return style_mapping.get(block_type)


def _item_to_layout_ir(item: dict) -> ParagraphIR | TableIR | CodeBlockIR | FormulaIR:
    if item["type"] == "table":
        return _item_to_table_ir(item)
    if item["type"] == "code_block":
        return CodeBlockIR(
            code=item["text"],
            language=item.get("language"),
            style_sample_id=item["sample_id"],
            block_id=item["block_id"],
            line_start=item["line_start"],
            line_end=item["line_end"],
        )
    if item["type"] == "formula_block":
        return FormulaIR(
            source=item["text"],
            source_format=item.get("source_format") or "latex",
            display=bool(item.get("display", True)),
            style_sample_id=item["sample_id"],
            block_id=item["block_id"],
            line_start=item["line_start"],
            line_end=item["line_end"],
        )
    return ParagraphIR(
        runs=_parse_inline_runs(item["text"]),
        style_sample_id=item["sample_id"],
        block_id=item["block_id"],
        block_type=item["type"],
        line_start=item["line_start"],
        line_end=item["line_end"],
        list_level=int(item.get("indent_level", 0)) if item["type"] == "list_item" else None,
        list_marker=item.get("marker"),
    )


def _item_to_table_ir(item: dict) -> TableIR:
    rows = []
    for row in item.get("rows") or []:
        cells = []
        for cell in row:
            text = cell.get("text", "") if isinstance(cell, dict) else str(cell)
            cells.append(
                CellIR(
                    blocks=[
                        ParagraphIR(
                            runs=_parse_inline_runs(text),
                            style_sample_id=item.get("sample_id"),
                            block_id=item["block_id"],
                            block_type="table_cell",
                            line_start=item["line_start"],
                            line_end=item["line_end"],
                        )
                    ]
                )
            )
        rows.append(TableRowIR(cells=cells))
    return TableIR(rows=rows)


def _render_text(block: dict) -> str:
    if block["type"] == "list_item":
        marker = block.get("marker") or "-"
        return f"{marker} {block['text']}"
    return block["text"]


def _parse_inline_runs(text: str) -> list[RunIR]:
    """解析最小 Markdown 加粗语法；未闭合的 ** 按普通文本处理。"""
    runs = []
    cursor = 0
    while cursor < len(text):
        start = text.find("**", cursor)
        if start == -1:
            _append_text_runs(runs, text[cursor:], bold=False)
            break
        if start > cursor:
            _append_text_runs(runs, text[cursor:start], bold=False)
        end = text.find("**", start + 2)
        if end == -1:
            _append_text_runs(runs, text[start:], bold=False)
            break
        _append_text_runs(runs, text[start + 2 : end], bold=True)
        cursor = end + 2
    return runs


def _append_text_runs(runs: list[RunIR], text: str, bold: bool) -> None:
    token = []
    for char in text:
        if char == "\t":
            if token:
                runs.append(RunIR.text_run("".join(token), bold=bold))
                token = []
            runs.append(RunIR.tab())
        elif char == "\n":
            if token:
                runs.append(RunIR.text_run("".join(token), bold=bold))
                token = []
            runs.append(RunIR.line_break())
        else:
            token.append(char)
    if token:
        runs.append(RunIR.text_run("".join(token), bold=bold))


def _diagnostic(block: dict, level: str, code: str, message: str, support: SupportStatus) -> Diagnostic:
    return Diagnostic(
        level=level,
        code=code,
        message=message,
        block_id=block.get("block_id"),
        line_start=block.get("line_start"),
        line_end=block.get("line_end"),
        support=support,
    )
