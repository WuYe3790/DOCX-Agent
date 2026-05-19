import json

from .diff_docx import diff_docx, tools_schema as diff_docx_schema
from .find_text import find_text, tools_schema as find_text_schema
from .insert_text_at import insert_text_at, tools_schema as insert_text_at_schema
from .insert_text_in_table_cell import insert_text_in_table_cell, tools_schema as insert_text_in_table_cell_schema
from .read_docx_structure import read_docx_structure, tools_schema as read_docx_structure_schema
from .unzip_docx import unzip_docx, tools_schema as unzip_docx_schema


TOOLS = {
    "read_docx_structure": read_docx_structure,
    "find_text": find_text,
    "insert_text_at": insert_text_at,
    "insert_text_in_table_cell": insert_text_in_table_cell,
    "diff_docx": diff_docx,
    "unzip_docx": unzip_docx,
}

TOOLS_SCHEMA = [
    read_docx_structure_schema,
    find_text_schema,
    insert_text_at_schema,
    insert_text_in_table_cell_schema,
    diff_docx_schema,
    unzip_docx_schema,
]


def render_tools_prompt() -> str:
    """生成精简工具说明，方便注入到不支持原生工具调用的 agent 提示词中。"""
    lines = [
        "你可以使用以下本地 DOCX 工具。每个工具都是一个独立 Python 文件，便于维护。",
        "优先工作流：read_docx_structure/find_text -> insert 工具 -> diff_docx -> unzip_docx。",
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
