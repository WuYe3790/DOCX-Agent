import json

from .clear_table_cell import clear_table_cell, tools_schema as clear_table_cell_schema
from .delete_text import delete_text, tools_schema as delete_text_schema
from .delete_table_row import delete_table_row, tools_schema as delete_table_row_schema
from .diff_docx import diff_docx, tools_schema as diff_docx_schema
from .find_text import find_text, tools_schema as find_text_schema
from .insert_paragraph_after import insert_paragraph_after, tools_schema as insert_paragraph_after_schema
from .insert_table_row_after import insert_table_row_after, tools_schema as insert_table_row_after_schema
from .insert_text_at import insert_text_at, tools_schema as insert_text_at_schema
from .insert_text_in_table_cell import insert_text_in_table_cell, tools_schema as insert_text_in_table_cell_schema
from .read_docx_structure import read_docx_structure, tools_schema as read_docx_structure_schema
from .replace_table_cell_text import replace_table_cell_text, tools_schema as replace_table_cell_text_schema
from .replace_text import replace_text, tools_schema as replace_text_schema
from .set_text_format import set_text_format, tools_schema as set_text_format_schema
from .unzip_docx import unzip_docx, tools_schema as unzip_docx_schema


TOOLS = {
    "read_docx_structure": read_docx_structure,
    "find_text": find_text,
    "insert_text_at": insert_text_at,
    "insert_text_in_table_cell": insert_text_in_table_cell,
    "insert_table_row_after": insert_table_row_after,
    "clear_table_cell": clear_table_cell,
    "delete_table_row": delete_table_row,
    "replace_table_cell_text": replace_table_cell_text,
    "replace_text": replace_text,
    "delete_text": delete_text,
    "insert_paragraph_after": insert_paragraph_after,
    "set_text_format": set_text_format,
    "diff_docx": diff_docx,
    "unzip_docx": unzip_docx,
}

TOOLS_SCHEMA = [
    read_docx_structure_schema,
    find_text_schema,
    insert_text_at_schema,
    insert_text_in_table_cell_schema,
    insert_table_row_after_schema,
    clear_table_cell_schema,
    delete_table_row_schema,
    replace_table_cell_text_schema,
    replace_text_schema,
    delete_text_schema,
    insert_paragraph_after_schema,
    set_text_format_schema,
    diff_docx_schema,
    unzip_docx_schema,
]


def render_tools_prompt() -> str:
    """生成精简工具说明，方便注入到不支持原生工具调用的 agent 提示词中。"""
    lines = [
        "你可以使用以下本地 DOCX 工具。每个工具都是一个独立 Python 文件，便于维护。",
        "优先工作流：read_docx_structure/find_text -> 编辑工具 -> diff_docx -> unzip_docx。",
        "表格操作优先用坐标工具：insert_table_row_after、clear_table_cell、delete_table_row、replace_table_cell_text。",
        "注意 read_docx_structure 的 table_index 按 //w:tbl 全文计数，嵌套表格也会计数；操作前要用表格行列文本确认目标。",
        "",
    ]
    for schema in TOOLS_SCHEMA:
        fn = schema["function"]
        params = fn["parameters"]
        required = params.get("required", [])
        properties = params.get("properties", {})
        lines.append(f"- {fn['name']}: {fn['description']}")
        lines.append(f"  required: {', '.join(required) if required else 'none'}")
        optional = [name for name in properties if name not in required]
        lines.append(f"  optional: {', '.join(optional) if optional else 'none'}")
    return "\n".join(lines)


def call_tool(name: str, arguments: str) -> str:
    if name not in TOOLS:
        return json.dumps({"status": "error", "message": f"unknown tool: {name}"}, ensure_ascii=False)
    args = json.loads(arguments) if isinstance(arguments, str) else arguments
    return TOOLS[name](**args)
